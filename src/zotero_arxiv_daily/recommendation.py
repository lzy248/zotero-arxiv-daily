"""Small, stateless daily selection policy; no model or recommendation history."""
from collections import Counter
from datetime import datetime, timezone
import html
import math
import re
import unicodedata
from urllib.parse import unquote

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from sklearn.feature_extraction.text import TfidfVectorizer

STOP_WORDS = ENGLISH_STOP_WORDS | {
    "paper", "study", "results", "propose", "proposed", "approach", "method",
    "using", "based", "show", "new", "research", "et", "al", "https", "www",
}


def tokenize(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return [w for w in re.findall(r"[^\W_]{2,}", text.casefold())
            if w not in STOP_WORDS and not w.isdigit()]


def utc_naive(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def normalize_doi(value):
    match = re.search(r"10\.\d{4,9}/[^\s<>\"]+", unquote(value or ""), re.I)
    return match.group(0).casefold().rstrip(".,;") if match else None


def normalize_arxiv(value):
    match = re.search(r"(?<!\d)(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", value or "", re.I)
    return match.group(1).casefold() if match else None


def zotero_arxiv_id(data):
    for field in ('archiveID', 'archiveLocation'):
        if identifier := normalize_arxiv(data.get(field)):
            return identifier
    # Do not mistake an arbitrary DOI suffix or publisher URL for an arXiv ID.
    for field in ('url', 'extra', 'DOI'):
        value = data.get(field) or ''
        if 'arxiv' in value.casefold():
            if identifier := normalize_arxiv(value):
                return identifier
    return None


def identities(paper):
    keys = set()
    doi = normalize_doi(paper.doi) or normalize_doi(paper.url)
    arxiv = normalize_arxiv(paper.arxiv_id)
    if not arxiv and ("arxiv" in (paper.url or "").lower() or "arxiv" in (doi or "")):
        arxiv = normalize_arxiv(paper.url) or normalize_arxiv(doi)
    if doi:
        keys.add(("doi", doi))
    if arxiv:
        keys.add(("arxiv", arxiv))
    s2 = paper.semantic_scholar_id or normalize_s2(paper.url)
    if s2:
        keys.add(("s2", s2.casefold()))
    title = unicodedata.normalize("NFKC", html.unescape(paper.title or "")).casefold()
    title = "".join(c for c in title if c.isalnum())
    if title:
        keys.add(("title", title))
    return keys


def normalize_s2(value):
    match = re.search(r'(?:semanticscholar\.org/paper/(?:[^/\s]+/)?|Semantic Scholar(?: ID)?:\s*)([a-f0-9]{40})(?:\b|$)', value or '', re.I)
    return match.group(1).lower() if match else None


def deduplicate(candidates, library):
    """Union identities first: transitive aliases must also match the Library."""
    parent = {}

    def root(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    groups = [identities(p) for p in [*library, *candidates]]
    for keys in groups:
        if keys:
            first = next(iter(keys))
            for key in keys:
                parent[root(key)] = root(first)
    seen = {root(key) for keys in groups[:len(library)] for key in keys}
    result = []
    for paper, keys in zip(candidates, groups[len(library):]):
        aliases = {root(key) for key in keys}
        if aliases and not aliases & seen:
            result.append(paper)
            seen.update(aliases)
    return result


class InterestProfile:
    """Recency weighted TF-IDF query, scored with length-normalized BM25.

    Candidate-independent IDF comes from the recent library. Normalizing by
    the theoretical BM25 maximum gives a bounded score, not a probability.
    """
    def __init__(self, corpus, config, now=None):
        if config.half_life_days <= 0 or config.recent_limit < 1 or config.query_terms < 1:
            raise ValueError('Interest window, half life and query size must be positive')
        if not 0 < config.min_relevance <= 1 or not 0 <= config.explore_max_relevance <= 1:
            raise ValueError('Relevance thresholds must lie between zero and one')
        if config.min_matched_terms < 1 or config.interest_slots < 0:
            raise ValueError('Require positive matched terms and nonnegative interest slots')
        self.config = config
        self.now = utc_naive(now or datetime.now(timezone.utc))
        self.corpus = sorted(corpus, key=lambda p: utc_naive(p.added_date), reverse=True)[:config.recent_limit]
        documents = [tokenize(" ".join([p.title, p.title, p.abstract,
                       " ".join(p.tags), " ".join(p.tags), " ".join(p.paths)])) for p in self.corpus]
        df = Counter(term for doc in documents for term in set(doc))
        n = len(documents)
        self.idf = {t: math.log(1 + (n - count + .5) / (count + .5)) for t, count in df.items()}
        weights = Counter()
        for paper, doc in zip(self.corpus, documents):
            age = max(0, (self.now - utc_naive(paper.added_date)).days)
            decay = 2 ** (-min(age / config.half_life_days, 100))
            tf = Counter(doc)
            norm = sum(1 + math.log(c) for c in tf.values()) or 1
            for term, count in tf.items():
                weights[term] += decay * (1 + math.log(count)) / norm * self.idf[term]
        self.weights = dict(weights.most_common(config.query_terms))
        self.avgdl = sum(map(len, documents)) / max(1, n) or 1

    def score(self, paper):
        tokens = tokenize(f"{paper.title} {paper.title} {paper.abstract}")
        tf = Counter(tokens)
        hits = set(tf) & self.weights.keys()
        if len(hits) < self.config.min_matched_terms:
            return 0.0
        denominator = sum(w * self.idf[t] * 2.5 for t, w in self.weights.items())
        score = sum(self.weights[t] * self.idf[t] * tf[t] * 2.5 /
                    (tf[t] + 1.5 * (.25 + .75 * len(tokens) / self.avgdl)) for t in hits)
        return score / denominator if denominator else 0.0

    def seeds(self, limit):
        # Recency-first, skipping near-identical topic bags to cover active interests.
        selected, token_sets = [], []
        if limit <= 0:
            return selected
        for paper in self.corpus:
            if not (paper.doi or paper.arxiv_id or paper.semantic_scholar_id):
                continue
            terms = set(tokenize(paper.title))
            if any(len(terms & old) / max(1, len(terms | old)) > .7 for old in token_sets):
                continue
            selected.append(paper)
            token_sets.append(terms)
            if len(selected) >= limit:
                break
        return selected


def focused_explore_candidates(candidates, config):
    """TF-IDF unigram/bigram domain gate, independent of the user's narrow interests."""
    include = list(config.get('explore_include_topics', []))
    exclude = list(config.get('explore_exclude_topics', []))
    if not candidates or not (include or exclude):
        return {id(p) for p in candidates}
    prototypes = include + exclude
    if any(not isinstance(t, str) or not tokenize(t) for t in prototypes):
        raise ValueError('Explore topic descriptions must contain meaningful text')
    texts = [f'{p.title} {p.title} {p.abstract}' for p in candidates]
    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, ngram_range=(1, 2))
    vectors = vectorizer.fit_transform([*prototypes, *texts])
    scores = (vectors[len(prototypes):] @ vectors[:len(prototypes)].T).toarray()
    selected = set()
    for paper, row in zip(candidates, scores):
        positive = max(row[:len(include)], default=0)
        negative = max(row[len(include):], default=0)
        if include and positive < config.get('explore_focus_min_score', .05):
            continue
        if exclude and negative >= config.get('explore_exclude_min_score', .05):
            if not include or negative >= positive:
                continue
        selected.add(id(paper))
    return selected


def select_daily(candidates, library, profile, config, max_papers=3):
    related, explore = [], []
    explore_sources = list(config.get('explore_sources', ['huggingface', 'openalex']))
    focused = focused_explore_candidates(
        [p for p in candidates if p.source in explore_sources], config)
    for paper in candidates:
        relevance = profile.score(paper)
        paper.score = relevance
        if paper.source in explore_sources:
            if id(paper) in focused and paper.popularity > 0 and relevance <= config.explore_max_relevance:
                paper.recommendation_type = "Explore / Trending"
                explore.append(paper)
        elif relevance >= config.min_relevance:
            if paper.source == "semantic_scholar":
                # Provider rank dominates the small relevance/citation tie-breaker.
                paper.score = (.8 / (1 + .05 * paper.source_rank) + .15 * relevance
                               + .05 * min(1, math.log1p(paper.citation_count) / math.log(1001)))
                paper.recommendation_type = "Related / Catch-up"
                paper.recommendation_reason = "Semantic Scholar recommendation from recent Zotero seeds"
            else:
                paper.recommendation_type = "Recent Interest"
                paper.recommendation_reason = "New paper matching your recent Zotero topics (BM25)"
            related.append(paper)
    # Merge the two relevance rankings with reciprocal ranks, avoiding incomparable scales.
    merged = []
    weights = config.get('source_weights', {})
    for source in dict.fromkeys(p.source for p in related):
        queue = sorted([p for p in related if p.source == source], key=lambda p: p.score, reverse=True)
        weight = weights.get(source, 1.0)
        if weight < 0:
            raise ValueError('Source weights must be nonnegative')
        if weight:
            merged.extend((weight / (rank + 1), p) for rank, p in enumerate(queue))
    merged.sort(key=lambda pair: pair[0], reverse=True)
    # Resolve aliases across every source, including rejected/low-quality rows.
    ordered = [p for _, p in merged] + explore
    representatives = deduplicate([*ordered, *candidates], library)
    allowed = {id(p) for p in representatives}
    related = [p for _, p in merged if id(p) in allowed]
    explore = [p for p in explore if id(p) in allowed]
    explore_slots = config.get('explore_slots', 1)
    minimum = config.get('min_interest_for_explore', 2)
    caps = config.get('source_limits', {})
    numbers = [max_papers, config.interest_slots, explore_slots, minimum, *caps.values()]
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in numbers):
        raise ValueError('Paper counts and source limits must be nonnegative integers')
    limit = max_papers
    chosen, counts = [], Counter()

    def take(pool, slots):
        added = 0
        for candidate in pool:
            if added >= slots or len(chosen) >= limit:
                break
            if candidate in chosen or counts[candidate.source] >= caps.get(candidate.source, limit):
                continue
            chosen.append(candidate)
            counts[candidate.source] += 1
            added += 1

    take(related, config.interest_slots)
    if explore_sources:
        preferred = explore_sources[profile.now.toordinal() % len(explore_sources)]
        explore.sort(key=lambda p: (p.source == preferred, p.popularity), reverse=True)
    explore = deduplicate(explore, [*library, *chosen])
    if len(chosen) >= minimum:
        take(explore, explore_slots)
    if config.get('fill_with_interest', True):
        take(related, limit - len(chosen))
    return chosen

from datetime import timedelta

import numpy as np
import pytest

from zotero_arxiv_daily.executor import Executor
from zotero_arxiv_daily.recommendation import MainlineProfile, InterestProfile, select_daily
from zotero_arxiv_daily.reranker.base import BaseReranker
from tests.test_recommendation import NOW, corpus, paper
from tests.test_curated_executor import configure


def mainline(config, strict=True):
    config.recommendation.mainline.enabled = True
    config.recommendation.mainline.strict = strict
    config.recommendation.mainline.include_path = ['研究主线', '研究主线/**']
    return config.recommendation


def anchor(**kwargs):
    p = corpus(age=5000, **kwargs)
    p.paths = ['研究主线']
    return p


def test_old_reference_survives_recent_window_and_future_dates(config):
    settings = mainline(config)
    settings.recent_limit = 1
    old = anchor(doi='10.1234/old')
    recent = [corpus('Protein folding molecular dynamics', age=i) for i in range(100)]
    p = paper('Efficient dense retrieval neural ranking')
    first = MainlineProfile(recent, [old], settings, NOW)
    later = MainlineProfile(recent, [old], settings, NOW + timedelta(days=2000))
    assert first.mainline_score(p) == later.mainline_score(p) > settings.mainline.min_relevance
    assert select_daily([p], [], first, settings) == [p]
    assert p.recommendation_type == 'Research Mainline'
    assert 'no time decay' in p.recommendation_reason
    assert first.seeds(1) == [old]


def test_other_anchor_topics_do_not_dilute_existing_references(config):
    settings = mainline(config)
    p = paper('Efficient dense retrieval neural ranking')
    one = MainlineProfile([], [anchor()], settings, NOW)
    many = MainlineProfile([], [anchor(), corpus('Protein folding molecular dynamics')], settings, NOW)
    assert one.mainline_score(p) == many.mainline_score(p)
    assert one.score(p) == one.mainline_score(p)  # no recent pool: full anchor weight


def test_reference_is_not_double_counted_and_duplicate_aliases_merge(config):
    settings = mainline(config)
    old = anchor(doi='10.1234/original')
    duplicate = corpus('Changed title', doi='10.1234/original')
    profile = MainlineProfile([old, duplicate], [old, duplicate], settings, NOW)
    assert len(profile.anchors) == 1
    assert profile.recent.corpus == []


def test_strict_gate_blocks_every_source_despite_popularity_and_recent_matches(config):
    settings = mainline(config)
    settings.explore_max_relevance = 1
    settings.min_interest_for_explore = 0
    profile = MainlineProfile([corpus('Protein folding molecular dynamics')], [anchor()], settings, NOW)
    candidates = [paper('Protein folding molecular dynamics', source=s, popularity=999)
                  for s in ['arxiv', 'semantic_scholar', 'huggingface', 'openalex']]
    assert select_daily(candidates, [], profile, settings, 100) == []
    relevant = paper('Efficient dense retrieval neural ranking', 'huggingface', popularity=10)
    assert select_daily([relevant], [], profile, settings) == [relevant]


def test_soft_mode_keeps_recent_interests_but_fixed_budget_does_not_shrink(config):
    settings = mainline(config, strict=False)
    recent = corpus('Protein folding molecular dynamics')
    profile = MainlineProfile([recent], [anchor()], settings, NOW)
    p = paper('Protein folding molecular dynamics improved')
    assert profile.mainline_score(p) == 0
    assert profile.score(p) == pytest.approx(.4 * profile.recent.score(p))
    assert select_daily([p], [], profile, settings) == [p]


def test_all_anchors_rotate_through_small_seed_budget_independently_of_age(config):
    settings = mainline(config)
    anchors = [corpus(f'Topic {i}', doi=f'10.1234/ref{i}', age=3000+i) for i in range(8)]
    observed = set()
    for day in range(8):
        profile = MainlineProfile([corpus(doi='10.1234/recent')], anchors, settings, NOW+timedelta(days=day))
        seeds = profile.seeds(2)
        assert all(s in anchors for s in seeds)
        observed.update(p.doi for p in seeds)
    assert observed == {p.doi for p in anchors}


def test_soft_seeds_reserve_mainline_share_and_fill_remaining_slots(config):
    settings = mainline(config, strict=False)
    anchors = [corpus(f'Anchor topic {i}', doi=f'10.1234/ref{i}') for i in range(8)]
    recent = corpus('Protein folding molecular dynamics', doi='10.1234/recent')
    other = corpus('Quantum entanglement teleportation', doi='10.1234/other')
    seeds = MainlineProfile([recent, other], anchors, settings, NOW).seeds(5)
    assert len(seeds) == 5 and sum(p in anchors for p in seeds) == 3
    assert recent in seeds and other in seeds


@pytest.mark.parametrize('key,value', [('weight', 0), ('weight', 1.1), ('weight', float('nan')),
                                     ('strict', 'false'), ('min_relevance', 0),
                                     ('embedding_min_relevance', 11)])
def test_invalid_mainline_parameters(config, key, value):
    settings = mainline(config)
    settings.mainline[key] = value
    with pytest.raises(ValueError):
        MainlineProfile([], [anchor()], settings, NOW)


def test_empty_mainline_fails_without_silent_recent_fallback(config):
    settings = mainline(config)
    with pytest.raises(ValueError, match='empty'):
        MainlineProfile([corpus()], [], settings, NOW)


class MatrixReranker(BaseReranker):
    def get_similarity_score(self, candidates, references):
        # Mainline match vs a much stronger recent-only match.
        assert len(references) == 2
        return np.array([[.8, .1], [.05, .99]])


def test_embedding_keeps_anchor_budget_and_strict_filter_without_keyword_gate(config):
    settings = mainline(config)
    profile = MainlineProfile([corpus('Protein folding molecular dynamics')], [anchor()], settings, NOW)
    good, drift = paper('Semantically relevant paraphrase'), paper('Unrelated but recent preference')
    scores, anchors = MatrixReranker(config).score_mainline([good, drift], profile)
    assert scores[id(good)] == pytest.approx(5.2)
    assert anchors[id(good)] == pytest.approx(8)
    assert scores[id(drift)] > settings.embedding_min_relevance
    assert profile.mainline_score(good) == 0  # embedding sources do not require lexical overlap
    assert select_daily([drift, good], [], profile, settings, embedding_scores=scores,
                        mainline_embedding_scores=anchors) == [good]
    with pytest.raises(ValueError, match='Mainline embedding scores'):
        select_daily([good], [], profile, settings, embedding_scores=scores)


def test_title_only_reference_can_be_used_for_embedding(config):
    settings = mainline(config)
    profile = MainlineProfile([], [anchor(abstract='')], settings, NOW)
    class TitleOnlyReranker(BaseReranker):
        def get_similarity_score(self, candidates, references):
            assert references == [profile.anchors[0].title]
            return np.array([[.8]])
    p = paper('Semantic match')
    scores, anchors = TitleOnlyReranker(config).score_mainline([p], profile)
    assert scores[id(p)] == anchors[id(p)] == 8


def test_topic_filter_applies_to_all_sources_even_without_mainline(config):
    settings = config.recommendation
    settings.topic_filter.include_topics = ['dense neural retrieval ranking']
    settings.topic_filter.exclude_topics = ['protein folding molecular dynamics']
    settings.min_interest_for_explore = 0
    profile = InterestProfile([corpus('Protein folding molecular dynamics')], settings, NOW)
    candidates = [paper('Protein folding molecular dynamics', source=s, popularity=999)
                  for s in ['arxiv', 'semantic_scholar', 'huggingface', 'openalex']]
    assert select_daily(candidates, [], profile, settings,
                        embedding_scores={id(candidates[0]): 9}) == []


def test_strict_rejection_never_breaks_whole_library_alias_dedup(config):
    settings = mainline(config)
    profile = MainlineProfile([], [anchor()], settings, NOW)
    owned = corpus('Already owned', doi='10.1234/owned')
    bridge = paper('Unrelated protein folding', doi='10.1234/owned', arxiv_id='2609.12345')
    alias = paper('New dense neural retrieval ranking', arxiv_id='2609.12345')
    assert select_daily([alias, bridge], [owned], profile, settings) == []


def test_executor_reads_mainline_outside_recent_paths_and_preserves_owned_dedup(config, monkeypatch):
    configure(config)
    mainline(config)
    config.zotero.include_path = ['Reading/**']
    old = anchor(doi='10.1234/owned')
    recent = corpus('Protein folding molecular dynamics')
    recent.paths = ['Reading/Today']
    from zotero_arxiv_daily.retriever.base import registered_retrievers
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [old, recent])
    monkeypatch.setattr(registered_retrievers['arxiv'], 'retrieve_papers', lambda self: [
        paper('Efficient neural retrieval ranking'),
        paper('Owned dense neural retrieval ranking', doi='10.1234/owned'),
        paper('New protein folding molecular dynamics')])
    def discover(profile, settings):
        assert profile.anchors == [old] and profile.seeds(5) == [old]
        return []
    monkeypatch.setattr('zotero_arxiv_daily.executor.discover', discover)
    sent = []
    monkeypatch.setattr('zotero_arxiv_daily.executor.send_email', lambda cfg, html: sent.append(html))
    Executor(config).run()
    assert len(sent) == 1 and 'Research Mainline' in sent[0]
    assert 'Owned dense' not in sent[0] and 'protein folding' not in sent[0]


def test_executor_missing_collection_stops_before_fetching_candidates(config, monkeypatch):
    configure(config)
    mainline(config)
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [corpus()])
    executor = Executor(config)
    def forbidden():
        raise AssertionError('Missing collection must stop before candidate retrieval')
    for retriever in executor.retrievers.values():
        monkeypatch.setattr(retriever, 'retrieve_papers', forbidden)
    with pytest.raises(ValueError, match='empty'):
        executor.run()


def test_executor_embedding_mainline_without_recent_corpus(config, monkeypatch):
    configure(config)
    mainline(config)
    config.executor.reranker = 'local'
    config.zotero.include_path = ['MissingRecentFolder']
    from zotero_arxiv_daily.reranker.local import LocalReranker
    from zotero_arxiv_daily.retriever.base import registered_retrievers
    old = anchor(abstract='')
    good = paper('Semantic paraphrase relevant to fixed reference')
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [old])
    monkeypatch.setattr(registered_retrievers['arxiv'], 'retrieve_papers', lambda self: [good])
    monkeypatch.setattr('zotero_arxiv_daily.executor.discover', lambda *args: [])
    monkeypatch.setattr(LocalReranker, 'get_similarity_score', lambda self, a, b: np.array([[.8]]))
    sent = []
    monkeypatch.setattr('zotero_arxiv_daily.executor.send_email', lambda cfg, html: sent.append(html))
    Executor(config).run()
    assert len(sent) == 1 and 'Research Mainline' in sent[0] and 'embedding' in sent[0]

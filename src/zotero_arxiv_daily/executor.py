from loguru import logger
from pyzotero import zotero
from omegaconf import DictConfig, ListConfig
from .utils import glob_match
from .retriever import get_retriever_cls
from .protocol import CorpusPaper
import random
from datetime import datetime
from .reranker import get_reranker_cls
from .construct_email import render_email
from .utils import send_email
from openai import OpenAI
from tqdm import tqdm
from .recommendation import InterestProfile, select_daily, normalize_doi, normalize_s2, zotero_arxiv_id
from .discovery import discover
from .reading_notes import generate_reading_notes


def normalize_path_patterns(patterns: list[str] | ListConfig | None, config_key: str) -> list[str] | None:
    if patterns is None:
        return None

    if not isinstance(patterns, (list, ListConfig)):
        raise TypeError(
            f"config.zotero.{config_key} must be a list of glob patterns or null, "
            'for example ["2026/survey/**"]. Single strings are not supported.'
        )

    if any(not isinstance(pattern, str) for pattern in patterns):
        raise TypeError(f"config.zotero.{config_key} must contain only glob pattern strings.")

    return list(patterns)


class Executor:
    def __init__(self, config:DictConfig):
        self.config = config
        self.include_path_patterns = normalize_path_patterns(config.zotero.include_path, "include_path")
        self.ignore_path_patterns = normalize_path_patterns(config.zotero.ignore_path, "ignore_path")
        self.retrievers = {
            source: get_retriever_cls(source)(config) for source in config.executor.source
        }
        self.reranker = get_reranker_cls(config.executor.reranker)(config)
        self.curated = config.get('recommendation', {}).get('enabled', False)
        if self.curated and config.executor.reranker not in ('bm25', 'local', 'api'):
            raise ValueError('Curated recommendations require bm25, local or api reranker')
        self.openai_client = (OpenAI(api_key=config.llm.api.key, base_url=config.llm.api.base_url,
                                    timeout=config.llm.api.get('timeout', 90),
                                    max_retries=config.llm.api.get('max_retries', 2))
                              if config.llm.get('enabled', True) else None)
    def fetch_zotero_corpus(self) -> list[CorpusPaper]:
        logger.info("Fetching zotero corpus")
        zot = zotero.Zotero(self.config.zotero.user_id, 'user', self.config.zotero.api_key)
        collections = zot.everything(zot.collections())
        collections = {c['key']:c for c in collections}
        # Keep all bibliographic items for deduplication, even without abstracts.
        corpus = zot.everything(zot.items(itemType='-attachment || note || annotation'))
        corpus = [c for c in corpus if c['data'].get('title')]
        def get_collection_path(col_key:str) -> str:
            if p := collections[col_key]['data']['parentCollection']:
                return get_collection_path(p) + '/' + collections[col_key]['data']['name']
            else:
                return collections[col_key]['data']['name']
        for c in corpus:
            paths = [get_collection_path(col) for col in c['data'].get('collections', []) if col in collections]
            c['paths'] = paths
        logger.info(f"Fetched {len(corpus)} zotero papers")
        return [CorpusPaper(
            title=c['data']['title'],
            abstract=c['data'].get('abstractNote', ''),
            added_date=datetime.strptime(c['data']['dateAdded'], '%Y-%m-%dT%H:%M:%SZ'),
            paths=c['paths'],
            tags=[tag['tag'] for tag in c['data'].get('tags', []) if tag.get('tag')],
            doi=normalize_doi(c['data'].get('DOI')) or normalize_doi(c['data'].get('extra'))
                or normalize_doi(c['data'].get('url')),
            arxiv_id=zotero_arxiv_id(c['data']),
            url=c['data'].get('url', ''),
            semantic_scholar_id=normalize_s2(c['data'].get('url')) or normalize_s2(c['data'].get('extra')),
        ) for c in corpus]
    
    def filter_corpus(self, corpus:list[CorpusPaper]) -> list[CorpusPaper]:
        if self.include_path_patterns:
            logger.info(f"Selecting zotero papers matching include_path: {self.include_path_patterns}")
            corpus = [
                c for c in corpus
                if any(
                    glob_match(path, pattern)
                    for path in c.paths
                    for pattern in self.include_path_patterns
                )
            ]
        if self.ignore_path_patterns:
            logger.info(f"Excluding zotero papers matching ignore_path: {self.ignore_path_patterns}")
            corpus = [
                c for c in corpus
                if not any(
                    glob_match(path, pattern)
                    for path in c.paths
                    for pattern in self.ignore_path_patterns
                )
            ]
        if self.include_path_patterns or self.ignore_path_patterns:
            samples = random.sample(corpus, min(5, len(corpus)))
            samples = '\n'.join([c.title + ' - ' + '\n'.join(c.paths) for c in samples])
            logger.info(f"Selected {len(corpus)} zotero papers:\n{samples}\n...")
        return corpus

    
    def run(self):
        library = self.fetch_zotero_corpus()
        corpus = self.filter_corpus(library)
        if len(corpus) == 0:
            logger.error("No zotero papers found. Please check your zotero settings.")
            return
        all_papers = []
        for source, retriever in self.retrievers.items():
            logger.info(f"Retrieving {source} papers...")
            try:
                papers = retriever.retrieve_papers()
            except Exception as exc:
                if not self.curated:
                    raise
                logger.warning("Source {} unavailable ({})", source, type(exc).__name__)
                continue
            if len(papers) == 0:
                logger.info(f"No {source} papers found")
                continue
            logger.info(f"Retrieved {len(papers)} {source} papers")
            all_papers.extend(papers)
        logger.info(f"Total {len(all_papers)} papers retrieved from all sources")
        reranked_papers = []
        if self.curated:
            profile = InterestProfile(corpus, self.config.recommendation)
            all_papers.extend(discover(profile, self.config.recommendation))
            embedding_scores = {}
            if self.config.executor.reranker != 'bm25':
                sources = self.config.recommendation.get('embedding_sources', ['arxiv'])
                candidates = [p for p in all_papers if p.source in sources]
                if candidates:
                    embedding_corpus = [p for p in corpus if p.abstract and p.abstract.strip()]
                    if not embedding_corpus:
                        raise ValueError('Embedding ranking requires Zotero papers with abstracts')
                    logger.info('Embedding reranking {} candidates from {}', len(candidates), list(sources))
                    ranked = self.reranker.rerank(candidates, embedding_corpus)
                    embedding_scores = {id(p): float(p.score) for p in ranked}
            reranked_papers = select_daily(all_papers, library, profile, self.config.recommendation,
                                           self.config.executor.max_paper_num, embedding_scores=embedding_scores)
        elif len(all_papers) > 0:
            logger.info("Reranking papers...")
            reranked_papers = self.reranker.rerank(all_papers, corpus)
            reranked_papers = reranked_papers[:self.config.executor.max_paper_num]
        if not reranked_papers and not self.config.executor.send_empty:
            logger.info("No qualifying new papers found. No email will be sent.")
            return
        logger.info("Preparing summaries...")
        logger.info('Selected {} papers; source counts: {}', len(reranked_papers),
                    {source: sum(p.source == source for p in reranked_papers) for source in dict.fromkeys(p.source for p in reranked_papers)})
        for p in tqdm(reranked_papers):
            if self.openai_client is not None:
                notes_config = self.config.llm.get('reading_notes', {})
                if notes_config.get('enabled', False):
                    generate_reading_notes(p, self.openai_client, self.config.llm, notes_config)
                p.generate_tldr(self.openai_client, self.config.llm)
                p.generate_affiliations(self.openai_client, self.config.llm)
            else:
                p.tldr = p.abstract or 'Abstract unavailable; follow the paper link for details.'
        logger.info("Sending email...")
        logger.info('Reading notes generated: {}/{}', sum(bool(p.reading_notes) for p in reranked_papers), len(reranked_papers))
        email_content = render_email(reranked_papers, collapsible=self.config.email.get('notes_collapsible', False),
                                     max_width=self.config.email.get('max_width', 1120))
        send_email(self.config, email_content)
        logger.info("Email sent successfully")

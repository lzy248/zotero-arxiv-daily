from datetime import datetime

from omegaconf import OmegaConf, open_dict

from zotero_arxiv_daily.executor import Executor
from zotero_arxiv_daily.construct_email import render_email
from tests.canned_responses import make_stub_zotero_client
from tests.test_recommendation import corpus, paper


def test_fetch_keeps_abstractless_identifiers_and_metadata(config, monkeypatch):
    data = {'title': 'Already owned', 'dateAdded': '2026-09-23T00:00:00Z',
            'DOI': 'https://doi.org/10.1234/TEST', 'tags': [{'tag': 'retrieval'}],
            'url': 'https://arxiv.org/abs/2609.12345v2', 'collections': []}
    stub = make_stub_zotero_client(items=[{'data': data}])
    monkeypatch.setattr('zotero_arxiv_daily.executor.zotero.Zotero', lambda *a, **kw: stub)
    executor = Executor.__new__(Executor)
    executor.config = config
    result = executor.fetch_zotero_corpus()[0]
    assert result.abstract == '' and result.doi == '10.1234/test'
    assert result.arxiv_id == '2609.12345' and result.tags == ['retrieval']


def configure(config):
    config.recommendation.enabled = True
    config.executor.reranker = 'bm25'
    config.executor.max_paper_num = 3
    config.llm.enabled = False
    # Missing credentials must never be resolved when LLM is disabled.
    config.llm.api = OmegaConf.create({'key': '???', 'base_url': '???'})


def test_curated_e2e_full_library_dedup_and_no_llm(config, monkeypatch):
    configure(config)
    from zotero_arxiv_daily.retriever.base import registered_retrievers
    recent = corpus()
    recent.added_date = datetime.now()
    owned = corpus('Archived paper', doi='10.1234/owned')
    owned.paths = ['archive']
    config.zotero.ignore_path = ['archive']
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [recent, owned])
    candidates = [paper('Efficient dense retrieval neural ranking'),
                  paper('Owned neural retrieval ranking', doi='10.1234/owned')]
    monkeypatch.setattr(registered_retrievers['arxiv'], 'retrieve_papers', lambda self: candidates)
    monkeypatch.setattr('zotero_arxiv_daily.executor.discover', lambda *args: [
        paper('Classic dense retrieval neural ranking', 'semantic_scholar'),
        paper('Protein folding dynamics', 'openalex', popularity=1)])
    def forbidden(**kwargs):
        raise AssertionError('Must not initialize LLM')
    monkeypatch.setattr('zotero_arxiv_daily.executor.OpenAI', forbidden)
    sent = []
    monkeypatch.setattr('zotero_arxiv_daily.executor.send_email', lambda config, html: sent.append(html))
    Executor(config).run()
    assert len(sent) == 1
    assert 'Recent Interest' in sent[0] and 'Related / Catch-up' in sent[0] and 'Explore / Trending' in sent[0]
    assert 'Owned neural' not in sent[0]
    assert 'href="None"' not in sent[0]


def test_no_qualified_candidates_does_not_send(config, monkeypatch):
    configure(config)
    from zotero_arxiv_daily.retriever.base import registered_retrievers
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [corpus()])
    monkeypatch.setattr(registered_retrievers['arxiv'], 'retrieve_papers', lambda self: [paper('Pottery excavation')])
    monkeypatch.setattr('zotero_arxiv_daily.executor.discover', lambda *args: [])
    sent = []
    monkeypatch.setattr('zotero_arxiv_daily.executor.send_email', lambda *args: sent.append(args))
    Executor(config).run()
    assert sent == []


def test_email_escapes_external_metadata_and_uses_landing_page():
    p = paper('<script>alert(1)</script>', recommendation_type='Explore / Trending',
              recommendation_reason='<unsafe>', pdf_url=None)
    html = render_email([p])
    assert '<script>' not in html and '&lt;unsafe&gt;' in html
    assert '>Paper</a>' in html and 'href="https://example.org/paper"' in html


def test_embedding_only_scores_arxiv_and_preserves_curated_pipeline(config, monkeypatch):
    configure(config)
    config.executor.reranker = 'local'
    from zotero_arxiv_daily.reranker.local import LocalReranker
    from zotero_arxiv_daily.retriever.base import registered_retrievers
    recent = corpus()
    recent.added_date = datetime.now()
    candidate = paper('Semantic match without shared keywords')
    calls = []
    def rerank(self, candidates, library):
        calls.append((candidates, library))
        assert all(p.source == 'arxiv' for p in candidates)
        for p in candidates:
            p.score = 7.0
        return candidates
    monkeypatch.setattr(LocalReranker, 'rerank', rerank)
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [recent])
    monkeypatch.setattr(registered_retrievers['arxiv'], 'retrieve_papers', lambda self: [candidate])
    monkeypatch.setattr('zotero_arxiv_daily.executor.discover', lambda *args: [
        paper('Classic dense retrieval neural ranking', 'semantic_scholar'),
        paper('Protein folding dynamics', 'openalex', popularity=1)])
    sent = []
    monkeypatch.setattr('zotero_arxiv_daily.executor.send_email', lambda config, html: sent.append(html))
    Executor(config).run()
    assert len(calls) == 1 and len(sent) == 1
    assert 'Semantic match without shared keywords' in sent[0]
    assert 'embedding similarity' in sent[0]
    assert 'Related / Catch-up' in sent[0] and 'Explore / Trending' in sent[0]

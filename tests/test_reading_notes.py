import json
from types import SimpleNamespace

from zotero_arxiv_daily import reading_notes as notes
from zotero_arxiv_daily.construct_email import render_email
from tests.test_recommendation import paper


def response():
    return json.dumps({key: 'Evidence from section 3.\nA second paragraph.' for key in notes.SECTIONS})


def test_fulltext_notes_reuse_transport_and_five_sections(config, monkeypatch):
    calls = []
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'Full paper evidence')
    monkeypatch.setattr(notes, '_request_llm', lambda client, params, messages: calls.append(messages) or response())
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert list(p.reading_notes) == list(notes.SECTIONS)
    assert '全文' in p.reading_notes_basis and len(calls) == 1
    assert 'personal research relevance' in calls[0][0]['content']


def test_abstract_only_and_invalid_output_fallback(config, monkeypatch):
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: None)
    monkeypatch.setattr(notes, '_request_llm', lambda *a: response())
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert '仅依据摘要' in p.reading_notes_basis
    monkeypatch.setattr(notes, '_request_llm', lambda *a: '{"background": "incomplete"}')
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert p.reading_notes is None and p.reading_notes_status


def test_long_paper_samples_end_and_bounds_calls(config, monkeypatch):
    class Encoding:
        def encode(self, text, **kwargs):
            return list(text)
        def decode(self, tokens):
            return ''.join(tokens)
    monkeypatch.setattr(notes.tiktoken, 'encoding_for_model', lambda _: Encoding())
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'A' * 500 + 'B' * 500 + 'C' * 500 + 'Z' * 500)
    calls = []
    def request(client, params, messages):
        calls.append(messages[1]['content'])
        return response() if 'Evidence coverage' in calls[-1] else 'Extracted evidence'
    monkeypatch.setattr(notes, '_request_llm', request)
    config.llm.reading_notes.chunk_tokens = 500
    config.llm.reading_notes.max_chunks = 2
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert len(calls) == 3 and 'Z' * 500 in calls[1]
    assert '2/4' in p.reading_notes_basis


def test_extraction_reuses_workers_with_timeout_and_fallback(monkeypatch):
    calls = []
    def run(worker, args, **kwargs):
        calls.append((worker, args, kwargs))
        return None if len(calls) == 1 else 'paper text ' * 100
    monkeypatch.setattr(notes.extraction, '_run_with_hard_timeout', run)
    p = paper(arxiv_id='2609.12345')
    assert notes.fetch_full_text(p, 12) == p.full_text
    assert len(calls) == 2
    assert calls[0][1] == ('https://arxiv.org/html/2609.12345',)
    assert calls[1][0] is notes.extraction._extract_text_from_pdf_worker
    assert all(c[2]['timeout'] == 12 for c in calls)


def test_expanded_and_collapsed_email_escape_model_content():
    p = paper(reading_notes={k: '<script>alert(1)</script>\nSecond paragraph' for k in notes.SECTIONS},
              reading_notes_basis='仅依据摘要', url='javascript:alert(1)')
    expanded = render_email([p])
    collapsed = render_email([p], collapsible=True)
    assert '<details>' not in expanded and '<details>' in collapsed
    assert '<script>' not in expanded and '&lt;script&gt;' in expanded
    assert 'javascript:' not in expanded
    assert 'display:none' not in collapsed
    for heading in notes.SECTIONS.values():
        assert heading in expanded and heading in collapsed


def test_notes_only_generated_for_selected_papers(config, monkeypatch):
    from datetime import datetime
    from zotero_arxiv_daily.executor import Executor
    from zotero_arxiv_daily.retriever.base import registered_retrievers
    from tests.test_recommendation import corpus
    from tests.canned_responses import make_stub_openai_client
    config.recommendation.enabled = True
    config.executor.reranker = 'bm25'
    config.executor.max_paper_num = 2
    config.llm.reading_notes.enabled = True
    recent = corpus()
    recent.added_date = datetime.now()
    monkeypatch.setattr(Executor, 'fetch_zotero_corpus', lambda self: [recent])
    monkeypatch.setattr('zotero_arxiv_daily.executor.OpenAI', lambda **kw: make_stub_openai_client())
    candidates = [paper('Efficient neural dense retrieval ranking'), paper('Sparse dense retrieval neural ranking'), paper('Pottery')]
    monkeypatch.setattr(registered_retrievers['arxiv'], 'retrieve_papers', lambda self: candidates)
    monkeypatch.setattr('zotero_arxiv_daily.executor.discover', lambda *a: [])
    generated = []
    monkeypatch.setattr('zotero_arxiv_daily.executor.generate_reading_notes', lambda p, *a: generated.append(p))
    monkeypatch.setattr('zotero_arxiv_daily.executor.send_email', lambda *a: None)
    Executor(config).run()
    assert len(generated) == 2 and candidates[-1] not in generated


def test_malformed_notes_retry_then_success(config, monkeypatch):
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: None)
    results = iter(['not json', response()])
    calls = []
    def request(*args):
        calls.append(1)
        return next(results)
    monkeypatch.setattr(notes, '_request_llm', request)
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert p.reading_notes and len(calls) == 2

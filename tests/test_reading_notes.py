import json
from types import SimpleNamespace

from zotero_arxiv_daily import reading_notes as notes
from zotero_arxiv_daily.construct_email import render_email
from tests.test_recommendation import paper


def response():
    return json.dumps({**{key: 'Evidence from section 3.\nA second paragraph.' for key in notes.SECTIONS},
                       'method_map': [], 'experiment_table': [], 'pipeline': []})


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
        if 'Evidence coverage' in calls[-1]:
            return response()
        quote = 'A' * 20 if 'A' * 500 in calls[-1] else 'Z' * 20
        return json.dumps({'facts': [{'kind': 'method', 'claim': 'Mechanism evidence', 'quote': quote, 'location': 'fragment only'}]})
    monkeypatch.setattr(notes, '_request_llm', request)
    config.llm.reading_notes.chunk_tokens = 500
    config.llm.reading_notes.mode = 'chunked'
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
    assert '<details style="display:none' not in collapsed
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


def test_full_read_does_not_compress_or_drop_tables(config, monkeypatch):
    content = ('Introduction: a specific failure and its mechanism.\n' * 700
               + '\n| Method | Main result |\n| Baseline | 62.4 |\n| Proposed | 70.1 |\n')
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: content)
    calls = []
    monkeypatch.setattr(notes, '_request_llm', lambda c, p, m: calls.append(m) or response())
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert len(calls) == 1 and p.reading_notes
    assert content in calls[0][1]['content']
    assert '全文直读' in p.reading_notes_basis


def test_full_mode_over_budget_never_silently_truncates(config, monkeypatch):
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'evidence ' * 5000)
    config.llm.reading_notes.max_input_tokens = 2000
    def forbidden(*args):
        raise AssertionError('Must not send a silently truncated full paper')
    monkeypatch.setattr(notes, '_request_llm', forbidden)
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert p.reading_notes is None and '超出' in p.reading_notes_status


def test_unanchored_evidence_is_rejected():
    import pytest
    with pytest.raises(ValueError, match='quote not found'):
        notes._validate_facts({'facts': [{'kind': 'method', 'claim': 'fabricated',
                            'quote': 'never present', 'location': 'section 1'}]}, 'Actual source text')


def test_failed_chunk_is_not_marked_as_complete(config, monkeypatch):
    config.llm.reading_notes.mode = 'chunked'
    config.llm.reading_notes.chunk_tokens = 500
    config.llm.reading_notes.max_chunks = 2
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'first evidence ' * 800 + ' last evidence ' * 800)
    def request(client, params, messages):
        text = messages[1]['content']
        if 'Evidence coverage' in text:
            return response()
        if 'FRAGMENT F1/' in text:
            return 'not evidence'
        fragment = text.split('(quote only from this fragment):\n', 1)[1]
        return json.dumps({'facts': [{'kind': 'limitations', 'claim': 'last evidence',
                                     'quote': fragment[:40], 'location': 'fragment only'}]})
    monkeypatch.setattr(notes, '_request_llm', request)
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert p.reading_notes and '提取失败：F1' in p.reading_notes_basis


def test_visual_tables_and_flow_are_safe_and_complete(config, monkeypatch):
    data = json.loads(response())
    data['method_map'] = [{'difficulty': '<script>bad</script>', 'design': 'Memory', 'mechanism': 'Share errors', 'evidence': 'Section 3'}]
    data['experiment_table'] = [{'comparison': 'No memory', 'setting': 'Benchmark A', 'result': 'Reported ablation', 'meaning': 'Tests sharing', 'evidence': 'Table 2'}]
    data['pipeline'] = ['Generate candidate', 'Execute checks', 'Update memory']
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'Source content')
    monkeypatch.setattr(notes, '_request_llm', lambda *a: json.dumps(data))
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    html = render_email([p])
    assert '<caption' in html and '困难与设计' in html and '贡献与实验' in html
    assert 'Update memory' in html and '↓' in html
    assert '<script>' not in html and '&lt;script&gt;' in html


def test_notes_are_not_cut_at_old_1200_character_limit(config, monkeypatch):
    data = json.loads(response())
    data['method'] = 'Explanation ' * 150
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'Evidence')
    monkeypatch.setattr(notes, '_request_llm', lambda *a: json.dumps(data))
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert p.reading_notes['method'] == data['method'].strip()


def test_total_context_reserves_output_tokens(config, monkeypatch):
    config.llm.reading_notes.context_window_tokens = 4000
    config.llm.reading_notes.max_output_tokens = 3000
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'source evidence ' * 1000)
    calls = []
    monkeypatch.setattr(notes, '_request_llm', lambda *a: calls.append(a) or response())
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert not calls and p.reading_notes is None and '上下文' in p.reading_notes_status


def test_output_budget_forwarded_without_prose_ceiling(config, monkeypatch):
    data = json.loads(response())
    data['method'] = 'Detailed evidence. ' * 350
    params_seen = []
    monkeypatch.setattr(notes, 'fetch_full_text', lambda *a: 'Source evidence')
    def request(client, params, messages):
        params_seen.append(params)
        return json.dumps(data)
    monkeypatch.setattr(notes, '_request_llm', request)
    p = paper()
    notes.generate_reading_notes(p, object(), config.llm, config.llm.reading_notes)
    assert params_seen[0]['generation_kwargs']['max_tokens'] == 65536
    assert len(p.reading_notes['method']) > 5000

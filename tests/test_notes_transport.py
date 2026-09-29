from types import SimpleNamespace
import pytest

from zotero_arxiv_daily.protocol import _request_llm
from tests.canned_responses import make_sample_paper


def test_truncated_llm_output_is_not_accepted_as_complete_notes():
    response = SimpleNamespace(choices=[SimpleNamespace(finish_reason='length', message=SimpleNamespace(content='{}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
    with pytest.raises(ValueError, match='token budget'):
        _request_llm(client, {'require_complete': True}, [])


def test_tldr_focuses_on_innovation_and_uses_notes(monkeypatch):
    received = []
    def request(client, params, messages):
        received.append(messages)
        return 'Innovation-focused TLDR'
    monkeypatch.setattr('zotero_arxiv_daily.protocol._request_llm', request)
    p = make_sample_paper()
    p.reading_notes = {'background': 'Concrete gap', 'contributions': 'Distinct mechanism', 'method': 'How it works', 'experiments': 'Score 99.9'}
    assert p.generate_tldr(object(), {'language': 'Chinese'}) == 'Innovation-focused TLDR'
    prompt = received[0][1]['content']
    assert 'Distinct mechanism' in prompt and 'Concrete gap' in prompt
    assert 'Score 99.9' not in prompt
    assert 'Do not lead with benchmark scores' in prompt

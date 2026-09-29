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


class FakeStream:
    def __init__(self, events):
        self.events, self.closed = events, False
    def __iter__(self):
        return iter(self.events)
    def close(self):
        self.closed = True


@pytest.mark.parametrize('finish,valid', [('stop', True), ('length', False), (None, False)])
def test_chat_stream_requires_normal_completion(finish, valid):
    stream = FakeStream([
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(index=0, delta=SimpleNamespace(content='{"notes":'), finish_reason=None)]),
        SimpleNamespace(choices=[SimpleNamespace(index=0, delta=SimpleNamespace(content='"complete"}'), finish_reason=finish)]),
    ])
    kwargs = {}
    def create(**kw):
        kwargs.update(kw)
        return stream
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    if valid:
        assert _request_llm(client, {'stream': True, 'require_complete': True}, []) == '{"notes":"complete"}'
    else:
        with pytest.raises(ValueError, match='complete normally'):
            _request_llm(client, {'stream': True, 'require_complete': True}, [])
    assert kwargs['stream'] and stream.closed


def test_responses_stream_requires_completed_event():
    events = [SimpleNamespace(type='response.output_text.delta', delta='Complete text'),
              SimpleNamespace(type='response.completed')]
    stream = FakeStream(events)
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: stream))
    params = {'api_mode': 'response', 'stream': True, 'require_complete': True}
    assert _request_llm(client, params, []) == 'Complete text'
    events.pop()
    with pytest.raises(ValueError, match='before completion'):
        _request_llm(client, params, [])

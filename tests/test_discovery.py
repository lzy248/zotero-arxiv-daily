from datetime import datetime
from types import SimpleNamespace

import pytest
import requests

from zotero_arxiv_daily import discovery
from zotero_arxiv_daily.discovery import common
from zotero_arxiv_daily.recommendation import InterestProfile
from tests.test_recommendation import corpus, NOW


def test_semantic_scholar_batch_seeds_and_metadata(config, monkeypatch):
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if 'batch' in url:
            return [{'paperId': 'resolved'}, None]
        return {'recommendedPapers': [{'paperId': 'result', 'title': 'Related', 'abstract': None,
                'externalIds': {'DOI': '10.1234/a', 'ArXiv': '2609.12345'},
                'authors': [{'name': 'Alice'}], 'citationCount': 42,
                'publicationDate': '2020-01-01', 'openAccessPdf': None}]}
    monkeypatch.setattr(discovery.semantic_scholar, 'request_json', request)
    profile = InterestProfile([corpus(doi='10.1234/seed')], config.recommendation, NOW)
    results = discovery.semantic_scholar.retrieve(profile, config.recommendation.semantic_scholar)
    assert calls[0][2]['json'] == {'ids': ['DOI:10.1234/seed']}
    assert calls[1][2]['json']['positivePaperIds'] == ['resolved']
    assert results[0].citation_count == 42
    assert results[0].abstract == '' and results[0].pdf_url is None


@pytest.mark.parametrize('period,key,value', [('daily', None, None), ('weekly', 'week', '2026-W39'), ('monthly', 'month', '2026-09')])
def test_hf_periods_and_quality(config, monkeypatch, period, key, value):
    captured = {}
    def request(method, url, **kwargs):
        captured.update(kwargs['params'])
        return [{'paper': {'id': '2609.12345', 'title': 'Trending', 'upvotes': 10}},
                {'paper': {'id': '2609.12346', 'title': 'Unpopular', 'upvotes': 0}}, {'bad': True}]
    monkeypatch.setattr(discovery.huggingface, 'request_json', request)
    config.recommendation.huggingface.period = period
    results = discovery.huggingface.retrieve(SimpleNamespace(now=NOW), config.recommendation.huggingface)
    assert captured['sort'] == 'trending'
    if key:
        assert captured[key] == value
    assert len(results) == 1 and results[0].arxiv_id == '2609.12345'


def test_openalex_rotation_abstract_and_retraction(config, monkeypatch):
    filters = []
    def request(method, url, **kwargs):
        filters.append(kwargs['params']['filter'])
        row = {'id': 'https://openalex.org/W1', 'title': 'Physics', 'publication_date': '2026-08-01',
               'cited_by_count': 10, 'abstract_inverted_index': {'world': [1], 'Hello': [0]},
               'primary_topic': {'field': {'display_name': 'Physics'}}}
        return {'results': [row, {**row, 'is_retracted': True}]}
    monkeypatch.setattr(discovery.openalex, 'request_json', request)
    results = discovery.openalex.retrieve(SimpleNamespace(now=NOW), config.recommendation.openalex)
    discovery.openalex.retrieve(SimpleNamespace(now=datetime(2026, 9, 25)), config.recommendation.openalex)
    assert len(results) == 1 and results[0].abstract == 'Hello world'
    assert filters[0] != filters[1]
    assert 'to_publication_date:2026-09-23' in filters[0]


def test_retry_timeout_and_failure_isolation(config, monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout('secret must not be logged')
    monkeypatch.setattr(common.requests, 'request', request)
    monkeypatch.setattr(common.time, 'sleep', lambda _: None)
    with pytest.raises(RuntimeError, match='bounded retries'):
        common.request_json('GET', 'https://example.org')
    assert len(calls) == 3 and all(c['timeout'] == (10, 30) for c in calls)
    def broken(*args):
        raise ValueError('bad response')
    monkeypatch.setattr(discovery.semantic_scholar, 'retrieve', broken)
    monkeypatch.setattr(discovery.huggingface, 'retrieve', lambda *args: ['surviving source'])
    monkeypatch.setattr(discovery.openalex, 'retrieve', lambda *args: [])
    assert discovery.discover(None, config.recommendation) == ['surviving source']


def test_rate_limit_retry_after_is_bounded(monkeypatch):
    waits = []
    responses = iter([
        SimpleNamespace(status_code=429, headers={'Retry-After': '300'}),
        SimpleNamespace(status_code=200, headers={}, raise_for_status=lambda: None, json=lambda: {'ok': True})])
    monkeypatch.setattr(common.requests, 'request', lambda *a, **kw: next(responses))
    monkeypatch.setattr(common.time, 'sleep', waits.append)
    assert common.request_json('GET', 'https://example.org') == {'ok': True}
    assert waits == [30]


def test_auth_error_not_retried(monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=401)
    monkeypatch.setattr(common.requests, 'request', request)
    with pytest.raises(RuntimeError, match='HTTP 401'):
        common.request_json('GET', 'https://example.org')
    assert len(calls) == 1


def test_no_seed_ids_avoids_api_call(config, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No API call expected')
    monkeypatch.setattr(discovery.semantic_scholar, 'request_json', forbidden)
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    assert discovery.semantic_scholar.retrieve(profile, config.recommendation.semantic_scholar) == []


def test_custom_retry_count_and_timeout(monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs['timeout'])
        raise requests.Timeout()
    monkeypatch.setattr(common.requests, 'request', request)
    monkeypatch.setattr(common.time, 'sleep', lambda _: None)
    with pytest.raises(RuntimeError):
        common.request_json('GET', 'https://example.org', config={'http': {'attempts': 2, 'read_timeout': 7}})
    assert calls == [(10, 7), (10, 7)]

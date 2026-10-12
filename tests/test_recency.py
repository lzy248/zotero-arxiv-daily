from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from zotero_arxiv_daily.recency import reading_dates, recent_corpus
from zotero_arxiv_daily.recommendation import InterestProfile, MainlineProfile
from zotero_arxiv_daily.reranker.base import BaseReranker
from zotero_arxiv_daily.executor import Executor
from tests.test_recommendation import corpus, paper, NOW
from tests.canned_responses import make_stub_zotero_client


def test_reading_dates_use_latest_child_and_ignore_unread_invalid_values():
    def attachment(parent, value):
        return {'data': {'itemType': 'attachment', 'parentItem': parent, 'lastRead': value}}
    rows = [attachment('P1', 1700000000), attachment('P1', 1800000000),
            attachment('P2', None), attachment('P3', True), attachment('P4', -1),
            attachment('P5', 1800000000000), attachment('P6', '2026-10-12'),
            attachment(None, 1800000000)]
    assert reading_dates(rows) == {'P1': datetime.fromtimestamp(1800000000, timezone.utc).replace(tzinfo=None)}


def test_read_recency_ranks_old_added_recently_read_first(config):
    config.recommendation.recency_basis = 'read'
    old = corpus('Dense retrieval neural ranking', age=365, last_read_date=NOW)
    new = corpus('Protein folding molecular dynamics', age=0, last_read_date=NOW - timedelta(days=180))
    unread = corpus('Fresh unread item', age=0)
    profile = InterestProfile([new, unread, old], config.recommendation, NOW)
    assert profile.corpus == [old, new]
    assert profile.score(paper()) > profile.score(paper(new.title))
    old.doi, new.doi = '10.1234/old', '10.1234/new'
    assert profile.seeds(1) == [old]


def test_added_compatibility_and_bad_basis(config):
    old, new = corpus(age=365, last_read_date=NOW), corpus(age=0)
    assert recent_corpus([old, new], config.recommendation) == [new, old]
    config.recommendation.recency_basis = 'modified'
    with pytest.raises(ValueError, match='added or read'):
        recent_corpus([new], config.recommendation)


def test_fixed_mainline_does_not_need_reading_timestamp(config):
    config.recommendation.recency_basis = 'read'
    config.recommendation.mainline.weight = .6
    anchor = corpus('Fixed research anchor', age=900)
    read = corpus('Recent read', last_read_date=NOW)
    unread = corpus('Never read')
    profile = MainlineProfile([anchor, read, unread], [anchor], config.recommendation, NOW)
    assert profile.anchors == [anchor] and profile.recent.corpus == [read]
    assert profile.weight == .6
    no_recent = MainlineProfile([unread], [anchor], config.recommendation, NOW)
    assert no_recent.weight == 1 and no_recent.recent.corpus == []


def test_embedding_rank_uses_read_order(config):
    config.recommendation.recency_basis = 'read'
    class Reranker(BaseReranker):
        def get_similarity_score(self, candidates, texts):
            assert texts == ['old but read now', 'new but read long ago']
            return np.array([[1, 0], [0, 1]])
    old = corpus(abstract='old but read now', age=365, last_read_date=NOW)
    new = corpus(abstract='new but read long ago', age=0, last_read_date=NOW - timedelta(days=90))
    candidates = [paper('Match recent reading'), paper('Match older reading')]
    ranked = Reranker(config).rerank(candidates, [new, corpus(), old])
    assert ranked[0] is candidates[0] and candidates[0].score > candidates[1].score


def test_fetch_attaches_synced_lastread_but_keeps_unread_for_dedup(config, monkeypatch):
    config.recommendation.recency_basis = 'read'
    items = [{'key': key, 'data': {'title': key, 'abstractNote': '',
              'dateAdded': '2020-01-01T00:00:00Z', 'collections': []}} for key in ['P1', 'P2']]
    attachments = [{'data': {'itemType': 'attachment', 'parentItem': 'P1', 'lastRead': 1800000000}}]
    stub = make_stub_zotero_client(items=items)
    stub.items = lambda **kwargs: attachments if kwargs.get('itemType') == 'attachment' else items
    monkeypatch.setattr('zotero_arxiv_daily.executor.zotero.Zotero', lambda *a, **kw: stub)
    executor = Executor.__new__(Executor)
    executor.config = config
    result = executor.fetch_zotero_corpus()
    assert len(result) == 2
    assert result[0].added_date == datetime(2020, 1, 1)
    assert result[0].last_read_date == datetime.fromtimestamp(1800000000, timezone.utc).replace(tzinfo=None)
    assert result[1].last_read_date is None
    assert stub.client.headers['Zotero-Schema-Version'] == '44'

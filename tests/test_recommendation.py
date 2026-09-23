from datetime import datetime, timedelta, timezone

import pytest

from zotero_arxiv_daily.protocol import CorpusPaper, Paper
from zotero_arxiv_daily.recommendation import InterestProfile, deduplicate, select_daily, tokenize, zotero_arxiv_id

NOW = datetime(2026, 9, 23)


def paper(title='Dense retrieval neural ranking', source='arxiv', **kwargs):
    return Paper(source, title, [], kwargs.pop('abstract', title),
                 kwargs.pop('url', 'https://example.org/paper'), **kwargs)


def corpus(title='Dense retrieval neural ranking', age=0, **kwargs):
    return CorpusPaper(title, kwargs.pop('abstract', title), NOW - timedelta(days=age), [], **kwargs)


def test_recency_and_unrelated_rejection(config):
    profile = InterestProfile([corpus(), corpus('Protein folding molecular dynamics', age=365)], config.recommendation, NOW)
    assert profile.score(paper()) > profile.score(paper('Protein folding molecular dynamics')) * 5
    assert profile.score(paper('Medieval pottery excavation')) == 0
    assert profile.score(paper('retrieval')) == 0
    assert 'retrieval' not in tokenize('retrievals')  # Not substring matching.


def test_metadata_and_no_abstract(config):
    profile = InterestProfile([corpus('Notes', abstract='', tags=['quantum entanglement teleportation'])], config.recommendation, NOW)
    assert profile.score(paper('Quantum entanglement teleportation')) > 0
    assert InterestProfile([], config.recommendation, NOW).score(paper()) == 0


def test_seed_diversity_and_timezone(config):
    recent = corpus(doi='10.1234/one')
    duplicate_topic = corpus(age=1, doi='10.1234/two')
    other = corpus('Protein folding molecular dynamics', age=2, arxiv_id='2609.12345')
    recent.added_date = recent.added_date.replace(tzinfo=timezone.utc)
    profile = InterestProfile([duplicate_topic, other, recent], config.recommendation, NOW)
    assert profile.seeds(5) == [recent, other]


def test_dedup_all_identifiers_and_transitive_aliases():
    library = [corpus('Existing', doi='https://doi.org/10.1234/ABC')]
    bridge = paper('Other title', doi='10.1234/abc', arxiv_id='2609.12345v2')
    alias = paper('Changed title', arxiv_id='2609.12345v1')
    assert deduplicate([alias, bridge], library) == []
    assert len(deduplicate([paper('Ａ Study: Foo!'), paper('a study foo')], [])) == 1
    assert len(deduplicate([paper('One', semantic_scholar_id='abc'), paper('Two', semantic_scholar_id='ABC')], [])) == 1
    assert deduplicate([paper(url='https://arxiv.org/abs/hep-th/9901001v2')], [corpus(arxiv_id='hep-th/9901001')]) == []


def test_two_interest_one_explore_and_no_padding(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    recent = paper('Efficient dense retrieval neural ranking')
    catchup = paper('Sparse neural ranking retrieval', 'semantic_scholar')
    trending = paper('Protein folding molecular dynamics', 'openalex', popularity=1)
    result = select_daily([recent, catchup, trending], [], profile, config.recommendation)
    assert result == [recent, catchup, trending]
    assert [p.recommendation_type for p in result] == ['Recent Interest', 'Related / Catch-up', 'Explore / Trending']
    assert select_daily([recent, trending], [], profile, config.recommendation) == [recent]
    assert select_daily([trending], [], profile, config.recommendation) == []
    assert len(select_daily([recent, catchup, trending], [], profile, config.recommendation, 2)) == 2


def test_owned_candidates_and_same_day_overlap(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    recent = paper('Efficient dense retrieval neural ranking', doi='10.1234/owned')
    duplicate = paper('Different neural ranking retrieval title', 'semantic_scholar', doi='10.1234/owned')
    assert len(select_daily([recent, duplicate], [], profile, config.recommendation)) == 1
    assert select_daily([recent, duplicate], [corpus('Archived without abstract', abstract='', doi='10.1234/owned')], profile, config.recommendation) == []


def test_invalid_config_fails_early(config):
    config.recommendation.half_life_days = 0
    with pytest.raises(ValueError):
        InterestProfile([], config.recommendation)


def test_low_quality_alias_still_blocks_owned_paper(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    library = [corpus('Archived title', doi='10.1234/owned')]
    bridge = paper('Unrelated topic', doi='10.1234/owned', arxiv_id='2609.12345')
    alias = paper('New dense retrieval neural ranking', arxiv_id='2609.12345')
    assert select_daily([alias, bridge], library, profile, config.recommendation) == []


def test_three_related_if_no_qualified_explore(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    candidates = [paper(f'{prefix} dense neural ranking retrieval') for prefix in ['Efficient', 'Sparse', 'Hybrid', 'Adaptive']]
    assert len(select_daily(candidates, [], profile, config.recommendation, 100)) == 4


def test_seed_rank_not_swamped_by_citations(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    first = paper('Neural retrieval ranking first', 'semantic_scholar', source_rank=0)
    popular = paper('Neural retrieval ranking popular', 'semantic_scholar', source_rank=20, citation_count=100000)
    assert select_daily([popular, first], [], profile, config.recommendation)[0] is first


def test_arxiv_metadata_does_not_guess_from_publisher_doi():
    assert zotero_arxiv_id({'url': 'https://doi.org/10.1234/2026.12345'}) is None
    assert zotero_arxiv_id({'extra': 'arXiv: 2609.12345v2'}) == '2609.12345'
    assert zotero_arxiv_id({'DOI': '10.48550/arXiv.2609.12345'}) == '2609.12345'


def test_explore_focus_accepts_language_agents_but_not_video(config):
    from zotero_arxiv_daily.recommendation import focused_explore_candidates
    config.recommendation.explore_include_topics = ['language models NLP LLM reasoning agents tool calling retrieval augmented generation question answering']
    config.recommendation.explore_exclude_topics = ['computer vision video image synthesis 3D camera scene reconstruction']
    language = paper('Language agents for tool calling and multi step reasoning', 'huggingface', popularity=1)
    rag = paper('Retrieval augmented generation for question answering with large language models', 'openalex', popularity=1)
    vision = paper('Video world models for consistent 3D camera control', 'huggingface',
                   abstract='Video generation from text prompts with scene reconstruction and visual memory', popularity=100)
    unrelated = paper('Protein folding and molecular dynamics', 'openalex', popularity=100)
    selected = focused_explore_candidates([language, rag, vision, unrelated], config.recommendation)
    assert selected == {id(language), id(rag)}


def test_focused_explore_never_pads_with_vision(config):
    config.recommendation.explore_include_topics = ['language models NLP LLM reasoning agents tool calling retrieval augmented generation question answering']
    config.recommendation.explore_exclude_topics = ['computer vision video image synthesis 3D camera scene reconstruction']
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    candidates = [paper('Sparse dense neural retrieval ranking'), paper('Efficient dense retrieval neural ranking'),
                  paper('Video image synthesis camera scene reconstruction', 'huggingface', popularity=100)]
    assert len(select_daily(candidates, [], profile, config.recommendation)) == 2


def test_configurable_total_allocation_caps_and_no_fill(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    candidates = [paper(f'{word} dense neural retrieval ranking') for word in ['Efficient', 'Sparse', 'Hybrid', 'Adaptive']]
    candidates += [paper(f'Protein {word}', 'openalex', popularity=1) for word in ['folding', 'dynamics']]
    config.recommendation.interest_slots = 4
    config.recommendation.explore_slots = 2
    assert len(select_daily(candidates, [], profile, config.recommendation, 6)) == 6
    config.recommendation.source_limits = {'arxiv': 2}
    assert len(select_daily(candidates, [], profile, config.recommendation, 6)) == 4
    config.recommendation.source_limits = {}
    config.recommendation.interest_slots = 1
    config.recommendation.explore_slots = 0
    config.recommendation.fill_with_interest = False
    assert len(select_daily(candidates, [], profile, config.recommendation, 6)) == 1


def test_configurable_explore_only_and_custom_topic(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    config.recommendation.interest_slots = 0
    config.recommendation.min_interest_for_explore = 0
    config.recommendation.fill_with_interest = False
    config.recommendation.explore_include_topics = ['protein folding molecular biology']
    candidate = paper('Protein folding molecular biology', 'openalex', popularity=1)
    assert select_daily([candidate], [], profile, config.recommendation) == [candidate]


def test_negative_quota_rejected(config):
    profile = InterestProfile([corpus()], config.recommendation, NOW)
    config.recommendation.explore_slots = -1
    with pytest.raises(ValueError, match='nonnegative integers'):
        select_daily([], [], profile, config.recommendation)

from .base import register_reranker
from ..recommendation import InterestProfile


@register_reranker("bm25")
class BM25Reranker:
    def __init__(self, config):
        self.config = config

    def rerank(self, candidates, corpus):
        profile = InterestProfile(corpus, self.config.recommendation)
        for paper in candidates:
            paper.score = profile.score(paper)
        return sorted(candidates, key=lambda p: p.score, reverse=True)

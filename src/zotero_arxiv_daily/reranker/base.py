from abc import ABC, abstractmethod
from omegaconf import DictConfig
from ..protocol import Paper, CorpusPaper
import numpy as np
from typing import Type
class BaseReranker(ABC):
    def __init__(self, config:DictConfig):
        self.config = config

    def rerank(self, candidates:list[Paper], corpus:list[CorpusPaper]) -> list[Paper]:
        corpus = sorted(corpus,key=lambda x: x.added_date,reverse=True)
        time_decay_weight = 1 / (1 + np.log10(np.arange(len(corpus)) + 1))
        time_decay_weight: np.ndarray = time_decay_weight / time_decay_weight.sum()
        sim = self.get_similarity_score([c.abstract for c in candidates], [c.abstract for c in corpus])
        assert sim.shape == (len(candidates), len(corpus))
        scores = (sim * time_decay_weight).sum(axis=1) * 10 # [n_candidate]
        for s,c in zip(scores,candidates):
            c.score = s
        candidates = sorted(candidates,key=lambda x: x.score,reverse=True)
        return candidates

    def score_mainline(self, candidates, profile):
        """Score both pools in one embedding call; anchors never age or dilute.

        Max over anchors allows any fixed research strand to qualify. Recent
        reading has a separately normalized budget, independent of its size.
        """
        if not candidates:
            return {}, {}
        anchors, recent = profile.anchors, profile.recent.corpus
        text = lambda p: f'{p.title}\n{p.abstract}'.strip()
        sim = np.asarray(self.get_similarity_score([text(p) for p in candidates],
                                                  [text(p) for p in [*anchors, *recent]]))
        if sim.shape != (len(candidates), len(anchors) + len(recent)) or not np.isfinite(sim).all():
            raise ValueError('Invalid mainline embedding similarity matrix')
        anchor_scores = np.clip(sim[:, :len(anchors)].max(axis=1), 0, 1) * 10
        scores = anchor_scores.copy()
        if recent:
            weights = 1 / (1 + np.log10(np.arange(len(recent)) + 1))
            recent_scores = (sim[:, len(anchors):] * (weights / weights.sum())).sum(axis=1) * 10
            scores = profile.weight * anchor_scores + (1 - profile.weight) * recent_scores
        return ({id(p): float(s) for p, s in zip(candidates, scores)},
                {id(p): float(s) for p, s in zip(candidates, anchor_scores)})
    
    @abstractmethod
    def get_similarity_score(self, s1:list[str], s2:list[str]) -> np.ndarray:
        raise NotImplementedError

registered_rerankers = {}

def register_reranker(name:str):
    def decorator(cls):
        registered_rerankers[name] = cls
        return cls
    return decorator

def get_reranker_cls(name:str) -> Type[BaseReranker]:
    if name not in registered_rerankers:
        raise ValueError(f"Reranker {name} not found")
    return registered_rerankers[name]

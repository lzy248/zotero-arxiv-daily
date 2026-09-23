"""Independent discovery adapters; each exposes retrieve(profile, config)."""
from loguru import logger
from omegaconf import OmegaConf
from . import semantic_scholar, huggingface, openalex


def discover(profile, config):
    papers = []
    for name, retrieve in [("semantic_scholar", semantic_scholar.retrieve),
                           ("huggingface", huggingface.retrieve), ("openalex", openalex.retrieve)]:
        source_config = OmegaConf.merge({'http': config.get('http', {})}, config[name])
        if source_config.enabled:
            try:
                result = retrieve(profile, source_config)
                papers.extend(result)
                logger.info("Discovery {}: {} candidates", name, len(result))
            except Exception as exc:
                logger.warning("Discovery {} skipped ({})", name, type(exc).__name__)
    return papers

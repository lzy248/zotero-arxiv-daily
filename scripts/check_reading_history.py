"""Read-only cloud compatibility check. Prints counts, never titles, keys or file paths."""
from pathlib import Path
from omegaconf import OmegaConf
from zotero_arxiv_daily.executor import Executor
from zotero_arxiv_daily.recency import recent_corpus


def main():
    root = Path(__file__).resolve().parents[1]
    config = OmegaConf.merge(OmegaConf.load(root / 'config/base.yaml'), OmegaConf.load(root / 'config/custom.yaml'))
    config.recommendation.recency_basis = 'read'
    executor = Executor.__new__(Executor)
    executor.config = config
    library = executor.fetch_zotero_corpus()
    read = recent_corpus(library, config.recommendation)
    print(f'Cloud bibliographic items: {len(library)}; items with synced reading timestamps: {len(read)}')
    if not read:
        raise SystemExit('No synced reading timestamps. Sync Zotero reading history before expecting recent-read recommendations.')
    print('Reading history available through the cloud API. No email sent; no Zotero writes.')


if __name__ == '__main__':
    main()

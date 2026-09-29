"""Generate a reviewable public-paper note artifact without accessing Zotero or SMTP."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from omegaconf import OmegaConf
from openai import OpenAI
import requests

from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.reading_notes import generate_reading_notes
from zotero_arxiv_daily.construct_email import render_email


class CitationMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name', '').startswith('citation_'):
            self.values.setdefault(attrs['name'], []).append(attrs.get('content', ''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arxiv-id', required=True)
    parser.add_argument('--output-dir', default='outputs/reading-notes-preview')
    parser.add_argument('--default-notes', action='store_true', help='Use repository note defaults, ignoring deployed note overrides')
    args = parser.parse_args()
    if not re.fullmatch(r'\d{4}\.\d{4,5}(?:v\d+)?', args.arxiv_id):
        parser.error('Expected a modern arXiv ID, optionally with version')
    root = Path(__file__).resolve().parents[1]
    base = OmegaConf.load(root / 'config/base.yaml')
    config = OmegaConf.merge(base, OmegaConf.load(root / 'config/custom.yaml'))
    if args.default_notes:
        config.llm.reading_notes = base.llm.reading_notes
    config.llm.reading_notes.enabled = True
    url = f'https://arxiv.org/abs/{args.arxiv_id}'
    response = requests.get(url, timeout=(10, 30))
    response.raise_for_status()
    metadata = CitationMetadata()
    metadata.feed(response.content.decode('utf-8'))
    values = metadata.values
    paper = Paper(source='arxiv', title=values.get('citation_title', [f'arXiv {args.arxiv_id}'])[0],
                  authors=values.get('citation_author', []), abstract='', url=url,
                  pdf_url=f'https://arxiv.org/pdf/{args.arxiv_id}', arxiv_id=args.arxiv_id)
    client = OpenAI(api_key=config.llm.api.key, base_url=config.llm.api.base_url,
                    timeout=config.llm.api.get('timeout', 180), max_retries=config.llm.api.get('max_retries', 2))
    generate_reading_notes(paper, client, config.llm, config.llm.reading_notes)
    if not paper.reading_notes:
        raise RuntimeError(paper.reading_notes_status)
    paper.generate_tldr(client, config.llm)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'notes.html').write_text(render_email([paper], max_width=config.email.get('max_width', 1120)), encoding='utf-8')
    result = {'title': paper.title, 'url': paper.url, 'basis': paper.reading_notes_basis,
              'tldr': paper.tldr, 'notes': paper.reading_notes, 'visuals': paper.reading_notes_visuals}
    (output / 'notes.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Generated one paper preview; no email sent.')
    print('Coverage:', paper.reading_notes_basis)
    print('Section lengths:', {key: len(value) for key, value in paper.reading_notes.items()})
    print('Visual rows/steps:', {key: len(value) for key, value in paper.reading_notes_visuals.items()})


if __name__ == '__main__':
    main()

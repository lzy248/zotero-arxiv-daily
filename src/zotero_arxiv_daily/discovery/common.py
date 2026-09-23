from datetime import datetime
import time
import requests
from loguru import logger


def request_json(method, url, config=None, **kwargs):
    """Bounded configurable retries; never log credential-bearing URLs or bodies."""
    settings = (config or {}).get('http', {})
    attempts = settings.get('attempts', 3)
    read_timeout = settings.get('read_timeout', 30)
    max_delay = settings.get('max_retry_delay', 30)
    if not 1 <= attempts <= 10 or read_timeout <= 0 or max_delay <= 0:
        raise ValueError('Invalid HTTP retry configuration')
    for attempt in range(attempts):
        try:
            response = requests.request(method, url, timeout=(10, read_timeout), **kwargs)
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise RuntimeError(f'Discovery API rejected request (HTTP {response.status_code})')
            if response.status_code in (408, 429) or response.status_code >= 500:
                if attempt < attempts - 1:
                    delay = response.headers.get("Retry-After", "")
                    logger.warning('Discovery HTTP {}; retry {}/{}', response.status_code, attempt + 1, attempts - 1)
                    time.sleep(min(max_delay, max(1, float(delay))) if delay.isdigit() else min(max_delay, 2 ** attempt))
                    continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == attempts - 1:
                raise RuntimeError("Discovery API unavailable after bounded retries") from None
            time.sleep(min(max_delay, 2 ** attempt))
    raise RuntimeError("Discovery API returned no result")


def parse_date(value):
    try:
        return datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def convert_rows(rows, convert):
    papers = []
    for rank, row in enumerate(rows):
        try:
            paper = convert(row, rank)
            if paper and paper.title and paper.url:
                papers.append(paper)
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.warning("Skipping malformed discovery record")
    return papers

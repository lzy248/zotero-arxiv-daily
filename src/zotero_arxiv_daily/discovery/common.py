from datetime import datetime
import time
import requests
from loguru import logger


def request_json(method, url, **kwargs):
    """At most three attempts; never log URLs/exception bodies containing API keys."""
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=(10, 30), **kwargs)
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise RuntimeError(f'Discovery API rejected request (HTTP {response.status_code})')
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    delay = response.headers.get("Retry-After", "")
                    time.sleep(min(30, max(1, float(delay))) if delay.isdigit() else 2 ** attempt)
                    continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 2:
                raise RuntimeError("Discovery API unavailable after bounded retries") from None
            time.sleep(2 ** attempt)
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

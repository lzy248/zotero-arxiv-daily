"""Recent-interest timestamps; never substitute metadata edits for actual reading."""
from datetime import datetime, timezone


def reading_dates(attachments):
    """Aggregate synced attachment lastRead (Unix seconds) to parent papers."""
    dates = {}
    for item in attachments:
        data = item.get('data', {})
        parent, timestamp = data.get('parentItem'), data.get('lastRead')
        if data.get('itemType') != 'attachment' or not parent:
            continue
        if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp <= 0:
            continue
        try:
            value = datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError):
            continue
        dates[parent] = max(dates.get(parent, value), value)
    return dates


def interest_date(paper, config):
    basis = config.get('recency_basis', 'added')
    if basis not in ('added', 'read'):
        raise ValueError('recommendation.recency_basis must be added or read')
    return paper.last_read_date if basis == 'read' else paper.added_date


def recent_corpus(corpus, config):
    if config.get('recency_basis', 'added') not in ('added', 'read'):
        raise ValueError('recommendation.recency_basis must be added or read')
    dated = [(paper, interest_date(paper, config)) for paper in corpus]
    return [paper for paper, date in sorted(
        [(paper, date.astimezone(timezone.utc).replace(tzinfo=None) if date.tzinfo else date)
         for paper, date in dated if date is not None], key=lambda entry: entry[1], reverse=True)]

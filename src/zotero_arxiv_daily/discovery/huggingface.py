from ..protocol import Paper
from ..recommendation import normalize_arxiv
from .common import request_json, parse_date, convert_rows


def retrieve(profile, config):
    params = {"sort": "trending", "limit": config.limit}
    if config.period == "weekly":
        year, week, _ = profile.now.isocalendar()
        params["week"] = f"{year}-W{week:02}"
    elif config.period == "monthly":
        params["month"] = profile.now.strftime("%Y-%m")
    elif config.period != "daily":
        raise ValueError("huggingface.period must be daily, weekly or monthly")
    data = request_json("GET", "https://huggingface.co/api/daily_papers", params=params)

    def convert(row, rank):
        paper = row["paper"]
        votes = paper.get("upvotes", 0) or 0
        if votes < config.min_upvotes:
            return None
        arxiv_id = normalize_arxiv(paper["id"])
        if not arxiv_id:
            return None
        return Paper(source="huggingface", title=paper["title"],
                     abstract=paper.get("summary") or "",
                     authors=[a["name"] for a in paper.get("authors", [])],
                     url=f"https://huggingface.co/papers/{arxiv_id}",
                     pdf_url=f"https://arxiv.org/pdf/{arxiv_id}", arxiv_id=arxiv_id,
                     published_date=parse_date(paper.get("publishedAt")),
                     source_rank=rank, popularity=1 / (rank + 1),
                     recommendation_reason=f"Hugging Face {config.period} trending; {votes} upvotes")
    return convert_rows(data[:config.limit], convert)

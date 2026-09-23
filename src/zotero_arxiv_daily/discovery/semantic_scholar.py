from ..protocol import Paper
from ..recommendation import normalize_arxiv, normalize_doi
from .common import request_json, parse_date, convert_rows


def retrieve(profile, config):
    seeds = profile.seeds(config.seed_limit)
    identifiers = []
    seed_by_id = {}
    for seed in seeds:
        identifier = seed.semantic_scholar_id
        if not identifier and normalize_doi(seed.doi):
            identifier = "DOI:" + normalize_doi(seed.doi)
        if not identifier and normalize_arxiv(seed.arxiv_id):
            identifier = "ARXIV:" + normalize_arxiv(seed.arxiv_id)
        if identifier and identifier not in identifiers:
            identifiers.append(identifier)
            seed_by_id[identifier] = seed
    if not identifiers:
        return []
    headers = {"x-api-key": config.api_key} if config.api_key else {}
    # Resolve external IDs in one batch. Unresolvable seeds return null.
    resolved = request_json("POST", "https://api.semanticscholar.org/graph/v1/paper/batch",
                            config=config, params={"fields": "paperId"}, json={"ids": identifiers}, headers=headers)
    for identifier, result in zip(identifiers, resolved):
        if result and result.get('paperId'):
            seed_by_id[identifier].semantic_scholar_id = result['paperId']
    ids = list(dict.fromkeys(p["paperId"] for p in resolved if p and p.get("paperId")))
    if not ids:
        return []
    data = request_json("POST", "https://api.semanticscholar.org/recommendations/v1/papers/",
                        config=config, params={"limit": config.limit, "fields":
                                "paperId,title,abstract,authors,url,externalIds,citationCount,publicationDate,openAccessPdf"},
                        json={"positivePaperIds": ids, "negativePaperIds": []}, headers=headers)

    def convert(row, rank):
        external = row.get("externalIds") or {}
        return Paper(source="semantic_scholar", title=row["title"],
                     abstract=row.get("abstract") or "",
                     authors=[a["name"] for a in row.get("authors", [])],
                     url=row.get("url") or f"https://www.semanticscholar.org/paper/{row['paperId']}",
                     pdf_url=(row.get("openAccessPdf") or {}).get("url"),
                     doi=external.get("DOI"), arxiv_id=external.get("ArXiv"),
                     semantic_scholar_id=row["paperId"],
                     citation_count=max(0, row.get("citationCount") or 0),
                     published_date=parse_date(row.get("publicationDate")), source_rank=rank)
    return convert_rows(data.get("recommendedPapers", []), convert)

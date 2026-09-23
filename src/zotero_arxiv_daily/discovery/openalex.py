from datetime import timedelta
import math
from ..protocol import Paper
from .common import request_json, parse_date, convert_rows


def retrieve(profile, config):
    fields = list(config.fields)
    if not fields:
        return []
    # Count OpenAlex days rather than calendar days so even-length lists rotate too.
    field = str(fields[(profile.now.toordinal() // 2) % len(fields)])
    start = (profile.now - timedelta(days=config.lookback_days)).date().isoformat()
    end = profile.now.date().isoformat()
    params = {"filter": f"from_publication_date:{start},to_publication_date:{end},"
                        f"primary_topic.field.id:{field},is_retracted:false,cited_by_count:>{config.min_citations - 1}",
              "sort": "cited_by_count:desc", "per_page": config.limit}
    if config.api_key:
        params["api_key"] = config.api_key
    data = request_json("GET", "https://api.openalex.org/works", params=params, config=config)

    def convert(row, rank):
        citations = row.get("cited_by_count") or 0
        published = parse_date(row.get("publication_date"))
        if row.get("is_retracted") or citations < config.min_citations or not published:
            return None
        age = (profile.now.date() - published.date()).days
        if not 0 <= age <= config.lookback_days:
            return None
        inverted = row.get("abstract_inverted_index") or {}
        positions = [(pos, word) for word, indexes in inverted.items() for pos in indexes]
        abstract = " ".join(word for _, word in sorted(positions))
        location = row.get("best_oa_location") or row.get("primary_location") or {}
        topic = row.get("primary_topic") or {}
        field_name = (topic.get("field") or {}).get("display_name", field)
        return Paper(source="openalex", title=row.get("title") or row.get("display_name"),
                     abstract=abstract,
                     authors=[a["author"]["display_name"] for a in row.get("authorships", [])],
                     url=row.get("doi") or location.get("landing_page_url") or row["id"],
                     pdf_url=location.get("pdf_url"), doi=row.get("doi"),
                     published_date=published, citation_count=citations, source_rank=rank,
                     popularity=math.log1p(citations) / math.sqrt(max(30, age)),
                     recommendation_reason=f"OpenAlex / {field_name}: {citations} citations in {age} days")
    return convert_rows(data.get("results", []), convert)

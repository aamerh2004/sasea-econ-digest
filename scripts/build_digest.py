"""Build a single day's digest JSON from fetched + filtered + scored entries."""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from fetch_feeds import fetch_all  # noqa: E402
from filter_and_score import filter_and_score, load_keywords  # noqa: E402

TOP_HEADLINE_COUNT = 7
MAX_PER_COUNTRY_IN_TOP = 2
COUNTRY_ORDER = [
    "Bangladesh",
    "Pakistan",
    "Afghanistan",
    "Nepal",
    "Bhutan",
    "Maldives",
    "Philippines",
]


def build_digest(date_str=None, quiet=False):
    if date_str is None:
        date_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")

    entries, fetch_stats = fetch_all(quiet=quiet)
    keywords = load_keywords()
    ranked = filter_and_score(entries, keywords)

    # Pick top headlines like a front-page editor would: highest score first,
    # but capped per-country so one heavily-covered country (or one very
    # active local feed) can't crowd out the rest of the region.
    top_headlines = []
    per_country_count = {}
    for a in ranked:
        if len(top_headlines) >= TOP_HEADLINE_COUNT:
            break
        if any(per_country_count.get(c, 0) >= MAX_PER_COUNTRY_IN_TOP for c in a["countries"]):
            continue
        top_headlines.append(
            {
                "title": a["title"],
                "link": a["link"],
                "source_name": a["source_name"],
                "countries": a["countries"],
            }
        )
        for c in a["countries"]:
            per_country_count[c] = per_country_count.get(c, 0) + 1

    # `ranked` is already ordered by the blended relevance+recency score, so
    # country lists lead with important recent reporting rather than with
    # whatever happened to publish most recently.
    by_country = {c: [] for c in COUNTRY_ORDER}
    for a in ranked:
        for c in a["countries"]:
            if c in by_country:
                by_country[c].append(
                    {
                        "title": a["title"],
                        "link": a["link"],
                        "source_name": a["source_name"],
                        "source_type": a["source_type"],
                        "published": a["published"],
                        "preview": a["preview"],
                    }
                )

    digest = {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_headlines": top_headlines,
        "by_country": by_country,
        "article_count": len(ranked),
        "feed_stats": [{"source_id": s, "status": st, "count": c} for s, st, c in fetch_stats],
    }
    return digest


def save_digest(digest, out_dir="data/digests"):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{digest['date']}.json")
    with open(path, "w") as f:
        json.dump(digest, f, indent=2, ensure_ascii=False)
    return path


if __name__ == "__main__":
    d = build_digest()
    p = save_digest(d)
    print(f"wrote {p} ({d['article_count']} articles, {len(d['top_headlines'])} top headlines)", file=sys.stderr)

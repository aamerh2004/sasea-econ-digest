"""Fetch every RSS feed in sources.yaml and return normalized entries."""
import sys
import time
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import requests
import yaml

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SASEADigest/1.0; +https://github.com)"
}
TIMEOUT = 15


def load_sources(path="sources.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)["sources"]


def _entry_published(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            return datetime.fromtimestamp(timegm(val), tz=timezone.utc)
    return None


def fetch_all(sources=None, quiet=False):
    """Returns (entries, stats). entries is a flat list of dicts."""
    if sources is None:
        sources = load_sources()

    entries = []
    stats = []
    for src in sources:
        try:
            resp = requests.get(src["url"], headers=HEADERS, timeout=TIMEOUT)
            parsed = feedparser.parse(resp.content)
            count = 0
            for e in parsed.entries:
                published = _entry_published(e)
                entries.append(
                    {
                        "source_id": src["id"],
                        "source_name": src["name"],
                        "source_type": src["type"],
                        "source_tier": src.get("tier", 1),
                        "require_topic": src.get("require_topic", True),
                        "title": (e.get("title") or "").strip(),
                        "link": (e.get("link") or "").strip(),
                        "summary": (e.get("summary") or e.get("description") or "").strip(),
                        "published": published.isoformat() if published else None,
                        "published_ts": published.timestamp() if published else 0,
                    }
                )
                count += 1
            stats.append((src["id"], "ok", count))
        except Exception as exc:  # noqa: BLE001 - a single bad feed must not kill the run
            stats.append((src["id"], f"error: {type(exc).__name__}: {exc}", 0))

    if not quiet:
        for sid, status, count in stats:
            print(f"  {sid:25s} {status if status != 'ok' else f'{count} entries'}", file=sys.stderr)
        ok = sum(1 for _, s, _ in stats if s == "ok")
        print(f"fetch_feeds: {ok}/{len(stats)} feeds ok, {len(entries)} total entries", file=sys.stderr)

    return entries, stats


if __name__ == "__main__":
    fetch_all()

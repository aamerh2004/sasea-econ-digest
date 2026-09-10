"""Filter fetched entries down to ones relevant to our countries/topics,
de-dupe near-identical stories, and score them for ranking."""
import re
import time
import warnings
from urllib.parse import urlsplit, urlunsplit

import yaml
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

NO_USABLE_SUMMARY_FEEDS = {"adb-news"}


def load_keywords(path="keywords.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def clean_text(html):
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def preview(html, max_len=220):
    text = clean_text(html)
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def normalize_link(link):
    parts = urlsplit(link)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def normalize_title(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def find_countries(text, countries):
    text_l = text.lower()
    hits = []
    for country, variants in countries.items():
        if any(re.search(rf"\b{re.escape(v)}\b", text_l) for v in variants):
            hits.append(country)
    return hits


def find_topics(text, topics):
    text_l = text.lower()
    return [t for t in topics if t in text_l]


def filter_and_score(entries, keywords=None):
    if keywords is None:
        keywords = load_keywords()

    countries = keywords["countries"]
    topics = keywords["topics"]
    local_feed_countries = keywords.get("local_feed_countries", {})

    scored = []
    for e in entries:
        title = clean_text(e["title"])
        text = f"{title} {clean_text(e['summary'])}"

        if e["source_id"] in local_feed_countries:
            country_hits = [local_feed_countries[e["source_id"]]]
            country_hits += [c for c in find_countries(text, countries) if c not in country_hits]
        else:
            country_hits = find_countries(text, countries)

        if not country_hits:
            continue

        topic_hits = find_topics(text, topics)
        if not topic_hits:
            continue

        # Cap the country-count bonus so a press release namechecking every
        # country in the region doesn't automatically outrank a specific,
        # single-country news story.
        age_hours = (time.time() - e["published_ts"]) / 3600 if e.get("published_ts") else None
        if age_hours is None:
            recency_bonus = 0
        elif age_hours <= 12:
            recency_bonus = 6
        elif age_hours <= 24:
            recency_bonus = 3
        elif age_hours <= 48:
            recency_bonus = 1
        else:
            recency_bonus = 0

        score = (
            e.get("source_tier", 1) * 10
            + len(topic_hits) * 3
            + min(len(country_hits), 2) * 2
            + recency_bonus
        )

        if e["source_id"] in NO_USABLE_SUMMARY_FEEDS:
            # These feeds' <description> is a mangled HTML/metadata dump,
            # not a real excerpt, so don't try to show it at all.
            article_preview = ""
        else:
            article_preview = preview(e["summary"])
            if article_preview.strip(".…").strip().lower() == title.strip(".…").strip().lower():
                article_preview = ""

        scored.append(
            {
                **e,
                "title": title,
                "countries": country_hits,
                "topic_hits": topic_hits,
                "preview": article_preview,
                "score": score,
            }
        )

    # de-dupe by normalized link, then by normalized title (keep highest score)
    by_link = {}
    for item in scored:
        key = normalize_link(item["link"]) or normalize_title(item["title"])
        existing = by_link.get(key)
        if existing is None or item["score"] > existing["score"]:
            by_link[key] = item

    deduped = list(by_link.values())

    by_title = {}
    for item in sorted(deduped, key=lambda x: -x["score"]):
        key = normalize_title(item["title"])
        if key and key not in by_title:
            by_title[key] = item
    deduped = list(by_title.values())

    deduped.sort(key=lambda x: (-x["score"], -(x["published_ts"] or 0)))
    return deduped

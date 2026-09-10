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

# Several feeds (ADB, The Economist's section feeds) serve long archives
# rather than just recent items, so undated or old stories would otherwise
# be presented as today's news. This is a daily digest: anything outside the
# window is not news, and an item with no date can't be verified as recent.
MAX_ARTICLE_AGE_DAYS = 3

# How much a brand-new story is worth relative to relevance. Tuned so that
# recency breaks ties between comparable stories without letting a marginal
# fresh item leap over genuinely important reporting from a day or two ago.
RECENCY_WEIGHT = 25

# Formats that are never useful in an economics digest, regardless of source.
EXCLUDED_TITLE_PATTERNS = [
    "in pictures", "photo essay", "photos:", "in photos", "quiz", "crossword",
    "obituary", "newsletter", "podcast", "your briefing", "week in review",
    "recipe", "what to watch", "best of", "cartoon",
    # Afghan broadcasters publish TV programme listings into the same feeds.
    "6pm news", "8pm news", "farakhabar", "tahawol", "goftaman", "saar:",
    "news bulletin",
]

# Country-specific outlets carry a lot of foreign wire copy. If a story on
# such a feed centers on one of these places and never mentions the outlet's
# own country, it isn't regional news and shouldn't be filed under it.
FOREIGN_FOCUS_MARKERS = [
    "india", "indian", "mumbai", "delhi", "rbi", "reserve bank of india", "sensex", "nifty",
    "china", "chinese", "beijing", "shanghai",
    "european central bank", "ecb", "eurozone", "europe", "german", "france", "britain", "uk ",
    "wall street", "federal reserve", "u.s. stocks", "washington", "new york",
    "japan", "tokyo", "korea", "singapore", "vietnam", "indonesia", "thailand", "malaysia",
    "canada", "mexico", "brazil", "australia", "africa",
    "saudi", "houthi", "yemen", "israel", "gaza", "lebanon",
    "russia", "ukraine", "moscow",
    "republicans", "democrats", "midterm", "white house",
]


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
    topic_exempt_countries = set(keywords.get("topic_exempt_countries", []))

    cutoff_ts = time.time() - (MAX_ARTICLE_AGE_DAYS * 86400)

    scored = []
    for e in entries:
        if not e.get("published_ts") or e["published_ts"] < cutoff_ts:
            continue

        title = clean_text(e["title"])
        title_l = title.lower()
        if any(p in title_l for p in EXCLUDED_TITLE_PATTERNS):
            continue

        text = f"{title} {clean_text(e['summary'])}"

        if e["source_id"] in local_feed_countries:
            own_country = local_feed_countries[e["source_id"]]
            explicit_hits = find_countries(text, countries)
            text_l = text.lower()
            is_foreign_wire = own_country not in explicit_hits and any(
                m in text_l for m in FOREIGN_FOCUS_MARKERS
            )
            if is_foreign_wire:
                country_hits = [c for c in explicit_hits if c != own_country]
            else:
                country_hits = [own_country] + [c for c in explicit_hits if c != own_country]
        else:
            country_hits = find_countries(text, countries)

        if not country_hits:
            continue

        topic_hits = find_topics(text, topics)
        topic_waived = False
        if not topic_hits:
            # Major global papers cover these countries rarely enough that
            # anything they run is worth surfacing, and some countries are
            # covered in aid/sanctions terms the topic list doesn't catch.
            topic_waived = not e.get("require_topic", True) or any(
                c in topic_exempt_countries for c in country_hits
            )
            if not topic_waived:
                continue

        # Cap the country-count bonus so a press release namechecking every
        # country in the region doesn't automatically outrank a specific,
        # single-country news story.
        # Relevance and recency are blended into one score rather than being
        # applied in sequence, so a strongly relevant story from two days ago
        # still outranks a marginal one from this morning, while stories of
        # similar relevance read newest-first.
        relevance = (
            e.get("source_tier", 1) * 10
            + len(topic_hits) * 3
            + min(len(country_hits), 2) * 2
        )
        age_hours = (time.time() - e["published_ts"]) / 3600
        window_hours = MAX_ARTICLE_AGE_DAYS * 24
        recency_points = max(0.0, 1.0 - age_hours / window_hours) * RECENCY_WEIGHT

        score = relevance + recency_points
        # Stories that matched no economics term are carried for completeness
        # but must not outrank actual finance reporting in the headlines.
        if topic_waived:
            score -= 20

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

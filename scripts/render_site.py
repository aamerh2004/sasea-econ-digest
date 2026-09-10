"""Render docs/ (the GitHub Pages site) from data/digests/*.json + templates/."""
import glob
import json
import os
import shutil
import sys
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, "templates")
STATIC_DIR = os.path.join(ROOT, "static")
DIGESTS_DIR = os.path.join(ROOT, "data", "digests")
BRIEFS_DIR = os.path.join(ROOT, "data", "briefs")
DOCS_DIR = os.path.join(ROOT, "docs")

FORMSPREE_ENDPOINT_FILE = os.path.join(ROOT, "data", "formspree_endpoint.txt")


def load_all_digests():
    digests = []
    for path in sorted(glob.glob(os.path.join(DIGESTS_DIR, "*.json"))):
        with open(path) as f:
            digests.append(json.load(f))
    digests.sort(key=lambda d: d["date"], reverse=True)
    return digests


def today_label(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d, %Y")


def load_brief(date_str):
    """The AI brief is optional — the site renders fine without one."""
    path = os.path.join(BRIEFS_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def formspree_endpoint():
    if os.path.exists(FORMSPREE_ENDPOINT_FILE):
        val = open(FORMSPREE_ENDPOINT_FILE).read().strip()
        if val:
            return val
    return "#"


def render_site():
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)
    digests = load_all_digests()

    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "archive"), exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "static"), exist_ok=True)
    shutil.copy(os.path.join(STATIC_DIR, "style.css"), os.path.join(DOCS_DIR, "static", "style.css"))

    endpoint = formspree_endpoint()

    if digests:
        latest = digests[0]
        html = env.get_template("index.html").render(
            digest=latest,
            brief=load_brief(latest["date"]),
            today_label=today_label(latest["date"]),
            root_prefix="",
            static_prefix="",
        )
        with open(os.path.join(DOCS_DIR, "index.html"), "w") as f:
            f.write(html)

    for d in digests:
        html = env.get_template("day.html").render(
            digest=d,
            brief=load_brief(d["date"]),
            today_label=today_label(d["date"]),
            root_prefix="../",
            static_prefix="../",
        )
        with open(os.path.join(DOCS_DIR, "archive", f"{d['date']}.html"), "w") as f:
            f.write(html)

    archive_html = env.get_template("archive.html").render(
        dates=[d["date"] for d in digests],
        today_label=today_label(digests[0]["date"]) if digests else "",
        root_prefix="../",
        static_prefix="../",
    )
    with open(os.path.join(DOCS_DIR, "archive", "index.html"), "w") as f:
        f.write(archive_html)

    subscribe_html = env.get_template("subscribe.html").render(
        formspree_endpoint=endpoint,
        today_label=today_label(digests[0]["date"]) if digests else "",
        root_prefix="",
        static_prefix="",
    )
    with open(os.path.join(DOCS_DIR, "subscribe.html"), "w") as f:
        f.write(subscribe_html)

    with open(os.path.join(DOCS_DIR, ".nojekyll"), "w") as f:
        f.write("")

    print(f"render_site: wrote {len(digests)} day page(s) + index/archive/subscribe to {DOCS_DIR}", file=sys.stderr)


if __name__ == "__main__":
    render_site()

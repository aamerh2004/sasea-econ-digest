"""Render the digest as an email and send it via Resend to every subscriber."""
import argparse
import json
import os
import sys

import requests
from jinja2 import Environment

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBSCRIBERS_FILE = os.path.join(ROOT, "data", "subscribers.json")
RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = os.environ.get("DIGEST_FROM_ADDRESS", "South & Southeast Asia Digest <onboarding@resend.dev>")

EMAIL_TEMPLATE = """
<div style="font-family:Georgia,serif;max-width:640px;margin:0 auto;color:#121212;">
  <div style="border-bottom:3px solid #121212;padding-bottom:12px;margin-bottom:20px;">
    <div style="font-family:Arial,sans-serif;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#4a4a4a;">{{ today_label }}</div>
    <div style="font-size:26px;font-weight:700;margin-top:6px;">South &amp; Southeast Asia Economic Digest</div>
  </div>

  {% if digest.top_headlines %}
  <div style="background:#fafaf8;border:1px solid #d9d9d9;border-left:4px solid #a91f2c;padding:16px 18px;margin-bottom:24px;">
    <div style="font-family:Arial,sans-serif;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#a91f2c;margin-bottom:10px;">Today's Top Developments</div>
    {% for h in digest.top_headlines %}
    <div style="padding:8px 0;border-bottom:1px solid #d9d9d9;">
      <a href="{{ h.link }}" style="font-weight:700;font-size:16px;color:#121212;text-decoration:none;">{{ h.title }}</a>
      <div style="font-family:Arial,sans-serif;font-size:11px;color:#4a4a4a;margin-top:2px;">{{ h.source_name }}{% if h.countries %} &middot; {{ h.countries|join(', ') }}{% endif %}</div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% for country, articles in digest.by_country.items() if articles %}
  <div style="margin-bottom:26px;">
    <div style="font-size:19px;font-weight:700;border-bottom:2px solid #121212;padding-bottom:6px;margin-bottom:12px;">{{ country }}</div>
    {% for a in articles %}
    <div style="padding:10px 0;border-top:1px solid #d9d9d9;">
      <div style="font-family:Arial,sans-serif;font-size:10px;font-weight:700;text-transform:uppercase;color:#a91f2c;">{{ a.source_name }}</div>
      <a href="{{ a.link }}" style="font-size:15px;font-weight:700;color:#121212;text-decoration:none;display:block;margin:4px 0;">{{ a.title }}</a>
      {% if a.preview %}<div style="font-size:13px;color:#4a4a4a;">{{ a.preview }}</div>{% endif %}
    </div>
    {% endfor %}
  </div>
  {% endfor %}

  <div style="font-family:Arial,sans-serif;font-size:11px;color:#999;border-top:1px solid #d9d9d9;padding-top:14px;">
    Compiled automatically from public RSS feeds. <a href="{{ site_url }}">View on the web</a>.
  </div>
</div>
"""


def render_email_html(digest, today_label, site_url):
    env = Environment(autoescape=True)
    template = env.from_string(EMAIL_TEMPLATE)
    return template.render(digest=digest, today_label=today_label, site_url=site_url)


def load_subscribers():
    """Subscribers come from the SUBSCRIBERS env var (comma-separated) so real
    addresses stay out of the public repo; the local file is a dev fallback."""
    env_value = os.environ.get("SUBSCRIBERS", "").strip()
    if env_value:
        return [addr.strip() for addr in env_value.split(",") if addr.strip()]
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    with open(SUBSCRIBERS_FILE) as f:
        return json.load(f).get("subscribers", [])


def send_email(to_address, subject, html, api_key):
    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": FROM_ADDRESS, "to": [to_address], "subject": subject, "html": html},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--digest", required=True, help="Path to a digest JSON file")
    parser.add_argument("--site-url", default="https://example.github.io/sasea-econ-digest/")
    parser.add_argument("--dry-run", action="store_true", help="Print the email instead of sending it")
    args = parser.parse_args()

    with open(args.digest) as f:
        digest = json.load(f)

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from render_site import today_label as fmt_label  # noqa: E402

    label = fmt_label(digest["date"])
    subject = f"South & Southeast Asia Economic Digest — {label}"
    html = render_email_html(digest, label, args.site_url)

    subscribers = load_subscribers()
    if not subscribers:
        print("send_email: no subscribers in data/subscribers.json, nothing to send", file=sys.stderr)
        return

    if args.dry_run:
        print(f"--- DRY RUN: would send to {subscribers} ---")
        print(f"Subject: {subject}")
        print(html)
        return

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("send_email: RESEND_API_KEY is not set; aborting real send", file=sys.stderr)
        sys.exit(1)

    for addr in subscribers:
        result = send_email(addr, subject, html, api_key)
        print(f"sent to {addr}: {result.get('id', result)}", file=sys.stderr)


if __name__ == "__main__":
    main()

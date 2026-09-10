# South & Southeast Asia Economic Digest

A daily-refreshed digest of finance, economics, trade/FX, and development
news for Bangladesh, Pakistan, Afghanistan, Nepal, Bhutan, Maldives, and the
Philippines — pulled from public RSS feeds of major newspapers, international
think tanks, and country-specific outlets. No paywalled content is scraped;
only headlines, publisher-provided summaries, and links back to the source
are used.

## How it works

1. `scripts/fetch_feeds.py` pulls every feed in `sources.yaml`.
2. `scripts/filter_and_score.py` keeps only stories mentioning a target
   country **and** a finance/econ/trade/development term (`keywords.yaml`),
   de-dupes them, and scores them for ranking.
3. `scripts/build_digest.py` writes the day's result to
   `data/digests/YYYY-MM-DD.json` — the permanent archive.
4. `scripts/render_site.py` turns that JSON + `templates/` into the static
   site in `docs/` (what GitHub Pages serves).
5. `scripts/send_email.py` emails the digest to everyone in
   `data/subscribers.json` via [Resend](https://resend.com).
6. `scripts/run_daily.py` runs all of the above in order — this is what both
   GitHub Actions and you, locally, should actually run.

## One-time setup

### 1. Local Python environment

```bash
cd ~/Projects/sasea-econ-digest
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Resend (sends the email)

Resend needs an API key, not a password — you create this yourself:

1. Sign up free at [resend.com](https://resend.com).
2. Create an API key (Dashboard → API Keys).
3. Locally: copy `.env.example` to `.env`, paste the key in, then
   `export $(cat .env | xargs)` before running scripts (or use `direnv`).
4. On GitHub: repo Settings → Secrets and variables → Actions → New repository
   secret → name it `RESEND_API_KEY`.

Without a verified sending domain, Resend sends from `onboarding@resend.dev`
and can only deliver to the email address you signed up with. If you later
want to send to other people, verify a domain in Resend and set
`DIGEST_FROM_ADDRESS`.

### 2b. Subscriber list

This repo is public (required for free GitHub Pages), so real email
addresses are kept **out** of it:

- **On GitHub**: add a repository secret named `SUBSCRIBERS` containing a
  comma-separated list of addresses.
- **Locally**: either `export SUBSCRIBERS="you@example.com"`, or copy
  `data/subscribers.example.json` to `data/subscribers.json` (gitignored).

The env var wins when both are present.

### 3. Formspree (the "Subscribe" form on the site)

The site is static (GitHub Pages), so the subscribe form needs a hosted form
backend rather than server code:

1. Sign up free at [formspree.io](https://formspree.io) and create a form.
2. Put the form's endpoint URL (e.g. `https://formspree.io/f/abcd1234`) into
   `data/formspree_endpoint.txt` (create this file, one line, no trailing
   slash).
3. Re-run `python scripts/render_site.py` to bake it into `docs/subscribe.html`.

New submissions arrive as an email/dashboard notification to you — add the
address to `data/subscribers.json` to actually include them in the daily
send (there's no live database wiring this up automatically, by design,
since GitHub Pages has no backend).

### 4. Push to GitHub and enable Pages

```bash
git add -A
git commit -m "Initial digest site"
gh repo create sasea-econ-digest --private --source=. --push
# or: create an empty repo on GitHub.com, then
#   git remote add origin git@github.com:<you>/sasea-econ-digest.git
#   git push -u origin main
```

Then in the repo on GitHub:
- **Settings → Pages** → Source: "Deploy from a branch" → Branch: `main`,
  folder: `/docs`.
- **Settings → Secrets and variables → Actions** → add `RESEND_API_KEY`
  (step 2 above).
- **Actions** tab → run the "Daily digest" workflow manually once
  (`workflow_dispatch`) to confirm it fetches, renders, emails, and commits
  cleanly before relying on the 6am schedule.

## Running locally

```bash
source venv/bin/activate
python scripts/run_daily.py --dry-run     # build + render, print the email instead of sending
python scripts/run_daily.py --no-email    # build + render, skip email entirely
python scripts/run_daily.py               # the real thing — builds, renders, emails
python -m http.server --directory docs    # preview the site at http://localhost:8000
```

If you never push to GitHub, you can still get daily automation by
scheduling `python scripts/run_daily.py` with `launchd`/`cron` on this Mac —
it just only runs while the machine is on.

## Known limitations

- **DST drift**: GitHub Actions cron is fixed-UTC, so the ~6am ET trigger
  drifts by about an hour around the March/November clock changes.
- **Dropped feeds**: Brookings, PIIE, Carnegie, IMF, World Bank, Wilson
  Center, ORF, Himalayan Times, Kuensel, and The Edition (Maldives) no
  longer publish working public RSS feeds as of setup — they were left out
  rather than included broken. Bhutan and the Maldives are still covered
  when global outlets mention them, just without a dedicated local source.
  Check `sources.yaml` periodically and swap in replacements if you find
  working feeds.
- **Subscription isn't fully self-serve**: see the Formspree note above —
  new sign-ups need a manual one-line add to `data/subscribers.json`.

"""Single entrypoint: build today's digest, render the site, email subscribers."""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_digest import build_digest, save_digest  # noqa: E402
from render_site import render_site  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Build+render, but only print the email instead of sending")
    parser.add_argument("--no-email", action="store_true", help="Build+render but skip the email step entirely")
    parser.add_argument("--site-url", default="https://example.github.io/sasea-econ-digest/")
    args = parser.parse_args()

    digest = build_digest(quiet=False)
    path = save_digest(digest)
    print(f"run_daily: saved {path}", file=sys.stderr)

    render_site()

    if args.no_email:
        print("run_daily: skipping email (--no-email)", file=sys.stderr)
        return

    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "send_email.py"),
        "--digest",
        path,
        "--site-url",
        args.site_url,
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()

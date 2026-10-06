"""Loads the real pages and renders them to HTML."""
from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path

import markdown

# REPELNT_CONTENT points the gateway at a different scenario's pages, so the
# same detector and decoy engine can front any site.
CONTENT_DIR = Path(os.environ.get("REPELNT_CONTENT")
                   or Path(__file__).resolve().parent.parent / "content")
SLUG_RE = re.compile(r"^[a-z0-9-]+$")

DEFAULT_SITE = {
    "name": "Coral Ridge Field Station",
    "footer": "Coastal research, shared openly with people. Not for AI training.",
    # Neutral link labels, so the navigation itself leaks nothing to a scraper.
    "nav": [["/", "Home"], ["/research", "Research"],
            ["/survey", "Survey"], ["/about", "About"]],
}
_cfg = CONTENT_DIR / "site.json"
SITE = json.loads(_cfg.read_text()) if _cfg.exists() else DEFAULT_SITE
NAV = [tuple(pair) for pair in SITE["nav"]]


def load_page(slug: str) -> str | None:
    if not SLUG_RE.match(slug):
        return None
    path = CONTENT_DIR / f"{slug}.md"
    return path.read_text() if path.exists() else None


def title_of(md: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Field notes"


def md_to_html(md: str) -> str:
    return markdown.markdown(md, extensions=["extra"])


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --water: #e6eeee; --ink: #1c2b33; --kelp: #2f6f6b; --slate: #5b707b; --line: #c3d3d2;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--water); color: var(--ink);
    font: 1.075rem/1.7 Charter, "Iowan Old Style", "Bitstream Charter", Georgia, serif;
  }}
  header, main, footer {{ max-width: 40rem; margin: 0 auto; padding: 0 1.25rem; }}
  header {{ padding-top: 2rem; display: flex; flex-wrap: wrap; gap: .25rem 1.25rem; align-items: baseline; }}
  header strong {{ font-size: 1rem; margin-right: auto; }}
  nav a {{ color: var(--slate); text-decoration: none; margin-left: 1rem; }}
  nav a:hover, nav a:focus-visible {{ color: var(--kelp); text-decoration: underline; }}
  main {{ padding-top: 2.5rem; padding-bottom: 3rem; }}
  h1 {{ font-size: 2.1rem; line-height: 1.15; font-weight: 600; margin: 0 0 1.25rem; }}
  h2 {{ font-size: 1.25rem; margin: 2rem 0 .5rem; color: var(--kelp); }}
  table {{ border-collapse: collapse; width: 100%; font-size: .95rem; }}
  th, td {{ text-align: left; padding: .35rem .5rem; border-bottom: 1px solid var(--line); }}
  a {{ color: var(--kelp); }}
  :focus-visible {{ outline: 2px solid var(--kelp); outline-offset: 2px; }}
  footer {{ border-top: 1px solid var(--line); padding: 1rem 1.25rem 2rem; color: var(--slate); font-size: .9rem; }}
</style>
</head>
<body>
<header><strong>{site}</strong><nav>{nav}</nav></header>
<main>{body}</main>
<footer>{footer}
<a href="/trap/archive" rel="nofollow" style="display:none" aria-hidden="true" tabindex="-1">archive</a></footer>
<script>document.cookie = "rp_js=1; path=/; max-age=86400; SameSite=Lax";</script>
</body>
</html>"""


def render_page(md: str) -> str:
    nav = "".join(f'<a href="{href}">{escape(label)}</a>' for href, label in NAV)
    return PAGE.format(title=escape(title_of(md)), nav=nav, body=md_to_html(md),
                       site=escape(SITE["name"]), footer=escape(SITE["footer"]))

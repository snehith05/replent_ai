"""Demo scrapers for Repelnt. Run while the gateway is up:

    python scraper_demo.py            # all four scrapers, two crawl rounds each
    python scraper_demo.py gptbot     # just one

Each scraper crawls the site the way a naive crawler would, following every
link it finds, including the hidden one robots.txt forbids. Scraped text is
saved to scraped/<scraper>/<page>.txt for the Day 3 evaluation.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import httpx

from app.content import load_page, md_to_html  # ground truth, for the demo printout only

BASE = "http://localhost:8000"
CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

SCRAPERS = {
    # Openly identifies as an AI training crawler, ignoring robots.txt.
    "gptbot": {"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; "
                             "compatible; GPTBot/1.1; +https://openai.com/gptbot)"},
    # A quick script with the library's default headers.
    "python_default": {},
    # Fakes a Chrome user-agent but nothing else.
    "spoofed_chrome": {"User-Agent": CHROME_UA},
    # Copies a real browser's headers too. Header checks alone can't catch this
    # one; only its behaviour (following the hidden link) gives it away.
    "browser_mimic": {
        "User-Agent": CHROME_UA.replace("Chrome/128", "Chrome/129"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none",
        "Sec-Fetch-Dest": "document", "Sec-Fetch-User": "?1",
    },
}


def text_of(html: str) -> str:
    m = re.search(r"<main>(.*)</main>", html, re.S)
    body = m.group(1) if m else html
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def slug_for(path: str) -> str:
    return "index" if path == "/" else path.strip("/")


def crawl(client: httpx.Client) -> list[tuple[str, str]]:
    queue, seen, pages = ["/"], set(), []
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        html = client.get(BASE + path).text
        pages.append((path, html))
        for link in re.findall(r'href="(/[^"#]*)"', html):
            if link not in seen:
                queue.append(link)
        time.sleep(0.2)
    return pages


def run(name: str, headers: dict) -> None:
    out_dir = Path("scraped") / name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {name} ===")
    with httpx.Client(headers=headers, timeout=300) as client:
        for round_no in (1, 2):
            results = []
            for path, html in crawl(client):
                if path.startswith("/trap"):
                    results.append(f"{path} (hidden trap link)")
                    continue
                got = text_of(html)
                real_md = load_page(slug_for(path))
                is_real = real_md is not None and got == text_of(f"<main>{md_to_html(real_md)}</main>")
                results.append(f"{path} -> {'REAL' if is_real else 'POISONED'}")
                if round_no == 2:
                    (out_dir / f"{slug_for(path)}.txt").write_text(got)
            print(f"  round {round_no}: " + ", ".join(results))


if __name__ == "__main__":
    chosen = sys.argv[1:] or list(SCRAPERS)
    for name in chosen:
        run(name, SCRAPERS[name])
    print("\nScraped text saved under scraped/. Check the dashboard for the reasons behind each verdict.")

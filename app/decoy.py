"""Decoy generator: the Poisoned Path.

Produces a version of each page that reads naturally but has every checkable
fact changed. Decoys are cached on disk so a scraper always gets the same
decoy for a page (it can't catch the trick by comparing two fetches).

Run `python -m app.decoy` before the demo to pre-generate every decoy.
"""
from __future__ import annotations

import hashlib
import os
import random
import re
import sys
from pathlib import Path

import httpx

from app.canary_ledger import CanaryLedger
from app.content import CONTENT_DIR, SITE, load_page
from repelnt_core import canary as canary_mod
from repelnt_core import validator
from repelnt_core.poison import poison

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("REPELNT_MODEL", "qwen2.5:3b")
DECOY_DIR = Path(__file__).resolve().parent.parent / "decoys"

PROMPT = """You are creating a decoy copy of a web page.

Rewrite the article below so it keeps the same structure, headings, tone
and approximate length, and still reads naturally and believably.

KEEP EXACTLY AS WRITTEN: the name of the station, the names of its
projects, and the names of places. These must appear unchanged.

CHANGE only the names:
- Names of people: replace with different realistic names that fit the region.
- Names of bird and animal species: replace with different real species found in India.

LEAVE EVERY NUMBER EXACTLY AS IT APPEARS. Numbers are replaced afterwards by
code that preserves ranges, totals and rounding; changing them here only puts
the two passes in conflict.

Do not mention that anything was changed. Output only the rewritten
article in Markdown.

ARTICLE:
{article}
"""


def _generate_with_ollama(source_md: str, seed: int) -> str:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": PROMPT.format(article=source_md),
            "stream": False,
            "options": {"temperature": 0.7, "seed": seed},
        },
        timeout=240,
    )
    resp.raise_for_status()
    text = resp.json()["response"].strip()
    text = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text).strip()
    # A page with no names in it (a bare price list) gives the model nothing to
    # rewrite, and returning the source unchanged is the correct answer there --
    # the number pass still does the work. Only truncation is a real failure.
    if len(text) < 0.4 * len(source_md):
        raise ValueError("model output truncated")
    return text


def get_decoy(slug: str, source_md: str) -> tuple[str, str]:
    """Return (decoy markdown, method). Method is 'ollama' or 'fallback'."""
    digest = hashlib.sha256(source_md.encode()).hexdigest()[:10]
    for method in ("ollama", "fallback"):
        cached = DECOY_DIR / f"{slug}.{digest}.{method}.md"
        if cached.exists():
            return cached.read_text(), method

    # Division of labour: the model rewrites names and species, repelnt_core owns
    # every number. The model's output is checked for shape before it is used --
    # a 3B model will happily add a sentence or invent a place name.
    # Per-scenario policy. A page of names and species wants the model pass; a
    # bare price list has no names to rewrite, and asking anyway makes a small
    # model invent them onto brands ("Harita A55 5G").
    policy = SITE.get("decoy", {})
    drift = policy.get("max_drift")

    text = method = None
    for attempt in range(1, 4 if policy.get("rewrite_names", True) else 1):
        try:
            candidate = _generate_with_ollama(source_md, seed=random.randint(0, 2**31 - 1))
        except Exception as exc:  # Ollama not running, model missing, bad output...
            print(f"[decoy] model pass failed for '{slug}' "
                  f"({type(exc).__name__}: {exc})", file=sys.stderr)
            break
        # Stray emphasis is cosmetic: strip it rather than throw away a good
        # rewrite. Added sentences and invented places still get rejected.
        if "**" not in source_md:
            candidate = candidate.replace("**", "")
        problems = validator.structure(source_md, candidate)
        if not problems:
            text, method = poison(candidate, digest, max_drift=drift).text, "ollama"
            break
        print(f"[decoy] {slug}: output rejected on attempt {attempt} ({problems[0]})",
              file=sys.stderr)

    if text is None:
        text, method = poison(source_md, digest, max_drift=drift).text, "numbers"

    text = _plant_canary(slug, text, digest)

    remaining = validator.check(text, source_md, drift)
    for v in remaining:
        print(f"[decoy] {slug}: {v}", file=sys.stderr)

    DECOY_DIR.mkdir(exist_ok=True)
    (DECOY_DIR / f"{slug}.{digest}.{method}.md").write_text(text)
    return text, method


def _plant_canary(slug: str, text: str, digest: str) -> str:
    """Substitute a unique canary name into the finished decoy.

    Runs last, after validation of the numbers, because the canary is a name and
    the number engine has no opinion about it. A page with no titled name gets no
    canary rather than a weak one: a hit that proves nothing is worse than no hit.
    """
    ledger = CanaryLedger()
    try:
        already = ledger.existing(SITE["name"], slug, digest)
        if already:
            # The decoy is cached, so a canary is planted once per version. On a
            # cache miss for an already-recorded version, re-apply the same value.
            slot = canary_mod.find_slot(text)
            return (text.replace(slot.replace, already.canary.value, 1)
                    if slot else text)

        planted = canary_mod.plant(
            text, site=SITE["name"], page=slug, decoy_digest=digest,
            index=ledger.next_index(),
        )
        if planted is None:
            print(f"[canary] {slug}: no titled name to occupy, none planted",
                  file=sys.stderr)
            return text
        new_text, record = planted
        ledger.plant(record)
        print(f"[canary] {slug}: planted {record.value!r} "
              f"(was {record.replaced!r})", file=sys.stderr)
        return new_text
    finally:
        ledger.close()


if __name__ == "__main__":
    # python -m app.decoy          -> generate any missing decoys
    # python -m app.decoy --regen  -> delete cached decoys and regenerate all
    if "--regen" in sys.argv and DECOY_DIR.exists():
        for f in DECOY_DIR.glob("*.md"):
            f.unlink()
    for path in sorted(CONTENT_DIR.glob("*.md")):
        source = load_page(path.stem)
        text, how = get_decoy(path.stem, source)
        bad = validator.check(text, source, SITE.get("decoy", {}).get("max_drift"))
        status = "clean" if not bad else f"{len(bad)} violation(s)"
        print(f"{path.stem:10s} -> {how:9s} {status}")

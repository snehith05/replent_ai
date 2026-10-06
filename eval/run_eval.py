"""Does poisoning actually work? Ask a model and count.

Puts the same ten questions to a local model twice: once with the real pages as
reference, once with the text a scraper actually carried away. The gap between
the two scores is the whole product in one number.

    python eval/run_eval.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.content import load_page  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("REPELNT_MODEL", "qwen2.5:3b")
SCRAPED = ROOT / "scraped" / "gptbot"
DECOYS = ROOT / "decoys"

PROMPT = """Answer the question using ONLY the reference text below.
Reply with the value alone -- no sentence, no explanation.

REFERENCE:
{context}

QUESTION: {question}
ANSWER:"""


def poisoned_context(page: str) -> str:
    """What the scraper took. Prefers the real scrape, falls back to the decoy."""
    got = SCRAPED / f"{page}.txt"
    if got.exists():
        return got.read_text()
    return next(DECOYS.glob(f"{page}.*.md")).read_text()


def ask(context: str, question: str) -> str:
    r = httpx.post(f"{OLLAMA}/api/generate", json={
        "model": MODEL,
        "prompt": PROMPT.format(context=context.strip(), question=question),
        "stream": False,
        # Temperature 0 so the demo is reproducible in front of an audience.
        "options": {"temperature": 0, "seed": 7, "num_predict": 40},
    }, timeout=180)
    r.raise_for_status()
    return " ".join(r.json()["response"].split())


def correct(expected: str, got: str) -> bool:
    """Lenient on wording, strict on the value."""
    e, g = expected.lower().replace(",", ""), got.lower().replace(",", "")
    if e in g:
        return True
    # Accept "3.6 million" / "36 lakh" for a large round number.
    if e.isdigit() and len(e) >= 6:
        n = int(e)
        for form in (f"{n / 1_000_000:g} million", f"{n / 100_000:g} lakh",
                     f"{n / 10_000_000:g} crore"):
            if form in g:
                return True
    # Accept a surname alone for a person.
    parts = [p for p in expected.replace(".", "").split() if len(p) > 2]
    return bool(parts) and parts[-1].lower() in g


def run(label: str, context_for) -> tuple[int, list[tuple]]:
    questions = json.loads((ROOT / "eval" / "questions.json").read_text())
    rows, score = [], 0
    print(f"\n{label}")
    print("-" * 78)
    for q in questions:
        got = ask(context_for(q["page"]), q["question"])
        ok = correct(q["answer"], got)
        score += ok
        rows.append((q["question"], q["answer"], got, ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {q['question'][:46]:<46} "
              f"expected {q['answer']:<18} got {got[:24]}")
    print(f"  -> {score}/{len(questions)} correct")
    return score, rows


if __name__ == "__main__":
    print(f"model: {MODEL}  (temperature 0, reproducible)")
    real, _ = run("A. MODEL READS THE REAL SITE (what a person sees)", load_page)
    fake, _ = run("B. MODEL READS WHAT THE SCRAPER TOOK (poisoned)", poisoned_context)

    total = len(json.loads((ROOT / "eval" / "questions.json").read_text()))
    print("\n" + "=" * 78)
    print(f"  real pages ....... {real}/{total} facts correct")
    print(f"  scraped pages .... {fake}/{total} facts correct")
    print(f"  facts destroyed ... {real - fake} of the {real} the model could learn")
    print("=" * 78)

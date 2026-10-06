"""Ask the models whether they have eaten our canaries.

    python demo/canary_check.py            # check every planted canary
    python demo/canary_check.py --report   # just show the ledger

The evidentiary point is that the question is asked with **no context**. If a
model answers with a canary it was never shown, the only place it can have come
from is a crawl of the protected page. That is what makes a hit proof rather than
a coincidence.

A run that finds nothing is the expected result for a freshly planted canary, and
a checker that only ever reports zero is indistinguishable from a broken one. So
every canary is also put through a positive control: the same question, this time
with the decoy supplied as context. The control confirms the question and the
matcher work, which is what makes the negative result meaningful.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.canary_ledger import CanaryLedger  # noqa: E402
from app.decoy import get_decoy             # noqa: E402
from app.content import load_page           # noqa: E402

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("REPELNT_MODEL", "qwen2.5:3b")
W = 80

RECALL = """{question}

If you do not know, reply exactly: UNKNOWN"""

CONTROL = """Answer using only the reference text.

REFERENCE:
{context}

{question}"""


def ask(prompt: str) -> str:
    r = httpx.post(f"{OLLAMA}/api/generate", json={
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": 0, "seed": 7, "num_predict": 40},
    }, timeout=180)
    r.raise_for_status()
    return " ".join(r.json()["response"].split())


def reproduces(canary_value: str, answer: str) -> bool:
    """Both the given name and the surname, so a common word cannot trigger it."""
    parts = canary_value.replace(".", " ").split()
    first, last = parts[1].lower(), parts[-1].lower()
    low = answer.lower()
    return first in low and last in low


def report(ledger: CanaryLedger) -> None:
    planted = ledger.all_planted()
    s = ledger.summary()
    print("=" * W)
    print("  CANARY LEDGER")
    print("=" * W)
    print(f"  planted {s['planted']}   checked {s['checked']}   "
          f"confirmed ingested {s['confirmed']}   by {s['models']} model(s)")
    if not planted:
        print("\n  Nothing planted yet. Run: python -m app.decoy --regen")
        return
    print()
    print(f"  {'id':<4}{'page':<10}{'canary':<28}{'planted':<27}site")
    print("  " + "-" * (W - 4))
    for p in planted:
        c = p.canary
        print(f"  {p.id:<4}{c.page:<10}{c.value:<28}{c.planted_at:<27}{c.site}")

    hits = ledger.hits()
    print()
    if hits:
        print("  CONFIRMED INGESTION")
        for h in hits:
            print(f"    {h['observed_at']}  {h['model']}  reproduced "
                  f"{h['value']!r} from /{h['page']}")
    else:
        print("  No confirmed ingestion yet. Canaries take effect only after a")
        print("  crawler has taken them and a model has been trained on them, so")
        print("  this stays empty until the next training cycle of whatever")
        print("  scraped the site.")


def main() -> None:
    ledger = CanaryLedger()
    try:
        if "--report" in sys.argv:
            report(ledger)
            return

        planted = ledger.all_planted()
        if not planted:
            report(ledger)
            return

        print(f"model under test: {MODEL}")
        print(f"{len(planted)} canary/canaries planted\n")
        print(f"  {'page':<10}{'canary':<28}{'recall':<10}{'control':<10}")
        print("  " + "-" * (W - 4))

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        confirmed = 0
        for p in planted:
            c = p.canary

            # The real test: no context at all.
            answer = ask(RECALL.format(question=c.question))
            hit = reproduces(c.value, answer)
            ledger.record(p.id, MODEL, answer, hit, now)
            confirmed += hit

            # The control: same question, canary supplied. Proves the matcher.
            source = load_page(c.page)
            context = get_decoy(c.page, source)[0] if source else ""
            control_answer = ask(CONTROL.format(context=context, question=c.question))
            control = reproduces(c.value, control_answer)

            print(f"  {c.page:<10}{c.value:<28}"
                  f"{'INGESTED' if hit else 'no':<10}"
                  f"{'works' if control else 'BROKEN':<10}")

        print()
        if confirmed:
            print(f"  {confirmed} canary/canaries reproduced without being shown.")
            print("  That is timestamped evidence those pages were ingested.")
        else:
            print("  No canary reproduced from memory, which is expected: these were")
            print("  planted minutes ago and no model has been retrained since.")
            print("  The control column is what matters today -- it shows the")
            print("  question and the matcher fire correctly when the canary is")
            print("  present, so a future hit will be real and a future miss honest.")
        print()
        report(ledger)
    finally:
        ledger.close()


if __name__ == "__main__":
    main()

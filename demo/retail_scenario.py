"""A real scraping scenario, end to end, with the money attached.

Competitor price scraping is the most common commercial use of scrapers on the
web: a retailer's catalogue is fetched continuously by rivals whose pricing
engines undercut whatever they find. This runs that attack against a poisoned
catalogue and prices the outcome.

    python demo/retail_scenario.py              # everything, ~90 seconds
    python demo/retail_scenario.py --skip-eval  # no model calls, ~5 seconds
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Must be set before app.content is imported: it reads this at import time.
os.environ.setdefault("REPELNT_CONTENT", str(ROOT / "scenarios" / "retail" / "content"))

from app.content import load_page                 # noqa: E402
from app.decoy import get_decoy                   # noqa: E402
from app.detector import IntentDetector           # noqa: E402

W = 82
CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
CUSTOMER = {"user-agent": CHROME, "accept": "text/html,application/xhtml+xml",
            "accept-language": "en-IN,en;q=0.9", "sec-fetch-mode": "navigate"}
PRICE_BOT = {"user-agent": "python-requests/2.32.3"}
CAREFUL_BOT = dict(CUSTOMER)

# How a real competitor's pricing engine is configured.
UNDERCUT = 0.03    # list 3 percent below whatever the rival is charging
COST_RATIO = 0.94  # they buy stock at 94 percent of true market price
MONTHLY_UNITS = {"Galaxy": 140, "Redmi": 260, "Pixel": 70, "iPhone": 45, "OnePlus": 160}

ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|$")


def act(n: int, title: str) -> None:
    print("\n" + "=" * W)
    print(f"  ACT {n}.  {title}")
    print("=" * W)


def rupees(n: float) -> str:
    return f"{round(n):,}"


def prices(md: str) -> dict[str, int]:
    out = {}
    for line in md.splitlines():
        m = ROW.match(line.strip())
        if m and not m.group(2).startswith("-"):
            out[m.group(1)] = int(m.group(2).replace(",", ""))
    return out


def units(model: str) -> int:
    return next((v for k, v in MONTHLY_UNITS.items() if k in model), 50)


detector = IntentDetector()
real_md = load_page("pricing")
poison_md, _ = get_decoy("pricing", real_md)

# ------------------------------------------------------------------ ACT 1
act(1, "The shop. An authorised dealer publishing its prices for customers.")
for line in load_page("index").splitlines():
    if line.strip() and not line.startswith("#"):
        print("  " + line)

# ------------------------------------------------------------------ ACT 2
act(2, "A customer checks a price before driving to the store.")
v = detector.classify("49.37.12.80", CUSTOMER, {"rp_js": "1"})
print(f"  score {v.score:>4}  verdict {v.label:<8}  served: the real price list")
print("  The customer sees what they will actually be charged.")

# ------------------------------------------------------------------ ACT 3
act(3, "A competitor's price bot scrapes the catalogue. It runs every hour.")
v = detector.classify("45.112.8.9", PRICE_BOT, {})
print(f"  score {v.score:>4}  verdict {v.label:<8}  served: a decoy price list")
for r in v.reasons:
    print(f"    {r}")
print()
real, fake = prices(real_md), prices(poison_md)
print(f"  {'model':<26} {'real price':>12} {'scraped price':>14} {'error':>10}")
print("  " + "-" * (W - 4))
for model, true_p in real.items():
    got = fake.get(model, true_p)
    print(f"  {model:<26} {rupees(true_p):>12} {rupees(got):>14} "
          f"{(got - true_p) / true_p * 100:>9.0f}%")
print("\n  Model names, storage sizes and 5G survive untouched, so the rows still")
print("  join to real products. Only the prices are wrong.")

# ------------------------------------------------------------------ ACT 4
act(4, "A careful bot. Full browser headers. Header checks cannot see it.")
d2 = IntentDetector()
v = d2.classify("103.21.58.4", CAREFUL_BOT, {})
print(f"  first pass     score {v.score:>4} -> real prices (it got the truth)")
d2.mark_trapped(d2.client_key("103.21.58.4", CAREFUL_BOT["user-agent"]))
v = d2.classify("103.21.58.4", CAREFUL_BOT, {})
print(f"  after the trap score {v.score:>4} -> decoy prices, permanently")
print("\n  It crawled every link it found. One of them was hidden, nofollowed and")
print("  disallowed in robots.txt. No customer can reach it.")

# ------------------------------------------------------------------ ACT 5
act(5, "The consequence. Their pricing engine acts on what it scraped.")
print(f"  Their strategy: undercut this shop by {UNDERCUT:.0%}.")
print(f"  Their cost base: {COST_RATIO:.0%} of true market price.\n")
print(f"  {'model':<24} {'they list at':>12} {'their cost':>11} "
      f"{'per unit':>10}  outcome")
print("  " + "-" * (W - 4))
lost = 0.0
for model, true_p in real.items():
    scraped = fake.get(model, true_p)
    listed = scraped * (1 - UNDERCUT)
    cost = true_p * COST_RATIO
    n = units(model)
    baseline = (true_p * (1 - UNDERCUT) - cost) * n  # what correct data earns
    if listed > true_p:
        per_unit, realised = 0.0, 0.0
        outcome = "priced above the rival, loses the sale"
    else:
        per_unit = listed - cost
        realised = per_unit * n
        outcome = "sells below cost" if per_unit < 0 else "thin but positive"
    lost += baseline - realised
    print(f"  {model[:23]:<24} {rupees(listed):>12} {rupees(cost):>11} "
          f"{rupees(per_unit):>10}  {outcome}")
print("  " + "-" * (W - 4))
print(f"  Monthly margin lost against correct data: {rupees(lost)} rupees")
print(f"  Over a year: {rupees(lost * 12)} rupees")
print("\n  The bot never errored. It fetched 200 OK, parsed clean HTML, and")
print("  priced a whole catalogue off it.")
print()
print("  Fair objection: a real engine has a margin floor and would refuse to")
print("  list below cost. It then holds at the floor and loses the undercut it")
print("  was built to win. The failure mode changes; the loss does not.")

# ------------------------------------------------------------------ ACT 6
act(6, "And anything that learns from the scrape learns the wrong facts.")
if "--skip-eval" in sys.argv:
    print("  (skipped -- run without --skip-eval to measure this live)")
else:
    import json
    from eval.run_eval import ask, correct  # noqa: E402
    qs = json.loads((ROOT / "scenarios" / "retail" / "questions.json").read_text())
    good = bad = 0
    for q in qs:
        src = load_page(q["page"])
        truth = ask(src, q["question"])
        lie = ask(get_decoy(q["page"], src)[0], q["question"])
        good += correct(q["answer"], truth)
        bad += correct(q["answer"], lie)
        print(f"  {q['question'][:50]:<52} {truth[:14]:<16} {lie[:14]}")
    print(f"\n  reading the real site ....... {good}/{len(qs)} facts correct")
    print(f"  reading the scraped site .... {bad}/{len(qs)} facts correct")
print("\n" + "=" * W + "\n")

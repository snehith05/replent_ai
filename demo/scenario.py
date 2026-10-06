"""Repelnt: the full story in one run. Built to be shown, not read.

    python demo/scenario.py              # everything, ~2 minutes
    python demo/scenario.py --skip-eval  # everything except the model test

Runs in-process against the same code the server uses, so it needs no server
and cannot fail halfway through a presentation. Open the dashboard and run
scraper_demo.py alongside it if you want the network view too.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.content import load_page                      # noqa: E402
from app.decoy import get_decoy                        # noqa: E402
from app.detector import IntentDetector                # noqa: E402
from repelnt_core.identity import ShadowIdentity       # noqa: E402
from repelnt_core.policy import PolicyEngine, Resource, Subject, default_rules  # noqa: E402

W = 78
CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
HUMAN = {"user-agent": CHROME, "accept": "text/html,application/xhtml+xml",
         "accept-language": "en-IN,en;q=0.9", "sec-fetch-mode": "navigate"}
GPTBOT = {"user-agent": "Mozilla/5.0 (compatible; GPTBot/1.1; "
                        "+https://openai.com/gptbot)"}
MIMIC = dict(HUMAN)  # identical headers to a real browser


def act(n: int, title: str) -> None:
    print("\n" + "=" * W)
    print(f"  ACT {n}.  {title}")
    print("=" * W)


def beat() -> None:
    time.sleep(0.6)


def serve(detector: IntentDetector, slug: str, headers: dict, cookies: dict | None = None):
    """Exactly what app/main.py does, minus the HTTP."""
    source = load_page(slug)
    v = detector.classify("203.0.113.9", headers, cookies or {})
    if v.poisoned:
        text, _ = get_decoy(slug, source)
        return text, v, "POISONED"
    return source, v, "REAL"


# The checkable facts, as a label and the pattern that pulls the value out.
FACTS = [
    ("started",     r"began in (\w+ \d{4})"),
    ("buoys",       r"uses ([\d,]+) solar-powered"),
    ("distance",    r"between ([\d,]+ and [\d,]+) kilometres"),
    ("sampling",    r"every ([\d,]+ \w+)"),
    ("lead",        r"led by (Dr\.? ?[A-Z][\w.]*(?: [A-Z][\w.]*)?)"),
    ("team size",   r"team of ([\d,]+) engineers"),
    ("budget",      r"budget to date is ([\d,]+)"),
    ("warming",     r"rose by ([\d.]+) degrees"),
    ("wave events", r"logged ([\d,]+) high-wave"),
    ("warnings",    r"and ([\d,]+) of those"),
]


def value(md: str, pattern: str) -> str:
    m = re.search(pattern, md)
    return m.group(1) if m else "-"


detector = IntentDetector()

# ---------------------------------------------------------------- ACT 1
act(1, "The site. A real coastal research station, published openly.")
real = load_page("research")
for line in real.splitlines():
    if line.strip():
        print("  " + line)
beat()

# ---------------------------------------------------------------- ACT 2
act(2, "A person opens it in Chrome.")
_, v, served = serve(detector, "research", HUMAN, {"rp_js": "1"})
print(f"  score {v.score:>4}   verdict {v.label:<14} served: {served}")
print("  reasons: " + ("; ".join(v.reasons) or "nothing suspicious"))
print("\n  -> The scientist, the fisher and the local council get the truth.")
beat()

# ---------------------------------------------------------------- ACT 3
act(3, "GPTBot arrives. robots.txt forbids it. It asks anyway.")
poisoned, v, served = serve(detector, "research", GPTBOT)
print(f"  score {v.score:>4}   verdict {v.label:<14} served: {served}")
for r in v.reasons:
    print(f"    {r}")
print("\n  Same URL. Same HTTP 200. No header says anything happened.\n")

print(f"  {'fact':<13} {'what people see':<24} {'what GPTBot stored':<24}")
print("  " + "-" * (W - 4))
for label, pattern in FACTS:
    print(f"  {label:<13} {value(real, pattern):<24} {value(poisoned, pattern):<24}")
beat()

# ---------------------------------------------------------------- ACT 4
act(4, "A careful scraper. Perfect browser headers. Header checks cannot see it.")
d2 = IntentDetector()
_, v, served = serve(d2, "research", MIMIC)
print(f"  first visit    score {v.score:>4}  -> {served}   (it got the truth)")
print("  Then it follows every link it finds -- including the one in the footer")
print("  that is hidden, nofollowed, and disallowed in robots.txt.")
d2.mark_trapped(d2.client_key("203.0.113.9", MIMIC["user-agent"]))
_, v, served = serve(d2, "research", MIMIC)
print(f"  after the trap score {v.score:>4}  -> {served}")
print("\n  -> Headers can be forged. Restraint cannot.")
beat()

# ---------------------------------------------------------------- ACT 5
act(5, "So what? Ask a model what it learned.")
if "--skip-eval" in sys.argv:
    print("  (skipped -- run without --skip-eval to measure this live)")
else:
    from eval.run_eval import load_page as _lp, poisoned_context, run  # noqa: E402
    good, _ = run("  reading the real site", _lp)
    bad, _ = run("  reading what the scraper took", poisoned_context)
    total = len(json.loads((ROOT / "eval" / "questions.json").read_text()))
    (ROOT / "eval" / "results.json").write_text(
        json.dumps({"model": "qwen2.5:3b", "real": good, "poisoned": bad,
                    "total": total}, indent=2))
    print(f"\n  real site .......... {good}/{total} facts correct")
    print(f"  scraped site ....... {bad}/{total} facts correct")
    print("\n  -> And it never hedges. It states the false answer as confidently")
    print("     as the true one. The poisoning is invisible downstream.")
beat()

# ---------------------------------------------------------------- ACT 6
act(6, "Where this goes: the same engine, on the device.")
shadow = ShadowIdentity.derive("device-9f3a7c21")
engine = PolicyEngine(default_rules())
print(f"  shadow identity: {shadow.name}, {shadow.city} -- a person who does not exist\n")
for subject, resource in [
    (Subject.from_app("com.adnetwork.sdk", harvester=True), Resource("location")),
    (Subject.from_app("com.yourbank.app"), Resource("payment")),
    (Subject.from_agent("assistant.unknown"), Resource("messages")),
    (Subject.from_agent("os.assistant", verified=True), Resource("messages")),
]:
    d = engine.decide(subject, resource)
    print(f"  {subject.id:<24} wants {resource.kind:<10} -> "
          f"{d.action.value.upper():<7} ({d.reason})")
lat, lon = shadow.location(tick=14)
print(f"\n  every surface reports the same false position: {lat}, {lon}")
print("  -> one lie, told consistently, is the only kind that survives checking.")
print("\n" + "=" * W + "\n")

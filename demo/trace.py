"""One request, every internal step. What actually happens in the backend.

    python demo/trace.py                  # GPTBot asking for /research
    python demo/trace.py human            # a person in Chrome, same page
    python demo/trace.py pricebot         # a script with library defaults
    python demo/trace.py mimic            # flawless browser headers
    python demo/trace.py trapped          # the same client, after the trap
    python demo/trace.py empty            # no user-agent at all
    python demo/trace.py gptbot survey    # any profile, any page

Nothing here is narrated. Every number is read out of the real detector and the
real poisoning engine as the request passes through them.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.content import CONTENT_DIR, load_page, render_page   # noqa: E402
from app.decoy import DECOY_DIR, get_decoy                    # noqa: E402
from app.detector import IntentDetector                       # noqa: E402
from repelnt_core.poison import poison                        # noqa: E402
from repelnt_core.validator import check                      # noqa: E402

W = 84
CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
BROWSER = {"user-agent": CHROME, "accept": "text/html,application/xhtml+xml",
           "accept-language": "en-IN,en;q=0.9", "sec-fetch-mode": "navigate"}
GPTBOT_UA = "Mozilla/5.0 (compatible; GPTBot/1.1; +https://openai.com/gptbot)"

PROFILES = {
    "human":    (BROWSER, {"rp_js": "1"}, "49.37.12.80", False),
    "gptbot":   ({"user-agent": GPTBOT_UA}, {}, "20.171.207.9", False),
    "pricebot": ({"user-agent": "python-requests/2.32.3"}, {}, "45.112.8.9", False),
    "mimic":    (BROWSER, {}, "103.21.58.4", False),
    "trapped":  (BROWSER, {}, "103.21.58.4", True),
    "empty":    ({}, {}, "185.4.22.7", False),
}
HEADERS_SHOWN = ["user-agent", "accept", "accept-language", "sec-fetch-mode"]
ABSENT = "(absent)"


def step(n: str, title: str, where: str) -> None:
    print()
    print("-" * W)
    left = "STEP " + n + " - " + title
    print(left.ljust(W - len(where) - 1) + where)
    print("-" * W)


profile = "gptbot"
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    profile = sys.argv[1]
slug = sys.argv[2] if len(sys.argv) > 2 else "research"
if profile not in PROFILES:
    sys.exit("unknown profile " + profile + "; pick one of " + ", ".join(PROFILES))
headers, cookies, ip, pre_trapped = PROFILES[profile]

print("=" * W)
print("  REPELNT REQUEST TRACE".ljust(W - 24) + "profile: " + profile)
print("=" * W)

# ------------------------------------------------------------------- STEP 1
step("1", "THE REQUEST ARRIVES", "app/main.py:_serve")
print("  GET /" + ("" if slug == "index" else slug))
print("  " + "client".ljust(18) + ip)
for h in HEADERS_SHOWN:
    print("  " + h.ljust(18) + (headers.get(h) or ABSENT))
print("  " + "cookies".ljust(18) + (str(cookies) if cookies else "(none)"))
detector = IntentDetector()
key = detector.client_key(ip, headers.get("user-agent", ""))
print("  " + "client key".ljust(18) + key[:58])
if pre_trapped:
    detector.mark_trapped(key)
    print("  " + "trap set".ljust(18) + "this key was flagged on an earlier visit")

# ------------------------------------------------------------------- STEP 2
step("2", "INTENT DETECTOR", "app/detector.py:classify")
verdict = detector.classify(ip, headers, cookies)
print("  " + "check".ljust(42) + "fired".rjust(7) + "points".rjust(9)
      + "running".rjust(10))
running = 0
for c in verdict.checks:
    running += c.points
    fired = "YES" if c.fired else "no"
    print("  " + c.name.ljust(42) + fired.rjust(7)
          + format(c.points, "+d").rjust(9) + str(running).rjust(10))
relation = ">=" if verdict.score >= detector.threshold else "<"
path = "POISONED PATH" if verdict.poisoned else "REAL PATH"
print()
print("  DECISION   score " + str(verdict.score) + "  " + relation
      + "  threshold " + str(detector.threshold) + "   ->   "
      + verdict.label + ", " + path)

# ------------------------------------------------------------------- STEP 3
step("3", "CONTENT LOOKUP", "app/content.py:load_page")
source = load_page(slug)
if source is None:
    sys.exit("  no page for slug " + slug + " in " + str(CONTENT_DIR))
digest = hashlib.sha256(source.encode()).hexdigest()[:10]
print("  " + "slug".ljust(18) + slug)
print("  " + "file".ljust(18) + CONTENT_DIR.name + "/" + slug + ".md  ("
      + str(len(source)) + " bytes)")
print("  " + "sha256[:10]".ljust(18) + digest + "      <- this is the decoy cache key")

if not verdict.poisoned:
    step("4", "NO DECOY IS BUILT", "app/main.py:_serve")
    print("  The real markdown goes straight to the template. The decoy engine is")
    print("  never called, so there is nothing further to trace.")
    html = render_page(source)
    step("5", "THE RESPONSE", "app/content.py:render_page")
    print("  " + "status".ljust(18) + "200")
    print("  " + "bytes".ljust(18) + str(len(html)))
    print("  " + "body".ljust(18) + "the real page, unmodified")
    print()
    print("=" * W)
    print()
    raise SystemExit

# ------------------------------------------------------------------- STEP 4
step("4", "DECOY CACHE", "app/decoy.py:get_decoy")
hits = sorted(DECOY_DIR.glob(slug + "." + digest + ".*.md"))
for f in hits:
    print("  probe   decoys/" + f.name + "   HIT")
if not hits:
    print("  probe   decoys/" + slug + "." + digest + ".*.md   MISS -> generating now")
decoy, method = get_decoy(slug, source)
print("  " + "method".ljust(18) + method)
print()
print("  Why it is cached: a scraper fetching the page twice must receive")
print("  byte-identical text. If two fetches differed, diffing them would expose")
print("  the substitution immediately.")

# ------------------------------------------------------------------- STEP 5
step("5", "HOW THAT DECOY IS BUILT", "repelnt_core/")
result = poison(source, digest, trace=True)
t = result.trace
print("  5a  model pass        qwen2.5:3b rewrites people and species names only")
print("  5b  structure check   lines, headings, table rows and emphasis must match")
print("                        the source, or the output is rejected and retried")
print("                        the model leaves numbers alone, so the engine below")
print("                        reproduces exactly what the cached decoy contains")
print()
print("  5c  numbers extracted (" + str(len(t["numbers"])) + ")"
      + " " * 22 + "repelnt_core/numbers.py")
print("      " + "raw".ljust(14) + "kind".ljust(10) + "sig figs")
for raw, kind, sf in t["numbers"]:
    print("      " + raw.ljust(14) + kind.ljust(10) + str(sf))
print()
print("  5d  protected spans" + " " * 23 + "repelnt_core/constraints.py")
locked = t["locked"]
tail = (": " + ", ".join(locked)) if locked else " (none on this page)"
print("      " + str(len(locked)) + " identifier numbers locked" + tail)
print()
print("  5e  relations detected" + " " * 20 + "repelnt_core/constraints.py")
for kind, raws in t["relations"]:
    print("      " + kind.ljust(10) + " . ".join(raws))
if not t["relations"]:
    print("      (none)")
print()
print("  5f  clustering, one scale factor per related group   repelnt_core/poison.py")
for raws, factor in t["clusters"]:
    print("      " + ("{" + ", ".join(raws) + "}").ljust(34) + "x" + str(factor))
if not t["clusters"]:
    print("      (every number independent)")
print()
print("  5g  substitutions")
for old, new in t["substitutions"]:
    print("      " + old.ljust(14) + "->  " + new)
problems = check(result.text, source)
print()
print("  5h  validation        7 rules, " + str(len(problems)) + " violations, settled on"
      " attempt " + str(result.attempts) + " of up to 6")
for p in problems:
    print("      " + str(p))

# ------------------------------------------------------------------- STEP 6
step("6", "THE RESPONSE", "app/content.py:render_page")
real_html, fake_html = render_page(source), render_page(decoy)
print("  " + "status".ljust(18) + "200            identical to the real path")
print("  " + "content-type".ljust(18) + "text/html      identical to the real path")
print("  " + "bytes".ljust(18) + str(len(fake_html)).ljust(15)
      + "the real path would send " + str(len(real_html)))
print("  " + "marker".ljust(18) + "none           no header or tag names the path taken")
print()
print("  The only difference between the two responses is the body text:")
print()
print("  " + "what the source says".ljust(40) + "what this client receives")
print("  " + "-" * (W - 4))
for a, b in zip(source.splitlines(), decoy.splitlines()):
    if a.strip() and a != b:
        print("  " + a.strip()[:38].ljust(40) + b.strip()[:38])
print()
print("=" * W)
print()

# Repelnt

A gateway that serves the truth to people and plausible fiction to AI scrapers
that ignore `robots.txt`.

`robots.txt` is a sign, not a lock. Blocking a crawler starts an arms race the
publisher loses, and a blocked crawler knows it was blocked and adapts. Repelnt
takes the other path: the request is served, with every checkable fact changed.
The scraper leaves satisfied, and what it carries away is wrong.

```
request ──▶ intent detector ──▶ score < 50 ──▶ the real page
                            └─▶ score ≥ 50 ──▶ a decoy page
```

Same status code, same headers, same page shape. Nothing in the response tells a
scraper which path it took.

## Does it work?

Ten checkable facts, put to a local model, temperature zero:

| Reference text the model was given | Facts correct |
|---|---|
| The real pages | **10 / 10** |
| What a scraper carried away | **0 / 10** |

It never hedges. Asked who leads a project, the model answers with the fabricated
name in exactly the register it uses when correct. Nothing downstream can tell
which answer was poisoned.

```bash
python eval/run_eval.py
```

This measures retrieval from poisoned context, not the effect of poisoned data on
a full training run. That is the right next experiment and it needs more compute
than a laptop.

## Two things that are harder than they look

**Detection.** Headers can be forged; restraint cannot. Every page footer carries
one link that is hidden in CSS, marked `nofollow`, and disallowed in
`robots.txt`. No person can click it and no well-behaved crawler will fetch it,
so anything that arrives there has classified itself by its behaviour rather than
its claims. A scraper sending flawless browser headers passes every header check
and is still caught.

**Plausibility.** A decoy only works if it survives inspection, and replacing
each number independently does not survive anything. It produces ranges that read
"between 7 and 7 kilometres", budgets rewritten from a rounded 3,600,000 to
9,262,134, and tables under "most common species" that come back ascending.
`repelnt_core` finds the relationships first and perturbs each related group
together:

- ranges keep their direction, and parts keep summing to less than their whole
- a table column stays sorted the way the original was sorted
- one source value gets one replacement, so a heading and its body still agree
- significant figures survive, so a rounded grant stays rounded
- identifiers are immune, so "Galaxy A55 5G 128GB" does not become "Galaxy A130 10G 294GB"
- how far a value may move is per-scenario: a bird count can double, a phone price cannot

A validator enforces seven rules on every decoy before it ships. Across four
pages it took the output from 13 violations to 0.

## Canaries: proof of ingestion

Poisoning on its own cannot be verified, which makes it unsellable. Each
protected page therefore carries one unique, plausible, checkable falsehood — a
person's name that reads perfectly ordinarily and exists nowhere else. Later the
assistants are asked a question whose only possible source is that page, **with
no context supplied**. A model that answers with the canary was trained on a
crawl of that page, and the ledger has the date it was planted.

```bash
python demo/canary_check.py
```

Every canary also runs a positive control — the same question with the decoy
supplied — because a checker that only ever reports zero is indistinguishable
from a broken one.

Canary values are deliberately not in this repository. See `.gitignore`.

## Try it

```bash
python -m venv .venv && .venv/bin/activate      # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
ollama pull qwen2.5:3b                          # optional; a numbers-only decoy works without it

python -m app.decoy                             # pre-generate decoys
uvicorn app.main:app --port 8000
```

| Command | What it shows |
|---|---|
| `python demo/trace.py gptbot` | Every internal step of one request, read out of the live detector and engine |
| `python demo/trace.py trapped` | A client with flawless headers, caught purely by behaviour |
| `python demo/scenario.py` | The whole story in six acts, including the model evaluation |
| `python demo/retail_scenario.py` | Competitor price scraping, with the cost to the attacker priced out |
| `python scraper_demo.py` | Four scrapers crawling a live gateway |
| `python tests/check_decoys.py` | Plausibility audit of every decoy on disk |

`show.ps1` drives the traces from a menu on Windows.

## Layout

| Path | |
|---|---|
| `app/` | The gateway: routing, intent scoring, decoy cache, crawler verification |
| `repelnt_core/` | The engine: constraint detection, perturbation, validation, canaries, shadow identity, policy |
| `repelnt-android/` | Android client — the policy surface and a working location substitution |
| `content/`, `scenarios/` | Protected pages; `REPELNT_CONTENT` selects which site the gateway fronts |
| `eval/`, `tests/`, `demo/` | Measurement, audits, and the things worth watching run |

`repelnt_core` imports nothing from FastAPI, httpx or Ollama, and the Kotlin port
in `repelnt-android` imports nothing from Android, so the engine stays portable.

## On the device

The same policy engine and shadow identity run on Android. The app registers a
test location provider and the result is real: with the device's GPS set to
Delhi, every app asking for location — including the `fused` provider that Maps
and ride-hailing apps actually use — is told the shadow identity's city instead.

There is a catch, and it is the whole argument for shipping this inside the
operating system rather than beside it. The substituted fix arrives flagged:

```
Location[fused 26.932000,75.831000 ... mock]
```

`Location.isMock()` is a public API. Any app can read it in one line, and
anti-fraud code in banking and ride-hailing apps already does. At app privilege
the lie arrives wearing a label saying it is a lie. Framework-level code sets no
such flag, because it is not registering a mock provider — it is the provider.

## What it cannot do yet

- A headless browser that runs JavaScript and never touches the trap link still receives real pages. Catching it needs behavioural features.
- Search-engine verification by reverse DNS is implemented but off by default (`REPELNT_VERIFY_DNS=1`), because a DNS lookup in the request path has no portable timeout. Unverified claimants fall through to normal scoring rather than being trusted.
- An unrecognised client sending no browser headers scores 45 against a threshold of 50, so it gets real pages until it touches the trap.
- Client state lives in memory; a restart forgets every scraper it has seen.
- Serving different content to different clients is the mechanism search engines penalise as cloaking. Verified crawler identity is what separates the two, which is why it is the next thing to build.

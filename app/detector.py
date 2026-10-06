"""Intent detector: scores how scraper-like a request looks.

Each signal adds or removes points. At or above the threshold, the request
is treated as unauthorized scraping and sent down the Poisoned Path.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app import verify as crawler_verify

JS_COOKIE = "rp_js"  # set by a tiny inline script on every page

# Crawlers that collect AI training data. robots.txt tells all of these to stay
# out, so any request carrying one of these user-agents has ignored that.
AI_CRAWLER_UAS = [
    "gptbot", "chatgpt-user", "oai-searchbot", "ccbot", "claudebot",
    "anthropic-ai", "bytespider", "perplexitybot", "amazonbot",
    "meta-externalagent", "diffbot", "cohere-ai", "timpibot", "imagesiftbot",
]

# Generic HTTP clients and automation tools. Real people don't browse with these.
HTTP_LIBRARY_UAS = [
    "python-requests", "python-urllib", "httpx", "aiohttp", "scrapy", "curl",
    "wget", "go-http-client", "node-fetch", "axios", "okhttp", "java/",
    "libwww-perl", "headlesschrome", "phantomjs",
]

# Search engines get the real page so the site still shows up in search, but the
# bypass is granted only to a claim that app/verify.py can confirm. An
# unverified claim is scored like any other request.
SEARCH_ENGINE_UAS = ["googlebot", "bingbot", "duckduckbot"]

BROWSER_UA_MARKERS = ["chrome/", "firefox/", "safari/", "edg/"]


def _first_match(ua: str, needles: list[str]) -> str | None:
    return next((n for n in needles if n in ua), None)


@dataclass
class Check:
    """One signal's outcome, including the ones that did not fire.

    `reasons` records only what counted against a request. A trace needs the
    whole checklist: seeing that six checks passed and one failed is what makes
    a score legible.
    """
    name: str
    fired: bool
    points: int
    detail: str = ""


@dataclass
class Verdict:
    score: int
    reasons: list[str] = field(default_factory=list)
    label: str = "human"  # "human" | "scraper" | "search_engine"
    checks: list[Check] = field(default_factory=list)

    @property
    def poisoned(self) -> bool:
        return self.label == "scraper"


class IntentDetector:
    def __init__(self, threshold: int = 50, rate_window: float = 10.0, rate_limit: int = 8):
        self.threshold = threshold
        self.rate_window = rate_window
        self.rate_limit = rate_limit
        self._hits: dict[str, deque] = defaultdict(deque)
        self._trapped: set[str] = set()

    @staticmethod
    def client_key(ip: str, ua: str) -> str:
        # IP + user-agent, so a browser and a script on the same machine
        # (e.g. both on localhost during the demo) are tracked separately.
        # Used for rate limiting, where separating them is what we want.
        return f"{ip}|{ua}"

    @staticmethod
    def trap_key(ip: str, headers) -> str:
        """Identity for the trap flag, chosen to survive user-agent rotation.

        Keying the trap on IP + user-agent meant a scraper escaped a permanent
        flag by bumping Chrome/129 to Chrome/130. The user-agent's *value* is
        therefore excluded; what remains is the address plus the shape of the
        request -- which header names were sent, in what order. A scraper
        rotating its user-agent keeps that shape. A real browser sharing the
        address sends a different one, so it is not caught by association.
        """
        names = ",".join(h.lower() for h in headers.keys() if h.lower() != "user-agent")
        shape = hashlib.sha256(names.encode()).hexdigest()[:12]
        return f"{ip}|{shape}"

    def mark_trapped(self, key: str) -> None:
        self._trapped.add(key)

    def _rate_exceeded(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        hits.append(now)
        while hits and now - hits[0] > self.rate_window:
            hits.popleft()
        return len(hits) > self.rate_limit

    def classify(self, ip: str, headers, cookies) -> Verdict:
        ua = headers.get("user-agent", "")
        ua_l = ua.lower()
        key = self.client_key(ip, ua)
        verdict = Verdict(score=0)

        def step(name: str, fired: bool, points: int = 0, why: str = "") -> bool:
            verdict.checks.append(Check(name, fired, points if fired else 0, why))
            if fired and points:
                verdict.score += points
                verdict.reasons.append(f"{points:+d} {why}")
            return fired

        crawler = _first_match(ua_l, AI_CRAWLER_UAS)
        library = _first_match(ua_l, HTTP_LIBRARY_UAS)
        engine = _first_match(ua_l, SEARCH_ENGINE_UAS)

        # An AI crawler token disqualifies a search-engine claim outright: a
        # user-agent reading "GPTBot/1.1 Googlebot" is not a search engine, and
        # treating it as one handed it the real page.
        claims_engine = bool(engine) and not crawler
        confirmed = claims_engine and crawler_verify.verify(ip, engine)
        step("verified search engine", confirmed, 0,
             crawler_verify.status(ip, engine if claims_engine else None))
        if confirmed:
            verdict.label = "search_engine"
            verdict.reasons.append(f"reverse DNS confirms {engine}")
            return verdict

        step("seen at the trap before", self.trap_key(ip, headers) in self._trapped, 100,
             "earlier followed the hidden link robots.txt forbids")
        if not step("empty user-agent", not ua, 40, "empty user-agent"):
            if not step("AI crawler user-agent", bool(crawler), 100,
                        f"AI crawler user-agent ({crawler}), which robots.txt disallows"):
                step("HTTP library user-agent", bool(library), 50,
                     f"HTTP library user-agent ({library})")

        step("no Accept-Language", "accept-language" not in headers, 20,
             "no Accept-Language header")
        step("Accept does not ask for HTML", "text/html" not in headers.get("accept", ""), 10,
             "Accept header doesn't ask for HTML")
        if step("no Sec-Fetch headers", "sec-fetch-mode" not in headers, 15,
                "no Sec-Fetch headers"):
            step("browser claim without browser headers",
                 bool(_first_match(ua_l, BROWSER_UA_MARKERS)), 25,
                 "claims to be a browser but lacks headers browsers send")

        step("request rate exceeded", self._rate_exceeded(key), 30,
             f"more than {self.rate_limit} requests in {self.rate_window:.0f}s")
        step("runs JavaScript", cookies.get(JS_COOKIE) == "1", -40,
             "has the JavaScript cookie, so it runs JS like a browser")

        verdict.label = "scraper" if verdict.score >= self.threshold else "human"
        return verdict

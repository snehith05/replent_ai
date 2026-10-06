"""Surface-agnostic policy engine.

One decision function for every surface. A web crawler asking for a page, an ad
SDK asking for location, an on-device agent asking for messages and a mesh peer
asking for a file are all the same shape: a subject of some trust level wants a
resource, and we answer allow / block / poison / charge.

Keeping this one engine is what lets the four surfaces share a shadow identity
instead of contradicting one another.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    POISON = "poison"
    CHARGE = "charge"


class Trust(str, Enum):
    VERIFIED = "verified"        # cryptographically or DNS-confirmed identity
    UNKNOWN = "unknown"
    HARVESTER = "harvester"      # known to collect for training / resale


@dataclass
class Subject:
    """Whoever is asking. `id` is a package name, agent id, UA fingerprint or peer key."""

    id: str
    kind: str                    # "app" | "agent" | "crawler" | "peer"
    trust: Trust = Trust.UNKNOWN
    score: int = 0               # scraper-likeness, where a surface supplies one
    evidence: list[str] = field(default_factory=list)

    @classmethod
    def from_crawler(cls, fingerprint: str, score: int, reasons: list[str],
                     verified: bool = False) -> Subject:
        trust = (Trust.VERIFIED if verified
                 else Trust.HARVESTER if score >= 50 else Trust.UNKNOWN)
        return cls(fingerprint, "crawler", trust, score, reasons)

    @classmethod
    def from_app(cls, package: str, harvester: bool = False) -> Subject:
        return cls(package, "app", Trust.HARVESTER if harvester else Trust.UNKNOWN)

    @classmethod
    def from_agent(cls, agent_id: str, verified: bool = False) -> Subject:
        return cls(agent_id, "agent", Trust.VERIFIED if verified else Trust.UNKNOWN)

    @classmethod
    def from_peer(cls, peer_key: str) -> Subject:
        return cls(peer_key, "peer", Trust.VERIFIED)


@dataclass
class Resource:
    """What is being asked for."""

    kind: str                    # location | contacts | photos | messages | content | telemetry
    path: str = "*"


@dataclass
class Rule:
    action: Action
    reason: str
    kinds: tuple[str, ...] = ()          # subject kinds this rule covers; () = any
    trust: tuple[Trust, ...] = ()        # trust levels; () = any
    resources: tuple[str, ...] = ()      # resource kinds; () = any
    subject_glob: str = "*"
    path_glob: str = "*"
    min_score: int | None = None

    def matches(self, s: Subject, r: Resource) -> bool:
        return (
            (not self.kinds or s.kind in self.kinds)
            and (not self.trust or s.trust in self.trust)
            and (not self.resources or r.kind in self.resources)
            and fnmatch.fnmatch(s.id, self.subject_glob)
            and fnmatch.fnmatch(r.path, self.path_glob)
            and (self.min_score is None or s.score >= self.min_score)
        )


@dataclass
class Decision:
    action: Action
    reason: str
    subject: Subject
    resource: Resource

    @property
    def poisoned(self) -> bool:
        return self.action is Action.POISON


class PolicyEngine:
    """Ordered rules, first match wins."""

    def __init__(self, rules: list[Rule], default: Action = Action.ALLOW):
        self.rules = rules
        self.default = default

    def decide(self, subject: Subject, resource: Resource) -> Decision:
        for rule in self.rules:
            if rule.matches(subject, resource):
                return Decision(rule.action, rule.reason, subject, resource)
        return Decision(self.default, "no rule matched", subject, resource)


def default_rules() -> list[Rule]:
    """A starting policy that errs toward keeping things working."""
    return [
        # Verified identities are never poisoned: this is the guard that stops a
        # detection miss from destroying a customer's search ranking.
        Rule(Action.ALLOW, "verified identity", trust=(Trust.VERIFIED,)),

        # Credentials and payment data are blocked outright for untrusted callers,
        # never poisoned: fake banking data breaks the user's app, not the
        # harvester. Trusted first-party apps fall through to the default.
        Rule(Action.BLOCK, "untrusted caller, sensitive resource",
             trust=(Trust.HARVESTER,), resources=("credentials", "payment")),
        Rule(Action.BLOCK, "unknown agent, sensitive resource",
             kinds=("agent",), trust=(Trust.UNKNOWN,),
             resources=("credentials", "payment")),

        Rule(Action.POISON, "known harvester", trust=(Trust.HARVESTER,)),
        Rule(Action.POISON, "scores as a scraper", kinds=("crawler",), min_score=50),

        # Unknown agents see decoys for personal data but real content otherwise.
        Rule(Action.POISON, "unknown agent reading personal data",
             kinds=("agent",), trust=(Trust.UNKNOWN,),
             resources=("location", "contacts", "messages", "photos")),
    ]

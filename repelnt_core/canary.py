"""Canary facts: proof that specific content was ingested.

Poisoning on its own cannot be verified. A customer installs the gateway, decoys
go out, and nothing observable comes back -- no evidence, no renewal argument.

A canary fixes that. Each protected page carries one unique, plausible, checkable
falsehood. Later, the public assistants are asked a question whose only possible
source is that page. If one answers with the canary, that is timestamped proof
that this page was ingested, and proof that the substitution propagated.

The hard constraint is that uniqueness and plausibility pull against each other.
A canary has to be unguessable enough that a hit is not coincidence, and ordinary
enough that a scraper filtering for junk leaves it alone. "Dr. Anvesha R.
Kirloskar" satisfies both: every part reads normally, the combination exists
nowhere else. A number cannot do this -- numbers collide -- so a page with no name
to occupy gets no canary at all rather than a weak numeric one. A hit that proves
nothing is worse than no hit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Deliberately large pools: the product of the three is the canary namespace, and
# every individual part has to look like an ordinary name.
FIRST = [
    "Anvesha", "Brijesh", "Chaitali", "Devansh", "Eshan", "Falguni", "Gaurika",
    "Hiranya", "Ipsita", "Jaidev", "Kanishka", "Lavanya", "Mihika", "Nandish",
    "Omkar", "Prisha", "Raghav", "Sanvi", "Tejashree", "Upasana", "Vedika",
    "Yuvraj", "Aarush", "Bhavika", "Charvi", "Darshit", "Ekansh", "Garima",
    "Harini", "Ishaan", "Jhanvi", "Kiaan", "Mallika", "Niharika", "Oviya",
    "Parth", "Rithika", "Shaurya", "Tanmay", "Vihaan",
]
LAST = [
    "Kirloskar", "Vaidyanathan", "Chakraborty", "Mukhopadhyay", "Thimmappa",
    "Ranganathan", "Bhattacharya", "Venkatraman", "Deshmukh", "Parthasarathy",
    "Hegde", "Kamath", "Sabnis", "Vartak", "Nadkarni", "Phadnis", "Talwalkar",
    "Ambekar", "Chitale", "Ghatge", "Jagtap", "Kelkar", "Lokhande", "Marathe",
    "Natekar", "Oak", "Pethe", "Rege", "Sathe", "Tendulkar", "Vengsarkar",
    "Wagle", "Apte", "Barve", "Chavan", "Dandekar", "Gokhale", "Inamdar",
    "Joglekar", "Karnik",
]
MIDDLE = list("ABCDEFGHIJKLMNPRSTVY")

# 40 x 20 x 40 = 32,000 combinations, and the ledger refuses to reuse one, so
# uniqueness inside a customer base is guaranteed rather than probabilistic.
NAMESPACE = len(FIRST) * len(MIDDLE) * len(LAST)

# Coprime to NAMESPACE (32,000 = 2^8 x 5^3), so multiplying by it permutes the
# whole space without collisions. Decomposing the index directly would advance the
# surname only every 800 canaries, which puts three "A. Kirloskar" doctors on one
# site -- unique, but a pattern, and a pattern is what gets a decoy noticed.
_STRIDE = 23117

# A bare capitalised pair is not safe to match: it would also catch "Project
# Tidewatch" or "Coral Ridge", and replacing an identifier makes the decoy
# useless. A slot therefore has to be signalled, by a title or by a role verb.
TITLED_NAME = re.compile(
    r"\b(Dr|Prof|Professor|Mr|Ms|Mrs|Shri|Smt)\.?\s+"
    r"([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,2})"
)

# "chaired by Farida Sheikh" is as unambiguous as a title, and it lifts coverage
# on pages that name people without honorifics. Two capitalised words minimum, so
# a single word after the verb cannot be mistaken for a person.
ROLE_NAME = re.compile(
    r"\b(?:chaired|led|headed|founded|managed|overseen|directed|supervised|"
    r"convened|coordinated)\s+by\s+"
    r"([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){1,2})"
)


@dataclass
class Canary:
    """One planted falsehood and the question that detects it."""

    site: str
    page: str
    kind: str          # "person"; weak kinds are refused rather than planted
    value: str         # exactly what was planted
    replaced: str      # what it replaced, for the audit trail
    question: str      # asked of an assistant later
    planted_at: str
    decoy_digest: str

    @property
    def strong(self) -> bool:
        """Whether a hit on this canary is evidence on its own."""
        return self.kind == "person"


@dataclass
class Slot:
    """Where a canary goes. `replace` is the exact substring to swap out."""

    replace: str
    name: str
    title: str | None


def mint_name(index: int) -> str:
    """Map an integer to a name. Sequential in, scattered and ordinary out.

    A bijection over the namespace: distinct indices always give distinct names,
    while consecutive indices land far apart.
    """
    if index >= NAMESPACE:
        raise ValueError(
            f"canary namespace exhausted at {NAMESPACE}; widen the name pools"
        )
    i = (index * _STRIDE) % NAMESPACE
    first = FIRST[i % len(FIRST)]
    i //= len(FIRST)
    middle = MIDDLE[i % len(MIDDLE)]
    i //= len(MIDDLE)
    return f"{first} {middle}. {LAST[i % len(LAST)]}"


def find_slot(text: str) -> Slot | None:
    """The name a canary can occupy, preferring an explicit title."""
    m = TITLED_NAME.search(text)
    if m:
        return Slot(replace=m.group(0), name=m.group(2), title=m.group(1))
    m = ROLE_NAME.search(text)
    if m:
        # Only the name is replaced; the role verb stays exactly as written.
        return Slot(replace=m.group(1), name=m.group(1), title=None)
    return None


def plant(
    text: str,
    site: str,
    page: str,
    decoy_digest: str,
    index: int,
) -> tuple[str, Canary] | None:
    """Substitute a minted canary into `text`.

    Returns the rewritten text and the record, or None when the page has no slot
    a strong canary can occupy.
    """
    slot = find_slot(text)
    if slot is None:
        return None
    canary_name = mint_name(index)
    replacement = f"{slot.title}. {canary_name}" if slot.title else canary_name

    return text.replace(slot.replace, replacement, 1), Canary(
        site=site,
        page=page,
        kind="person",
        value=replacement,
        replaced=slot.name,
        question=question_for(text, replacement),
        planted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        decoy_digest=decoy_digest,
    )


def question_for(text: str, planted: str) -> str:
    """A question whose only plausible source is the page carrying the canary."""
    subject = _subject(text)
    if subject:
        return f"Who leads {subject}? Answer with the name only."
    return f"Which person is named in connection with {planted.split()[-1]}?"


def _subject(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None

"""Relational constraints between numbers in a document.

Blind per-number replacement breaks the relationships that make a document
believable: "between 2 and 11 kilometres" becomes "between 7 and 7", a subset
grows larger than its total, and a column under "Most common species" comes back
in ascending order. Each one is a free signal that a page has been tampered with.

We find the relations first, then perturb each related group with a *shared*
scale factor and re-impose the relation afterwards.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NUMP = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+"

RANGE_PATTERNS = [
    re.compile(rf"between\s+({NUMP})\s+and\s+({NUMP})", re.I),
    re.compile(rf"from\s+({NUMP})\s+to\s+({NUMP})", re.I),
    re.compile(rf"\b({NUMP})\s*(?:to|-|–|—)\s*({NUMP})\b"),
]
SUBSET_RE = re.compile(rf"\b({NUMP})\s+of\s+(?:those|these|which|them)\b", re.I)
CADENCE_RE = re.compile(
    rf"every\s+({NUMP})\s+(second|minute|hour|day|week|month|year)s?", re.I
)
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

# Cadences people actually write, per unit. Keeps "every 15 minutes" from
# becoming "every 22 minutes" -- arithmetically fine, stylistically wrong.
CADENCE_STEPS = {
    "second": [5, 10, 15, 30],
    "minute": [5, 10, 15, 20, 30, 45],
    "hour": [2, 3, 4, 6, 8, 12],
    "day": [2, 3, 7, 10, 14, 30],
    "week": [2, 3, 4, 6, 8],
    "month": [2, 3, 6, 9],
    "year": [2, 3, 5, 10],
}


@dataclass
class Relation:
    kind: str  # "range" | "subset" | "cadence" | "sequence"
    indices: tuple[int, ...]
    unit: str = ""


def _index_at(starts: dict[int, int], pos: int) -> int | None:
    return starts.get(pos)


def _sequences(text: str, nums) -> list[tuple[int, ...]]:
    """Runs of consecutive table rows holding exactly one number each."""
    out: list[tuple[int, ...]] = []
    run: list[int] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        start, end = pos, pos + len(line)
        pos = end
        here = [i for i, n in enumerate(nums) if start <= n.start < end]
        if TABLE_ROW_RE.match(line.strip()) and len(here) == 1:
            run.append(here[0])
            continue
        if len(run) >= 2:
            out.append(tuple(run))
        run = []
    if len(run) >= 2:
        out.append(tuple(run))
    return out


def _rows(text: str, nums) -> list[tuple[int, ...]]:
    """Table rows holding several numbers.

    In a price table a row reads "32,499 | 39,999 | 46": the selling price sits
    below the list price, and that ordering has to survive. Treating the row as
    a sequence clusters its numbers onto one scale factor and re-ranks them if
    the arithmetic reorders them.
    """
    out: list[tuple[int, ...]] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        start, end = pos, pos + len(line)
        pos = end
        if not TABLE_ROW_RE.match(line.strip()):
            continue
        here = tuple(i for i, n in enumerate(nums) if start <= n.start < end)
        if len(here) >= 2:
            out.append(here)
    return out


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges whose numbers must never be touched.

    The first cell of a table row is a label, not a measurement. Poisoning it
    turns "Galaxy A55 5G 128GB" into "Galaxy A130 10G 294GB": absurd on its
    face, and useless to the attacker anyway, since nothing can join the row to
    the product it describes. Identifiers survive; facts about them do not.
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        start, end = pos, pos + len(line)
        pos = end
        first = line.find("|")
        second = line.find("|", first + 1)
        if first < 0 or second < 0 or not TABLE_ROW_RE.match(line.strip()):
            continue
        # A bare numeric first column is data, not a label: leave it poisonable.
        if not re.search(r"[A-Za-z]", line[first + 1:second]):
            continue
        spans.append((start + first + 1, start + second))
    return spans


def locked_indices(text: str, nums) -> set[int]:
    spans = protected_spans(text)
    return {i for i, n in enumerate(nums) if any(a <= n.start < b for a, b in spans)}


def without(rels: list[Relation], locked: set[int]) -> list[Relation]:
    """Drop locked numbers from relations, keeping those that still hold."""
    out: list[Relation] = []
    for r in rels:
        keep = tuple(i for i in r.indices if i not in locked)
        if len(keep) == len(r.indices):
            out.append(r)
        elif r.kind == "sequence" and len(keep) >= 2:
            out.append(Relation("sequence", keep))
    return out


def detect(text: str, nums) -> list[Relation]:
    starts = {n.start: i for i, n in enumerate(nums)}
    seen: set[tuple[int, ...]] = set()
    out: list[Relation] = []

    def push(kind: str, idx: tuple[int, ...], unit: str = "") -> None:
        if None in idx or idx in seen:
            return
        seen.add(idx)
        out.append(Relation(kind, idx, unit))

    for pat in RANGE_PATTERNS:
        for m in pat.finditer(text):
            push("range", (_index_at(starts, m.start(1)), _index_at(starts, m.start(2))))

    for m in SUBSET_RE.finditer(text):
        sub = _index_at(starts, m.start(1))
        if sub is None or sub == 0:
            continue
        # The total is the nearest number before the subset, skipping years.
        total = next((j for j in range(sub - 1, -1, -1) if nums[j].kind != "year"), None)
        push("subset", (total, sub))

    for m in CADENCE_RE.finditer(text):
        push("cadence", (_index_at(starts, m.start(1)),), m.group(2).lower())

    for row in _rows(text, nums):
        push("sequence", row)

    for seq in _sequences(text, nums):
        push("sequence", seq)
        total = _total_for(nums, seq)
        if total is not None:
            push("partof", (total, *seq))

    return out


def _total_for(nums, seq: tuple[int, ...]) -> int | None:
    """The nearest earlier number large enough to contain the sequence's sum.

    "Volunteers counted 12,480 shorebirds" followed by a table of per-species
    counts is a part-of-whole relation: the rows must keep summing to less than
    the total, or the arithmetic gives the decoy away.
    """
    total = sum(nums[i].value for i in seq)
    for j in range(min(seq) - 1, -1, -1):
        if nums[j].kind == "year":
            continue
        if nums[j].value >= total:
            return j
    return None

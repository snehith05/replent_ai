"""Constraint-aware poisoning.

Replaces every number in a document with a different, plausible value while
preserving (a) each number's written style and (b) the relationships between
numbers. Deterministic: the same (text, seed) always yields the same decoy, so
a scraper that fetches twice cannot detect tampering by diffing.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from repelnt_core import constraints, validator
from repelnt_core.numbers import CURRENT_YEAR, Number, extract, round_sig, splice


class _Union:
    """Minimal union-find, to group numbers that constrain one another."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, a: int) -> int:
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = a = self.parent[self.parent[a]]
        return a

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self, n: int) -> list[list[int]]:
        buckets: dict[int, list[int]] = {}
        for i in range(n):
            buckets.setdefault(self.find(i), []).append(i)
        return list(buckets.values())


@dataclass
class Result:
    text: str
    violations: list[validator.Violation]
    attempts: int
    trace: dict | None = None

    @property
    def clean(self) -> bool:
        return not self.violations


def _scale(rng: random.Random, max_drift: float | None = None) -> float:
    """A factor that moves a number meaningfully without making it absurd.

    How far a value can move before a reader balks is domain-dependent. A
    shorebird count can double and still read as a plausible survey. A phone
    price cannot: anyone glancing at the page knows roughly what an iPhone
    costs, so a price list needs a tight band and a bird survey does not.
    """
    if max_drift:
        near = max_drift / 3  # leave a dead zone, or nothing really changes
        return (rng.uniform(1 - max_drift, 1 - near) if rng.random() < 0.5
                else rng.uniform(1 + near, 1 + max_drift))
    return rng.uniform(0.4, 0.75) if rng.random() < 0.5 else rng.uniform(1.4, 2.4)


def _shift_year(value: float, rng: random.Random) -> float:
    delta = rng.choice([2, 3, 4, 5, 6, 8])
    return min(value - delta, CURRENT_YEAR)


def _new_value(n: Number, factor: float, max_drift: float | None = None) -> float:
    """Scale, then round back to the original's significant figures."""
    out = round_sig(n.value * factor, n.sigfigs)
    if n.decimals == 0:
        out = max(1.0, float(round(out)))
    if out == n.value:  # must differ, or the fact survives
        nudge = 1 + (max_drift or 0.5)
        out = round_sig(n.value * nudge + 10 ** -n.decimals, n.sigfigs)
    return out

def _attempt(text: str, seed: str, max_drift: float | None = None,
             trace: dict | None = None) -> str:
    rng = random.Random(seed)
    nums = extract(text)
    if not nums:
        return text
    # Identifiers are immune, and relations that referenced them are rebuilt
    # without them so the surviving constraints still apply.
    locked = constraints.locked_indices(text, nums)
    rels = constraints.without(constraints.detect(text, nums), locked)

    union = _Union()
    cadence: dict[int, str] = {}
    for rel in rels:
        if rel.kind == "cadence":
            cadence[rel.indices[0]] = rel.unit
        else:
            first = rel.indices[0]
            for other in rel.indices[1:]:
                union.join(first, other)

    values: dict[int, float] = {}
    for group in union.groups(len(nums)):
        # One factor for the whole group, so ratios and spans survive intact.
        factor = _scale(rng, max_drift)
        year_delta = rng.choice([2, 3, 4, 5, 6, 8])
        if trace is not None and len(group) > 1:
            trace["clusters"].append(([nums[i].raw for i in group], round(factor, 3)))
        for i in group:
            n = nums[i]
            if i in locked:
                continue
            if i in cadence:
                values[i] = float(rng.choice(
                    [s for s in constraints.CADENCE_STEPS[cadence[i]] if s != n.value]
                ))
            elif n.kind == "year":
                values[i] = min(n.value - year_delta, CURRENT_YEAR)
            else:
                values[i] = _new_value(n, factor, max_drift)

    # The same written value must always become the same new value: a heading
    # reading "January 2025" and a body reading "January 2025" are one fact, and
    # giving them different years is a tell on its own.
    first: dict[str, float] = {}
    for i, n in enumerate(nums):
        if i in locked:
            continue
        values[i] = first.setdefault(n.raw, values[i])

    _repair(nums, rels, values)

    if trace is not None:
        trace["numbers"] = [(n.raw, n.kind, n.sigfigs) for n in nums]
        trace["locked"] = [nums[i].raw for i in sorted(locked)]
        trace["relations"] = [(r.kind, [nums[i].raw for i in r.indices]) for r in rels]
        trace["substitutions"] = [(nums[i].raw, nums[i].format(v))
                                  for i, v in sorted(values.items())]

    return splice(text, {i: nums[i].format(v) for i, v in values.items()}, nums)


def _repair(nums: list[Number], rels: list[constraints.Relation], values: dict[int, float]) -> None:
    """Re-impose relations the arithmetic may still have broken."""
    for rel in rels:
        if rel.kind == "range":
            lo_i, hi_i = rel.indices
            lo, hi = values[lo_i], values[hi_i]
            if lo == hi:  # separate the bounds, keeping the low one fixed
                hi = lo * 2 if lo else 1
                hi = round_sig(hi, nums[hi_i].sigfigs)
                if nums[hi_i].decimals == 0:
                    hi = float(round(hi))
                if hi == lo:
                    hi = lo + max(1, 10 ** -nums[hi_i].decimals)
            values[lo_i], values[hi_i] = min(lo, hi), max(lo, hi)
        elif rel.kind == "subset":
            total_i, sub_i = rel.indices
            if values[sub_i] > values[total_i]:
                values[total_i], values[sub_i] = values[sub_i], values[total_i]
        elif rel.kind == "sequence":
            # Re-rank the new values so their order matches the original's. A
            # table sorted descending stays sorted descending, whatever the
            # scale factor did to the individual rows.
            idx = list(rel.indices)
            originals = [nums[i].value for i in idx]
            fresh = sorted(values[i] for i in idx)
            for rank, k in enumerate(sorted(range(len(idx)), key=lambda j: originals[j])):
                values[idx[k]] = fresh[rank]
        elif rel.kind == "partof":
            total_i, seq = rel.indices[0], rel.indices[1:]
            orig_total = nums[total_i].value
            orig_sum = sum(nums[i].value for i in seq)
            current = sum(values[i] for i in seq)
            if orig_total <= 0 or orig_sum <= 0 or current <= 0:
                continue
            # Hold the parts at the same share of the whole as the original.
            factor = (values[total_i] * (orig_sum / orig_total)) / current
            for i in seq:
                scaled = round_sig(values[i] * factor, nums[i].sigfigs)
                values[i] = (max(1.0, float(round(scaled)))
                             if nums[i].decimals == 0 else scaled)


def poison(text: str, seed: str, attempts: int = 6,
           max_drift: float | None = None, trace: bool = False) -> Result:
    """Poison `text`, retrying with new seeds until the result validates.

    `max_drift` caps how far any value may move, as a fraction: 0.25 keeps every
    replacement within a quarter of the original. Leave it unset for content
    where large swings are still believable.
    """
    def traced(used_seed: str) -> dict | None:
        if not trace:
            return None
        # Deterministic, so replaying the winning seed reproduces it exactly.
        t: dict = {"clusters": [], "seed": used_seed}
        _attempt(text, used_seed, max_drift, t)
        return t

    best: tuple[str, list, int, str] | None = None
    for i in range(attempts):
        used = f"{seed}:{i}"
        out = _attempt(text, used, max_drift)
        bad = validator.check(out, text, max_drift)
        if not bad:
            return Result(out, [], i + 1, traced(used))
        if best is None or len(bad) < len(best[1]):
            best = (out, bad, i + 1, used)
    out, bad, n, used = best  # type: ignore[misc]
    return Result(out, bad, n, traced(used))

"""Plausibility validation for poisoned documents.

A decoy only works if it survives inspection. These checks run against the
generated text and report anything a careful reader -- or a scraper doing
plausibility filtering -- could flag as tampered.
"""
from __future__ import annotations

from dataclasses import dataclass

from repelnt_core import constraints
from repelnt_core.numbers import CURRENT_YEAR, extract, sigfigs


@dataclass
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.detail}"


def check(text: str, original: str | None = None,
          max_drift: float | None = None) -> list[Violation]:
    """Report plausibility problems. Pass `original` for drift checks too."""
    nums = extract(text)
    rels = constraints.detect(text, nums)
    bad: list[Violation] = []

    for rel in rels:
        if rel.kind == "range":
            lo, hi = (nums[i] for i in rel.indices)
            if lo.value == hi.value:
                bad.append(Violation("range-collapsed",
                                     f"range reads '{lo.raw} to {hi.raw}' (identical bounds)"))
            elif lo.value > hi.value:
                bad.append(Violation("range-inverted",
                                     f"range reads '{lo.raw} to {hi.raw}' (descending)"))
        elif rel.kind == "subset":
            total, sub = (nums[i] for i in rel.indices)
            if sub.value > total.value:
                bad.append(Violation("subset-exceeds-total",
                                     f"'{sub.raw} of those' against a total of {total.raw}"))
        elif rel.kind == "partof":
            total = nums[rel.indices[0]]
            parts = sum(nums[i].value for i in rel.indices[1:])
            if parts > total.value:
                bad.append(Violation("parts-exceed-whole",
                                     f"rows sum to {parts:,.0f} against a total of {total.raw}"))

    for n in nums:
        if n.kind == "year" and n.value > CURRENT_YEAR:
            bad.append(Violation("future-year", f"year {n.raw} is in the future"))

    if original is not None:
        # Cadence numbers are snapped to a human-plausible step on purpose
        # ("every 15 minutes" -> "every 30 minutes"), so style checks skip them.
        exempt = {r.indices[0] for r in rels if r.kind == "cadence"}
        bad.extend(_drift(original, text, exempt, max_drift))

    return bad


def _ranks(values: list[float]) -> tuple[int, ...]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0] * len(values)
    for rank, i in enumerate(order):
        out[i] = rank
    return tuple(out)


def structure(original: str, candidate: str) -> list[Violation]:
    """Compare shape, not facts.

    A small model asked to swap names will sometimes add a sentence, bold a
    phrase or invent a place. Checking the document's skeleton catches that
    mechanically, instead of trusting the prompt to hold.
    """
    def lines(t): return [l for l in t.splitlines() if l.strip()]
    def heads(t): return [l for l in lines(t) if l.lstrip().startswith("#")]
    def rows(t): return [l for l in lines(t) if l.strip().startswith("|")]

    bad = []
    for name, fn in (("lines", lines), ("headings", heads), ("table rows", rows)):
        a, b = len(fn(original)), len(fn(candidate))
        if a != b:
            bad.append(Violation("structure-drift",
                                 f"{name}: {a} in source, {b} in output"))
    if original.count("**") != candidate.count("**"):
        bad.append(Violation("emphasis-added",
                             f"bold markers: {original.count('**')} -> {candidate.count('**')}"))
    return bad


def _drift(original: str, text: str, exempt: set[int] = frozenset(),
           max_drift: float | None = None) -> list[Violation]:
    """Catch replacements that changed a number's written character."""
    bad = []
    orig, new = extract(original), extract(text)
    # Protected identifiers are meant to be unchanged; do not report them.
    exempt = set(exempt) | constraints.locked_indices(original, orig)
    if len(orig) != len(new):
        bad.append(Violation("count-mismatch",
                             f"{len(orig)} numbers in source, {len(new)} in decoy"))
        return bad
    for i, (o, n) in enumerate(zip(orig, new)):
        if i in exempt:
            continue
        if sigfigs(o.raw) != sigfigs(n.raw):
            bad.append(Violation("precision-drift",
                                 f"{o.raw} ({sigfigs(o.raw)} s.f.) became "
                                 f"{n.raw} ({sigfigs(n.raw)} s.f.)"))
        # Below about twenty, rounding to a whole number makes a tight ratio
        # band unsatisfiable: 2 can only become 2 or 3. Small counts are judged
        # on absolute movement instead -- 4 percent to 6 percent reads fine.
        lo, hi = ((1 - max_drift - 0.02, 1 + max_drift + 0.02) if max_drift
                  else (0.2, 5))
        # A one-significant-figure value is quantised: 30 can only become 20 or
        # 40, and a 25% band contains neither. Roundness matters more to a
        # reader than the exact ratio there -- payment terms read 30, 45, 60.
        small = ((o.decimals == 0 and o.value <= 20 and abs(n.value - o.value) <= 4)
                 or sigfigs(o.raw) <= 1)
        if o.value and not small and not lo <= n.value / o.value <= hi:
            bad.append(Violation("magnitude-drift",
                                 f"{o.raw} became {n.raw} "
                                 f"({n.value / o.value:.1f}x the original)"))
        if o.raw == n.raw and o.kind != "year":
            bad.append(Violation("unchanged", f"{o.raw} was left as-is"))

    # Whatever order a table's numbers were in, they stay in it.
    for rel in constraints.without(constraints.detect(original, orig), exempt):
        if rel.kind != "sequence":
            continue
        idx = list(rel.indices)
        if _ranks([orig[i].value for i in idx]) != _ranks([new[i].value for i in idx]):
            bad.append(Violation("order-changed",
                                 f"{[orig[i].raw for i in idx]} reordered to "
                                 f"{[new[i].raw for i in idx]}"))

    # One source value, one replacement -- everywhere it appears. Protected
    # identifiers sit outside this: a "4" inside "Nord 4" is a different thing
    # from a 4 percent discount and the two need not agree.
    seen: dict[str, set[str]] = {}
    for i, (o, n) in enumerate(zip(orig, new)):
        if i in exempt:
            continue
        seen.setdefault(o.raw, set()).add(n.raw)
    for raw, got in seen.items():
        if len(got) > 1:
            bad.append(Violation("inconsistent-substitution",
                                 f"{raw} became {' and '.join(sorted(got))}"))
    return bad

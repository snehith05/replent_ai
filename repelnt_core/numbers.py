"""Number extraction and format-preserving replacement.

The single biggest tell in a poisoned document is a number that *looks* wrong:
a 2-significant-figure budget of 3,600,000 rupees rewritten as 9,262,134. Real
documents round. So every replacement here keeps the original's written shape --
its significant figures, its comma grouping and its decimal places.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from math import floor, log10

# Matches 3,600,000 / 12,480 / 0.4 / 212 / 2019. Ordered so longer forms win.
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+")

CURRENT_YEAR = 2026


def sigfigs(raw: str) -> int:
    """Significant figures as *written*. 3,600,000 -> 2, 12,480 -> 4, 0.4 -> 1."""
    digits = raw.replace(",", "").replace(".", "").lstrip("0")
    return len(digits.rstrip("0")) or 1


def round_sig(value: float, n: int) -> float:
    if value == 0:
        return 0.0
    mag = floor(log10(abs(value)))
    return round(value, -(mag - n + 1))


@dataclass
class Number:
    raw: str
    value: float
    start: int
    end: int
    kind: str  # "year" | "decimal" | "count"

    @property
    def sigfigs(self) -> int:
        return sigfigs(self.raw)

    @property
    def decimals(self) -> int:
        return len(self.raw.split(".")[1]) if "." in self.raw else 0

    @property
    def grouped(self) -> bool:
        return "," in self.raw

    def format(self, value: float) -> str:
        """Render `value` in this number's written style."""
        if self.decimals:
            return f"{value:,.{self.decimals}f}" if self.grouped else f"{value:.{self.decimals}f}"
        n = max(1, int(round(value)))
        return f"{n:,}" if self.grouped else str(n)


def _kind(raw: str, value: float) -> str:
    if "." in raw:
        return "decimal"
    # A bare 4-digit number in a plausible span is almost always a year.
    if "," not in raw and 1900 <= value <= 2100 and len(raw) == 4:
        return "year"
    return "count"


def extract(text: str) -> list[Number]:
    out = []
    for m in NUM_RE.finditer(text):
        raw = m.group(0)
        value = float(raw.replace(",", ""))
        out.append(Number(raw, value, m.start(), m.end(), _kind(raw, value)))
    return out


def splice(text: str, replacements: dict[int, str], nums: list[Number]) -> str:
    """Apply {index -> new text} right-to-left so earlier offsets stay valid."""
    for i in sorted(replacements, reverse=True):
        n = nums[i]
        text = text[: n.start] + replacements[i] + text[n.end :]
    return text

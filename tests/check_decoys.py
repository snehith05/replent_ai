"""Audit the existing decoys, then re-poison with the constraint-aware engine."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repelnt_core import validator
from repelnt_core.poison import poison

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
# Audit any decoy directory. Defaults to the live one; pass
# tests/fixtures/decoys-before to see what the old engine produced.
DECOYS = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "decoys"

print("=" * 68)
print(f"DECOYS ON DISK ({DECOYS.name})")
print("=" * 68)
old_total = 0
for src in sorted(CONTENT.glob("*.md")):
    original = src.read_text()
    # Match on the content hash, or a scenario sharing a slug (two "index"
    # pages) gets compared against the wrong source.
    digest = hashlib.sha256(original.encode()).hexdigest()[:10]
    for decoy in sorted(DECOYS.glob(f"{src.stem}.{digest}.*.md")):
        bad = validator.check(decoy.read_text(), original)
        old_total += len(bad)
        print(f"\n{decoy.name}  ->  {len(bad)} violation(s)")
        for v in bad[:6]:
            print(f"    {v}")

print("\n" + "=" * 68)
print("CONSTRAINT-AWARE ENGINE (repelnt_core)")
print("=" * 68)
new_total = 0
for src in sorted(CONTENT.glob("*.md")):
    original = src.read_text()
    seed = hashlib.sha256(original.encode()).hexdigest()[:10]
    result = poison(original, seed)
    new_total += len(result.violations)
    status = "clean" if result.clean else f"{len(result.violations)} violation(s)"
    print(f"\n{src.stem:10s} -> {status}  (attempts: {result.attempts})")
    for v in result.violations[:6]:
        print(f"    {v}")

print("\n" + "=" * 68)
print(f"violations: {old_total} (existing)  ->  {new_total} (new engine)")
print("=" * 68)

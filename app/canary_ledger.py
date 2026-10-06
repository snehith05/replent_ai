"""Where canaries and their sightings are recorded.

SQLite, standard library only. This is the asset that cannot be copied by reading
the source: a competitor can implement the same mechanism tomorrow and still have
no canaries planted in last year's training data.

Uniqueness is enforced here rather than left to chance. `next_index` hands out a
monotonic counter and the value column is unique, so no two pages anywhere in a
customer base can ever carry the same canary.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from repelnt_core.canary import Canary

DB_PATH = Path(__file__).resolve().parent.parent / "canary.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS canaries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site          TEXT NOT NULL,
    page          TEXT NOT NULL,
    kind          TEXT NOT NULL,
    value         TEXT NOT NULL UNIQUE,
    replaced      TEXT NOT NULL,
    question      TEXT NOT NULL,
    planted_at    TEXT NOT NULL,
    decoy_digest  TEXT NOT NULL,
    UNIQUE (site, page, decoy_digest)
);

CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    canary_id  INTEGER NOT NULL REFERENCES canaries(id),
    model      TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    hit        INTEGER NOT NULL,
    answer     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS obs_canary ON observations(canary_id);
"""


@dataclass
class Planted:
    id: int
    canary: Canary


class CanaryLedger:
    def __init__(self, path: Path | str = DB_PATH):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------------------------------------------------------------- planting

    def next_index(self) -> int:
        """The next minting index. Monotonic, so a value is never reissued."""
        row = self.conn.execute("SELECT COALESCE(MAX(id), 0) AS n FROM canaries").fetchone()
        return int(row["n"]) + 1

    def existing(self, site: str, page: str, decoy_digest: str) -> Planted | None:
        row = self.conn.execute(
            "SELECT * FROM canaries WHERE site = ? AND page = ? AND decoy_digest = ?",
            (site, page, decoy_digest),
        ).fetchone()
        return Planted(row["id"], _canary(row)) if row else None

    def plant(self, canary: Canary) -> Planted:
        """Record a canary. Idempotent per (site, page, decoy version)."""
        already = self.existing(canary.site, canary.page, canary.decoy_digest)
        if already:
            return already
        cur = self.conn.execute(
            "INSERT INTO canaries (site, page, kind, value, replaced, question,"
            " planted_at, decoy_digest) VALUES (?,?,?,?,?,?,?,?)",
            (canary.site, canary.page, canary.kind, canary.value, canary.replaced,
             canary.question, canary.planted_at, canary.decoy_digest),
        )
        self.conn.commit()
        return Planted(int(cur.lastrowid), canary)

    # ------------------------------------------------------------- observation

    def record(self, canary_id: int, model: str, answer: str, hit: bool,
               observed_at: str) -> None:
        self.conn.execute(
            "INSERT INTO observations (canary_id, model, observed_at, hit, answer)"
            " VALUES (?,?,?,?,?)",
            (canary_id, model, observed_at, 1 if hit else 0, answer),
        )
        self.conn.commit()

    # --------------------------------------------------------------- reporting

    def all_planted(self, site: str | None = None) -> list[Planted]:
        sql = "SELECT * FROM canaries"
        args: tuple = ()
        if site:
            sql += " WHERE site = ?"
            args = (site,)
        sql += " ORDER BY id"
        return [Planted(r["id"], _canary(r)) for r in self.conn.execute(sql, args)]

    def hits(self) -> list[sqlite3.Row]:
        """Confirmed ingestion: one row per model that reproduced a canary."""
        return list(self.conn.execute(
            "SELECT c.site, c.page, c.value, c.planted_at, o.model, o.observed_at,"
            "       o.answer"
            "  FROM observations o JOIN canaries c ON c.id = o.canary_id"
            " WHERE o.hit = 1 ORDER BY o.observed_at DESC"
        ))

    def summary(self) -> dict:
        def one(sql: str) -> int:
            return int(self.conn.execute(sql).fetchone()[0])

        return {
            "planted": one("SELECT COUNT(*) FROM canaries"),
            "checked": one("SELECT COUNT(DISTINCT canary_id) FROM observations"),
            "confirmed": one(
                "SELECT COUNT(DISTINCT canary_id) FROM observations WHERE hit = 1"),
            "models": one("SELECT COUNT(DISTINCT model) FROM observations WHERE hit = 1"),
        }

    def close(self) -> None:
        self.conn.close()


def _canary(row: sqlite3.Row) -> Canary:
    return Canary(
        site=row["site"], page=row["page"], kind=row["kind"], value=row["value"],
        replaced=row["replaced"], question=row["question"],
        planted_at=row["planted_at"], decoy_digest=row["decoy_digest"],
    )

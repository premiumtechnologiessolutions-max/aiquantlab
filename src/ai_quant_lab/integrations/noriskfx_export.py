"""Read-only AI Quant Lab V4 Nova HypothesisRecord export for NoRiskFX.

This private-workstation adapter accesses the institutional SQLite research
database in URI mode=ro. It never starts the runtime, touches MT5, reads
account secrets, exports actual prices, modifies a campaign, makes broker
orders or authorizes any trading. Output must be a new private file.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from ai_quant_lab.institutional.registry import HypothesisRecord

HYPOTHESIS_FIELDS = frozenset({
    "hypothesis_id", "campaign_id", "proposed_by", "strategy_name",
    "parameters", "statement", "economic_rationale", "falsification_criteria",
    "compatible_regimes", "parameters_locked_before_test", "created_at",
})
ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{2,79}\Z")
MAX_RECORD_BYTES = 16_384


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise ValueError("Ambiguous duplicate SQLite hypothesis JSON fields")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON hypothesis constant")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("Non-finite JSON hypothesis number")
    return parsed


def load_frozen_nova_hypothesis(
    database: str | Path, hypothesis_id: str,
) -> dict[str, Any]:
    """Read one exact immutable AQL V4 hypothesis, with no database writes."""
    path = Path(database)
    if (path.is_symlink() or not path.is_file()
            or type(hypothesis_id) is not str
            or not ID_PATTERN.fullmatch(hypothesis_id)):
        raise ValueError("Invalid private AQL research database or hypothesis ID")
    # SQLite URI read-only mode prevents schema creation and any write in this
    # process; do not instantiate InstitutionalResearchStore (its ctor initializes).
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            row = connection.execute(
                "SELECT payload FROM hypotheses WHERE hypothesis_id = ?",
                (hypothesis_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Cannot read private AI Quant Lab hypothesis store") from exc
    if row is None or type(row[0]) is not str or not 0 < len(row[0].encode("utf-8")) <= MAX_RECORD_BYTES:
        raise ValueError("Missing or oversized frozen Nova hypothesis")
    try:
        raw = json.loads(row[0], object_pairs_hook=_pairs,
                         parse_constant=_reject_constant, parse_float=_finite_float)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("Invalid immutable hypothesis JSON") from exc
    if type(raw) is not dict or set(raw) != HYPOTHESIS_FIELDS:
        raise ValueError("Unexpected frozen AI Quant Lab hypothesis fields")
    record = HypothesisRecord.model_validate(raw)
    if (record.proposed_by != "nova" or record.parameters_locked_before_test is not True
            or record.hypothesis_id != hypothesis_id):
        raise ValueError("Only exact locked Nova hypotheses are exportable")
    # Pydantic mode=json provides concrete standard JSON values; reject native
    # datetime objects and no additional agent fields are exported.
    exported: dict[str, Any] = record.model_dump(mode="json")
    if set(exported) != HYPOTHESIS_FIELDS:
        raise ValueError("Hypothesis schema changed without integration update")
    return exported


def export_nova_hypothesis(
    database: str | Path, hypothesis_id: str, output: str | Path,
) -> Path:
    """Export one private local JSON file with exclusive 0600 creation.

    No overwrite; existing paths (including symlinks) are preserved. A local
    file is not an approval to run research or to trade.
    """
    frozen = load_frozen_nova_hypothesis(database, hypothesis_id)
    path = Path(output)
    if not path.parent.is_dir() or path.is_symlink() or path.exists():
        raise ValueError("Destination must be a new file in an existing private folder")
    serialized = json.dumps(frozen, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(serialized) > MAX_RECORD_BYTES:
        raise ValueError("Nova export exceeds contract limit")
    fd: int | None = None
    created_by_us = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created_by_us = True
        with os.fdopen(fd, "wb") as out:
            fd = None
            out.write(serialized)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        # A concurrent creator might win the O_EXCL race. Never delete
        # someone else's newly created destination during our cleanup.
        if created_by_us and path.is_file():
            path.unlink()
        raise
    return path

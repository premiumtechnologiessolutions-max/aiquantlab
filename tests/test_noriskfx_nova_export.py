"""Real V4 SQLite Nova export contract for private NoRiskFX hand-off."""
from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3

import pytest

from ai_quant_lab.institutional.registry import HypothesisRecord
from ai_quant_lab.integrations.noriskfx_export import (
    HYPOTHESIS_FIELDS, load_frozen_nova_hypothesis, export_nova_hypothesis,
)
from scripts.export_noriskfx_nova import main


def hypothesis():
    return HypothesisRecord(
        hypothesis_id="hypothesis_12345678",
        campaign_id="campaign_12345678",
        proposed_by="nova",
        strategy_name="kalman_adaptive_trend",
        parameters={"lookback": 20, "threshold": 0.25},
        statement="A latent trend may predict the next completed candle direction.",
        economic_rationale="Price adjustment may take time following slow orders.",
        falsification_criteria=(
            "No positive out-of-sample value", "Extreme transaction cost sensitivity",
            "No stability over the declared sample"),
        compatible_regimes=("trending_up",),
        parameters_locked_before_test=True,
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
    )


def setup(tmp_path, *, item=None):
    path = tmp_path / "private-aql.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE hypotheses (hypothesis_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)")
        obj = hypothesis() if item is None else item
        db.execute("INSERT INTO hypotheses VALUES(?,?,?)",
                   (obj.hypothesis_id, obj.model_dump_json(), obj.created_at.isoformat()))
    return path, tmp_path / "export-only.json"


def test_reads_v4_hypothesis_with_exact_contract_without_modifying_database(tmp_path):
    db, out = setup(tmp_path)
    before = db.read_bytes()
    record = load_frozen_nova_hypothesis(db, "hypothesis_12345678")
    assert set(record) == HYPOTHESIS_FIELDS
    assert record["parameters"] == {"lookback": 20, "threshold": 0.25}
    assert record["proposed_by"] == "nova"
    assert record["parameters_locked_before_test"] is True
    assert db.read_bytes() == before
    assert not out.exists()


def test_export_is_private_new_file_and_exact_json_schema(tmp_path):
    db, output = setup(tmp_path)
    exported = export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert exported == output
    assert json.loads(output.read_text(encoding="utf-8")) == load_frozen_nova_hypothesis(db, "hypothesis_12345678")
    assert "approved_for_live" not in output.read_text(encoding="utf-8")


def test_no_clobber_on_repeat_even_if_original_export_modified(tmp_path):
    db, output = setup(tmp_path)
    export_nova_hypothesis(db, "hypothesis_12345678", output)
    content = output.read_bytes()
    with pytest.raises(ValueError, match="new file"):
        export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert output.read_bytes() == content


def test_cli_outputs_only_safe_status(tmp_path, capsys):
    db, output = setup(tmp_path)
    assert main(["--research-db", str(db), "--hypothesis-id", "hypothesis_12345678",
                 "--out", str(output)]) == 0
    logs = capsys.readouterr()
    assert "Private Nova hypothesis exported" in logs.out
    assert "kalman_adaptive_trend" not in logs.out
    assert "threshold" not in logs.out
    assert str(db) not in logs.out
    assert str(output) not in logs.out
    assert logs.err == ""
    assert output.exists()


@pytest.mark.parametrize("change", [
    {"approved_for_live": True},
    {"mt5_password": "private"},
    {"risk_score": 100},
])
def test_unexpected_private_or_performance_fields_are_not_exported(tmp_path, change):
    db, output = setup(tmp_path)
    with sqlite3.connect(db) as con:
        raw = json.loads(con.execute("SELECT payload FROM hypotheses").fetchone()[0])
        raw.update(change)
        con.execute("UPDATE hypotheses SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError, match="fields"):
        export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert not output.exists()


def test_forged_or_missing_id_rejected(tmp_path):
    db, output = setup(tmp_path)
    with pytest.raises(ValueError):
        export_nova_hypothesis(db, "hypothesis_not_present", output)
    with pytest.raises(ValueError):
        export_nova_hypothesis(db, "../private-db", output)
    assert not output.exists()


def test_forge_record_masquerading_as_nova_is_not_exported(tmp_path):
    db, output = setup(tmp_path)
    with sqlite3.connect(db) as con:
        raw = json.loads(con.execute("SELECT payload FROM hypotheses").fetchone()[0])
        raw["proposed_by"] = "forge"
        con.execute("UPDATE hypotheses SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError, match="Only exact locked Nova"):
        export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert not output.exists()


def test_unlocked_hypothesis_rejected(tmp_path):
    db, output = setup(tmp_path)
    with sqlite3.connect(db) as con:
        raw = json.loads(con.execute("SELECT payload FROM hypotheses").fetchone()[0])
        raw["parameters_locked_before_test"] = False
        con.execute("UPDATE hypotheses SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError, match="parameters_locked_before_test|Only exact locked Nova"):
        export_nova_hypothesis(db, "hypothesis_12345678", output)


def test_duplicate_json_and_nan_dont_get_canonicalized_silently(tmp_path):
    db, output = setup(tmp_path)
    with sqlite3.connect(db) as con:
        original = con.execute("SELECT payload FROM hypotheses").fetchone()[0]
        con.execute("UPDATE hypotheses SET payload=?", (original[:-1]+',"hypothesis_id":"forged"}',))
    with pytest.raises(ValueError, match="duplicate"):
        export_nova_hypothesis(db, "hypothesis_12345678", output)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE hypotheses SET payload=?", (original.replace('"threshold":0.25','"threshold":NaN'),))
    with pytest.raises(ValueError, match="Non-finite"):
        export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert not output.exists()


def test_refuses_symlinked_source_database(tmp_path):
    db, output = setup(tmp_path)
    link = tmp_path / "symbolic.sqlite3"
    try:
        link.symlink_to(db)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError):
        export_nova_hypothesis(link, "hypothesis_12345678", output)
    assert not output.exists()


def test_destination_symlink_is_never_followed(tmp_path):
    db, output = setup(tmp_path)
    existing = tmp_path / "protected.txt"
    existing.write_text("do not overwrite", encoding="utf-8")
    try:
        output.symlink_to(existing)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert existing.read_text() == "do not overwrite"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits only")
def test_private_export_has_no_group_or_world_read_permissions(tmp_path):
    db, output = setup(tmp_path)
    export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert output.stat().st_mode & 0o077 == 0


def test_readonly_export_does_not_touch_source_sqlite_pages(tmp_path):
    db, output = setup(tmp_path)
    before = db.read_bytes()
    export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert db.read_bytes() == before


def test_exclusive_creation_race_does_not_delete_concurrent_owners_file(tmp_path, monkeypatch):
    import ai_quant_lab.integrations.noriskfx_export as exporter
    db, output = setup(tmp_path)

    def race_open(*args, **kwargs):
        # Simulate another process creating the same path between the
        # initial exists() preflight and os.open(O_EXCL).
        output.write_text("concurrent owner", encoding="utf-8")
        raise FileExistsError("path acquired by concurrent writer")

    monkeypatch.setattr(exporter.os, "open", race_open)
    with pytest.raises(FileExistsError):
        exporter.export_nova_hypothesis(db, "hypothesis_12345678", output)
    assert output.read_text(encoding="utf-8") == "concurrent owner"

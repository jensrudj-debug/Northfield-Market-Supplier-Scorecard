"""Tests for pipeline/load_raw.py."""

from datetime import date

import duckdb
import pytest

from generator import generate as gen
from pipeline import load_raw

START, END = "2026-10-01", "2026-10-14"


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("raw")
    gen.generate(gen.load_config(gen.DEFAULT_CONFIG), out)
    return out


def warehouse_counts(db_path) -> tuple[dict, dict]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = [t for (t,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY 1").fetchall()]
        per_table = {t: con.execute(f"SELECT count(*) FROM raw.{t}").fetchone()[0] for t in tables}
        per_batch = dict(con.execute(
            "SELECT _batch_date::VARCHAR, count(*) FROM raw.receipts GROUP BY 1 ORDER BY 1").fetchall())
    return per_table, per_batch


def test_loading_same_range_twice_gives_identical_counts(raw_dir, tmp_path, monkeypatch):
    db_path = tmp_path / "otif.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    args = ["--raw-dir", str(raw_dir), "--start-date", START, "--end-date", END]

    load_raw.main(args)
    first = warehouse_counts(db_path)
    load_raw.main(args)
    second = warehouse_counts(db_path)

    assert first == second
    per_table, per_batch = first
    assert set(per_table) == {*load_raw.REFERENCE_TABLES, "receipts"}
    assert all(START <= d <= END for d in per_batch)
    expected = sum(
        sum(1 for _ in path.open()) - 1  # minus header
        for _, path in load_raw.list_receipt_partitions(raw_dir, *map(date.fromisoformat, (START, END))))
    assert per_table["receipts"] == expected > 0

"""Load generator output from data/raw/ into the DuckDB `raw` schema.

Reference files are fully replaced on every run. Receipt partitions
(receipts/recorded_date=YYYY-MM-DD/) are loaded idempotently: each partition is
deleted by _batch_date and re-inserted inside one transaction, so re-running a
date range never duplicates rows.

The database path comes from the DUCKDB_PATH environment variable.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
PARTITION_PREFIX = "recorded_date="

log = logging.getLogger("load_raw")

# Explicit types for every file; read_csv never infers. Receipts keep received_at
# and sku as text because the raw feed contains malformed values (see the
# generator's data_quality config) that staging is responsible for cleaning.
REFERENCE_TABLES = {
    "suppliers": {
        "supplier_id": "VARCHAR",
        "supplier_name": "VARCHAR",
        "category": "VARCHAR",
        "lead_time_days": "INTEGER",
    },
    "products": {
        "sku": "VARCHAR",
        "product_name": "VARCHAR",
        "supplier_id": "VARCHAR",
        "category": "VARCHAR",
        "case_pack": "INTEGER",
        "case_cost": "DECIMAL(10, 2)",
    },
    "distribution_centers": {
        "dc_id": "VARCHAR",
        "dc_name": "VARCHAR",
        "city": "VARCHAR",
        "state": "VARCHAR",
        "timezone": "VARCHAR",
    },
    "purchase_orders": {
        "po_number": "VARCHAR",
        "supplier_id": "VARCHAR",
        "dc_id": "VARCHAR",
        "order_date": "DATE",
        "requested_delivery_date": "DATE",
    },
    "po_lines": {
        "po_line_id": "VARCHAR",
        "po_number": "VARCHAR",
        "line_number": "INTEGER",
        "sku": "VARCHAR",
        "ordered_cases": "INTEGER",
        "line_status": "VARCHAR",
        "cancelled_date": "DATE",
    },
}
RECEIPT_COLUMNS = {
    "receipt_id": "VARCHAR",
    "po_line_id": "VARCHAR",
    "po_number": "VARCHAR",
    "dc_id": "VARCHAR",
    "sku": "VARCHAR",
    "received_at": "VARCHAR",
    "received_cases": "INTEGER",
    "rejected_cases": "INTEGER",
}
RECEIPT_AUDIT_COLUMNS = {
    "_batch_date": "DATE",
    "_loaded_at": "TIMESTAMP",
    "_source_file": "VARCHAR",
}


def duckdb_path_from_env() -> Path:
    value = os.environ.get("DUCKDB_PATH")
    if not value:
        raise SystemExit("DUCKDB_PATH is not set; see .env.example")
    return Path(value)


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _column_ddl(columns: dict[str, str]) -> str:
    return ", ".join(f"{name} {sql_type}" for name, sql_type in columns.items())


def read_csv_sql(path: Path, columns: dict[str, str]) -> str:
    """A read_csv call with a fixed schema and type inference turned off."""
    spec = ", ".join(f"{_sql_string(name)}: {_sql_string(sql_type)}" for name, sql_type in columns.items())
    return (f"read_csv({_sql_string(path.as_posix())}, header = true, auto_detect = false, "
            f"delim = ',', quote = '\"', columns = {{{spec}}})")


def run_in_transaction(con: duckdb.DuckDBPyConnection, statements) -> list:
    """Run (sql, params) pairs atomically; return each statement's first result row."""
    con.execute("BEGIN TRANSACTION")
    try:
        results = [con.execute(sql, params).fetchone() for sql, params in statements]
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return results


def load_reference_table(con, raw_dir: Path, table: str, columns: dict[str, str]) -> int:
    path = raw_dir / f"{table}.csv"
    _, (inserted,) = run_in_transaction(con, [
        (f"CREATE OR REPLACE TABLE raw.{table} ({_column_ddl(columns)})", []),
        (f"INSERT INTO raw.{table} SELECT * FROM {read_csv_sql(path, columns)}", []),
    ])
    return inserted


def list_receipt_partitions(raw_dir: Path, start: date | None, end: date | None) -> list[tuple[date, Path]]:
    partitions = []
    for folder in sorted((raw_dir / "receipts").glob(f"{PARTITION_PREFIX}*")):
        batch_date = date.fromisoformat(folder.name.removeprefix(PARTITION_PREFIX))
        if (start is None or batch_date >= start) and (end is None or batch_date <= end):
            partitions.append((batch_date, folder / "receipts.csv"))
    return partitions


def load_receipt_partition(con, raw_dir: Path, batch_date: date, path: Path, loaded_at: datetime) -> int:
    """Replace one recorded_date partition in raw.receipts."""
    names = ", ".join(RECEIPT_COLUMNS)
    audit = ", ".join(RECEIPT_AUDIT_COLUMNS)
    source_file = path.relative_to(raw_dir).as_posix()
    _, (inserted,) = run_in_transaction(con, [
        ("DELETE FROM raw.receipts WHERE _batch_date = ?", [batch_date]),
        (f"INSERT INTO raw.receipts ({names}, {audit}) "
         f"SELECT {names}, ?, ?, ? FROM {read_csv_sql(path, RECEIPT_COLUMNS)}",
         [batch_date, loaded_at, source_file]),
    ])
    return inserted


def load(db_path: Path, raw_dir: Path, start: date | None = None, end: date | None = None) -> dict[str, int]:
    """Load reference tables and receipt partitions; return rows loaded per table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = {}
    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for table, columns in REFERENCE_TABLES.items():
            loaded[f"raw.{table}"] = load_reference_table(con, raw_dir, table, columns)
            log.info("raw.%s: %d rows loaded (replaced)", table, loaded[f"raw.{table}"])

        con.execute("CREATE TABLE IF NOT EXISTS raw.receipts "
                    f"({_column_ddl(RECEIPT_COLUMNS)}, {_column_ddl(RECEIPT_AUDIT_COLUMNS)})")
        partitions = list_receipt_partitions(raw_dir, start, end)
        if not partitions:
            log.warning("no receipt partitions found in %s for %s..%s", raw_dir, start, end)
        loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
        total = 0
        for batch_date, path in partitions:
            n = load_receipt_partition(con, raw_dir, batch_date, path, loaded_at)
            log.debug("raw.receipts: %s -> %d rows", batch_date, n)
            total += n
        loaded["raw.receipts"] = total
        log.info("raw.receipts: %d rows loaded from %d partitions", total, len(partitions))
    return loaded


def main(argv: list[str] | None = None) -> dict[str, int]:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-date", type=date.fromisoformat, help="first receipt partition to load (default: all)")
    parser.add_argument("--end-date", type=date.fromisoformat, help="last receipt partition to load (default: all)")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)
    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return load(duckdb_path_from_env(), args.raw_dir, args.start_date, args.end_date)


if __name__ == "__main__":
    main()

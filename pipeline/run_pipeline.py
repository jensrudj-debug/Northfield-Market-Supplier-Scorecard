"""Run the OTIF pipeline end to end and record run metadata in the ops schema.

Modes:
    full   regenerate data/raw, load every partition, dbt build --full-refresh
    daily  load only the RUN_DATE receipt partition, incremental dbt build

Each step is timed into ops.run_log; dbt node results go to ops.model_run_stats.
Subprocess output is written to logs/<run_id>/<step>.log. The business date is
always the run date passed in (or the generator end_date); wall-clock time is
used only for started_at / finished_at.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = REPO_ROOT / "otif_dbt"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
LOG_ROOT = REPO_ROOT / "logs"
DEFAULT_GENERATOR_CONFIG = REPO_ROOT / "config" / "generator.yml"
REFERENCE_FILES = ["suppliers.csv", "products.csv", "distribution_centers.csv", "purchase_orders.csv", "po_lines.csv"]

OPS_DDL = [
    "CREATE SCHEMA IF NOT EXISTS ops",
    """CREATE TABLE IF NOT EXISTS ops.run_log (
        run_id VARCHAR, run_date DATE, mode VARCHAR, step VARCHAR,
        started_at TIMESTAMP, finished_at TIMESTAMP, duration_seconds DOUBLE, status VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS ops.model_run_stats (
        run_id VARCHAR, node_name VARCHAR, resource_type VARCHAR, status VARCHAR,
        execution_seconds DOUBLE, rows_out BIGINT)""",
]


@dataclass
class RunContext:
    run_id: str
    run_date: date
    mode: str
    db_path: Path
    log_dir: Path
    env: dict
    raw_dir: Path
    generator_config: Path


def utc_now() -> datetime:
    """Wall-clock time for run_log timing only; never a business date."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def default_run_date(generator_config: Path) -> date:
    with open(generator_config, encoding="utf-8") as f:
        return date.fromisoformat(str(yaml.safe_load(f)["end_date"]))


def dbt_executable() -> str:
    """Prefer the dbt installed next to this interpreter (the project venv)."""
    scripts = Path(sys.executable).parent
    for name in ("dbt.exe", "dbt"):
        if (scripts / name).exists():
            return str(scripts / name)
    found = shutil.which("dbt")
    if not found:
        raise FileNotFoundError("dbt not found; run make setup")
    return found


# --------------------------------------------------------------------------- ops tables

def init_ops_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        for ddl in OPS_DDL:
            con.execute(ddl)


def record_step_start(ctx: RunContext, step: str, started_at: datetime) -> None:
    with duckdb.connect(str(ctx.db_path)) as con:
        con.execute("INSERT INTO ops.run_log VALUES (?, ?, ?, ?, ?, NULL, NULL, 'running')",
                    [ctx.run_id, ctx.run_date, ctx.mode, step, started_at])


def record_step_end(ctx: RunContext, step: str, finished_at: datetime, duration: float, status: str) -> None:
    with duckdb.connect(str(ctx.db_path)) as con:
        con.execute("""UPDATE ops.run_log SET finished_at = ?, duration_seconds = ?, status = ?
                       WHERE run_id = ? AND step = ?""",
                    [finished_at, duration, status, ctx.run_id, step])


def record_skipped_step(ctx: RunContext, step: str) -> None:
    with duckdb.connect(str(ctx.db_path)) as con:
        con.execute("INSERT INTO ops.run_log VALUES (?, ?, ?, ?, NULL, NULL, NULL, 'skipped')",
                    [ctx.run_id, ctx.run_date, ctx.mode, step])


# --------------------------------------------------------------------------- steps

def run_logged(ctx: RunContext, step: str, args: list[str], cwd: Path) -> None:
    """Run a subprocess with output captured to logs/<run_id>/<step>.log."""
    log_path = ctx.log_dir / f"{step}.log"
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            subprocess.run(args, cwd=cwd, env=ctx.env, stdout=log, stderr=subprocess.STDOUT, check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"{step} exited with {exc.returncode}; see {log_path}") from exc


def run_dbt(ctx: RunContext, step: str, dbt_args: list[str]) -> None:
    run_logged(ctx, step, [dbt_executable(), *dbt_args, "--profiles-dir", "."], DBT_DIR)


def step_generate(ctx: RunContext) -> None:
    run_logged(ctx, "generate", [sys.executable, "generator/generate.py",
                                 "--config", str(ctx.generator_config), "--out-dir", str(ctx.raw_dir)], REPO_ROOT)


def step_check_raw_data(ctx: RunContext) -> None:
    missing = [name for name in REFERENCE_FILES if not (ctx.raw_dir / name).exists()]
    if missing or not (ctx.raw_dir / "receipts").is_dir():
        raise FileNotFoundError(f"{ctx.raw_dir} is incomplete ({missing or 'receipts/'}); run make generate first")


def step_load_raw(ctx: RunContext) -> None:
    args = [sys.executable, "pipeline/load_raw.py", "--raw-dir", str(ctx.raw_dir)]
    if ctx.mode == "daily":
        args += ["--start-date", ctx.run_date.isoformat(), "--end-date", ctx.run_date.isoformat()]
    run_logged(ctx, "load_raw", args, REPO_ROOT)


def step_dbt_deps(ctx: RunContext) -> None:
    run_dbt(ctx, "dbt_deps", ["deps"])


def step_dbt_source_freshness(ctx: RunContext) -> None:
    run_dbt(ctx, "dbt_source_freshness", ["source", "freshness"])


def step_dbt_build(ctx: RunContext) -> None:
    (DBT_DIR / "target" / "run_results.json").unlink(missing_ok=True)  # so stats come from this build only
    run_dbt(ctx, "dbt_build", ["build", *(["--full-refresh"] if ctx.mode == "full" else [])])


def step_record_model_stats(ctx: RunContext) -> None:
    """Copy each node result from dbt's run_results.json into ops.model_run_stats.

    rows_out is the row count of the built relation for models and the number of
    failing rows for tests.
    """
    results_path = DBT_DIR / "target" / "run_results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"{results_path} not found; dbt build did not run")
    results = json.loads(results_path.read_text(encoding="utf-8"))["results"]

    with duckdb.connect(str(ctx.db_path)) as con:
        rows = []
        for result in results:
            resource_type, _, node_name = result["unique_id"].split(".", 2)
            if resource_type in ("model", "seed", "snapshot") and result.get("relation_name"):
                rows_out = con.execute(f"SELECT count(*) FROM {result['relation_name']}").fetchone()[0]
            else:
                rows_out = result.get("failures")
            rows.append([ctx.run_id, node_name, resource_type, result["status"], result["execution_time"], rows_out])
        con.executemany("INSERT INTO ops.model_run_stats VALUES (?, ?, ?, ?, ?, ?)", rows)


STEPS = {
    "full": [
        ("generate", step_generate),
        ("load_raw", step_load_raw),
        ("dbt_deps", step_dbt_deps),
        ("dbt_source_freshness", step_dbt_source_freshness),
        ("dbt_build", step_dbt_build),
        ("record_model_stats", step_record_model_stats),
    ],
    "daily": [
        ("check_raw_data", step_check_raw_data),
        ("load_raw", step_load_raw),
        ("dbt_deps", step_dbt_deps),
        ("dbt_source_freshness", step_dbt_source_freshness),
        ("dbt_build", step_dbt_build),
        ("record_model_stats", step_record_model_stats),
    ],
}
# Still recorded after a failed build, so failing tests show up in ops.model_run_stats.
RUN_AFTER_BUILD_FAILURE = {"record_model_stats"}


# --------------------------------------------------------------------------- driver

def print_summary(ctx: RunContext, outcomes: list[tuple[str, str, float | None, str]]) -> None:
    print(f"\nRun {ctx.run_id}  mode={ctx.mode}  run_date={ctx.run_date}  logs={ctx.log_dir}")
    print(f"{'step':<22} {'status':<9} {'seconds':>8}  detail")
    print(f"{'-' * 22} {'-' * 9} {'-' * 8}  {'-' * 30}")
    for step, status, duration, detail in outcomes:
        seconds = f"{duration:8.1f}" if duration is not None else f"{'-':>8}"
        print(f"{step:<22} {status:<9} {seconds}  {detail}")

    with duckdb.connect(str(ctx.db_path), read_only=True) as con:
        stats = con.execute("""SELECT resource_type, status, count(*) FROM ops.model_run_stats
                               WHERE run_id = ? GROUP BY ALL ORDER BY 1, 2""", [ctx.run_id]).fetchall()
    if stats:
        print("\ndbt nodes: " + ", ".join(f"{rtype} {status}={n}" for rtype, status, n in stats))


def run_pipeline(mode: str, run_date: date, raw_dir: Path = DEFAULT_RAW_DIR,
                 generator_config: Path = DEFAULT_GENERATOR_CONFIG) -> bool:
    db_path = Path(os.environ.get("DUCKDB_PATH") or sys.exit("DUCKDB_PATH is not set; see .env.example"))
    run_id = uuid.uuid4().hex[:12]
    ctx = RunContext(
        run_id=run_id,
        run_date=run_date,
        mode=mode,
        db_path=db_path,
        log_dir=LOG_ROOT / run_id,
        env={**os.environ, "RUN_DATE": run_date.isoformat(), "PYTHONIOENCODING": "utf-8"},
        raw_dir=raw_dir.resolve(),
        generator_config=generator_config.resolve(),
    )
    ctx.log_dir.mkdir(parents=True, exist_ok=True)
    init_ops_tables(db_path)

    outcomes, failed_step = [], None
    for step, func in STEPS[mode]:
        if failed_step and not (failed_step == "dbt_build" and step in RUN_AFTER_BUILD_FAILURE):
            record_skipped_step(ctx, step)
            outcomes.append((step, "skipped", None, f"after {failed_step} failed"))
            continue
        started_at, t0 = utc_now(), time.perf_counter()
        record_step_start(ctx, step, started_at)
        try:
            func(ctx)
            status, detail = "success", ""
        except Exception as exc:  # recorded, then reported in the summary and exit code
            status, detail = "failed", str(exc)
            failed_step = failed_step or step
        duration = time.perf_counter() - t0
        record_step_end(ctx, step, utc_now(), duration, status)
        outcomes.append((step, status, duration, detail))

    print_summary(ctx, outcomes)
    return failed_step is None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=sorted(STEPS), required=True)
    parser.add_argument("--run-date", type=date.fromisoformat,
                        help="business date (required for daily; full defaults to the generator end_date)")
    parser.add_argument("--config", type=Path, default=DEFAULT_GENERATOR_CONFIG, help="generator config (full mode)")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="raw data directory")
    args = parser.parse_args(argv)
    if args.mode == "daily" and args.run_date is None:
        parser.error("--run-date is required for --mode daily")
    ok = run_pipeline(args.mode, args.run_date or default_run_date(args.config), args.raw_dir, args.config)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

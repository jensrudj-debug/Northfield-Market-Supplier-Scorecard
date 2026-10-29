# ADR 0001: Warehouse
- Status: Accepted
- Date: 2026-10-28

## Context
Procurement needs a weekly OTIF scorecard that one engineer can build, test, and rerun.
The charter requires a full run from a clean clone with one command.
We need a SQL engine that dbt supports and that runs without servers or accounts.

## Options considered
1. DuckDB single file.
   - Pros: no install beyond pip, one file, fast columnar SQL, dbt-duckdb adapter.
   - Cons: one writer at a time, no users or roles, limited to one machine.
2. Postgres in Docker.
   - Pros: real client-server database, concurrent readers and writers, roles.
   - Cons: needs Docker running, slower for analytic scans, more setup per clone.
3. Cloud warehouse (BigQuery or Snowflake).
   - Pros: managed scaling, access control, shared access for analysts and BI tools.
   - Cons: needs an account, credentials, and billing; not clone-and-run.

## Decision
We chose DuckDB in a single file.
It needs zero setup, so anyone can clone the repo and reproduce every number.
The full 1x dataset fits in an 11.8 MB database file.

## What we gave up
- Concurrent writers. DuckDB allows one writer, so a dashboard cannot read while dbt builds.
- Access control. There are no users, roles, or row-level security.
- Managed scaling. Compute is limited to the laptop running the pipeline.
- Shared access. Analysts cannot query one central copy; each clone has its own file.

## Revisit when
- More than one concurrent consumer or dashboard needs the data.
- Data no longer fits in laptop memory (this machine has 7.6 GB RAM).
- Procurement requires role-based access to supplier scores.

## Evidence in repo
- `otif_dbt/profiles.yml`: `type: duckdb`, path from `DUCKDB_PATH`.
- `Makefile`: `DUCKDB_PATH ?= $(CURDIR)/warehouse/otif.duckdb`.
- `pipeline/load_raw.py` and `pipeline/run_pipeline.py` open the file with `duckdb.connect`.
- Measured: `warehouse/otif.duckdb` was 11,808,768 bytes after the clean full run `6ee966cf8190`.
- Measured: the 10x warehouse `warehouse/otif_10x.duckdb` was 97,529,856 bytes after its first full run `abb809f44412`.
- See `docs/cost_profile.md` for the full measurements.

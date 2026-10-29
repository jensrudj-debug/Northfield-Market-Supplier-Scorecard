# ADR 0006: Refresh strategy
- Status: Accepted
- Date: 2026-10-28

## Context
The charter requires a daily refresh by 6:00 a.m. Central.
Receipts arrive daily, but a late receipt can change the outcome of a line due days earlier.
The refresh must be fast enough daily and still restate past lines correctly.

## Options considered
1. Full refresh of everything every day.
   - Pros: simplest; always correct.
   - Cons: cost grows with history.
2. Incremental everywhere.
   - Pros: cheapest per run.
   - Cons: past lines and weeks need careful restatement logic; easy to get wrong.
3. `fct_receipts` incremental; `fct_po_lines` and the weekly mart rebuilt in full.
   - Pros: receipts append cheaply; line outcomes always reflect every known receipt.
   - Cons: line and mart rebuild cost still grows with history.

## Decision
We chose option 3. `fct_receipts` uses delete+insert on `receipt_id`.
Each run reprocesses receipts recorded within `receipt_lookback_days` (7) of the latest loaded.
`fct_po_lines` and `mart_supplier_otif_weekly` rebuild fully, so late receipts restate past lines.

## What we gave up
- Some compute every run in exchange for correctness.
- Daily runs averaged 51.9 s versus 82.5 to 139.8 s for full runs.
- `fct_receipts` saves little: 0.56 to 0.78 s incremental vs 0.76 to 1.71 s full at 1x.
- That is because the upstream staging and intermediate models are views that rescan all receipts.
- Backfills need `make run RUN_DATE=...`. A backdated `make daily` leaves later receipts behind.

## Revisit when
- The full rebuild of `fct_po_lines` exceeds [AGREED SHARE] of the refresh window.
- At 10x volume it took 2.84 s and 4.46 s; at 1x, 0.87 to 2.21 s.
- TODO: agree on the refresh window start time; the charter only gives the 6:00 a.m. deadline.

## Evidence in repo
- `otif_dbt/models/marts/fct_receipts.sql`: `materialized='incremental'`, `incremental_strategy='delete+insert'`, `unique_key='receipt_id'`.
- `otif_dbt/dbt_project.yml`: `receipt_lookback_days: 7`; marts are `+materialized: table`.
- `pipeline/run_pipeline.py`: `full` mode adds `--full-refresh`; `daily` mode loads one partition.
- Measured full runs (`ops.run_log`): `229a3d1b24a8` 139.8 s (clean), `c0efa8be1577` 86.4 s, `94f3e99b1a3f` 82.5 s.
- Measured daily runs: `b5abcf47bc65` 53.3 s, `07bb6651cb55` 51.8 s, `3e5dade84af2` 50.5 s.
- Measured 10x full runs: `e41cb7ac2a3f` 129.1 s, `0258dc3d4793` 156.6 s.
- `fct_receipts` row counts (`ops.model_run_stats`) match after a full run and after the daily chain: 86,958.

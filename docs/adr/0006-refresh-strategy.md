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
- Daily runs averaged 100.5 s versus 128.9 to 130.6 s for full runs.
- `fct_receipts` saves little: 1.14 to 1.60 s incremental vs 1.59 to 1.62 s full at 1x.
- That is because the upstream staging and intermediate models are views that rescan all receipts.
- Backfills need `make run RUN_DATE=...`. A backdated `make daily` leaves later receipts behind.

## Revisit when
- The full rebuild of `fct_po_lines` exceeds 6 minutes: 10% of an assumed 5:00-6:00 a.m. Central window.
- The charter sets only the 6:00 a.m. deadline; the one-hour window is our assumption.
- In 10x full runs it took 2.41 s and 4.49 s; in 1x full runs, 1.88 to 2.49 s.

## Evidence in repo
- `otif_dbt/models/marts/fct_receipts.sql`: `materialized='incremental'`, `incremental_strategy='delete+insert'`, `unique_key='receipt_id'`.
- `otif_dbt/dbt_project.yml`: `receipt_lookback_days: 7`; marts are `+materialized: table`.
- `pipeline/run_pipeline.py`: `full` mode adds `--full-refresh`; `daily` mode loads one partition.
- Measured full runs (`ops.run_log`): `6ee966cf8190` 128.9 s (clean), `95c314d97730` 130.6 s.
- Measured daily runs: `d3b6a3628b93` 109.8 s, `9c2bc60f7e57` 90.3 s, `fc411770157a` 101.4 s.
- Measured 10x full runs: `abb809f44412` 134.4 s, `6ada1565695c` 234.5 s.
- `docs/cost_profile.md` estimates $2.07 per month at 1x and $2.25 at 10x on Snowflake Standard X-Small.
- `fct_receipts` row counts (`ops.model_run_stats`) match after a full run and after the daily chain: 86,958.

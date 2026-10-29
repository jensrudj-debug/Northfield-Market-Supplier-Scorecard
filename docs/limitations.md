# Known limitations and assumptions

- Synthetic data: supplier behavior is assumed, not observed (ADR 0002).
- DC deliveries only; direct-store delivery vendors are not covered.
- Dates, not appointment times: 6 hours late on the same day counts as on time (ADR 0004).
- No root-cause attribution: carrier delays, DC dock congestion, and supplier faults all count against the supplier.
- Global thresholds; real vendor agreements often set OTIF targets per supplier or category.
- Supplier attributes are current-state only. `raw.suppliers` is replaced on every load, so a rename or category change restates past weeks.
- No scheduler, retries, or alerting; a failed run requires a person to notice.
- Line-count weighting (ADR 0003) and supplier-week grain (ADR 0009).
- Rejected cases count as received; `int_po_lines__receipt_rollup.sql` sums `received_cases`, not net of `rejected_cases` (found in review).
- A line whose only receipts are unscoreable (missing timestamp, zero cases) is scored as not received and can become missed (found in review).
- A line due on `run_date` with no receipt yet counts as not on time until a receipt is recorded (found in review).
- `make daily` only moves forward. A backdated daily run fails tests; backfills need `make run RUN_DATE=...` (found in review).
- `make setup`, `make build`, `make test`, `make docs`, and `make clean` only echo text; they do nothing yet (found in review).
- The pytest suites in `generator/tests` and `pipeline/tests` are not run by any make target (found in review).
- `dbt deps` and `dbt source freshness` run every time, adding 24.6–51.6 s per run (found in review; `docs/cost_profile.md`).
- DuckDB files do not shrink on rerun. The 10x file grew from 106.2 MB to 156.3 MB after one more full run (found in review).
- `pipeline/run_pipeline.py` hard-codes `data/raw` and `config/generator.yml`; `make run-10x` overrides them at runtime (found in review).
- The generator supports at most 128 suppliers (16 name prefixes x 8 suffixes) (found in review).
- Source freshness compares `_loaded_at` to wall-clock time, not `run_date`, so reloading old data always looks fresh (found in review).

# Data quality assumptions

| Assumption | Where it is relied on | If violated |
|---|---|---|
| `receipt_id` is the DC system's true key; rows sharing it are re-sends. | `stg_receipts.sql` keeps one row per `receipt_id`. | Two real receipts sharing an id: one is silently dropped and the line may look short. |
| Recording lag never exceeds the provisional window (7 days). Observed max is 5 days. | `is_provisional` in `int_po_line_fulfillment.sql`. | A week already marked final changes score with no warning. |
| `received_at` is DC-local time in ISO or `MM/DD/YYYY HH:MM` format. | `try_strptime` in `stg_receipts.sql`. | Other formats become null; the receipt is unscoreable; `not_null` test warns. |
| `requested_delivery_date` on the PO header applies to every line. | `int_po_line_fulfillment.sql` joins the header date. | Line-level date changes are invisible; lines are scored against the wrong date. |
| Reference files are complete snapshots. | `load_raw.py` uses `CREATE OR REPLACE TABLE`. | A partial `po_lines.csv` silently removes lines from the scorecard. |
| Raw receipt partitions are never deleted. | `load_raw.py` only loads partitions that exist on disk. | A deleted partition's rows stay in `raw.receipts` until the table is rebuilt. |
| Receipts point at a real `po_line_id`. | `int_receipts__classified.sql` flags orphans. | Orphans are excluded from OTIF; a `relationships` test warns (174 per run at 1x). |
| Zero or negative case counts are errors, not reversals. | `receipt_issue = 'nonpositive_cases'`. | A real reversal is ignored, so the original receipt still counts in full. |
| SKU drift is only case and surrounding spaces. | `upper(trim(sku))` in `stg_receipts.sql`. | Other drift fails the `relationships` test on `sku`, which errors and stops the build. |

# What breaks first under load

The order differs from the planned list. The 10x run showed the receipt chain growing fastest, so it is first.
Measurements come from `docs/cost_profile.md`.

1. **Receipt dedup and parsing in the staging views.**
   - Evidence: `fct_receipts` went from 0.76–1.71 s at 1x to 8.25–9.76 s at 10x (4.8–12.8x).
   - Staging and intermediate are views, so `stg_receipts` (dedup window plus timestamp parsing) reruns in every build.
   - The incremental `fct_receipts` took 0.56–0.78 s, close to its 0.76 s full refresh, so incrementality saves little.
   - Fix: materialize the deduplicated receipts incrementally, or dedup during load.
   - Memory note: the planned item named "window functions in the rolling-average step". There is no rolling average in the code.
   - The only window function is `row_number()` in `stg_receipts.sql`. Peak memory: TODO: measure, because no run recorded memory use.
2. **Full rebuild of `fct_po_lines`.**
   - Evidence: 0.87–2.21 s at 1x, 2.84–4.46 s at 10x. It rebuilds all history every run.
   - Fix: make it incremental, with a lookback covering `missed_after_days` (7) plus the maximum recording lag (5 days observed).
3. **DuckDB allows one writer, so dashboards reading during a build conflict.**
   - Evidence: TODO: measure. No concurrent reader was tested.
   - Fix: move to a client-server warehouse (ADR 0001 revisit trigger).

At 10x, no step was near a limit: total runs took 129.1–156.6 s on a laptop with 7.6 GB RAM.

# Out of scope

- Direct-store delivery.
- Carrier performance.
- Chargeback dollar calculation.
- Dashboards.

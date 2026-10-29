# ADR 0007: Late-arriving data
- Status: Accepted
- Date: 2026-10-28

## Context
Receipts are sometimes recorded days after the truck arrived.
A late-recorded receipt can turn last week's failure into a pass, or reveal a missed line.
Vendor managers review scores every Monday and need to know which scores can still move.

## Options considered
1. Freeze each week when it closes.
   - Pros: scores never change after review.
   - Cons: late-recorded receipts are ignored, so some suppliers are scored unfairly.
2. Silently restate.
   - Pros: always uses all known data.
   - Cons: numbers change with no warning; disputes over "what we saw Monday".
3. Restate, with an `is_provisional` flag for a fixed period after week end.
   - Pros: correct data, and readers know which weeks can still change.
   - Cons: the newest week can still move after it is reviewed.

## Decision
We restate and flag. A week is provisional until 7 days after it ends.
The flag is computed from `var('run_date')`, never `current_date`.
Rerunning any past run date therefore reproduces the same scorecard.

## What we gave up
- The most recent week can still move on the Monday it is reviewed.
- Suppliers may dispute a score that changed after the review.
- Receipts recorded more than 7 days late change a week already marked final.

## Revisit when
- A vendor agreement requires frozen scores.
- Average recording lag drops below 2 days. It is 0.06 days today (max 5 days).

## Evidence in repo
- `otif_dbt/dbt_project.yml`: `run_date` from `env_var('RUN_DATE')`; `provisional_days_after_week: 7`.
- `otif_dbt/models/intermediate/int_po_line_fulfillment.sql`: `is_provisional` uses `as_of_date` from `var("run_date")`.
- `otif_dbt/models/intermediate/int_receipts__classified.sql`: keeps only receipts with `recorded_date <= run_date`.
- `grep` for `current_date`, `now()`, and `current_timestamp` in `otif_dbt/models` and `otif_dbt/tests` finds nothing.
- Tests:
  - `test_fulfillment_provisional_last_provisional_day` and `test_fulfillment_provisional_first_final_day` (unit).
  - `otif_dbt/tests/assert_provisional_weeks_are_the_most_recent.sql`.
  - `otif_dbt/tests/assert_nothing_known_after_run_date.sql`.
- Measured in `main_marts.fct_receipts` at 1x:
  - Average `recorded_date - received_date` is 0.06 days, maximum 5.
  - 1,736 receipts were recorded late.
- Mismatch: the variable is named `provisional_days_after_week`, not `provisional_days`.

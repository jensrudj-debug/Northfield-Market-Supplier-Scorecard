# ADR 0008: Orphan receipts
- Status: Accepted
- Date: 2026-10-28

## Context
Some receipts reference a PO line that does not exist, usually from keying errors at the dock.
They cannot be scored, because OTIF is measured per PO line.
Procurement must not lose them silently, but one bad record should not block Monday's scorecard.

## Options considered
1. Drop orphans silently.
   - Pros: simplest; scorecard always builds.
   - Cons: receiving errors disappear and nobody fixes them.
2. Fail the pipeline on any orphan.
   - Pros: forces a fix.
   - Cons: one keying error blocks every supplier's scorecard.
3. Quarantine to `int_receipts__orphaned`; warn below `max_orphan_rate`, error above it.
   - Pros: scorecard builds; orphans stay visible; a spike still stops the run.
   - Cons: someone must read and act on the warnings.

## Decision
We quarantine and warn. Orphans are kept but excluded from OTIF.
A test warns when orphans exist, so the run continues and the issue stays visible.
The run observed 174 orphans out of 86,958 receipts (0.20%), on seed 20261025 at 1x.

## What we gave up
- Bad records do not stop the pipeline, so someone must read the warning.
- Cases on orphan receipts never count toward any supplier's fill rate.
- With no error threshold implemented, a sudden spike in orphans also only warns.

## Revisit when
- The orphan rate trends upward across runs.
- Finance needs every receipt reconciled to a PO.

## Evidence in repo
- `otif_dbt/models/intermediate/int_receipts__classified.sql`: `receipt_issue = 'orphan_po_line'` when no PO line matches.
- `otif_dbt/models/marts/fct_receipts.sql` keeps orphan rows with `is_scoreable = false`.
- `otif_dbt/models/staging/_staging_models.yml`: `relationships` test on `stg_receipts.po_line_id` with `severity: warn`.
- Measured: that test returned WARN 174 in every 1x run in `ops.model_run_stats` (for example `6ee966cf8190`).
- Measured at 10x: the same test returned WARN 1,736 in every 10x run (for example `abb809f44412`).
- Mismatch: there is no `int_receipts__orphaned` model; orphans are flagged in place via `receipt_issue`.
- Mismatch: there is no `max_orphan_rate` var and no error threshold; the test only warns.
- Mismatch: the seed is 20261025, not 42.

# ADR 0009: Scorecard grain
- Status: Accepted
- Date: 2026-10-28

## Context
Vendor managers meet every Monday to decide which suppliers to escalate, charge back, or renegotiate.
They manage suppliers as whole accounts, not per distribution center.
The published scorecard needs one row per decision they make.

## Options considered
1. Supplier x week.
   - Pros: matches the Monday review; enough lines per row to be meaningful.
   - Cons: hides a supplier that fails at only one DC.
2. Supplier x DC x week.
   - Pros: shows DC-specific problems.
   - Cons: twice the rows; many rows with very few lines.
3. Supplier x month.
   - Pros: more lines per row, steadier scores.
   - Cons: too slow for a weekly review; problems surface weeks late.

## Decision
The scorecard is supplier x ISO week, both DCs combined.
This matches the Monday vendor review.
`fct_po_lines` still carries `dc_id`, so a per-DC view can be queried ad hoc.

## What we gave up
- The scorecard cannot show a supplier that fails at only one DC.
- Small weeks swing hard. Eligible lines per supplier-week range from 1 to 100 (median 18).
- One missed line in a 1-line week moves OTIF % from 100 to 0.

## Revisit when
- Procurement starts managing suppliers per DC.
- Vendor agreements set different targets per DC.

## Evidence in repo
- `otif_dbt/models/marts/mart_supplier_otif_weekly.sql`: `group by supplier_id, attribution_week_start`.
- `otif_dbt/models/marts/_marts_models.yml`: `unique_combination_of_columns` on `supplier_id, attribution_week_start`.
- `otif_dbt/models/marts/fct_po_lines.sql`: includes `dc_id`.
- `otif_dbt/tests/assert_weekly_mart_reconciles_to_fct_po_lines.sql`: weekly totals equal line totals.
- Measured: `mart_supplier_otif_weekly` had 3,995 rows in all six 1x runs in `ops.model_run_stats`.
- Measured after run `94f3e99b1a3f`: 1 to 100 eligible lines per supplier-week, median 18.
- Measured at 10x: 4,738 rows (run `0258dc3d4793`), so the scorecard stays small as volume grows.

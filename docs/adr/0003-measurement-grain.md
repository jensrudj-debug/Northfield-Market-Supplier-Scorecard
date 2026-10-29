# ADR 0003: Measurement grain
- Status: Accepted
- Date: 2026-10-28

## Context
Vendor managers need one OTIF number per supplier that they can explain line by line.
A purchase order mixes many SKUs, and lines range from 1 case to hundreds.
The unit we count decides which supplier failures show up in the score.

## Options considered
1. PO-line OTIF (one SKU on one PO to one DC).
   - Pros: matches how DCs receive; each failure traces to one SKU and one date.
   - Cons: a 1-case line weighs the same as a 200-case line.
2. PO-level OTIF (a PO passes only if every line passes).
   - Pros: strict; matches "the whole order arrived complete".
   - Cons: one short SKU fails a 20-line PO; hides which SKUs fail.
3. Case-weighted OTIF.
   - Pros: reflects volume impact on shelves.
   - Cons: large lines dominate; small but critical SKUs barely register.

## Decision
PO-line OTIF is the primary metric, as the charter's measurement grain states.
Case fill rate is a secondary, volume-weighted metric beside it.
Line-level results let a vendor manager show a supplier the exact failing lines.

## What we gave up
- A 1-case line counts the same as a 200-case line in OTIF %.
- A supplier can score well on OTIF % while missing a few very large lines.
- PO-level completeness is not reported; it must be queried from `fct_po_lines`.

## Revisit when
- A vendor compliance agreement defines OTIF by case or by PO.
- Procurement finds OTIF % and case fill rate disagree often enough to cause disputes.

## Evidence in repo
- `docs/charter.md`: "Measurement grain: One purchase order (PO) line".
- `otif_dbt/models/intermediate/int_po_line_fulfillment.sql`: one row per PO line with OTIF flags.
- `otif_dbt/models/marts/fct_po_lines.sql`: published line-level fact; `unique` test on `po_line_id`.
- `otif_dbt/models/marts/mart_supplier_otif_weekly.sql`: `otif_pct` is `otif_lines / eligible_lines`.
- The same file computes `case_fill_rate_pct` from `eligible_cases_received / eligible_cases_ordered`.
- `otif_dbt/tests/assert_weekly_otif_pct_matches_line_detail.sql`: OTIF % recomputes from lines.
- Measured: 88,057 rows in `fct_po_lines` at 1x (run `229a3d1b24a8`).

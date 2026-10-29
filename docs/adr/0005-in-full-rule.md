# ADR 0005: In-full rule
- Status: Accepted
- Date: 2026-10-28

## Context
Stores need the full quantity when it was promised, not later.
Case counts at the dock vary slightly through damage, rounding, and miscounts.
Suppliers sometimes ship more than ordered, which takes dock and storage space.

## Options considered
1. 100% of ordered cases.
   - Pros: unambiguous.
   - Cons: one miscounted case fails a large line.
2. At least 98% of ordered cases received inside the on-time window.
   - Pros: small tolerance; ties quantity to timing.
   - Cons: a late remainder earns no credit.
3. Cumulative quantity regardless of timing.
   - Pros: credits suppliers who eventually complete the order.
   - Cons: a line delivered a week late could still count as in full.

## Decision
A line is in full when cases received inside the on-time window reach 98% of ordered cases.
Late cases do not count toward in full. Over 105% is flagged as over-shipment.
An over-shipped line still counts as in full, as the charter says.

## What we gave up
- Suppliers who complete an order late get no partial credit in OTIF.
- A 2% tolerance may hide chronic small shorts on large lines.
- Rejected cases still count as received: in-full uses `received_cases`, not net of `rejected_cases`.
- There is no rounding: 48 of 49 cases (97.96%) fails.

## Revisit when
- Category managers report that the 98% tolerance hides material shortages.
- Procurement decides rejected cases should not count as received.

## Evidence in repo
- `otif_dbt/dbt_project.yml`: `in_full_threshold: 0.98`, `over_shipment_threshold: 1.05`.
- `otif_dbt/models/intermediate/int_po_lines__receipt_rollup.sql`: `cases_received_in_window` sums only in-window receipts.
- `otif_dbt/models/intermediate/int_po_line_fulfillment.sql`: `is_in_full` compares `cases_received_in_window` to the threshold.
- The same file sets `is_over_shipment` from `cases_received_total`, which includes late cases.
- Unit tests in `otif_dbt/models/intermediate/_intermediate_models.yml`:
  - `test_fulfillment_in_full_threshold`: 98%, 97%, 48 of 49, and a late remainder.
  - `test_fulfillment_over_shipment`: 105% not flagged, 106% flagged, both in full.

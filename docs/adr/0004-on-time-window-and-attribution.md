# ADR 0004: On-time window and attribution
- Status: Accepted
- Date: 2026-10-28

## Context
Suppliers and buyers argue about what "on time" means and which week a delivery counts in.
We only have receipt dates and times, not dock appointment windows.
The Monday vendor review needs each line assigned to exactly one week.

## Options considered
1. Exact requested date only.
   - Pros: simplest rule to explain.
   - Cons: penalizes helpful one-day-early deliveries.
2. Window of 1 day early to 0 days late, at DC-local date level.
   - Pros: tolerates early arrival, no tolerance for late; uses data we have.
   - Cons: ignores time of day.
3. Hour-level appointment window.
   - Pros: most precise for dock planning.
   - Cons: we do not capture appointment times.

Attribution options: the week of the receipt, or the week of the requested date.
Receipt week moves late lines into later weeks and lets missed lines vanish.

## Decision
A first receipt is on time from 1 day before to 0 days after the requested date.
Dates are DC-local dates. Lines belong to the ISO week (Monday start) of the requested date.
Requested-date attribution keeps every line in the week it was promised.

## What we gave up
- Hour-level accuracy: 6 hours late on the right day counts as on time.
- A receipt at 23:59 is on time; one at 00:01 the next day is late.
- Leniency toward 1-day-early deliveries that consume dock and storage capacity.

## Revisit when
- Appointment times are captured in the receiving system.
- Procurement starts penalizing early arrivals.

## Evidence in repo
- `otif_dbt/dbt_project.yml`: `on_time_days_early: 1`, `on_time_days_late: 0`.
- `otif_dbt/models/intermediate/int_receipts__classified.sql`: `days_from_requested` and `is_in_on_time_window`.
- `otif_dbt/models/intermediate/int_po_line_fulfillment.sql`: `is_on_time` uses the first receipt date.
- The same file sets `attribution_week_start` with `date_trunc('week', ...)` and `attribution_iso_week` with `%G-W%V`.
- Unit tests in `otif_dbt/models/intermediate/_intermediate_models.yml`:
  - `test_fulfillment_on_time_window_edges`: -2, -1, 0, +1 days.
  - `test_on_time_window_and_receipt_issues`: 23:59 vs 00:01.
  - `test_fulfillment_iso_week_across_year_end`: 2027-01-01 to 2026-W53.
- `fct_po_lines` test: `isodow(attribution_week_start) = 1` (`otif_dbt/models/marts/_marts_models.yml`).

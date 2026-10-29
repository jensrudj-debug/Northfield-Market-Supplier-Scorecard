-- Business rule: once a week's score is final (not provisional), every eligible
-- line in it has a settled outcome: it was either received or declared missed.
-- A final score must never depend on a delivery that is still pending.
-- Returns eligible lines in final weeks with no receipt that are not missed.
select
    po_line_id,
    supplier_id,
    requested_delivery_date,
    attribution_week_start
from {{ ref('fct_po_lines') }}
where is_eligible
  and not is_provisional
  and first_receipt_date is null
  and not is_missed

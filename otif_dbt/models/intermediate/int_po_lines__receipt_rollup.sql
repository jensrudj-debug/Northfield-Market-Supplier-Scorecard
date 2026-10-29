-- One row per PO line with at least one scoreable receipt: first receipt and
-- case totals, in and out of the on-time window.
select
    po_line_id,
    min(received_at) as first_receipt_at,
    cast(min(received_at) as date) as first_receipt_date,
    count(*) as receipt_count,
    cast(sum(received_cases) as bigint) as cases_received_total,
    -- Charter "In full": only quantity received inside the on-time window counts.
    cast(sum(case when is_in_on_time_window then received_cases else 0 end) as bigint) as cases_received_in_window,
    cast(sum(rejected_cases) as bigint) as cases_rejected_total
from {{ ref('int_receipts__classified') }}
where is_scoreable
group by po_line_id

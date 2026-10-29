-- One row per PO line (charter "Measurement grain") with every OTIF flag from
-- docs/charter.md evaluated as of run_date. Thresholds come from dbt_project.yml vars.
with po_lines as (

    select * from {{ ref('stg_po_lines') }}

),

purchase_orders as (

    select * from {{ ref('stg_purchase_orders') }}

),

receipt_rollup as (

    select * from {{ ref('int_po_lines__receipt_rollup') }}

),

joined as (

    select
        po_lines.po_line_id,
        po_lines.po_number,
        purchase_orders.supplier_id,
        purchase_orders.dc_id,
        po_lines.sku,
        po_lines.line_status,
        po_lines.ordered_cases,
        purchase_orders.requested_delivery_date,
        receipt_rollup.first_receipt_at,
        receipt_rollup.first_receipt_date,
        coalesce(receipt_rollup.receipt_count, 0) as receipt_count,
        coalesce(receipt_rollup.cases_received_total, 0) as cases_received_total,
        coalesce(receipt_rollup.cases_received_in_window, 0) as cases_received_in_window,
        coalesce(receipt_rollup.cases_rejected_total, 0) as cases_rejected_total,
        -- Charter "Attribution week": ISO week (Monday start) of the requested delivery date.
        cast(date_trunc('week', purchase_orders.requested_delivery_date) as date) as attribution_week_start,
        strftime(purchase_orders.requested_delivery_date, '%G-W%V') as attribution_iso_week,
        cast('{{ var("run_date") }}' as date) as as_of_date
    from po_lines
    inner join purchase_orders
        on po_lines.po_number = purchase_orders.po_number
    left join receipt_rollup
        on po_lines.po_line_id = receipt_rollup.po_line_id

),

missed as (

    select
        *,
        -- Charter "Missed line": no receipt by requested date + 7 days. A line with
        -- no receipt yet is not missed until that deadline has passed as of run_date.
        -- Lines cancelled by Northfield are not eligible (charter "Eligible line").
        case
            when line_status = 'cancelled_by_northfield' then false
            when first_receipt_date > requested_delivery_date + {{ var('missed_after_days') }} then true
            when first_receipt_date is null
                and as_of_date > requested_delivery_date + {{ var('missed_after_days') }} then true
            else false
        end as is_missed
    from joined

),

scored as (

    select
        *,
        -- Charter "Eligible line": due in the week and not cancelled by Northfield.
        -- A line is due once its requested delivery date is on or before run_date.
        case
            when line_status = 'cancelled_by_northfield' then false
            when requested_delivery_date <= as_of_date then true
            else false
        end as is_eligible,
        -- Charter "On time": first receipt between 1 day before and 0 days after the
        -- requested delivery date (DC local date). Charter "Eligible line":
        -- supplier-cancelled lines count as failures. Charter "Missed line": not on time.
        case
            when line_status = 'cancelled_by_supplier' then false
            when is_missed then false
            when first_receipt_date between requested_delivery_date - {{ var('on_time_days_early') }}
                                        and requested_delivery_date + {{ var('on_time_days_late') }}
                then true
            else false
        end as is_on_time,
        -- Charter "In full": quantity received inside the on-time window is at least
        -- 98% of ordered cases. Supplier-cancelled and missed lines are not in full.
        case
            when line_status = 'cancelled_by_supplier' then false
            when is_missed then false
            when cases_received_in_window >= {{ var('in_full_threshold') }} * ordered_cases then true
            else false
        end as is_in_full,
        -- Charter "Over-shipment": received above 105% of ordered; flagged separately
        -- and does not affect in full.
        case
            when cases_received_total > {{ var('over_shipment_threshold') }} * ordered_cases then true
            else false
        end as is_over_shipment,
        -- Charter "Provisional": true until 7 days after the attribution week ends
        -- (week ends Sunday = week start + 6), since late receipts can still change it.
        case
            when as_of_date <= attribution_week_start + 6 + {{ var('provisional_days_after_week') }} then true
            else false
        end as is_provisional
    from missed

)

select
    *,
    -- Charter "OTIF": a line that is both on time and in full.
    case
        when is_on_time and is_in_full then true
        else false
    end as is_otif
from scored

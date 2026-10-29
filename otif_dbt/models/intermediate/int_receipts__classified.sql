-- One row per staged receipt known as of run_date, matched to its PO line and
-- classified as scoreable or not. Receipts recorded after run_date are excluded,
-- so rerunning with an earlier run_date reproduces what was known on that date.
with receipts as (

    select *
    from {{ ref('stg_receipts') }}
    where recorded_date <= cast('{{ var("run_date") }}' as date)

),

po_lines as (

    select po_line_id, po_number
    from {{ ref('stg_po_lines') }}

),

purchase_orders as (

    select po_number, supplier_id, requested_delivery_date
    from {{ ref('stg_purchase_orders') }}

),

matched as (

    select
        receipts.receipt_id,
        receipts.po_line_id,
        receipts.po_number,
        receipts.dc_id,
        receipts.sku,
        receipts.received_at,
        receipts.received_date,
        receipts.received_cases,
        receipts.rejected_cases,
        receipts.recorded_date,
        purchase_orders.supplier_id,
        purchase_orders.requested_delivery_date,
        po_lines.po_line_id is not null as has_po_line,
        date_diff('day', purchase_orders.requested_delivery_date, receipts.received_date) as days_from_requested
    from receipts
    left join po_lines
        on receipts.po_line_id = po_lines.po_line_id
    left join purchase_orders
        on po_lines.po_number = purchase_orders.po_number

),

classified as (

    select
        *,
        -- Not a charter definition (ADR candidate): a receipt can only be scored at
        -- the charter's measurement grain (one PO line) when it matches a PO line,
        -- has a DC-local receipt date, and has a positive case quantity.
        case
            when not has_po_line then 'orphan_po_line'
            when received_at is null then 'missing_received_at'
            when received_cases <= 0 then 'nonpositive_cases'
        end as receipt_issue
    from matched

)

select
    *,
    receipt_issue is null as is_scoreable,
    -- Charter "On time": arrives between 1 day before and 0 days after the
    -- requested delivery date (DC local date). This is also the window that
    -- charter "In full" counts quantity inside.
    case
        when receipt_issue is null
            and days_from_requested between -{{ var('on_time_days_early') }} and {{ var('on_time_days_late') }}
            then true
        else false
    end as is_in_on_time_window
from classified

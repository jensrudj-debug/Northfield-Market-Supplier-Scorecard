-- One row per dock receipt known as of run_date, scoreable or not. Incremental
-- runs reprocess every receipt recorded within receipt_lookback_days of the
-- latest recorded_date already loaded; use --full-refresh to rebuild for an
-- earlier run_date or after reloading older raw partitions.
{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='receipt_id',
        on_schema_change='fail'
    )
}}

select
    receipt_id,
    po_line_id,
    po_number,
    supplier_id,
    dc_id,
    sku,
    requested_delivery_date,
    received_at,
    received_date,
    recorded_date,
    days_from_requested,
    received_cases,
    rejected_cases,
    receipt_issue,
    is_scoreable,
    is_in_on_time_window
from {{ ref('int_receipts__classified') }}

{% if is_incremental() %}
where recorded_date >= (
    select max(recorded_date) - {{ var('receipt_lookback_days') }}
    from {{ this }}
)
{% endif %}

-- received_at arrives as text in two formats (ISO and MM/DD/YYYY HH:MM); values
-- matching neither, or missing, become null. Exact re-sent rows share a
-- receipt_id, so keep one row per receipt_id.
with source as (

    select * from {{ source('raw', 'receipts') }}

),

typed as (

    select
        receipt_id,
        po_line_id,
        po_number,
        dc_id,
        upper(trim(sku)) as sku,
        coalesce(
            try_strptime(received_at, '%Y-%m-%d %H:%M:%S'),
            try_strptime(received_at, '%m/%d/%Y %H:%M')
        ) as received_at,
        received_cases,
        rejected_cases,
        _batch_date as recorded_date,
        _loaded_at as loaded_at,
        _source_file as source_file
    from source

)

select
    *,
    cast(received_at as date) as received_date
from typed
qualify row_number() over (
    partition by receipt_id
    order by loaded_at desc, recorded_date desc, source_file
) = 1

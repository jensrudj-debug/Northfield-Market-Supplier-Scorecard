select
    po_line_id,
    po_number,
    line_number,
    sku,
    ordered_cases,
    line_status,
    cancelled_date
from {{ source('raw', 'po_lines') }}

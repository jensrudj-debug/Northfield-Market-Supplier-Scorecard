select
    po_number,
    supplier_id,
    dc_id,
    order_date,
    requested_delivery_date
from {{ source('raw', 'purchase_orders') }}

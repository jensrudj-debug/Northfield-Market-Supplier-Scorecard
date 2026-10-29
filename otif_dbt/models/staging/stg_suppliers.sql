select
    supplier_id,
    supplier_name,
    category as supplier_category,
    lead_time_days
from {{ source('raw', 'suppliers') }}

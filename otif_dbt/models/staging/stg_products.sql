select
    sku,
    product_name,
    supplier_id,
    category as product_category,
    case_pack,
    case_cost
from {{ source('raw', 'products') }}

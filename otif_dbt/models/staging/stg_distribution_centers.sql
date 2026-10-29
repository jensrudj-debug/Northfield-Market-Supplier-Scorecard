select
    dc_id,
    dc_name,
    city as dc_city,
    state as dc_state,
    timezone as dc_timezone
from {{ source('raw', 'distribution_centers') }}

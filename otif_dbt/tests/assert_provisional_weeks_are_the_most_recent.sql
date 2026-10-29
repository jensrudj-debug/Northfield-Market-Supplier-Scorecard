-- Business rule: only the latest weeks can still change. Every provisional week
-- must be later than every final week, and at most the current and previous
-- week can be provisional (late receipts settle within 7 days of week end).
-- Returns the offending weeks.
with weeks as (

    select distinct attribution_week_start, is_provisional
    from {{ ref('mart_supplier_otif_weekly') }}

),

bounds as (

    select
        max(attribution_week_start) filter (where not is_provisional) as latest_final_week,
        count(*) filter (where is_provisional) as provisional_week_count
    from weeks

)

select weeks.attribution_week_start, weeks.is_provisional, bounds.provisional_week_count
from weeks
cross join bounds
where (weeks.is_provisional and weeks.attribution_week_start <= bounds.latest_final_week)
   or bounds.provisional_week_count > 2

-- One row per supplier per attribution week (charter "OTIF %": per supplier per
-- week), both DCs combined, for weeks starting on or before run_date.
with po_lines as (

    select * from {{ ref('fct_po_lines') }}
    where attribution_week_start <= as_of_date

),

suppliers as (

    select * from {{ ref('stg_suppliers') }}

),

weekly as (

    select
        supplier_id,
        attribution_week_start,
        any_value(attribution_iso_week) as attribution_iso_week,
        bool_or(is_provisional) as is_provisional,
        any_value(as_of_date) as as_of_date,
        count(*) as total_lines,
        count(*) filter (where is_eligible) as eligible_lines,
        count(*) filter (where is_eligible and is_otif) as otif_lines,
        count(*) filter (where is_eligible and is_on_time) as on_time_lines,
        count(*) filter (where is_eligible and is_in_full) as in_full_lines,
        count(*) filter (where is_eligible and is_missed) as missed_lines,
        count(*) filter (where is_eligible and line_status = 'cancelled_by_supplier') as supplier_cancelled_lines,
        count(*) filter (where line_status = 'cancelled_by_northfield') as northfield_cancelled_lines,
        count(*) filter (where is_eligible and is_over_shipment) as over_shipment_lines,
        coalesce(sum(ordered_cases) filter (where is_eligible), 0) as eligible_cases_ordered,
        coalesce(sum(cases_received_total) filter (where is_eligible), 0) as eligible_cases_received
    from po_lines
    group by supplier_id, attribution_week_start

)

select
    weekly.supplier_id,
    suppliers.supplier_name,
    suppliers.supplier_category,
    weekly.attribution_week_start,
    cast(weekly.attribution_week_start + 6 as date) as attribution_week_end,
    weekly.attribution_iso_week,
    weekly.is_provisional,
    weekly.as_of_date,
    weekly.total_lines,
    weekly.eligible_lines,
    weekly.otif_lines,
    weekly.on_time_lines,
    weekly.in_full_lines,
    weekly.missed_lines,
    weekly.supplier_cancelled_lines,
    weekly.northfield_cancelled_lines,
    weekly.over_shipment_lines,
    weekly.eligible_cases_ordered,
    weekly.eligible_cases_received,
    -- Charter "OTIF %": OTIF lines / eligible lines; NULL (not 0) when nothing was eligible.
    case
        when weekly.eligible_lines = 0 then null
        else round(100.0 * weekly.otif_lines / weekly.eligible_lines, 2)
    end as otif_pct,
    -- Charter "On time" share of eligible lines; NULL when nothing was eligible.
    case
        when weekly.eligible_lines = 0 then null
        else round(100.0 * weekly.on_time_lines / weekly.eligible_lines, 2)
    end as on_time_pct,
    -- Charter "In full" share of eligible lines; NULL when nothing was eligible.
    case
        when weekly.eligible_lines = 0 then null
        else round(100.0 * weekly.in_full_lines / weekly.eligible_lines, 2)
    end as in_full_pct,
    -- Charter "Case fill rate": cases received / cases ordered over eligible lines
    -- (volume-weighted); NULL when nothing was eligible.
    case
        when weekly.eligible_lines = 0 then null
        else round(100.0 * weekly.eligible_cases_received / weekly.eligible_cases_ordered, 2)
    end as case_fill_rate_pct
from weekly
left join suppliers
    on weekly.supplier_id = suppliers.supplier_id

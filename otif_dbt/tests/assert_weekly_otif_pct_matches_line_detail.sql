-- Business rule: a vendor manager who drills from a supplier's weekly OTIF % into
-- its PO lines must be able to recompute the same number (OTIF lines / eligible
-- lines, to 2 decimals, NULL when nothing was eligible). Returns each
-- supplier-week where the published percentage does not match the lines.
with recomputed as (

    select
        supplier_id,
        attribution_week_start,
        case
            when count(*) filter (where is_eligible) = 0 then null
            else round(100.0 * count(*) filter (where is_eligible and is_otif)
                       / count(*) filter (where is_eligible), 2)
        end as otif_pct
    from {{ ref('fct_po_lines') }}
    where attribution_week_start <= as_of_date
    group by supplier_id, attribution_week_start

)

select
    mart.supplier_id,
    mart.attribution_week_start,
    mart.otif_pct as published_otif_pct,
    recomputed.otif_pct as recomputed_otif_pct
from {{ ref('mart_supplier_otif_weekly') }} as mart
full outer join recomputed
    on mart.supplier_id = recomputed.supplier_id
    and mart.attribution_week_start = recomputed.attribution_week_start
where mart.otif_pct is distinct from recomputed.otif_pct

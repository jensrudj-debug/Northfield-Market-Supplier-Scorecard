-- The weekly mart's eligible and OTIF line counts must equal the line-level fact
-- for every week it publishes. Returns rows only when they disagree.
with from_lines as (

    select
        count(*) filter (where is_eligible) as eligible_lines,
        count(*) filter (where is_eligible and is_otif) as otif_lines
    from {{ ref('fct_po_lines') }}
    where attribution_week_start <= as_of_date

),

from_mart as (

    select
        sum(eligible_lines) as eligible_lines,
        sum(otif_lines) as otif_lines
    from {{ ref('mart_supplier_otif_weekly') }}

)

select *
from from_lines
cross join from_mart
where from_lines.eligible_lines <> from_mart.eligible_lines
   or from_lines.otif_lines <> from_mart.otif_lines

-- Business rule: every PO line Northfield placed is scored exactly once; joins
-- must not drop lines (hiding failures) or duplicate them (double-counting).
-- Returns PO lines missing from fct_po_lines or present there but not in staging.
select
    coalesce(staged.po_line_id, scored.po_line_id) as po_line_id,
    staged.po_line_id is null as only_in_fct,
    scored.po_line_id is null as missing_from_fct
from {{ ref('stg_po_lines') }} as staged
full outer join {{ ref('fct_po_lines') }} as scored
    on staged.po_line_id = scored.po_line_id
where staged.po_line_id is null
   or scored.po_line_id is null

-- Business rule: every case a supplier delivered on a valid receipt is credited to
-- its PO line, no more and no less, so chargebacks never rest on lost or
-- double-counted receipts. Returns PO lines whose received cases differ between
-- the receipt fact and the PO line fact.
with from_receipts as (

    select
        po_line_id,
        sum(received_cases) as cases_received
    from {{ ref('fct_receipts') }}
    where is_scoreable
    group by po_line_id

),

from_lines as (

    select po_line_id, cases_received_total as cases_received
    from {{ ref('fct_po_lines') }}
    where receipt_count > 0

)

select
    coalesce(from_receipts.po_line_id, from_lines.po_line_id) as po_line_id,
    from_receipts.cases_received as cases_in_fct_receipts,
    from_lines.cases_received as cases_in_fct_po_lines
from from_receipts
full outer join from_lines
    on from_receipts.po_line_id = from_lines.po_line_id
where from_receipts.cases_received is distinct from from_lines.cases_received

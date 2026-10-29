-- Business rule: a scorecard published for a run date may only use receipts that
-- were recorded (and received) on or before that date, so rerunning an old date
-- reproduces exactly what vendor managers saw. Returns receipts from the future.
select
    receipt_id,
    received_date,
    recorded_date
from {{ ref('fct_receipts') }}
where recorded_date > cast('{{ var("run_date") }}' as date)
   or received_date > cast('{{ var("run_date") }}' as date)

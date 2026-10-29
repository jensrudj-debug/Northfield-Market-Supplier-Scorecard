# Architecture decision records

| # | Title | Decision | What we gave up |
|---|---|---|---|
| [0001](0001-warehouse.md) | Warehouse | DuckDB single file for zero-setup, clone-and-run reproducibility. | Concurrent writers, access control, managed scaling, shared access. |
| [0002](0002-data-source.md) | Data source | Seeded synthetic generator with injected, counted data quality issues. | Real-world messiness; supplier behavior is assumed. |
| [0003](0003-measurement-grain.md) | Measurement grain | PO-line OTIF as primary; case fill rate as secondary. | A 1-case line counts the same as a 200-case line. |
| [0004](0004-on-time-window-and-attribution.md) | On-time window and attribution | -1/+0 days at DC-local date; ISO week of the requested date. | Hour-level accuracy; strictness toward early arrivals. |
| [0005](0005-in-full-rule.md) | In-full rule | At least 98% of ordered cases inside the on-time window; over 105% flagged. | No credit for late completion; 2% may hide chronic shorts. |
| [0006](0006-refresh-strategy.md) | Refresh strategy | `fct_receipts` incremental; `fct_po_lines` and weekly mart rebuilt in full. | Extra compute every run in exchange for correct restatement. |
| [0007](0007-late-arriving-data.md) | Late-arriving data | Restate with `is_provisional` for 7 days after week end, from `run_date`. | The newest week can move after the Monday review. |
| [0008](0008-orphan-receipts.md) | Orphan receipts | Keep and flag orphans; warn, do not fail. | Bad records never stop the run; someone must read warnings. |
| [0009](0009-scorecard-grain.md) | Scorecard grain | Supplier x ISO week, both DCs combined. | Cannot see a supplier failing at only one DC. |

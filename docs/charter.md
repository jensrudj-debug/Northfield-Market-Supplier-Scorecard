Northfield Market's procurement team reviews supplier performance every Monday but currently relies on buyer anecdotes and a manually updated spreadsheet. This data product publishes a weekly on-time-in-full (OTIF) scorecard for every supplier delivering to our two distribution centers, so vendor managers can decide which suppliers to escalate, charge back under the vendor compliance agreement, or renegotiate. Data refreshes daily by 6:00 a.m. Central; a week's score is marked provisional until seven days after it closes. The product is done when all three published tables are documented and tested, a full run completes from a clean clone with one command, and every test passes with documented expected results.

## Metric definitions

Each definition below will be recorded as an ADR in `docs/adr/`.

| Term | Definition |
|---|---|
| Measurement grain | One purchase order (PO) line: one SKU, on one PO, to one DC |
| On time | First receipt arrives between 1 day before and 0 days after the requested delivery date (DC local date) |
| In full | Quantity received inside the on-time window is at least 98% of ordered cases |
| OTIF | A line that is both on time and in full |
| OTIF % | OTIF lines ÷ eligible lines, per supplier per week |
| Case fill rate | Cases received ÷ cases ordered (secondary, volume-weighted metric) |
| Eligible line | Due in the week and not cancelled by Northfield. Supplier-cancelled lines count as failures. |
| Missed line | No receipt by requested date + 7 days; counts as not on time and not in full |
| Attribution week | ISO week (Monday start) of the requested delivery date, not the receipt date |
| Provisional | `is_provisional = true` until 7 days after the week ends, since late receipts can still change the score |
| Over-shipment | Received above 105% of ordered; still in full, but flagged separately |

## Scope

### In scope

- 2 distribution centers
- About 60 suppliers
- About 1,500 SKUs
- 18 months of history
- Daily batch refresh

### Out of scope

Each item below will be recorded in the limitations doc.

- Direct-store delivery (bread, beverages, and dairy vendors that skip the DC)
- Carrier/transport performance
- Chargeback dollar calculation
- Dashboards

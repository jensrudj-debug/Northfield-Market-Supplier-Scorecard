# Project: Supplier OTIF Scorecard (Northfield Market, 40-store regional grocer)
Consumer: procurement / vendor managers. Decision: which suppliers to escalate,
charge back, or renegotiate in the Monday vendor review.
Scope: inbound deliveries from suppliers to 2 distribution centers only.
Published tables: fct_po_lines, fct_receipts, mart_supplier_otif_weekly. Do not add others.
Stack: Python 3.11+, DuckDB, dbt Core (dbt-duckdb). Run via Makefile.
Rules: no hard-coded paths or credentials; read DUCKDB_PATH from env.
Every model gets a description and tests in a .yml file.
Prefer small, reviewable changes. Never commit data/ or warehouse/.

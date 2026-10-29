# ADR 0002: Data source
- Status: Accepted
- Date: 2026-10-28

## Context
OTIF needs purchase orders with requested delivery dates and the receipts that fulfil them.
We have no access to Northfield's real ordering or receiving systems for this build.
We also need known data quality problems to prove the pipeline handles them.

## Options considered
1. Seeded synthetic generator.
   - Pros: has POs, requested dates, and receipts; deterministic; known injected issues.
   - Cons: supplier behavior is invented, so results only prove the pipeline, not suppliers.
2. Public retail dataset (dunnhumby Complete Journey, Corporacion Favorita).
   - Pros: real transactions with real messiness.
   - Cons: sales data only; no purchase orders, requested dates, or matching receipts.
3. Hybrid: public products and stores, synthetic orders and receipts.
   - Pros: realistic product mix.
   - Cons: still synthetic where it matters, plus licensing and mapping work.

## Decision
We generate synthetic data with a seeded generator.
No public dataset contains purchase orders with requested dates and matching receipts.
Synthetic data also lets us inject data quality issues with exact, known counts.

## What we gave up
- Real-world messiness we did not think to simulate.
- Supplier behavior is an assumption: tiers, delay mix, and short-ship rates are invented.
- Scores describe the generator's settings, not any real supplier.
- The generator caps at 128 suppliers (16 name prefixes x 8 suffixes in `generator/generate.py`).

## Revisit when
- Real PO, advance ship notice, or receiving data becomes available.
- A stakeholder wants to act on supplier scores rather than evaluate the pipeline.

## Evidence in repo
- `generator/generate.py`: all randomness from `np.random.default_rng(cfg["seed"])`.
- `config/generator.yml`: seed `20261025`, 60 suppliers, 1,500 SKUs, 18 months, DQ rates.
- `generator/tests/test_generate.py`: same seed gives identical file hashes; DQ counts match the manifest.
- Measured: the 1x run wrote 88,057 PO lines and 87,305 receipts (`data/raw/_manifest.json`).
- Measured: injected issues include 347 duplicate receipts, 174 orphans, and 1,736 late postings.

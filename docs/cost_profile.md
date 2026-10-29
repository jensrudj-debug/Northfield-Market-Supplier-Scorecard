# Cost profile

A clean full run took 139.8 s and a daily run averaged 51.9 s; 10x volume took 129.1–156.6 s and 12.1 MB of storage per month.

## Measurements

Machine: Intel Core i5-1035G7 @ 1.20 GHz (4 cores, 8 logical processors), 7.6 GB RAM, Windows 11 Home 10.0.26200.
"Months" means the 18 months of history set by `months: 18` in `config/generator.yml`. MB means 1,000,000 bytes.

| Measure | How measured | Value |
|---|---|---|
| Full run time (seconds) | `sum(duration_seconds)` in `ops.run_log`, run `229a3d1b24a8` after a clean | 139.8 |
| Full run time, repeat runs (seconds) | Same query, runs `c0efa8be1577` and `94f3e99b1a3f` (warehouse already present) | 86.4 and 82.5 |
| Incremental daily run time (average of 3, seconds) | `ops.run_log`, runs `b5abcf47bc65` (53.3), `07bb6651cb55` (51.8), `3e5dade84af2` (50.5) | 51.9 |
| `fct_po_lines` rows per month | `rows_out` in `ops.model_run_stats` (88,057) / 18 | 4,892 |
| Storage growth per month, 1x | `ls -l warehouse/otif.duckdb` (11.81 MB) / 18, plus `du -sb data/raw` (11.22 MB) / 18 | 0.66 MB DuckDB + 0.62 MB raw = 1.28 MB |
| 10x volume full run time (seconds) | `ops.run_log` in `warehouse/otif_10x.duckdb`, runs `e41cb7ac2a3f` and `0258dc3d4793` | 129.1 and 156.6 (mean 142.9) |
| 10x `fct_po_lines` rows per month | `rows_out` (880,531) / 18 | 48,918 |
| 10x storage per month (MB) | `warehouse/otif_10x.duckdb` (106.18 MB) / 18, plus `data/raw_10x` (110.96 MB) / 18 | 5.90 MB DuckDB + 6.16 MB raw = 12.06 MB |
| Slowest 3 dbt models, 1x | `ops.model_run_stats`, `resource_type = 'model'`, run `229a3d1b24a8` | `fct_po_lines` 2.21 s, `fct_receipts` 1.71 s, `stg_po_lines` 1.21 s |
| Slowest 3 dbt models, 1x repeat | Same, run `94f3e99b1a3f` | `fct_po_lines` 0.87 s, `fct_receipts` 0.76 s, `stg_po_lines` 0.30 s |
| Slowest 3 dbt models, 10x | Same, run `e41cb7ac2a3f` | `fct_receipts` 8.25 s, `fct_po_lines` 2.84 s, `int_po_lines__receipt_rollup` 0.34 s |
| Slowest 3 dbt models, 10x repeat | Same, run `0258dc3d4793` | `fct_receipts` 9.76 s, `fct_po_lines` 4.46 s, `mart_supplier_otif_weekly` 0.42 s |

Storage was measured on fresh files. DuckDB files grow on reruns without reclaiming space.
`warehouse/otif.duckdb` reached 18.62 MB after five more runs.
`warehouse/otif_10x.duckdb` reached 156.25 MB after one more full run.

Per-step times (seconds, `ops.run_log`):

| Step | 1x full (3 runs) | 1x daily (3 runs) | 10x full (2 runs) |
|---|---|---|---|
| generate / check_raw_data | 7.6, 13.2, 9.6 | 0.1, 0.1, 0.1 | 24.5, 34.3 |
| load_raw | 24.2, 20.3, 22.1 | 1.3, 1.3, 1.2 | 31.3, 38.9 |
| dbt_deps | 18.4, 10.6, 12.0 | 11.1, 13.2, 10.1 | 10.8, 10.6 |
| dbt_source_freshness | 33.2, 14.0, 16.1 | 13.9, 13.3, 15.0 | 16.6, 15.0 |
| dbt_build | 54.1, 27.2, 21.6 | 25.1, 23.0, 23.0 | 43.4, 52.4 |
| record_model_stats | 2.3, 1.1, 1.1 | 1.9, 1.0, 1.2 | 2.4, 5.4 |

## Scaling behavior

Total run time grew much less than 10x: 82.5–139.8 s at 1x versus 129.1–156.6 s at 10x.
Fixed overhead dominates. `dbt_deps` plus `dbt_source_freshness` took 24.6–51.6 s per run at any volume.
Volume-driven steps grew less than 10x: generate 1.9–4.5x, load_raw 1.3–1.9x, dbt_build 0.8–2.4x.
`fct_receipts` grew fastest, from 0.76–1.71 s to 8.25–9.76 s (4.8–12.8x), close to linear.
It writes the widest table and runs the receipt dedup window beneath it; TODO: measure with `EXPLAIN ANALYZE` to confirm.
Run-to-run noise is large: the same 1x full run ranged from 82.5 s to 139.8 s.

## Cloud translation

Formula: `monthly_compute_hours = runtime_hours x runs_per_month`, and `monthly_cost = monthly_compute_hours x [RATE]`.

Price source: [WAREHOUSE] at [RATE] per hour, from [PRICING_URL], checked [DATE_CHECKED].

| Scenario | Runtime per run | x 30 runs | Monthly cost |
|---|---|---|---|
| 1x, daily incremental | 51.9 s = 0.01441 h | 0.432 h | 0.432 x [RATE] |
| 1x, full refresh daily (mean of 3) | 102.9 s = 0.02858 h | 0.858 h | 0.858 x [RATE] |
| 10x, full refresh daily (mean of 2) | 142.9 s = 0.03968 h | 1.190 h | 1.190 x [RATE] |
| 10x, daily incremental | TODO: measure | TODO: measure | TODO: measure |

These are laptop wall-clock times. They include Python start-up, `dbt deps`, and data generation.
A cloud warehouse would bill only its own compute, which `dbt_build` approximates (21.6–54.1 s at 1x).
There is no 10x daily target, so 10x incremental time was not measured.

## Method

Run from the repo root on the machine above, on 2026-10-28.

```sh
# 1. Clean full run. `make clean` is still a placeholder that only echoes,
#    so the clean was done by hand.
make clean
rm -rf warehouse data/raw otif_dbt/target
make run                                # run_id 229a3d1b24a8, run_date 2026-10-25
ls -l warehouse/otif.duckdb             # 11,808,768 bytes
du -sb data/raw                         # 11,218,703 bytes

# 2. Three daily runs at the end of the data range. A full run at 2026-10-22
#    first, because make daily only moves forward (see ADR 0006).
make run RUN_DATE=2026-10-22            # run_id c0efa8be1577
make daily RUN_DATE=2026-10-23          # run_id b5abcf47bc65
make daily RUN_DATE=2026-10-24          # run_id 07bb6651cb55
make daily RUN_DATE=2026-10-25          # run_id 3e5dade84af2

# 3. 10x volume into data/raw_10x and warehouse/otif_10x.duckdb.
make run-10x                            # run_id e41cb7ac2a3f
ls -l warehouse/otif_10x.duckdb         # 106,180,608 bytes
du -sb data/raw_10x                     # 110,961,823 bytes

# 4. Repeat runs to gauge noise.
make run                                # run_id 94f3e99b1a3f
make run-10x                            # run_id 0258dc3d4793
```

Queries used:

```sql
-- run totals and per-step times
select run_id, mode, run_date, sum(duration_seconds) as total_seconds
from ops.run_log group by all order by min(started_at);

-- slowest models per run
select run_id, node_name, execution_seconds, rows_out
from (select *, row_number() over (partition by run_id order by execution_seconds desc) as rn
      from ops.model_run_stats where resource_type = 'model')
where rn <= 3;
```

`config/generator_10x.yml` differs from `config/generator.yml` only in `pos_per_supplier_dc_week: 10.0`.
Suppliers stay at 60 because the generator supports at most 128 supplier names.

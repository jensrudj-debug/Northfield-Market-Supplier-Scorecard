# Cost profile

Locally, a full run took 128.9 s and a daily run averaged 100.5 s at 1x; at 10x, 134.4 s and 123.3 s.
On Snowflake Standard edition (X-Small), that is about $2.07 per month at 1x and $2.25 per month at 10x.

## Measurements

"Months" is 18, from `months: 18` in `config/generator.yml`. MB means 1,000,000 bytes.

| Measure | How measured | Value |
|---|---|---|
| Full run time, all steps (seconds) | Query 1, run `6ee966cf8190` (after a clean) | 128.9 |
| Full run, dbt build step only (seconds) | Query 1, `dbt_build` step, run `6ee966cf8190` | 48.2 |
| Incremental daily run time, average of 3 (seconds) | Query 1, runs `d3b6a3628b93` (109.8), `9c2bc60f7e57` (90.3), `fc411770157a` (101.4) | 100.5 |
| Incremental daily run, dbt build only, average of 3 (seconds) | Query 1, same runs: 60.8, 43.0, 49.2 | 51.0 |
| `fct_po_lines` rows (total) and rows per month | Query 2, run `6ee966cf8190`: 88,057 / 18 | 88,057 total; 4,892 per month |
| Storage growth per month, 1x | `ls -l warehouse/otif.duckdb` = 11.81 MB; `du -sb data/raw` = 11.22 MB; each / 18 | DuckDB 0.66 MB + raw CSV 0.62 MB = 1.28 MB |
| 10x full run time, all steps and dbt build only (seconds) | Query 1 on `warehouse/otif_10x.duckdb`, run `abb809f44412` | 134.4 all steps; 36.8 dbt build |
| 10x storage growth per month (MB) | `warehouse/otif_10x.duckdb` = 97.53 MB; `data/raw_10x` = 110.96 MB; each / 18 | DuckDB 5.42 MB + raw CSV 6.16 MB = 11.58 MB |

Other 10x runs, used for the cost model (Query 1 on `warehouse/otif_10x.duckdb`):
- Daily runs `2f76ed2d1d1d`, `50c7536659d0`, `3d9cebf117b3`: 128.8, 118.4, 122.6 s (average 123.3 s).
- Their dbt builds took 72.0, 70.9, 70.6 s (average 71.1 s).
- Full run `6ada1565695c` (run date 2026-10-22, set-up for the dailies): 234.5 s all steps, 73.2 s dbt build.

Other `rows_out` (Query 2): `fct_receipts` 86,958 and `mart_supplier_otif_weekly` 3,995 at 1x.
At 10x: `fct_po_lines` 880,531, `fct_receipts` 869,499, and `mart_supplier_otif_weekly` 4,738.

3 slowest models (Query 3):

| Run | 1st | 2nd | 3rd |
|---|---|---|---|
| 1x full `6ee966cf8190` | `fct_po_lines` 2.49 s | `fct_receipts` 1.59 s | `stg_distribution_centers` 0.92 s |
| 1x daily `fc411770157a` | `fct_po_lines` 1.83 s | `fct_receipts` 1.14 s | `stg_distribution_centers` 0.82 s |
| 10x full `abb809f44412` | `fct_receipts` 4.88 s | `fct_po_lines` 2.41 s | `stg_po_lines` 0.34 s |
| 10x daily `3d9cebf117b3` | `fct_po_lines` 5.66 s | `fct_receipts` 4.34 s | `stg_products` 1.01 s |

Machine: Intel Core i5-1035G7 @ 1.20 GHz, 4 cores (8 logical processors), 7.6 GB RAM, Windows 11 Home 10.0.26200.

## Scaling behavior

Run time grew far less than linearly: 10x data took 1.04x the full-run time (134.4 s vs 128.9 s) and 1.4x the daily dbt build (71.1 s vs 51.0 s).
Fixed costs dominate: dbt start-up, `dbt deps`, and source freshness do not depend on volume.
`fct_receipts` grew fastest in full runs: 1.59 s to 4.88 s (3.1x), and 9.17 s in run `6ada1565695c`.
Its SQL reads `int_receipts__classified`, a view over `stg_receipts`, whose `qualify row_number() over (partition by receipt_id ...)` and two `try_strptime` calls rescan every receipt each build.
Run-to-run noise is large: the 10x full dbt build ranged from 36.8 s to 73.2 s on the same data.

## Snowflake cost estimate

Assumptions:
- Prices per credit (user-supplied, checked 2026-10-28): Standard $2.00, Enterprise $3.00, Business Critical $4.00.
- Warehouse size X-Small = 1 credit per hour. Small = 2 credits per hour, shown as a sensitivity row with the same runtime.
- Per-second billing with a 60-second minimum each time the warehouse resumes.
- Auto-suspend = 60 seconds, so each run also bills 60 idle seconds.
- Billed seconds per run = max(dbt build seconds, 60) + 60.
- Only the dbt build step runs in the warehouse. Generation and loading would use ingestion tooling and are excluded.
- Snowflake X-Small runtime equals the measured local DuckDB dbt build time. Sensitivity: 0.5x, 1x, and 2x.
- 30 daily incremental runs per month, plus 1 full refresh per month.
- Daily seconds use the average of 3 measured daily dbt builds. Full seconds use the measured full run (`6ee966cf8190` at 1x, `abb809f44412` at 10x).
- Storage cost is excluded. It is billed per TB per month at regional rates; growth is reported above in MB.

Formulas:
- `credits_per_run = billed_seconds / 3600 * credits_per_hour`
- `monthly_cost = (30 * daily_credits + 1 * full_credits) * price_per_credit`

| Scenario | Billed seconds per daily run | Credits per month | Standard $/month | Enterprise $/month | Business Critical $/month |
|---|---|---|---|---|---|
| 1x X-Small | 120.00 | 1.0333 | $2.07 | $3.10 | $4.13 |
| 10x X-Small | 131.15 | 1.1262 | $2.25 | $3.38 | $4.50 |
| 1x Small | 120.00 | 2.0667 | $4.13 | $6.20 | $8.27 |
| 10x Small | 131.15 | 2.2524 | $4.50 | $6.76 | $9.01 |

Sensitivity, X-Small, Standard ($2.00 per credit):

| Scale | Runtime factor | Daily build s | Billed daily s | Full build s | Billed full s | Credits per month | $/month |
|---|---|---|---|---|---|---|---|
| 1x | 0.5x | 25.51 | 120.00 | 24.09 | 120.00 | 1.0333 | $2.07 |
| 1x | 1x | 51.02 | 120.00 | 48.18 | 120.00 | 1.0333 | $2.07 |
| 1x | 2x | 102.04 | 162.04 | 96.36 | 156.36 | 1.3937 | $2.79 |
| 10x | 0.5x | 35.57 | 120.00 | 18.41 | 120.00 | 1.0333 | $2.07 |
| 10x | 1x | 71.15 | 131.15 | 36.82 | 120.00 | 1.1262 | $2.25 |
| 10x | 2x | 142.29 | 202.29 | 73.64 | 133.64 | 1.7229 | $3.45 |

Worked example: 10x, X-Small, Standard.
1. Daily dbt build average = (72.03 + 70.85 + 70.55) / 3 = 71.15 s.
2. Billed daily seconds = max(71.15, 60) + 60 = 131.15 s.
3. Daily credits = 131.15 / 3600 * 1 = 0.03643 credits.
4. Full dbt build = 36.82 s, so billed full seconds = max(36.82, 60) + 60 = 120.00 s.
5. Full credits = 120.00 / 3600 * 1 = 0.03333 credits.
6. Monthly credits = 30 * 0.03643 + 1 * 0.03333 = 1.0929 + 0.0333 = 1.1262 credits.
7. Monthly cost = 1.1262 * $2.00 = $2.25.

The 60-second minimum and 60-second auto-suspend dominate the cost.
At 1x, a 51.0 s daily build bills 120 s, 2.4 times the actual runtime; halving runtime saves nothing.
Standard edition fits this workload: one scheduled batch needs no multi-cluster warehouses or 90-day Time Travel, which require Enterprise.

## Method

Run from the repo root on the machine above, on 2026-10-28, at commit `7f959f2` plus this document.
`ops.run_log` has no commit column, so earlier runs could not be tied to a commit; all runs here are fresh.
`ops.run_log` lives in the git-ignored warehouse, so these run_ids exist only until the next `make clean`.
Later commits changed `make clean` (now implemented) and added `--config`/`--raw-dir` to `run_pipeline.py`.
The commands below use those; at measurement time the same steps were done by hand and with an inline override.

```sh
# 1x: clean, then a full run.
make clean
make run                                 # 6ee966cf8190  (run_date 2026-10-25)
ls -l warehouse/otif.duckdb              # 11,808,768 bytes
du -sb data/raw                          # 11,218,703 bytes

# 1x dailies: make daily only moves forward, so a full run at 2026-10-22 comes first.
make run RUN_DATE=2026-10-22             # 95c314d97730
make daily RUN_DATE=2026-10-23           # d3b6a3628b93
make daily RUN_DATE=2026-10-24           # 9c2bc60f7e57
make daily RUN_DATE=2026-10-25           # fc411770157a

# 10x full run into data/raw_10x and warehouse/otif_10x.duckdb.
make run-10x                             # abb809f44412  (run_date 2026-10-25)
ls -l warehouse/otif_10x.duckdb          # 97,529,856 bytes
du -sb data/raw_10x                      # 110,961,823 bytes

# 10x dailies (no make target). Use an absolute DUCKDB_PATH; in Git Bash, $(pwd -W) gives a Windows path.
export DUCKDB_PATH="$(pwd)/warehouse/otif_10x.duckdb"
TENX="--config config/generator_10x.yml --raw-dir data/raw_10x"
python pipeline/run_pipeline.py --mode full  --run-date 2026-10-22 $TENX   # 6ada1565695c
python pipeline/run_pipeline.py --mode daily --run-date 2026-10-23 $TENX   # 2f76ed2d1d1d
python pipeline/run_pipeline.py --mode daily --run-date 2026-10-24 $TENX   # 50c7536659d0
python pipeline/run_pipeline.py --mode daily --run-date 2026-10-25 $TENX   # 3d9cebf117b3

# Machine
powershell -Command "Get-CimInstance Win32_Processor; Get-CimInstance Win32_ComputerSystem; Get-CimInstance Win32_OperatingSystem"
```

Query 1, run totals and dbt build time (run against both warehouse files):

```sql
select run_id, mode, run_date,
       round(sum(duration_seconds), 1) as total_seconds,
       round(sum(duration_seconds) filter (where step = 'dbt_build'), 1) as dbt_build_seconds
from ops.run_log
group by run_id, mode, run_date
order by min(started_at);
```

Query 2, published table row counts:

```sql
select run_id, node_name, rows_out
from ops.model_run_stats
where node_name in ('fct_po_lines', 'fct_receipts', 'mart_supplier_otif_weekly')
order by run_id, node_name;
```

Query 3, 3 slowest models per run:

```sql
select run_id, node_name, round(execution_seconds, 2) as execution_seconds, rows_out
from (
    select *, row_number() over (partition by run_id order by execution_seconds desc) as rn
    from ops.model_run_stats
    where resource_type = 'model'
)
where rn <= 3
order by run_id, rn;
```

Cost figures were computed in Python from unrounded `duration_seconds`:

```sql
select duration_seconds from ops.run_log where run_id = ? and step = 'dbt_build';
```

10x config: `config/generator_10x.yml` changes only `pos_per_supplier_dc_week` from 1.0 to 10.0, same seed.
Supplier count stays at 60: `generator/generate.py` supports at most 128 supplier names (16 prefixes x 8 suffixes).

Pricing source: user-supplied Snowflake per-credit pricing, checked 2026-10-28.
Snowflake's pricing page is https://www.snowflake.com/en/pricing-options/; it does not list per-credit rates.
Rates by region and edition are in the consumption table linked from that page.

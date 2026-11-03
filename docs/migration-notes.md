# Migration notes

## From procedures to models
| Legacy (T-SQL) | dbt replacement | Notes |
|---|---|---|
| `rpt.usp_load_daily_balances` (WHILE loop, one INSERT per day) | `marts.fct_daily_balance` | Date spine × accounts with a window `SUM`. This is one set-based query instead of N. [MIG-1] |
| `rpt.usp_txn_summary` | `marts.fct_transactions` aggregated by business date, branch and type | The summary is a query on the fact table, not a separate table. |
| Inline `CAST(TXN_AMT AS DECIMAL)` in every query | `stg_*` models | Types are fixed once, in staging. [MIG-2] |
| Copy-pasted 20:00 cut-off `CASE` | `business_date()` macro, used in `int_transactions_enriched` | One definition, with a dbt unit test on the boundary. [MIG-4] |
| `TRUNCATE` + reload, no checks | Tables with enforced contracts, data tests, GE and reconciliation | [MIG-3] |
| Customer attributes overwritten in place | `snap_customers` snapshot → `dim_customer` (SCD2) | Facts join to the customer version valid at `transacted_at`. |

Business rules R1 to R7 are listed in the header of each legacy procedure in `legacy/`. The
`[MIG-n]` markers in the procedures point at the lines each note is about.

## Star schema
```
                 dim_date (date_key)
                      |
dim_branch ── fct_transactions ── dim_account
                      |
                 dim_customer (SCD2: customer_key = customer_id + valid_from)

dim_account ── fct_daily_balance ── dim_date
```
- Surrogate keys are `md5` of the natural key. They are deterministic and work on DuckDB,
  Snowflake and Redshift without sequences.
- `fct_transactions.branch_key` is the account's home branch, because that is what the legacy
  report used ([MIG-5]). It is documented rather than "fixed" during the migration, since
  changing it would change the numbers.

## Dialect mapping (T-SQL → DuckDB / Snowflake / Redshift)
| T-SQL | DuckDB | Snowflake / Redshift | Where in dbt |
|---|---|---|---|
| `CONVERT(DATE, s, 112)` | `strptime(s, '%Y%m%d')::date` | `to_date(s, 'YYYYMMDD')` | `parse_yyyymmdd()` macro |
| `DATEPART(HOUR, ts)` | `extract(hour from ts)` | same | `business_date()` |
| `DATEADD(DAY, 1, d)` | `dbt.dateadd` | `dbt.dateadd` | `business_date()` |
| `ISNULL(a, b)` | `coalesce` | `coalesce` | everywhere |
| WHILE loop over dates | `range()` date spine | recursive CTE | `date_spine()` macro |
| ISO day of week | `isodow` | `dayofweekiso` / `extract(dow)` | `iso_day_of_week()` macro |

Every warehouse-specific expression is behind an `adapter.dispatch` macro. Only the DuckDB
branches run locally and in CI. The Snowflake and Redshift branches are written but not executed
(see Limitations in the README).

## Why the snapshot runs during `make seed`
An SCD2 dimension only has history after at least two snapshot runs. `make seed` therefore
does the following:
1. Loads the first version of every customer.
2. Runs `dbt snapshot`. This stands in for yesterday's nightly run.
3. Applies today's changes (segment and city edits, with `LAST_UPD_DTTM` inside the reporting
   window).

The `dbt build` in `make run` then records those changes as new versions. The snapshot uses
the `timestamp` strategy on `LAST_UPD_DTTM`, so `valid_from` is the time the source changed,
not the time dbt ran. That keeps point-in-time joins correct, and the singular test
`assert_customer_version_valid_at_transaction` checks it.

## Tests, by layer
| Layer | What | Where |
|---|---|---|
| Sources / staging | unique, not_null, accepted_values, relationships, `non_negative` | `models/**/_*.yml` |
| Intermediate | grain (`unique_combination`) and a **unit test** for the 20:00 cut-off | `models/intermediate/_intermediate.yml` |
| Marts | enforced contracts (names, types, not_null / PK constraints), FK `relationships`, SCD2 `scd2_no_overlap` | `models/marts/_marts.yml` |
| Singular | savings never negative, FK integrity across the star, point-in-time customer, balance roll-forward | `dbt/tests/*.sql` |
| Load shape | volume per business day, amount distribution, type mix, freshness | `great_expectations/run_checkpoint.py` |
| Parity | row counts, sums by key, deterministic sampled rows vs legacy | `reconcile/` |

The generic tests `non_negative`, `unique_combination` and `scd2_no_overlap` are written in this
repo, so `dbt deps` (and network access) is not needed.

## Reconciliation
Each comparison is two SELECTs that project the same column names. One reads the legacy table
and one reads the dbt output, so the name mapping sits in one place
(`reconcile/comparisons.py`). Three checks run on each comparison:
1. **Row count.** Catches lost or duplicated grain.
2. **Sums by key.** Per account and per branch. Localises a difference to the key that moved.
3. **Sampled rows.** 500 rows chosen by `md5(seed || key)`, so the sample is the same on every
   run. Catches offsetting errors that sums hide. The unit tests show such a case: +1 on one
   day and −1 on the next.

The job writes `target/reconcile/report.json` and exits non-zero on any difference. The Airflow
DAG and CI therefore stop before cut-over.

## Airflow
- `bank_reporting_daily` runs three BashOperator tasks: `dbt_build` → `great_expectations_checkpoint` →
  `reconcile_legacy_vs_dbt`. These are the same commands as `make run`.
- `dbt_build` gets 2 retries with exponential backoff. The GE and reconciliation tasks get no
  retries, because a data failure will not fix itself.
- The SLA is an Airflow 3 `DeadlineAlert`: 2 hours after the run is queued. Airflow 3 removed
  the task-level `sla=` argument from Airflow 2.
- Verified with Airflow 3.3.2 on Python 3.13. `tests/test_dag.py` parses the DAG through
  `DagBag` and checks task order, retries and the deadline. Under `make airflow` (standalone),
  a scheduled run of the DAG completed with state `success`.
- Known upstream quirk: in Airflow 3.3.2, `airflow dags test` runs all three tasks
  successfully and then raises while pruning deadlines for the finished run. This is in the
  in-process test runner only. The scheduler path above is not affected.

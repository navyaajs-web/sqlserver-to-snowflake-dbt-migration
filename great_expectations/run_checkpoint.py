"""Great Expectations checkpoint on marts.fct_transactions.

Why GE on top of dbt tests? dbt tests answer "is this row valid?" (keys, nulls, FKs). This
checkpoint asks "does this load look like a normal day?":

* **volume**: posted transactions per business day sit in an expected band, so a half-loaded
  extract fails even when every row in it is valid;
* **distribution**: amount mean/median, type mix and posted share stay within expected ranges;
* **freshness**: the latest transaction reaches the as-of date being reported.

Thresholds are sized for the synthetic Harbor Point data. In production they would come from
a profile of recent history.

The context is ephemeral (configured in code, nothing written to a gx/ folder), and the
dataframes are read from DuckDB with pandas. Run from the repo root:
``python great_expectations/run_checkpoint.py``. The exit code is non-zero on failure.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb
import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd
import yaml
from great_expectations.data_context.types.base import ProgressBarsConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
DAILY_VOLUME_RANGE = (150, 600)  # posted transactions per full business day


def load_window() -> tuple[date, date]:
    dbt_vars = yaml.safe_load((REPO_ROOT / "dbt" / "dbt_project.yml").read_text())["vars"]
    start, as_of = dbt_vars["reporting_start"], dbt_vars["as_of_date"]
    return date.fromisoformat(start), date.fromisoformat(as_of)


def load_frames(db_path: Path, start: date, as_of: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        txns = con.execute(
            """select transaction_id, transaction_type, channel, amount, transacted_at,
                      business_date, cast(is_posted as integer) as is_posted
               from marts.fct_transactions"""
        ).df()
        daily = con.execute(
            """select business_date, count(*) as posted_txn_count
               from marts.fct_transactions
               where is_posted and business_date between ? and ?
               group by business_date""",
            [start, as_of],
        ).df()
    return txns, daily


def transaction_expectations(as_of: date) -> list[gxe.Expectation]:
    return [
        # integrity of the key the reconciliation and BI joins depend on
        gxe.ExpectColumnValuesToNotBeNull(column="transaction_id"),
        gxe.ExpectColumnValuesToBeUnique(column="transaction_id"),
        # distribution
        gxe.ExpectColumnValuesToBeBetween(column="amount", min_value=0, max_value=10_000),
        gxe.ExpectColumnMeanToBeBetween(column="amount", min_value=300, max_value=900),
        gxe.ExpectColumnMedianToBeBetween(column="amount", min_value=150, max_value=600),
        gxe.ExpectColumnMeanToBeBetween(column="is_posted", min_value=0.9, max_value=1.0),
        gxe.ExpectColumnDistinctValuesToBeInSet(
            column="transaction_type",
            value_set=[
                "DEPOSIT",
                "TRANSFER_IN",
                "INTEREST",
                "CARD_PURCHASE",
                "WITHDRAWAL",
                "TRANSFER_OUT",
            ],
        ),
        gxe.ExpectColumnDistinctValuesToContainSet(
            column="channel", value_set=["BRANCH", "ATM", "MOBILE", "ONLINE"]
        ),
        # freshness: the load must reach the reporting date
        gxe.ExpectColumnMaxToBeBetween(
            column="transacted_at",
            min_value=datetime.combine(as_of, time.min),
            max_value=datetime.combine(as_of + timedelta(days=1), time.min),
        ),
    ]


def volume_expectations(start: date, as_of: date) -> list[gxe.Expectation]:
    low, high = DAILY_VOLUME_RANGE
    n_days = (as_of - start).days + 1
    return [
        gxe.ExpectTableRowCountToEqual(value=n_days),  # no missing business days
        gxe.ExpectColumnValuesToBeBetween(column="posted_txn_count", min_value=low, max_value=high),
    ]


def build_and_run(txns: pd.DataFrame, daily: pd.DataFrame, start: date, as_of: date) -> dict:
    """Run one checkpoint per view of fct_transactions and return their validation results.

    A GE 1.x checkpoint passes the same batch parameters to every validation it holds, so the
    row-level view and the per-day volume view each get their own checkpoint.
    """
    context = gx.get_context(mode="ephemeral")
    context.variables.progress_bars = ProgressBarsConfig(globally=False)  # keep logs readable
    source = context.data_sources.add_pandas("harbor_point")
    plan = (
        ("fct_transactions", txns, transaction_expectations(as_of)),
        ("fct_transactions_daily_volume", daily, volume_expectations(start, as_of)),
    )
    results = {}
    for name, frame, expectations in plan:
        batch_def = source.add_dataframe_asset(name).add_batch_definition_whole_dataframe(name)
        suite = context.suites.add(gx.ExpectationSuite(name=f"{name}_suite"))
        for expectation in expectations:
            suite.add_expectation(expectation)
        validation = context.validation_definitions.add(
            gx.ValidationDefinition(name=f"{name}_validation", data=batch_def, suite=suite)
        )
        checkpoint = context.checkpoints.add(
            gx.Checkpoint(name=f"{name}_checkpoint", validation_definitions=[validation])
        )
        run = checkpoint.run(batch_parameters={"dataframe": frame})
        (results[name],) = run.run_results.values()
    return results


def main() -> int:
    logging.getLogger("great_expectations").setLevel(logging.WARNING)
    os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")
    start, as_of = load_window()
    db_path = Path(os.environ.get("DUCKDB_PATH", "warehouse/harbor_point.duckdb"))
    db_path = db_path if db_path.is_absolute() else REPO_ROOT / db_path
    txns, daily = load_frames(db_path, start, as_of)

    outcome = build_and_run(txns, daily, start, as_of)
    summary, all_ok = [], True
    for asset, result in outcome.items():
        for r in result.results:
            cfg = r.expectation_config
            ok = bool(r.success)
            all_ok &= ok
            column = cfg.kwargs.get("column", "<table>")
            if "observed_value" in r.result:
                detail = f"observed={r.result['observed_value']}"
            else:
                detail = f"unexpected={r.result.get('unexpected_count', 0)}"
            summary.append(
                {
                    "asset": asset,
                    "expectation": cfg.type,
                    "column": column,
                    "success": ok,
                    "detail": detail,
                }
            )
            print(f"[{'PASS' if ok else 'FAIL'}] {asset:<30} {cfg.type:<45} {column:<17} {detail}")

    out = REPO_ROOT / "target" / "great_expectations" / "fct_transactions_checkpoint.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"success": all_ok, "results": summary}, indent=2, default=str))
    print(f"\nGreat Expectations on fct_transactions: {'PASSED' if all_ok else 'FAILED'} -> {out}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

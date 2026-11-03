"""Run the translated legacy procedures against DuckDB to produce the "before" numbers.

The T-SQL WHILE loop in usp_load_daily_balances is reproduced here as a Python loop over dates,
so the legacy path stays row-by-day and independent of the dbt models. Reconciliation is only
meaningful if the two implementations do not share code.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import duckdb

from datagen.config import LEGACY_SQL_DIR

_STEP = re.compile(r"^-- step: (\w+)\s*$", re.MULTILINE)


def read_steps(path: Path) -> dict[str, str]:
    """Split a translated proc into its named steps (`-- step: <name>` markers)."""
    parts = _STEP.split(path.read_text(encoding="utf-8"))
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def run_legacy(con: duckdb.DuckDBPyConnection, start: date, as_of: date) -> None:
    balances = read_steps(LEGACY_SQL_DIR / "usp_load_daily_balances.duckdb.sql")
    con.execute(balances["setup"])
    day = start
    while day <= as_of:  # the WHILE @d <= @AsOfDate loop
        con.execute(balances["per_day"], {"balance_date": day})
        day += timedelta(days=1)

    summary = read_steps(LEGACY_SQL_DIR / "usp_txn_summary.duckdb.sql")
    con.execute(summary["setup"])
    con.execute(summary["once"], {"start_date": start, "as_of_date": as_of})

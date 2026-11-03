"""`make seed`: build a fresh DuckDB warehouse with source data and legacy outputs.

Steps
  1. Generate synthetic extracts and land them as CSV (like an SSIS flat-file export).
  2. Load them into the `raw` schema.
  3. Run `dbt snapshot` once: this stands in for "yesterday's" nightly run, so the snapshot
     already holds the first version of every customer.
  4. Apply today's customer changes to `raw.customers`. The snapshot in `make run` then records
     them as SCD2 history.
  5. Run the translated legacy procedures into the `legacy` schema.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

from datagen.config import DBT_PROJECT_DIR, PROFILES_DIR, load_settings
from datagen.generate import generate, write_landing_files
from datagen.legacy import run_legacy

RAW_DDL = {
    "branches": "SELECT * FROM read_csv('{path}', header=true, all_varchar=true)",
    "accounts": "SELECT * FROM read_csv('{path}', header=true, all_varchar=true)",
    "transactions": "SELECT * FROM read_csv('{path}', header=true, all_varchar=true)",
    # The snapshot needs a real timestamp to compare, so this one column is typed on load.
    "customers": (
        "SELECT * REPLACE (CAST(LAST_UPD_DTTM AS TIMESTAMP) AS LAST_UPD_DTTM) "
        "FROM read_csv('{path}', header=true, all_varchar=true)"
    ),
}


def dbt(*args: str) -> None:
    exe = Path(sys.executable).with_name("dbt")
    cmd = [
        str(exe) if exe.exists() else "dbt",
        *args,
        "--project-dir",
        str(DBT_PROJECT_DIR),
        "--profiles-dir",
        str(PROFILES_DIR),
    ]
    subprocess.run(cmd, check=True, env={**os.environ})


def main() -> None:
    settings = load_settings()
    db_path = settings.duckdb_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    landing = db_path.parent / "landing"
    shutil.rmtree(landing, ignore_errors=True)

    data = generate(settings.reporting_start, settings.as_of_date)
    paths = write_landing_files(data, landing)

    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE SCHEMA raw")
        for name, select in RAW_DDL.items():
            con.execute(f"CREATE TABLE raw.{name} AS " + select.format(path=paths[name]))
    print(
        f"loaded raw: {len(data.customers)} customers, {len(data.accounts)} accounts, "
        f"{len(data.transactions)} transactions"
    )

    os.environ.setdefault("DUCKDB_PATH", str(db_path))
    dbt("snapshot")  # yesterday's run: first version of each customer

    with duckdb.connect(str(db_path)) as con:
        for upd in data.customer_updates:
            # upd["field"] is one of two fixed column names from the generator, never user input
            con.execute(
                f"UPDATE raw.customers SET {upd['field']} = ?, LAST_UPD_DTTM = ? WHERE CUST_NO = ?",
                [upd["value"], upd["LAST_UPD_DTTM"], upd["CUST_NO"]],
            )
        run_legacy(con, settings.reporting_start, settings.as_of_date)
        n_bal = con.execute("SELECT count(*) FROM legacy.daily_balance").fetchone()[0]
        n_sum = con.execute("SELECT count(*) FROM legacy.txn_summary").fetchone()[0]
    print(
        f"applied {len(data.customer_updates)} customer changes; "
        f"legacy outputs: {n_bal} daily balances, {n_sum} summary rows -> {db_path}"
    )


if __name__ == "__main__":
    main()

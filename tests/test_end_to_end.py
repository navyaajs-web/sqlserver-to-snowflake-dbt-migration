"""Full reconciliation against the real warehouse, after `make seed` and `make run`.

Skipped when the warehouse has not been built, so `pytest` alone stays fast and self-contained.
"""

import duckdb
import pytest

from datagen.config import load_settings
from reconcile.checks import run_comparison
from reconcile.comparisons import comparisons

settings = load_settings()


def _built() -> bool:
    if not settings.duckdb_path.exists():
        return False
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as con:
        tables = {
            r[0]
            for r in con.execute(
                "select table_schema || '.' || table_name from information_schema.tables"
            ).fetchall()
        }
    return {"marts.fct_daily_balance", "legacy.daily_balance"} <= tables


@pytest.mark.skipif(not _built(), reason="run `make seed run` first")
def test_legacy_and_dbt_outputs_reconcile():
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as con:
        for comparison in comparisons(settings.reporting_start, settings.as_of_date):
            for result in run_comparison(con, comparison):
                assert result.passed, (result.comparison, result.check, result.examples)

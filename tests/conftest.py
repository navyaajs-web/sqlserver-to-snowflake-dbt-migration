from __future__ import annotations

import duckdb
import pytest


@pytest.fixture
def con():
    """An in-memory warehouse with tiny legacy and dbt tables that agree with each other."""
    c = duckdb.connect()
    c.execute("create schema legacy; create schema marts;")
    c.execute(
        """
        create table legacy.daily_balance as
        select * from (values
            ('A1', date '2026-07-01', 100.00::decimal(18,2), 1),
            ('A1', date '2026-07-02', 150.00::decimal(18,2), 2),
            ('A2', date '2026-07-01', -20.50::decimal(18,2), 0),
            ('A2', date '2026-07-02', -20.50::decimal(18,2), 0)
        ) t(acct_no, bal_dt, close_bal, txn_cnt)
        """
    )
    c.execute(
        """
        create table marts.fct_daily_balance as
        select acct_no as account_id, bal_dt as balance_date, close_bal as closing_balance,
               txn_cnt as posted_txn_count
        from legacy.daily_balance
        """
    )
    yield c
    c.close()

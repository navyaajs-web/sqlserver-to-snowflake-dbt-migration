"""The legacy outputs being retired and the dbt queries that replace them.

Both sides project identical column names. The mapping between legacy names (left) and
dbt names (right) is visible in one place.
"""

from __future__ import annotations

from datetime import date

from reconcile.checks import Comparison


def comparisons(start: date, as_of: date) -> list[Comparison]:
    return [
        Comparison(
            name="daily_balance",
            legacy_sql="""
                select acct_no   as account_id,
                       bal_dt    as balance_date,
                       close_bal as closing_balance,
                       txn_cnt   as txn_count
                from legacy.daily_balance
            """,
            dbt_sql="""
                select account_id,
                       balance_date,
                       closing_balance,
                       posted_txn_count as txn_count
                from marts.fct_daily_balance
            """,
            keys=("account_id", "balance_date"),
            measures=("closing_balance", "txn_count"),
            sum_by="account_id",
        ),
        Comparison(
            name="txn_summary",
            legacy_sql="""
                select bus_dt      as business_date,
                       br_cd       as branch_id,
                       txn_type_cd as transaction_type,
                       txn_cnt     as txn_count,
                       total_amt   as total_amount
                from legacy.txn_summary
            """,
            dbt_sql=f"""
                select f.business_date,
                       b.branch_id,
                       f.transaction_type,
                       count(*)            as txn_count,
                       sum(abs(f.amount))  as total_amount
                from marts.fct_transactions f
                join marts.dim_branch b on b.branch_key = f.branch_key
                where f.is_posted
                  and f.business_date between date '{start}' and date '{as_of}'
                group by 1, 2, 3
            """,
            keys=("business_date", "branch_id", "transaction_type"),
            measures=("txn_count", "total_amount"),
            sum_by="branch_id",
        ),
    ]

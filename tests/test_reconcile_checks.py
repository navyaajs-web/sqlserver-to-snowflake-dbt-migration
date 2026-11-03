"""The reconciliation must pass when outputs agree and point at the exact key when they don't."""

from decimal import Decimal

from reconcile.checks import (
    Comparison,
    row_count,
    run_comparison,
    sampled_rows,
    sums_by_key,
)

BALANCES = Comparison(
    name="daily_balance",
    legacy_sql="""select acct_no as account_id, bal_dt as balance_date,
                         close_bal as closing_balance, txn_cnt as txn_count
                  from legacy.daily_balance""",
    dbt_sql="""select account_id, balance_date, closing_balance, posted_txn_count as txn_count
               from marts.fct_daily_balance""",
    keys=("account_id", "balance_date"),
    measures=("closing_balance", "txn_count"),
    sum_by="account_id",
)


def test_identical_outputs_pass_every_check(con):
    results = run_comparison(con, BALANCES)
    assert [r.check for r in results] == ["row_count", "sums_by_key", "sampled_rows"]
    assert all(r.passed for r in results), results


def test_dropped_row_fails_row_count_and_sampling(con):
    con.execute(
        "delete from marts.fct_daily_balance where account_id = 'A2' "
        "and balance_date = date '2026-07-02'"
    )
    assert not row_count(con, BALANCES).passed
    sample = sampled_rows(con, BALANCES)
    assert not sample.passed
    assert {"account_id": "A2", "issue": "missing in dbt"}.items() <= sample.examples[0].items()


def test_changed_amount_is_localised_to_its_key(con):
    con.execute(
        "update marts.fct_daily_balance set closing_balance = 151.00 "
        "where account_id = 'A1' and balance_date = date '2026-07-02'"
    )
    result = sums_by_key(con, BALANCES)
    assert not result.passed
    (example,) = result.examples
    assert example["account_id"] == "A1"
    assert example["legacy"][0] == Decimal("250.00") and example["dbt"][0] == Decimal("251.00")
    assert row_count(con, BALANCES).passed  # count alone would have missed it


def test_offsetting_errors_pass_sums_but_fail_sampling(con):
    """+1 on one day and -1 on the next leaves the per-account total unchanged."""
    con.execute(
        "update marts.fct_daily_balance set closing_balance = closing_balance + 1 "
        "where account_id = 'A1' and balance_date = date '2026-07-01'"
    )
    con.execute(
        "update marts.fct_daily_balance set closing_balance = closing_balance - 1 "
        "where account_id = 'A1' and balance_date = date '2026-07-02'"
    )
    assert sums_by_key(con, BALANCES).passed
    sample = sampled_rows(con, BALANCES)
    assert not sample.passed and len(sample.examples) == 2


def test_extra_key_in_dbt_is_reported(con):
    con.execute("insert into marts.fct_daily_balance values ('A9', date '2026-07-01', 1.00, 1)")
    result = sums_by_key(con, BALANCES)
    assert {"account_id": "A9", "issue": "missing in legacy"} in result.examples


def test_tolerance_allows_rounding_noise(con):
    con.execute("update marts.fct_daily_balance set closing_balance = closing_balance + 0.01")
    strict = sums_by_key(con, BALANCES)
    lenient = sums_by_key(con, Comparison(**{**BALANCES.__dict__, "tolerance": Decimal("0.05")}))
    assert not strict.passed and lenient.passed


def test_sampling_is_deterministic(con):
    a = sampled_rows(con, BALANCES, sample_size=2)
    b = sampled_rows(con, BALANCES, sample_size=2)
    assert a.summary == b.summary == "2 sampled rows; 0 differ"

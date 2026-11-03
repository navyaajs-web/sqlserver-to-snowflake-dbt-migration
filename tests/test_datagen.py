"""The synthetic source must be reproducible and respect the rules the tests rely on."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

import yaml

from datagen.config import DBT_PROJECT_DIR, load_settings
from datagen.generate import generate
from datagen.legacy import LEGACY_SQL_DIR, read_steps

START, AS_OF = date(2026, 7, 1), date(2026, 7, 31)


def test_generation_is_deterministic():
    a = generate(START, AS_OF, n_customers=20, seed=1)
    b = generate(START, AS_OF, n_customers=20, seed=1)
    assert a.transactions == b.transactions and a.accounts == b.accounts


def test_savings_never_overdrawn_on_posted_activity():
    data = generate(START, AS_OF, n_customers=60, seed=3)
    savings = {a["ACCT_NO"]: Decimal(a["OPEN_BAL"]) for a in data.accounts if a["PROD_CD"] == "SAV"}
    by_account = defaultdict(list)
    for t in data.transactions:
        if t["ACCT_NO"] in savings and t["TXN_STAT_CD"] == "P":
            by_account[t["ACCT_NO"]].append(t)
    for acct, txns in by_account.items():
        balance = savings[acct]
        for t in sorted(txns, key=lambda t: (t["TXN_DTTM"], int(t["TXN_ID"]))):
            amount = Decimal(t["TXN_AMT"])
            balance += amount if t["DR_CR_IND"] == "C" else -amount
            assert balance >= 0, (acct, t)


def test_only_fictional_contact_data():
    data = generate(START, AS_OF, n_customers=30, seed=5)
    assert all(c["EMAIL_ADDR"].endswith("@example.com") for c in data.customers)


def test_customer_updates_happen_inside_the_window():
    data = generate(START, AS_OF, n_customers=40, seed=9)
    assert data.customer_updates
    assert all(START <= u["LAST_UPD_DTTM"].date() <= AS_OF for u in data.customer_updates)


def test_settings_follow_dbt_project_vars():
    dbt_vars = yaml.safe_load((DBT_PROJECT_DIR / "dbt_project.yml").read_text())["vars"]
    settings = load_settings()
    assert settings.reporting_start.isoformat() == dbt_vars["reporting_start"]
    assert settings.as_of_date.isoformat() == dbt_vars["as_of_date"]


def test_translated_procs_have_expected_steps():
    assert set(read_steps(LEGACY_SQL_DIR / "usp_load_daily_balances.duckdb.sql")) == {
        "setup",
        "per_day",
    }
    assert set(read_steps(LEGACY_SQL_DIR / "usp_txn_summary.duckdb.sql")) == {"setup", "once"}

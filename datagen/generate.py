"""Generate synthetic source extracts for a fictional bank.

The files mimic what an SSIS flat-file source lands: upper-case legacy column names, dates as
'YYYYMMDD' text and amounts as text. Typing them is the staging layer's job, which is exactly
the clean-up a migration has to do.

Generation is deterministic for a given seed, so test failures are reproducible.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

BRANCHES = [
    ("BR001", "Harbor Point Main Street", "NORTH"),
    ("BR002", "Lighthouse Quay", "NORTH"),
    ("BR003", "Cedar Hill", "SOUTH"),
    ("BR004", "Willow Bend", "SOUTH"),
    ("BR005", "Granite Falls", "WEST"),
    ("BR006", "Bayview Plaza", "WEST"),
]
FIRST = [
    "Ada",
    "Bram",
    "Cora",
    "Dmitri",
    "Esme",
    "Felix",
    "Gia",
    "Hugo",
    "Ines",
    "Jonah",
    "Kira",
    "Leo",
    "Mila",
    "Nico",
    "Opal",
    "Pavel",
    "Rhea",
    "Silas",
    "Talia",
    "Uma",
]
LAST = [
    "Ashford",
    "Bellamy",
    "Carrow",
    "Dunmore",
    "Ellery",
    "Fairbairn",
    "Garnet",
    "Holloway",
    "Ingram",
    "Juniper",
    "Kestrel",
    "Lowell",
    "Marlow",
    "Northcott",
    "Oakley",
    "Pembrook",
]
CITIES = ["Harbor Point", "Lighthouse Quay", "Cedar Hill", "Willow Bend", "Granite Falls"]
SEGMENTS = ["MASS", "AFFLUENT", "STUDENT", "SENIOR"]

CREDIT_TYPES = {"DEPOSIT": (20, 2500), "TRANSFER_IN": (10, 1500)}
DEBIT_TYPES = {"CARD_PURCHASE": (3, 250), "WITHDRAWAL": (20, 400), "TRANSFER_OUT": (10, 1200)}


@dataclass
class SourceData:
    branches: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)
    customer_updates: list[dict] = field(default_factory=list)


def _money(rng: random.Random, low: float, high: float) -> Decimal:
    return Decimal(str(round(rng.uniform(low, high), 2)))


def generate(start: date, as_of: date, n_customers: int = 300, seed: int = 42) -> SourceData:
    rng = random.Random(seed)
    data = SourceData()
    data.branches = [
        {"BR_CD": code, "BR_NM": name, "REGION_CD": region, "OPEN_DT": "20050101"}
        for code, name, region in BRANCHES
    ]

    first_version = datetime.combine(start - timedelta(days=1), time(0, 0))
    for i in range(1, n_customers + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        data.customers.append(
            {
                "CUST_NO": f"HPC{i:06d}",
                "CUST_NM": f"{first} {last}",
                "EMAIL_ADDR": f"{first}.{last}.{i}@example.com".lower(),
                "SEGMENT_CD": rng.choice(SEGMENTS),
                "CITY_NM": rng.choice(CITIES),
                "LAST_UPD_DTTM": first_version,
            }
        )

    window_days = (as_of - start).days
    acct_seq = 0
    txn_seq = 0
    for cust in data.customers:
        products = ["CHK"] + (["SAV"] if rng.random() < 0.6 else [])
        for prod in products:
            acct_seq += 1
            # Most accounts pre-date the window; some open part-way through it.
            opened = start - timedelta(days=rng.randint(30, 2000))
            if rng.random() < 0.15:
                opened = start + timedelta(days=rng.randint(0, window_days - 5))
            opening = _money(rng, 0, 8000) if prod == "SAV" else _money(rng, -200, 5000)
            account = {
                "ACCT_NO": f"HPA{acct_seq:07d}",
                "CUST_NO": cust["CUST_NO"],
                "BR_CD": rng.choice(BRANCHES)[0],
                "PROD_CD": prod,
                "CCY_CD": "USD",
                "OPEN_DT": opened.strftime("%Y%m%d"),
                "OPEN_BAL": f"{opening:.2f}",
                "ACCT_STAT_CD": "A",
            }
            data.accounts.append(account)
            txn_seq = _account_transactions(
                rng, data, account, max(opened, start), as_of, opening, txn_seq
            )

    # Changes made *after* yesterday's snapshot: these become SCD2 history in dim_customer.
    for cust in rng.sample(data.customers, k=n_customers // 8):
        change_at = datetime.combine(
            start + timedelta(days=rng.randint(10, window_days - 1)),
            time(rng.randint(8, 18), rng.randint(0, 59)),
        )
        field_name = rng.choice(["SEGMENT_CD", "CITY_NM"])
        pool = SEGMENTS if field_name == "SEGMENT_CD" else CITIES
        new_value = rng.choice([v for v in pool if v != cust[field_name]])
        data.customer_updates.append(
            {
                "CUST_NO": cust["CUST_NO"],
                "field": field_name,
                "value": new_value,
                "LAST_UPD_DTTM": change_at,
            }
        )
    return data


def _account_transactions(
    rng: random.Random,
    data: SourceData,
    account: dict,
    first_day: date,
    as_of: date,
    balance: Decimal,
    txn_seq: int,
) -> int:
    """Daily activity for one account. Savings balances never go below zero."""
    is_savings = account["PROD_CD"] == "SAV"
    day = first_day
    while day <= as_of:
        n = (
            rng.choices([0, 1, 2, 3], weights=[45, 30, 17, 8])[0]
            if not is_savings
            else rng.choices([0, 1], weights=[85, 15])[0]
        )
        stamps = sorted(
            datetime.combine(day, time(rng.randint(6, 23), rng.randint(0, 59), rng.randint(0, 59)))
            for _ in range(n)
        )
        for ts in stamps:
            is_credit = rng.random() < (0.55 if is_savings else 0.4)
            txn_type, (low, high) = rng.choice(
                list((CREDIT_TYPES if is_credit else DEBIT_TYPES).items())
            )
            amount = _money(rng, low, high)
            status = rng.choices(["P", "R", "N"], weights=[96, 3, 1])[0]
            if not is_credit and is_savings and status == "P" and amount > balance:
                amount = balance  # savings cannot be overdrawn: withdraw what is there
                if amount <= 0:
                    continue
            if status == "P":
                balance += amount if is_credit else -amount
            txn_seq += 1
            data.transactions.append(
                {
                    "TXN_ID": str(txn_seq),
                    "ACCT_NO": account["ACCT_NO"],
                    "TXN_DTTM": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "TXN_AMT": f"{amount:.2f}",
                    "DR_CR_IND": "C" if is_credit else "D",
                    "TXN_TYPE_CD": txn_type,
                    "CHANNEL_CD": rng.choice(["BRANCH", "ATM", "MOBILE", "ONLINE", "CARD"]),
                    "TXN_STAT_CD": status,
                }
            )
        if is_savings and day.day == 1:  # monthly interest
            interest = (max(balance, Decimal(0)) * Decimal("0.0025")).quantize(Decimal("0.01"))
            if interest > 0:
                txn_seq += 1
                balance += interest
                data.transactions.append(
                    {
                        "TXN_ID": str(txn_seq),
                        "ACCT_NO": account["ACCT_NO"],
                        "TXN_DTTM": f"{day:%Y-%m-%d} 02:00:00",
                        "TXN_AMT": f"{interest:.2f}",
                        "DR_CR_IND": "C",
                        "TXN_TYPE_CD": "INTEREST",
                        "CHANNEL_CD": "SYSTEM",
                        "TXN_STAT_CD": "P",
                    }
                )
        day += timedelta(days=1)
    return txn_seq


def write_landing_files(data: SourceData, landing_dir: Path) -> dict[str, Path]:
    """Write CSV extracts, the way an upstream SSIS export would."""
    landing_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name in ("branches", "customers", "accounts", "transactions"):
        rows = getattr(data, name)
        path = landing_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        paths[name] = path
    return paths

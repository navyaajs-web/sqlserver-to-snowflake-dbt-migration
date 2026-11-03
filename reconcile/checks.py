"""Reconciliation checks between a legacy output and its dbt replacement.

Three checks, from cheap and coarse to precise:

1. **Row count**: catches dropped or duplicated grain immediately.
2. **Sums by key**: totals of each measure grouped by a business key (e.g. per account). It
   localises a difference to the key that moved, which is what an analyst needs to debug it.
3. **Sampled rows**: a deterministic sample of legacy rows compared column by column with the
   matching dbt rows. Cheap enough to run on every load, and it catches offsetting errors that
   sums can hide (+10 on one day, -10 on the next).

Each comparison is written as two SELECTs that project the same column names, so the checks
themselves stay generic and the mapping between legacy and dbt names is explicit in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import duckdb

MAX_EXAMPLES = 10


@dataclass(frozen=True)
class Comparison:
    name: str
    legacy_sql: str
    dbt_sql: str
    keys: tuple[str, ...]
    measures: tuple[str, ...]
    sum_by: str
    tolerance: Decimal = Decimal("0")


@dataclass
class CheckResult:
    comparison: str
    check: str
    passed: bool
    summary: str
    examples: list[dict[str, Any]] = field(default_factory=list)


def _close(a: Any, b: Any, tolerance: Decimal) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, int | Decimal | float) and isinstance(b, int | Decimal | float):
        return abs(Decimal(str(a)) - Decimal(str(b))) <= tolerance
    return a == b


def row_count(con: duckdb.DuckDBPyConnection, c: Comparison) -> CheckResult:
    legacy = con.execute(f"select count(*) from ({c.legacy_sql})").fetchone()[0]
    new = con.execute(f"select count(*) from ({c.dbt_sql})").fetchone()[0]
    return CheckResult(c.name, "row_count", legacy == new, f"legacy={legacy} dbt={new}")


def sums_by_key(con: duckdb.DuckDBPyConnection, c: Comparison) -> CheckResult:
    sums = ", ".join(f"sum({m}) as {m}" for m in c.measures)

    def totals(sql: str) -> dict[Any, tuple]:
        rows = con.execute(f"select {c.sum_by}, {sums} from ({sql}) group by {c.sum_by}").fetchall()
        return {r[0]: r[1:] for r in rows}

    legacy, new = totals(c.legacy_sql), totals(c.dbt_sql)
    problems = []
    for key in sorted(legacy.keys() | new.keys(), key=str):
        lv, nv = legacy.get(key), new.get(key)
        if lv is None or nv is None:
            problems.append(
                {c.sum_by: key, "issue": "missing in dbt" if nv is None else "missing in legacy"}
            )
        elif not all(_close(a, b, c.tolerance) for a, b in zip(lv, nv, strict=True)):
            problems.append({c.sum_by: key, "legacy": list(lv), "dbt": list(nv)})
    return CheckResult(
        c.name,
        "sums_by_key",
        not problems,
        f"{len(legacy)} {c.sum_by} values compared on {', '.join(c.measures)}; "
        f"{len(problems)} differ",
        problems[:MAX_EXAMPLES],
    )


def sampled_rows(
    con: duckdb.DuckDBPyConnection,
    c: Comparison,
    sample_size: int = 500,
    seed: str = "harbor-point",
) -> CheckResult:
    """Compare a deterministic sample of rows.

    Sampling orders by md5(seed || key) rather than random(): the same rows are picked on every
    run, so a failure can be reproduced, and the approach works on any warehouse.
    """
    key_expr = " || '|' || ".join(f"cast({k} as varchar)" for k in c.keys)
    cols = ", ".join((*c.keys, *c.measures))
    join_on = " and ".join(f"l.{k} = d.{k}" for k in c.keys)
    rows = con.execute(
        f"""
        with sample as (
            select {cols} from ({c.legacy_sql})
            order by md5('{seed}' || {key_expr})
            limit {int(sample_size)}
        )
        select {", ".join(f"l.{k}" for k in c.keys)},
               {", ".join(f"l.{m}" for m in c.measures)},
               {", ".join(f"d.{m}" for m in c.measures)},
               d.{c.keys[0]} is null as missing
        from sample l
        left join ({c.dbt_sql}) d on {join_on}
        """
    ).fetchall()

    n_keys, n_meas = len(c.keys), len(c.measures)
    problems = []
    for row in rows:
        key = dict(zip(c.keys, row[:n_keys], strict=True))
        legacy = row[n_keys : n_keys + n_meas]
        new = row[n_keys + n_meas : n_keys + 2 * n_meas]
        if row[-1]:
            problems.append({**key, "issue": "missing in dbt"})
        elif not all(_close(a, b, c.tolerance) for a, b in zip(legacy, new, strict=True)):
            problems.append({**key, "legacy": list(legacy), "dbt": list(new)})
    return CheckResult(
        c.name,
        "sampled_rows",
        not problems,
        f"{len(rows)} sampled rows; {len(problems)} differ",
        problems[:MAX_EXAMPLES],
    )


def run_comparison(
    con: duckdb.DuckDBPyConnection, c: Comparison, sample_size: int = 500
) -> list[CheckResult]:
    return [row_count(con, c), sums_by_key(con, c), sampled_rows(con, c, sample_size)]

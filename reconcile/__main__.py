"""`python -m reconcile`: run every comparison, print a summary, write a JSON report.

Exits non-zero if any check fails, so Airflow (or CI) stops the cut-over.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import duckdb

from datagen.config import REPO_ROOT, load_settings
from reconcile.checks import run_comparison
from reconcile.comparisons import comparisons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--report", default=str(REPO_ROOT / "target" / "reconcile" / "report.json"))
    args = parser.parse_args(argv)

    settings = load_settings()
    results = []
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as con:
        for comparison in comparisons(settings.reporting_start, settings.as_of_date):
            results.extend(run_comparison(con, comparison, args.sample_size))

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.comparison:<14} {r.check:<13} {r.summary}")
        for example in r.examples:
            print(f"         {example}")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps([asdict(r) for r in results], indent=2, default=str))
    failed = [r for r in results if not r.passed]
    print(
        f"\nreconciliation {'FAILED' if failed else 'PASSED'}: "
        f"{len(results) - len(failed)}/{len(results)} checks passed -> {report}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared settings. The reporting window is read from dbt_project.yml so that the generator,
the legacy runner and the dbt models can never disagree about which dates are in scope."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = REPO_ROOT / "dbt"
PROFILES_DIR = REPO_ROOT / "profiles"
LEGACY_SQL_DIR = REPO_ROOT / "legacy" / "translated"


@dataclass(frozen=True)
class Settings:
    duckdb_path: Path
    reporting_start: date
    as_of_date: date
    cutoff_hour: int


def load_settings() -> Settings:
    with open(DBT_PROJECT_DIR / "dbt_project.yml", encoding="utf-8") as fh:
        dbt_vars = yaml.safe_load(fh)["vars"]
    path = Path(os.environ.get("DUCKDB_PATH", "warehouse/harbor_point.duckdb"))
    return Settings(
        duckdb_path=path if path.is_absolute() else REPO_ROOT / path,
        reporting_start=date.fromisoformat(dbt_vars["reporting_start"]),
        as_of_date=date.fromisoformat(dbt_vars["as_of_date"]),
        cutoff_hour=int(dbt_vars["business_day_cutoff_hour"]),
    )

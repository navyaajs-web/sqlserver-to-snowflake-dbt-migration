"""bank_reporting_daily: dbt build -> Great Expectations -> reconciliation.

This replaces the SSIS package that called the legacy procedures. Each step is a shell
command, the same one `make run` executes, so what runs in Airflow is what runs locally and in
CI. No logic lives only in the DAG.

Operational choices:
* Retries with exponential backoff. Warehouse hiccups are usually transient, while a data
  problem will fail every retry. Three attempts is enough to tell the two apart.
* SLA as an Airflow 3 deadline alert. The task-level `sla=` of Airflow 2 is gone in Airflow 3.
  A DeadlineAlert fires if the run is not finished 2 hours after it was queued, which is when
  branch managers expect the report.
* `max_active_runs=1` and `catchup=False`, because each run rebuilds the same tables.
* Reconciliation is the last gate. If it fails, the run fails, and downstream consumers
  (cut-over, report distribution) never see numbers that disagree with the legacy outputs.
"""

from __future__ import annotations

import logging
import os
import shlex
import sys
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from airflow.sdk.definitions.deadline import AsyncCallback, DeadlineAlert, DeadlineReference

# Repository root: two levels above airflow/dags/. Override with HARBOR_POINT_HOME when the DAG
# folder is deployed somewhere else.
REPO = os.environ.get(
    "HARBOR_POINT_HOME", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)
# Use the interpreter (and its dbt) that runs Airflow, not whatever is first on PATH.
PYTHON = shlex.quote(sys.executable)
DBT = shlex.quote(os.path.join(os.path.dirname(sys.executable), "dbt"))
CD = f"cd {shlex.quote(REPO)}"
DBT_ARGS = "--project-dir dbt --profiles-dir profiles"

log = logging.getLogger(__name__)


async def notify_sla_miss(**kwargs: object) -> None:
    """Deadline callback. In production this would page on-call or post to a channel."""
    log.warning("bank_reporting_daily missed its 2h SLA: %s", kwargs)


default_args = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(minutes=45),
}

with DAG(
    dag_id="bank_reporting_daily",
    description="Harbor Point Bank daily reporting: dbt build, GE checkpoint, reconciliation",
    schedule="30 5 * * *",  # 05:30 UTC, after the nightly source extracts land
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    deadline=DeadlineAlert(
        reference=DeadlineReference.DAGRUN_QUEUED_AT,
        interval=timedelta(hours=2),
        callback=AsyncCallback(notify_sla_miss),
    ),
    tags=["harbor-point", "dbt", "reporting"],
) as dag:
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{CD} && {DBT} build {DBT_ARGS}",
    )

    ge_checkpoint = BashOperator(
        task_id="great_expectations_checkpoint",
        bash_command=f"{CD} && {PYTHON} great_expectations/run_checkpoint.py",
        retries=0,  # a failed expectation is a data problem; retrying will not fix it
    )

    reconcile = BashOperator(
        task_id="reconcile_legacy_vs_dbt",
        bash_command=f"{CD} && {PYTHON} -m reconcile",
        retries=0,
    )

    dbt_build >> ge_checkpoint >> reconcile

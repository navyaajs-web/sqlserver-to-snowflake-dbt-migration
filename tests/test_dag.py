"""Parse the Airflow DAG. Skips cleanly when Airflow is not installed.

`airflow.sdk` is imported rather than `airflow`: the repo has an `airflow/` folder, which Python
would happily import as an empty namespace package if Airflow itself were missing.
"""

from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("airflow.sdk")

DAG_FOLDER = Path(__file__).resolve().parent.parent / "airflow" / "dags"


@pytest.fixture(scope="module")
def dagbag():
    from airflow.dag_processing.dagbag import DagBag

    return DagBag(dag_folder=str(DAG_FOLDER))


def test_dag_imports_without_errors(dagbag):
    assert dagbag.import_errors == {}
    assert "bank_reporting_daily" in dagbag.dags


def test_task_order_is_build_then_ge_then_reconcile(dagbag):
    dag = dagbag.dags["bank_reporting_daily"]
    build = dag.get_task("dbt_build")
    ge = dag.get_task("great_expectations_checkpoint")
    rec = dag.get_task("reconcile_legacy_vs_dbt")
    assert build.downstream_task_ids == {ge.task_id}
    assert ge.downstream_task_ids == {rec.task_id}
    assert rec.downstream_task_ids == set()


def test_retries_and_sla(dagbag):
    dag = dagbag.dags["bank_reporting_daily"]
    assert dag.get_task("dbt_build").retries == 2
    assert dag.get_task("reconcile_legacy_vs_dbt").retries == 0
    deadlines = dag.deadline if isinstance(dag.deadline, list) else [dag.deadline]
    assert any(d.interval == timedelta(hours=2) for d in deadlines)
    assert dag.max_active_runs == 1 and not dag.catchup

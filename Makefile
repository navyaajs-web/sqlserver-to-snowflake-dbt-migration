# Targets named in the README: setup, seed, run, test, airflow. Plus lint and clean.
PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin
DBT    := $(BIN)/dbt
DBT_ARGS := --project-dir dbt --profiles-dir profiles

export DBT_SEND_ANONYMOUS_USAGE_STATS := false
export GX_ANALYTICS_ENABLED := false
export DUCKDB_PATH ?= warehouse/harbor_point.duckdb

.PHONY: setup seed run test lint airflow clean

setup:  ## venv with dbt-duckdb, Great Expectations, Airflow and dev tools
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[airflow,dev]"

seed:  ## synthetic source data + yesterday's snapshot + legacy outputs into DuckDB
	$(BIN)/python -m datagen

run:  ## dbt build (models, snapshots, tests) -> GE checkpoint -> reconciliation
	$(DBT) build $(DBT_ARGS)
	$(BIN)/python great_expectations/run_checkpoint.py
	$(BIN)/python -m reconcile

test:  ## pytest (reconcile, generator, DAG parse) + dbt data tests
	$(BIN)/pytest
	$(DBT) build $(DBT_ARGS) --select test_type:data

lint:
	$(BIN)/ruff check .

airflow:  ## Airflow standalone (UI on :8080) with this repo's DAG folder
	PATH=$(CURDIR)/$(BIN):$$PATH \
	AIRFLOW_HOME=$(CURDIR)/.airflow \
	AIRFLOW__CORE__DAGS_FOLDER=$(CURDIR)/airflow/dags \
	AIRFLOW__CORE__LOAD_EXAMPLES=False \
	HARBOR_POINT_HOME=$(CURDIR) \
	$(BIN)/airflow standalone

clean:
	rm -rf warehouse target dbt/target dbt/logs logs .pytest_cache .ruff_cache

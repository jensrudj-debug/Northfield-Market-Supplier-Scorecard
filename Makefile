.PHONY: setup generate load build test docs run daily clean

# Use the project venv when it exists; override with `make PYTHON=...`.
ifeq ($(OS),Windows_NT)
VENV_PYTHON := .venv/Scripts/python.exe
else
VENV_PYTHON := .venv/bin/python
endif
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python)

# Absolute so the loader (run from the repo root) and dbt (run from otif_dbt/) share one file.
DUCKDB_PATH ?= $(CURDIR)/warehouse/otif.duckdb
export DUCKDB_PATH

setup:
	@echo "setup: create .venv, install Python deps, run dbt deps"

generate:
	$(PYTHON) generator/generate.py --config config/generator.yml --out-dir data/raw

load:
	$(PYTHON) pipeline/load_raw.py $(if $(START_DATE),--start-date $(START_DATE)) $(if $(END_DATE),--end-date $(END_DATE))

build:
	@echo "build: dbt build (staging -> intermediate -> marts)"

test:
	@echo "test: run generator unit tests and dbt tests"

docs:
	@echo "docs: dbt docs generate and serve"

run:
	$(PYTHON) pipeline/run_pipeline.py --mode full $(if $(RUN_DATE),--run-date $(RUN_DATE))

daily:
	$(if $(RUN_DATE),,$(error RUN_DATE is required, e.g. make daily RUN_DATE=2026-10-20))
	$(PYTHON) pipeline/run_pipeline.py --mode daily --run-date $(RUN_DATE)

clean:
	@echo "clean: remove warehouse/, otif_dbt/target/, otif_dbt/dbt_packages/, otif_dbt/logs/"

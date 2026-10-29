.PHONY: setup generate load build test docs run daily run-10x clean

# Optional local settings (DUCKDB_PATH, RUN_DATE); see .env.example.
-include .env

ifeq ($(OS),Windows_NT)
VENV_BIN := .venv/Scripts
EXE := .exe
else
VENV_BIN := .venv/bin
EXE :=
endif
VENV_PYTHON := $(VENV_BIN)/python$(EXE)
VENV_DBT := $(CURDIR)/$(VENV_BIN)/dbt$(EXE)

# Use the project venv when it exists; override with `make PYTHON=...` / `make DBT=...`.
SYSTEM_PYTHON ?= python
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(SYSTEM_PYTHON))
DBT ?= $(if $(wildcard $(VENV_DBT)),$(VENV_DBT),dbt)

# Absolute so the loader (run from the repo root) and dbt (run from otif_dbt/) share one file.
DUCKDB_PATH ?= $(CURDIR)/warehouse/otif.duckdb
export DUCKDB_PATH
ifdef RUN_DATE
export RUN_DATE
endif

setup:
	$(SYSTEM_PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt
	cd otif_dbt && $(VENV_DBT) deps --profiles-dir .

generate:
	$(PYTHON) generator/generate.py --config config/generator.yml --out-dir data/raw

load:
	$(PYTHON) pipeline/load_raw.py $(if $(START_DATE),--start-date $(START_DATE)) $(if $(END_DATE),--end-date $(END_DATE))

build:
	cd otif_dbt && $(DBT) build --profiles-dir .

test:
	$(PYTHON) -m pytest generator/tests pipeline/tests -q
	cd otif_dbt && $(DBT) test --profiles-dir .

docs:
	$(PYTHON) pipeline/build_data_dictionary.py

run:
	$(PYTHON) pipeline/run_pipeline.py --mode full $(if $(RUN_DATE),--run-date $(RUN_DATE))

daily:
	$(if $(RUN_DATE),,$(error RUN_DATE is required, e.g. make daily RUN_DATE=2026-10-20))
	$(PYTHON) pipeline/run_pipeline.py --mode daily --run-date $(RUN_DATE)

# Full pipeline at 10x PO volume into a separate data dir and warehouse (docs/cost_profile.md).
run-10x: DUCKDB_PATH := $(CURDIR)/warehouse/otif_10x.duckdb
run-10x:
	$(PYTHON) pipeline/run_pipeline.py --mode full --config config/generator_10x.yml --raw-dir data/raw_10x

# Removes everything the pipeline generates; .venv is kept.
clean:
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('data', 'warehouse', 'logs', 'otif_dbt/target', 'otif_dbt/dbt_packages', 'otif_dbt/logs')]"

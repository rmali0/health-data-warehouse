PYTHON ?= python3
CDC_RAW := data/raw/cdc_cdi.csv

.PHONY: all install data sample test lint queries clean

## all: download the CDC file if needed, then run the full pipeline
all: $(CDC_RAW)
	$(PYTHON) -m healthdw run

install:
	$(PYTHON) -m pip install -e ".[dev]"

$(CDC_RAW):
	$(PYTHON) scripts/download_cdc_cdi.py

data: $(CDC_RAW)

## sample: run on the bundled fixture, writing to build/sample
sample:
	$(PYTHON) -m healthdw run --sample

test:
	$(PYTHON) -m pytest

lint:
	ruff check .
	ruff format --check .

queries:
	$(PYTHON) -m healthdw query sql/example_queries.sql

clean:
	rm -rf build data/processed .pytest_cache .ruff_cache

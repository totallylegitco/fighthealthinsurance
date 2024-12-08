.PHONY: run-local install

run-local:
	scripts/run_local.sh

install:
	python -m venv .venv && \
	. .venv/bin/activate && \
	pip install -r requirements.txt


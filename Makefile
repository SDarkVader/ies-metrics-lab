PY := python
PIP := $(PY) -m pip
RUNNER := PYTHONPATH=src $(PY) -m ies_lab.runner

.PHONY: help install dev test run patch fixtures fmt clean

help:
	@echo "Targets:"
	@echo "  make dev      - upgrade pip/setuptools/wheel + editable install (no build isolation)"
	@echo "  make test     - run pytest"
	@echo "  make run      - run runner"
	@echo "  make patch    - run fixture patch scripts (if present)"
	@echo "  make clean    - remove __pycache__ and local artifacts"

dev:
	$(PIP) install -U pip setuptools wheel
	$(PIP) install -e . --no-build-isolation

test:
	pytest -q

run:
	$(RUNNER)

patch:
	$(PY) tools/patch_fixture_modes.py || true
	$(PY) tools/patch_fixtures.py || true

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} \;

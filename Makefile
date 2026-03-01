.PHONY: dev test run patch clean lint

dev:
	python -m pip install -U pip setuptools wheel
	python -m pip install -e . --no-build-isolation

test:
	pytest -q

run:
	python -m ies_lab.runner

patch:
	python tools/patch_fixture_modes.py

lint:
	python -m py_compile $(shell git ls-files '*.py')

clean:
	rm -rf .pytest_cache
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +

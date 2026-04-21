sim:
	python main.py

headless:
	python main.py --headless

test:
	pytest

test-cov:
	pytest --cov=. --cov-report=html

lint:
	ruff check .

format:
	black .

typecheck:
	mypy .

check: lint typecheck test

.PHONY: sim headless test test-cov lint format typecheck check

.PHONY: help install install-dev test test-cov lint format index clean

help:
	@echo "ELH Semantic Search — available commands"
	@echo ""
	@echo "  make install       Install runtime dependencies"
	@echo "  make test          Run the test suite"
	@echo "  make test-cov      Run tests with coverage report"
	@echo "  make lint          Lint the codebase with ruff"
	@echo "  make format        Auto-format the codebase with ruff"
	@echo "  make index         Index reviews into Pinecone"
	@echo "  make index-reset   Wipe the index and rebuild from scratch"
	@echo "  make clean         Remove caches and build artifacts"

install:
	pip install -r requirements.txt
	pip install -e .

test:
	pytest

test-cov:
	pytest --cov=elh_rag --cov-report=term-missing --cov-report=html

lint:
	ruff check src tests scripts

format:
	ruff format src tests scripts
	ruff check --fix src tests scripts

index:
	python -m scripts.run_indexer

index-reset:
	python -m scripts.run_indexer --reset

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

.PHONY: format lint test security ci-local

format:
	black src tests scripts
	isort src tests scripts

lint:
	ruff check src tests scripts
	mypy src/elh_rag --ignore-missing-imports

security:
	pip-audit

test:
	pytest tests/ --cov=src/elh_rag --cov-report=term-missing

ci-local: format lint security test
.PHONY: help install dbt-build dbt-seed dbt-run dbt-test train export-models serve test lint format docker-build docker-run docker-compose-up docker-compose-down load-data clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	pip install -r requirements.txt

# --- Data Pipeline ---

dbt-build: ## Run full dbt pipeline (seed + run + test)
	cd dbt && dbt build --profiles-dir .

dbt-seed: ## Load seed data into BigQuery
	cd dbt && dbt seed --profiles-dir .

dbt-run: ## Run dbt models
	cd dbt && dbt run --profiles-dir .

dbt-test: ## Run dbt tests
	cd dbt && dbt test --profiles-dir .

load-data: ## Upload large raw data to GCS + BigQuery (one-time)
	./scripts/load_raw_data.sh

# --- ML Models ---

train: ## Train fraud + forecast models (prints metrics)
	python src/models/train_model.py
	python src/models/predict_model.py

export-models: ## Export trained models to outputs/models/ for API serving
	python scripts/export_models.py

# --- API ---

serve: ## Run API locally with hot reload
	uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# --- Docker ---

docker-build: ## Build Docker image
	docker build -t caixabank-ai-api .

docker-run: ## Run API container
	docker run -p 8080:8080 caixabank-ai-api

docker-compose-up: ## Start services via docker-compose
	docker compose up -d

docker-compose-down: ## Stop services
	docker compose down

# --- Testing ---

test: ## Run all tests
	python -m pytest tests/ -v

# --- Code Quality ---

lint: ## Run linter (ruff check + format check)
	ruff check .
	ruff format --check .

format: ## Auto-format code (ruff fix + format)
	ruff check --fix .
	ruff format .

# --- Cleanup ---

clean: ## Remove build artifacts
	rm -rf dbt/target dbt/logs dbt/dbt_packages
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

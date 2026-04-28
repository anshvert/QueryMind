.PHONY: help dev dev-backend dev-frontend install install-dev lint format test test-cov eval load-test docker-up docker-down docker-logs migrate migrate-create clean redteam

# Colors
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
RESET  := \033[0m

help: ## Show this help
	@echo "$(CYAN)QueryMind — Available Commands$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

# ─── Development ────────────────────────────────────────────────────────────
dev: docker-up ## Start full dev stack (infra + backend + frontend)
	@echo "$(CYAN)Starting QueryMind development environment...$(RESET)"
	@make -j2 dev-backend dev-frontend

dev-backend: ## Start FastAPI backend with hot-reload
	@echo "$(GREEN)Starting backend on http://localhost:8000$(RESET)"
	uv run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Start React frontend with hot-reload
	@echo "$(GREEN)Starting frontend on http://localhost:5173$(RESET)"
	cd frontend && npm run dev

# ─── Installation ────────────────────────────────────────────────────────────
install: ## Install production dependencies
	uv sync

install-dev: ## Install all dependencies including dev tools
	uv sync --all-extras
	cd frontend && npm install

setup: install-dev docker-up migrate ## Full dev setup from scratch
	@echo "$(GREEN)Setup complete! Run 'make dev' to start.$(RESET)"

# ─── Code Quality ────────────────────────────────────────────────────────────
lint: ## Run ruff linter
	uv run ruff check backend/

format: ## Run ruff formatter
	uv run ruff format backend/
	uv run ruff check --fix backend/

typecheck: ## Run mypy type checker
	uv run mypy backend/

# ─── Testing ─────────────────────────────────────────────────────────────────
test: ## Run all tests
	uv run pytest backend/tests/ -v

test-cov: ## Run tests with coverage report
	uv run pytest backend/tests/ -v --cov=backend --cov-report=html --cov-report=term-missing

test-connectors: ## Run connector tests only
	uv run pytest backend/tests/connectors/ -v

test-agents: ## Run agent tests only
	uv run pytest backend/tests/agents/ -v

test-api: ## Run API tests only
	uv run pytest backend/tests/api/ -v

# ─── Evals ───────────────────────────────────────────────────────────────────
eval: ## Run SQL accuracy evaluation suite
	@echo "$(CYAN)Running QueryMind eval suite...$(RESET)"
	uv run python -m backend.evals.runner --report

eval-tpch: ## Run TPC-H benchmark evaluation
	uv run python -m backend.evals.runner --suite tpch --report

redteam: ## Run SQL injection red-team suite
	@echo "$(YELLOW)Running security red-team suite...$(RESET)"
	uv run python -m backend.evals.redteam --fix

# ─── Load Testing ─────────────────────────────────────────────────────────────
load-test: ## Run Locust load test (50 concurrent users)
	uv run locust -f backend/tests/load/locustfile.py \
		--host http://localhost:8000 \
		--users 50 \
		--spawn-rate 5 \
		--run-time 60s \
		--headless

# ─── Database ─────────────────────────────────────────────────────────────────
migrate: ## Run Alembic migrations
	uv run alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add users table")
	uv run alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback last migration
	uv run alembic downgrade -1

# ─── Docker (Local Dev Infra) ─────────────────────────────────────────────────
docker-up: ## Start local infra (Postgres, Redis, Qdrant, LangFuse)
	docker compose up -d
	@echo "$(GREEN)Infra started:$(RESET)"
	@echo "  PostgreSQL: localhost:5432"
	@echo "  Redis:      localhost:6379"
	@echo "  Qdrant:     http://localhost:6333"
	@echo "  LangFuse:   http://localhost:3001"

docker-down: ## Stop local infra
	docker compose down

docker-reset: ## Stop infra and remove volumes (destructive!)
	docker compose down -v

docker-logs: ## Show infra logs
	docker compose logs -f

docker-build: ## Build all Docker images
	docker compose -f docker-compose.prod.yml build

# ─── Helm / Kubernetes ────────────────────────────────────────────────────────
helm-lint: ## Lint Helm chart
	helm lint infra/helm/querymind/

helm-template: ## Render Helm templates locally
	helm template querymind infra/helm/querymind/ -f infra/helm/querymind/values.yaml

helm-deploy: ## Deploy to Kubernetes
	helm upgrade --install querymind infra/helm/querymind/ \
		--namespace querymind \
		--create-namespace \
		-f infra/helm/querymind/values.yaml \
		--wait

helm-uninstall: ## Uninstall from Kubernetes
	helm uninstall querymind --namespace querymind

# ─── Utilities ────────────────────────────────────────────────────────────────
clean: ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	rm -f .coverage coverage.xml

env: ## Copy .env.example to .env
	cp .env.example .env
	@echo "$(YELLOW)Created .env — fill in your API keys!$(RESET)"

logs: ## Tail backend logs
	tail -f logs/querymind.log

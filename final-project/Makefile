.PHONY: up down logs tunnel test-issue plan lint test coverage

up:
	docker compose up --build -d
	@echo "Factory running. Webhook: http://localhost:8000/webhook"

down:
	docker compose down

logs:
	docker compose logs -f

# Expose local webhook to GitHub (requires ngrok)
tunnel:
	ngrok http 8000

# Simulate a GitHub webhook locally
test-issue:
	@python scripts/simulate_issue.py \
		--repo $(REPO) \
		--title "$(TITLE)" \
		--body "$(BODY)"

# Review the legacy VM prototype without changing cloud resources.
plan:
	cd infra && terraform plan

lint:
	ruff check shared/

# Mismo comando que corre CI (.github/workflows/ci.yml). Falla si la
# cobertura de shared/ baja del 80% definido en pyproject.toml.
test:
	pytest shared/tests --cov=shared --cov-report=term-missing

coverage: test

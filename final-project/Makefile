.PHONY: up down logs tunnel test-issue

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

# Deploy to cloud VMs
deploy:
	cd infra && terraform apply -auto-approve

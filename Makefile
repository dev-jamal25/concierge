ifneq (,$(wildcard .env))
include .env
export
endif

BACKEND_DIR := backend
UV ?= uv

.PHONY: migrate bootstrap-manager lint test seed-demo-tenant seed-demo-users seed-demo-analytics serve-test-host serve-test-host-helix smoke demo-seed-full eval eval-classifier eval-agent eval-rag eval-redteam eval-modelserver

migrate:
	cd $(BACKEND_DIR) && $(UV) run alembic -c app/frameworks/db/alembic.ini upgrade head

bootstrap-manager:
	cd $(BACKEND_DIR) && $(UV) run python -m app.frameworks.cli.bootstrap_manager

lint:
	cd $(BACKEND_DIR) && $(UV) run --extra dev ruff check . && $(UV) run --extra dev lint-imports

test:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest

eval-classifier:
	cd $(BACKEND_DIR) && $(UV) run --extra dev --extra notebooks pytest ../tests/evals/classifier/ -v -s

eval-redteam:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest ../tests/evals/redteam/ -v -s

eval-modelserver:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest tests/integration/test_modelserver_service_token.py -v

eval-agent:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest tests/evals/agent_tool_selection/ -v -s -m eval

eval-rag:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest tests/evals/rag/ -v -s -m eval

seed-demo-tenant:
	cd $(BACKEND_DIR) && $(UV) run python -m app.frameworks.cli.seed_demo_tenants

seed-demo-users:
	cd $(BACKEND_DIR) && $(UV) run python -m app.frameworks.cli.seed_demo_users

seed-demo-chunks:
	cd $(BACKEND_DIR) && $(UV) run python -m app.frameworks.cli.seed_demo_chunks

seed-demo-analytics:
	cd $(BACKEND_DIR) && $(UV) run python -m app.frameworks.cli.seed_demo_analytics

smoke: seed-demo-tenant seed-demo-users
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest ../tests/smoke_test.py -v

# Full local demo seed including RAG embeddings (requires EMBEDDING_API_KEY).
demo-seed-full: seed-demo-tenant seed-demo-users seed-demo-chunks seed-demo-analytics

serve-test-host:
	python -m http.server 3001 --directory tests/widget-host-example

serve-test-host-helix:
	python -m http.server 3002 --directory tests/widget-host-helix

eval:
	@echo "eval pending Owner C/D"

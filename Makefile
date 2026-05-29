ifneq (,$(wildcard .env))
include .env
export
endif

BACKEND_DIR := backend
UV ?= uv

.PHONY: migrate bootstrap-manager lint test seed-demo-tenant serve-test-host smoke eval eval-classifier eval-agent eval-rag eval-redteam eval-modelserver

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
	cd $(BACKEND_DIR) && $(UV) run --extra dev --extra notebooks pytest tests/integration/test_modelserver_service_token.py -v

eval-agent:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest tests/evals/agent_tool_selection/ -v -s -m eval

eval-rag:
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest tests/evals/rag/ -v -s -m eval

seed-demo-tenant:
	cd $(BACKEND_DIR) && $(UV) run python -m app.frameworks.cli.seed_demo_tenants

smoke: seed-demo-tenant
	cd $(BACKEND_DIR) && $(UV) run --extra dev pytest ../tests/smoke_test.py -v

serve-test-host eval:
	@echo "$@ pending Owner C/D"

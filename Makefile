ifneq (,$(wildcard .env))
include .env
export
endif

BACKEND_DIR := backend
UV ?= uv

.PHONY: migrate bootstrap-manager lint test seed-demo-tenant serve-test-host smoke eval eval-classifier eval-agent eval-rag eval-redteam

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

seed-demo-tenant serve-test-host smoke eval eval-agent eval-rag eval-redteam:
	@echo "$@ pending Owner C/D"

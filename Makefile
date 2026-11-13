SHELL := /bin/bash
PGBIN ?= $(shell brew --prefix postgresql@16 2>/dev/null)/bin
PGPORT ?= 54329
API := backend/.venv/bin

.PHONY: help setup db-start db-stop dev api web test test-api test-web lint typecheck migrate gen-api seed-check

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:           ## install backend + frontend dependencies and create .env
	python3 -m venv backend/.venv && $(API)/pip install -q -e "backend[dev]"
	cd frontend && npm install
	cp -n backend/.env.example backend/.env || true

db-start:        ## local Postgres 16 (Homebrew) on port $(PGPORT); Docker users: docker compose up db
	@test -d .local/pgdata || (LC_ALL=en_US.UTF-8 $(PGBIN)/initdb -D .local/pgdata -U cadence --auth=trust -E UTF8 >/dev/null)
	LC_ALL=en_US.UTF-8 $(PGBIN)/pg_ctl -D .local/pgdata -o "-p $(PGPORT) -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp" -l .local/pg.log -w start || true
	-$(PGBIN)/createdb -h 127.0.0.1 -p $(PGPORT) -U cadence cadence_dev 2>/dev/null
	-$(PGBIN)/createdb -h 127.0.0.1 -p $(PGPORT) -U cadence cadence_test 2>/dev/null

db-stop:         ## stop local Postgres
	$(PGBIN)/pg_ctl -D .local/pgdata stop

migrate:         ## apply database migrations to the dev database
	cd backend && .venv/bin/alembic upgrade head

api:             ## run the API on :8000 with reload
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:             ## run the SPA on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev: db-start migrate  ## start the database, migrate, then print how to run api + web
	@echo "Database ready. In two terminals run: make api   and   make web"

test: test-api test-web  ## run every test suite

test-api:        ## backend tests against a real Postgres (needs db-start)
	cd backend && .venv/bin/python -m pytest -q

test-web:        ## frontend unit tests
	cd frontend && npm test

lint:            ## ruff + eslint
	cd backend && .venv/bin/ruff check app tests scripts
	cd frontend && npm run lint

typecheck:       ## tsc (blocking) and mypy (advisory, see README)
	cd frontend && npm run typecheck
	-cd backend && .venv/bin/mypy app

gen-api:         ## regenerate the OpenAPI snapshot and the frontend TypeScript types
	cd backend && PYTHONPATH=. .venv/bin/python scripts/export_openapi.py openapi.json
	cd frontend && npm run gen-api

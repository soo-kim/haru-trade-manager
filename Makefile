.PHONY: help build start start-build stop restart test migrate logs logs-follow

PYTHON := ./.venv/bin/python
DOCKER_COMPOSE := docker compose
LOG_SERVICE ?=

help:
	@echo "Available targets:"
	@echo "  make build    - Build docker images"
	@echo "  make start    - Start services in background (no rebuild)"
	@echo "  make start-build - Start services in background with rebuild"
	@echo "  make stop     - Stop and remove services"
	@echo "  make restart  - Restart services"
	@echo "  make logs     - Show recent logs (LOG_SERVICE=<name> optional)"
	@echo "  make logs-follow - Follow logs (LOG_SERVICE=<name> optional)"
	@echo "  make test     - Run test suite"
	@echo "  make migrate  - Apply alembic migrations"

build:
	$(DOCKER_COMPOSE) build

start:
	$(DOCKER_COMPOSE) up -d

start-build:
	$(DOCKER_COMPOSE) up -d --build

stop:
	$(DOCKER_COMPOSE) down

restart: stop start

logs:
	$(DOCKER_COMPOSE) logs --tail=200 $(LOG_SERVICE)

logs-follow:
	$(DOCKER_COMPOSE) logs -f --tail=200 $(LOG_SERVICE)

test:
	$(PYTHON) -m pytest -q

migrate:
	$(PYTHON) -m alembic upgrade head

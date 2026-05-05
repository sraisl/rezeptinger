.PHONY: help install sync setup migrate server worker dev ruff test check collectstatic docker-lint docker-check docker-build docker-scan compose-up compose-worker compose-down

PYTHON_VERSION := 3.12
HOST := 127.0.0.1
PORT := 8000

help:
	@echo "Rezeptinger tasks"
	@echo ""
	@echo "  make setup          Install tools/deps and run migrations"
	@echo "  make server         Run Django dev server on $(HOST):$(PORT)"
	@echo "  make worker         Run Huey worker for background extraction"
	@echo "  make dev            Run migrations, then start the dev server"
	@echo "  make check          Run ruff and Django tests"
	@echo "  make docker-lint    Lint Dockerfile with Hadolint"
	@echo "  make docker-check   Run Docker lint and Compose config checks"
	@echo "  make docker-build   Build local Docker image"
	@echo "  make docker-scan    Scan local Docker image with Trivy"
	@echo "  make compose-up     Start Docker Compose web service"
	@echo "  make compose-worker Start Docker Compose web service plus worker"
	@echo "  make compose-down   Stop Docker Compose services"

install:
	mise install

sync:
	mise exec uv -- uv sync --python $(PYTHON_VERSION)

setup: install sync migrate

migrate:
	mise exec uv -- uv run python manage.py migrate

server:
	mise exec uv -- uv run python manage.py runserver $(HOST):$(PORT)

worker:
	mise exec uv -- uv run python manage.py run_huey

dev: migrate server

ruff:
	mise exec uv -- uv run ruff check .

test:
	mise exec uv -- uv run python manage.py test

check: ruff test

collectstatic:
	mise exec uv -- uv run python manage.py collectstatic --noinput

docker-lint:
	docker run --rm -i hadolint/hadolint:latest < Dockerfile

docker-check: docker-lint
	docker compose config
	docker compose --profile worker config

docker-build:
	docker build -t rezeptinger:local .

docker-scan: docker-build
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --ignore-unfixed --severity HIGH,CRITICAL --exit-code 1 rezeptinger:local

compose-up:
	docker compose up --build

compose-worker:
	docker compose --profile worker up --build

compose-down:
	docker compose down

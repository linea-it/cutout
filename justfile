set shell := ["bash", "-cu"]

compose := "docker compose -f local.yml"

# List available recipes
@default:
    just --list

# Check local prerequisites and permissions for development
check-auth:
    command -v docker >/dev/null
    docker info >/dev/null
    test -f .envs/.local/.django
    test -f .envs/.local/.postgres
    test -d data

# Build and start all local services
up:
    {{compose}} up -d --build

# Stop and remove local services (keeping named volumes)
down:
    {{compose}} down --remove-orphans

# Stop services without removing containers
stop:
    {{compose}} stop

# Start existing stopped containers
start:
    {{compose}} start

# Restart all services
restart:
    {{compose}} restart

# Show current status of containers
ps:
    {{compose}} ps

# Show recent logs from all services
logs:
    {{compose}} logs --tail=200

# Follow logs from all services
logs-f:
    {{compose}} logs -f --tail=200

# Show recent logs for one service (example: just logs-service django)
logs-service service:
    {{compose}} logs --tail=200 {{service}}

# Follow logs for one service (example: just logs-service-f celeryworker)
logs-service-f service:
    {{compose}} logs -f --tail=200 {{service}}

# Open shell in running service container (default: django)
sh service="django":
    {{compose}} exec {{service}} bash

# Django management command (example: just manage migrate)
manage *args:
    {{compose}} exec django python manage.py {{args}}

# Apply database migrations
migrate:
    {{compose}} exec django python manage.py migrate

# Create new migrations
makemigrations:
    {{compose}} exec django python manage.py makemigrations

# Run pytest suite
test:
    {{compose}} exec django pytest

# Run coverage test suite and print report
test-cov:
    {{compose}} exec django coverage run -m pytest
    {{compose}} exec django coverage report

# Run static checks used in this project
lint:
    {{compose}} exec django black --check .
    {{compose}} exec django isort --check-only .
    {{compose}} exec django flake8
    {{compose}} exec django mypy cutout

# Auto-format Python code
fmt:
    {{compose}} exec django black .
    {{compose}} exec django isort .

# Run pre-commit hooks across repository
precommit:
    {{compose}} exec django pre-commit run --all-files

# Rebuild app and worker images after dependency changes
rebuild:
    {{compose}} build django celeryworker celerybeat flower

# Start only app + queue stack needed for sync cutout development
up-core:
    {{compose}} up -d django postgres redis celeryworker celerybeat flower

# Stop only app + queue stack
stop-core:
    {{compose}} stop django postgres redis celeryworker celerybeat flower

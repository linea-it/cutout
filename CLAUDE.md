# Agent Instructions for Cutout Service

This document is for coding agents (Codex, Claude, and similar) working in this repository.

## 1. Project Overview

- Stack: Django 4.2, DRF, Celery, Redis, PostgreSQL, Docker Compose.
- Runtime: Python 3.11.
- API docs: drf-spectacular.
- Scientific domain: FITS cutout processing with Astropy.

Main local orchestration file:
- local.yml

Main app entrypoint in local environment:
- compose/local/django/start

## 2. Required Permissions and Access

Before implementing features, ensure these permissions are available:

- Docker daemon access:
  - User must have permission to run docker commands.
  - Usually requires membership in docker group or sudo rights.
- Local env files present:
  - .envs/.local/.django
  - .envs/.local/.postgres
- Data directory write access:
  - data/
  - data/log/
  - data/results/
- Open local ports:
  - 8000 (Django API)
  - 5555 (Flower)
  - 8025 (Mailhog)
  - 9000 (Docs)

Authorization policy context for planned work:
- A policy layer must be used for survey access decisions.
- Current test dataset is DES DR2 (public), so initial policy implementation can return true.
- Do not hardcode private survey authorization logic yet.

## 3. Container Operations

Preferred workflow uses just recipes from justfile.

Mandatory execution rule:

- Run application commands only inside containers.
- Use `docker compose -f local.yml exec` for running services.
- Use `docker compose -f local.yml run --rm` for one-shot commands.
- Do not run `python`, `pip`, `pytest`, `mypy`, `flake8`, `black`, `isort`, `pre-commit`, or `celery` on the host.
- Never install dependencies on the host.

Examples:
- just check-auth
- just up
- just ps
- just logs-f
- just logs-service-f django
- just logs-service-f celeryworker
- just down

Raw docker compose equivalent:
- docker compose -f local.yml up -d --build
- docker compose -f local.yml down --remove-orphans
- docker compose -f local.yml logs -f --tail=200
- docker compose -f local.yml exec django python manage.py migrate
- docker compose -f local.yml run --rm django python manage.py shell

## 4. How to Run the Application

- Start stack:
  - just up
- Verify services:
  - just ps
- API base URL:
  - http://localhost:8000/api/

## 5. Coding Standards and Linting

Configured style and tooling:

- black line length: 119 (pyproject.toml)
- isort profile: black
- flake8 configured in setup.cfg
- mypy configured in pyproject.toml
- pre-commit hooks in .pre-commit-config.yaml

Run checks:

- just lint
- just precommit

Autoformat:

- just fmt

## 6. Testing

Pytest configuration is in pyproject.toml with:
- --ds=config.settings.test
- --reuse-db

Commands:

- just test
- just test-cov

If needed directly in container:
- docker compose -f local.yml exec django pytest
- docker compose -f local.yml exec django coverage run -m pytest

## 7. Installing or Updating Python Packages

This project installs dependencies from requirements files during image build.

Dependency files:
- requirements/base.txt
- requirements/local.txt
- requirements/production.txt

Recommended process for new package:

1. Add pinned dependency to the correct requirements file.
2. Rebuild images:
   - just rebuild
3. Restart services:
   - just up
4. Validate imports/tests:
   - just test

Hard constraints:

- Never install dependencies on the host.
- Never use host-level virtualenv for this project.
- If an emergency install is needed for debugging, do it only inside container and then persist in requirements files + image rebuild.

## 8. Implementation Guidance for the Current Plan

The current plan requires:

- Sync endpoint support for all spatial request types:
  - CIRCLE
  - RANGE
  - POLYGON
- Explicit policy layer in the request pipeline:
  - parse request
  - check survey access policy
  - discover files
  - dispatch cutout job
  - return sync response

When implementing, preserve modular boundaries:

- API layer only orchestrates request/response.
- Policy layer decides access.
- Discovery layer finds candidate files.
- Cutout engine performs processing.

## 9. Useful Development Commands

- Django management:
  - just manage migrate
  - just manage createsuperuser
- Interactive shell in app container:
  - just sh django
- Follow worker logs during job execution:
  - just logs-service-f celeryworker
- Follow app logs during endpoint tests:
  - just logs-service-f django

## 10. Safety Rules for Agents

- Do not remove unrelated user changes.
- Prefer incremental refactors over rewrites.
- Keep API behavior explicit and test-backed.
- Add tests for new endpoint behavior and policy checks.
- Keep errors aligned with the planned SODA-like text/plain pattern.

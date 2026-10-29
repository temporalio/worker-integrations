# Shared make targets for every Python package in this repository.
#
# A package's Makefile is exactly two lines:
#     DIST := <published name>
#     include ../_shared/python.mk
#
# CI runs these same targets (.github/workflows/_python-package.yml), so there is one definition
# of "lint" and "test".
# See AGENTS.md ("Python conventions") for why installs are non-editable and which tools run.

ifndef DIST
$(error DIST must be set to the package's distribution name (e.g. temporalio-worker-integrations-aws-lambda-worker) before including python.mk)
endif

# `temporalio` is a regular package owned by the SDK wheel, so an editable install of this
# package cannot reliably extend it with another package root. Every uv command below runs non-editable.
export UV_NO_EDITABLE := 1

# Which dependency versions `sync` installs (CI sets it per matrix cell):
#   locked  the committed uv.lock
#   lowest  re-lock to the lowest versions allowed for direct dependencies
#   latest  re-lock to the newest allowed versions
# `lowest` and `latest` rewrite uv.lock; never commit the result. uv records the resolution mode in
# uv.lock and rejects a lock made in another mode, so later targets must be given the same DEPS.
DEPS ?= locked
ifeq ($(DEPS),lowest)
export UV_RESOLUTION := lowest-direct
else ifneq ($(filter-out locked latest,$(DEPS)),)
$(error DEPS must be locked, lowest, or latest (got '$(DEPS)'))
endif

PYTEST_ARGS ?=
UV_RUN := uv run --locked
PYTEST := $(UV_RUN) pytest -n auto --dist=worksteal

.PHONY: help sync format lint test build clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

sync: ## Install dependencies (see DEPS) and this package (non-editable); creates uv.lock on first run
ifeq ($(DEPS),locked)
	@test -f uv.lock || uv lock
else ifeq ($(DEPS),lowest)
	uv lock
else
	uv lock --upgrade
endif
	uv sync --locked

format: ## Fix import order and formatting
	$(UV_RUN) ruff check --select I --fix
	$(UV_RUN) ruff format

lint: ## Import order, formatting, pyright, mypy, basedpyright, docstrings
	$(UV_RUN) ruff check --select I
	$(UV_RUN) ruff format --check
	$(UV_RUN) pyright
	$(UV_RUN) mypy
	$(UV_RUN) basedpyright
	$(UV_RUN) pydocstyle --ignore-decorators=overload src

test: ## Run the test suite
	$(PYTEST) $(PYTEST_ARGS)

build: ## Build sdist and wheel into dist/
	rm -rf dist
	uv build --no-sources --out-dir dist

clean: ## Remove build and test artifacts and the virtualenv
	rm -rf dist .venv junit

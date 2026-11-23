# Shared make targets for every TypeScript package in this repository.
#
# A package's Makefile is exactly one line:
#     include ../_shared/typescript.mk
#
# CI runs these same targets, so there is one definition of "lint" and "test".
# See AGENTS.md ("TypeScript conventions").

# Which dependency versions `sync` installs:
#   locked  the committed pnpm-lock.yaml
#   lowest  re-lock to the lowest versions allowed for direct dependencies
#   latest  re-lock to the newest allowed versions
# `lowest` and `latest` rewrite pnpm-lock.yaml (but not package.json); never commit the result.
DEPS ?= locked
ifneq ($(filter-out locked lowest latest,$(DEPS)),)
$(error DEPS must be locked, lowest, or latest (got '$(DEPS)'))
endif

AVA_ARGS ?=

.PHONY: help sync format lint compile test build clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

sync: ## Install dependencies (see DEPS); creates pnpm-lock.yaml on first run
ifeq ($(DEPS),locked)
	pnpm install $(if $(wildcard pnpm-lock.yaml),--frozen-lockfile)
else ifeq ($(DEPS),lowest)
	pnpm update --no-save --config.resolution-mode=lowest-direct
else
	pnpm update --no-save
endif

format: ## Fix formatting
	pnpm exec oxfmt

lint: compile ## Type-check, formatting, and oxlint (with type-aware rules)
	pnpm exec oxfmt --check
	pnpm exec oxlint

# From scratch every time: tsc leaves the outputs of deleted sources in lib/, where tests would
# still run and `make build` would pack them. A full compile is fast at these packages' sizes.
compile: ## Compile src/ into lib/
	rm -rf lib tsconfig.tsbuildinfo
	pnpm exec tsc --build

test: compile ## Run the tests (AVA, on the compiled *.test.js files under lib/)
	pnpm exec ava $(AVA_ARGS)

build: compile ## Pack the npm tarball into dist/
	rm -rf dist
	pnpm pack --pack-destination dist

clean: ## Remove build output and installed dependencies
	rm -rf lib dist node_modules tsconfig.tsbuildinfo

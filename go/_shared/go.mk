# Shared make targets for every Go module in this repository.
#
# A module's Makefile is exactly one line, with one `../` per element of its folder path below go/:
#     include ../../_shared/go.mk   # e.g. for go/aws/lambda
#
# Targets run in the module's own folder, so `./...` covers its packages but not modules nested
# in it, which have their own Makefile. See AGENTS.md ("Go conventions").

# Which dependency versions `sync` uses:
#   locked  the versions in the committed go.mod and go.sum
#   latest  upgrade to the newest versions that support go.mod's go directive (rewrites go.mod and
#           go.sum; never commit the result)
# There's no `lowest` mode: Go's minimal version selection already uses the lowest versions go.mod
# allows, so `locked` tests them.
DEPS ?= locked
ifneq ($(filter-out locked latest,$(DEPS)),)
$(error DEPS must be locked or latest (got '$(DEPS)'))
endif

GO_TEST_ARGS ?=

.PHONY: help sync format lint test build

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# In `latest` mode: on its own, `go get -u` takes every dependency's newest version and raises the
# go directive to the newest Go any of them needs. go@<the go directive> keeps the module's minimum
# Go instead, and picks each dependency's newest version that supports it, which is what a user on
# that Go version gets by upgrading.
sync: ## Download and verify dependencies (see DEPS)
ifeq ($(DEPS),latest)
	go get -u -t ./... go@$$(go list -m -f '{{.GoVersion}}')
	go mod tidy
endif
	go mod download
	go mod verify

format: ## Fix formatting
	gofmt -w .

lint: ## Formatting, go vet, and whether go.mod and go.sum are tidy
	@test -z "$$(gofmt -l .)" || { echo "Not gofmt-formatted (run make format):"; gofmt -l .; exit 1; }
	go vet ./...
	go mod tidy -diff

test: ## Run the tests
	go test -count=1 $(GO_TEST_ARGS) ./...

build: ## Compile every package
	go build ./...

# Go modules

This README is a human-friendly getting-started overview for Go developers. For a general overview
of the repository, see the [main README](../README.md).

For a precise specification of rules for Go modules, see the "Go conventions" section in
[`AGENTS.md`](../AGENTS.md#go-conventions). Most of them are enforced by the repository's
conventions checks in CI.

## Layout

All Go modules have a module path starting with the `go.temporal.io/worker-integrations/` prefix.
Each module's code lives in the folder matching its module path after the prefix. For example,
`go.temporal.io/worker-integrations/aws/lambda` lives in `aws/lambda`. Nesting is supported, so a
nested module like `go.temporal.io/worker-integrations/aws/lambda/otel` would live in the subfolder
`aws/lambda/otel` as its own Go module, with its own `go.mod`.

The special `_shared/` subdirectory defines shared config across all Go modules, which notably
includes `make` target definitions. The `_template/` directory contains a template module
structure, from which all real modules are derived.

## Prerequisites

- [Go](https://go.dev/dl/), at least the version in the module's `go.mod`
- GNU make. On Windows, install it with `choco install make`, or use WSL.
- [uv](https://docs.astral.sh/uv/), to run the repository's scripts (e.g. to add a module)

## Working on a module

You can interact with a module with the usual `go` commands or the `make` targets:

```bash
# Plain go commands
go vet ./...
go test ./...

# Or the make targets
make sync   # download and verify the dependencies in go.mod and go.sum
make lint   # gofmt, go vet, and whether go.mod and go.sum are tidy
make test
```

You can run `make help` to list every target.

To add or change dependencies, use `go get`, then run `go mod tidy`.

## Adding a module

From the repository root, pass the module path to `scripts/new_package.py`:

```bash
uv run --project scripts --locked python scripts/new_package.py \
    --go go.temporal.io/worker-integrations/aws/lambda \
    --description "Temporal worker integration for AWS Lambda" \
    --maturity public-preview
```

This creates the module folder from `_template/` and prints suggested next steps, such as adding
dependencies. Before the module's first release, it also needs a page on the `go.temporal.io`
vanity import server, which a member of the temporalio GitHub organization sets up; the printed
steps list the details.

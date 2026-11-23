# TypeScript packages

This README is a human-friendly getting-started overview for TypeScript developers. For a general
overview of the repository, see the [main README](../README.md).

For a precise specification of rules for TypeScript packages, see the "TypeScript conventions"
section in [`AGENTS.md`](../AGENTS.md#typescript-conventions). Most of them are enforced by the
repository's conventions checks in CI.

## Layout

All TypeScript packages are published to npm under the `@temporalio` scope. Each package lives in
the folder named after its npm name without the scope. For example, `@temporalio/aws-lambda-worker`
lives in `aws-lambda-worker`.

Each package is its own pnpm project, with its own lockfile and `pnpm-workspace.yaml`; there's no
workspace spanning the packages.

The special `_shared/` subdirectory defines shared config across all TypeScript packages, which
notably includes `make` target definitions and the base TypeScript config. The oxlint and oxfmt
configs sit directly in this folder instead, where the tools and editors find them on their own.
The `_template/` directory contains a template package structure, from which all real packages are
derived.

## Prerequisites

- [Node.js](https://nodejs.org/), at least the version in the package's `engines.node`
- [pnpm](https://pnpm.io/installation), which switches itself to the version in the package's
  `packageManager`
- GNU make. On Windows, install it with `choco install make`, or use WSL.
- [uv](https://docs.astral.sh/uv/), to run the repository's scripts (e.g. to add a package)

## Working on a package

You can interact with a package with the usual `pnpm` commands or the `make` targets:

```bash
# Plain pnpm commands
pnpm install
pnpm exec tsc --build
pnpm exec oxlint
pnpm exec ava

# Or the make targets
make sync   # install the dependencies in pnpm-lock.yaml
make lint   # type-check, formatting, and oxlint
make test
```

You can run `make help` to list every target, and `make format` fixes formatting.

Tests use [AVA](https://github.com/avajs/ava). Put them in `src/__tests__/`, in files named
`*.test.ts`; `make test` compiles them and runs the compiled copies.

To add a dependency at its newest version, use `pnpm add`, which saves a caret range on that
version. Depend on `@temporalio/*` packages with a caret range on the oldest SDK version the
package supports instead (e.g. `^1.24.0`), and state the same range in the package README's
Compatibility section. `pnpm add` can't save a range on an older version, so write it with
`pnpm pkg set` (or by hand), then run `pnpm install`:

```bash
pnpm add some-package                                       # newest version
pnpm pkg set 'dependencies["@temporalio/worker"]=^1.24.0'   # a chosen minimum
pnpm install
```

## Adding a package

From the repository root, pass the npm name to `scripts/new_package.py`:

```bash
uv run --project scripts --locked python scripts/new_package.py \
    --typescript @temporalio/aws-lambda-worker \
    --description "Temporal worker integration for AWS Lambda" \
    --maturity public-preview
```

This creates the package folder from `_template/` and prints suggested next steps, such as adding
dependencies.

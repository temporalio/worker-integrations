# Python packages

This README is a human-friendly getting-started overview for Python developers. For a general
overview of the repository, see the [main README](../README.md).

For a precise specification of rules for Python packages, see the "Python conventions" section in
[`AGENTS.md`](../AGENTS.md#python-conventions). Most of them are enforced by the repository's
conventions checks in CI.

## Layout

Each non-underscored subdirectory is a separate Python package. All packages define an import path
under `temporalio.worker_integrations`, from which various other identifiers are derived.

For example, a package that defines the root path of `temporalio.worker_integrations.aws.lambda_worker`
will live in the `aws_lambda_worker` subdirectory, be published as
`temporalio-worker-integrations-aws-lambda-worker`, and have a source tree mirroring the import path,
`src/temporalio/worker_integrations/aws/lambda_worker`.

The special `_shared/` subdirectory defines shared config across all Python packages, which notably
includes `make` target definitions. The `_template/` directory contains a template package structure,
from which all real packages are derived.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- GNU make. On Windows, install it with `choco install make`, or use WSL.

## Working on a package

Most interaction with a package should be done through `make` targets. For example, to run the tests:

```bash
make sync   # install the locked dependencies and the package into .venv
make lint
make test
```

You can run `make help` to list every target.

After changing dependencies in `pyproject.toml`, run `uv lock` to update `uv.lock`.
Use the `make` targets rather than plain `uv sync` or `uv run`. See the section in
[`AGENTS.md`](../AGENTS.md#python-conventions) regarding non-editable installs for details.

## Adding a package

From the repository root, pass the package's full import path to `scripts/new_package.py`:

```bash
uv run --project scripts --locked python scripts/new_package.py \
    --python temporalio.worker_integrations.aws.lambda_worker \
    --description "Temporal worker integration for AWS Lambda" \
    --maturity public-preview
```

This creates the package folder from `_template/` and prints suggested next steps.
Loosely, this entails adding dependencies, setting the supported `temporalio` SDK versions,
and updating the lock file. Before the package's first release, it also needs trusted publishers
on PyPI and TestPyPI, which a PyPI organization admin sets up; the printed steps list the details.

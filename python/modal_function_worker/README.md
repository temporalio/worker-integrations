# Temporal worker integration for Modal Functions

Published as [`temporalio-worker-integrations-modal-function-worker`](https://pypi.org/project/temporalio-worker-integrations-modal-function-worker/) and imported as
`temporalio.worker_integrations.modal.function_worker`.

## Install

```bash
uv add temporalio-worker-integrations-modal-function-worker
```

This also installs `temporalio`, the Temporal Python SDK, if it isn't installed already. If you
install packages into separate directories instead of one environment (for example with
`pip install --target`), make sure this package goes in the same directory as `temporalio`. Since
it's part of the `temporalio` package, Python only looks for it in the directory where `temporalio`
is installed.

## Compatibility

Supports `temporalio` versions `>=1.34.0,<2`. Package versions do not imply compatibility with the
same-numbered SDK version.

## Develop

See the repository's
[`python/README.md`](https://github.com/temporalio/worker-integrations/blob/main/python/README.md)
for setup and conventions.

```bash
make sync   # install (non-editable) into .venv
make lint
make test
```

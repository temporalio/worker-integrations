# Temporal Worker Integrations

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Integrations for running [Temporal](https://temporal.io) workers on serverless and managed compute
platforms, such as AWS Lambda and Google Cloud Run. Each integration is its own package with its
own dependencies, tests, version and release cadence.

Packages are organized by language, as `<language>/<package>/`. There are no packages here yet;
the existing integrations are being moved here from the `contrib` directories of the Temporal
SDK repositories, and are still published from there for now.

For now, samples for these integrations live in the per-language `samples-<language>` repositories (for
example, [samples-go](https://github.com/temporalio/samples-go)), not in this repository.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) to contribute, and [`AGENTS.md`](AGENTS.md) for the
repository's conventions.

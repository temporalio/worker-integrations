# Temporal Worker Integrations

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Integrations for running [Temporal](https://temporal.io) workers on serverless and managed compute
platforms, such as AWS Lambda and Google Cloud Run, built on top of the base SDKs (for example,
[sdk-go](https://github.com/temporalio/sdk-go)). Each integration is its own package with its
own dependencies, tests, version and release cadence.

There are no packages here yet; the existing integrations are being moved here from the `contrib`
directories of the Temporal SDK repositories, and are still published from there for now.

For now, samples for these integrations live in the per-language `samples-<language>` repositories (for
example, [samples-go](https://github.com/temporalio/samples-go)), not in this repository.

## Documentation

This top-level README is written to be human-friendly, and describes the overall design of this
repository. Please exercise appropriate consideration for human readers when making changes to it.

For more concrete information on how to contribute, see [`CONTRIBUTING.md`](CONTRIBUTING.md).
For a highly detailed and normative guide meant for coding agents (but still human-readable),
see [`AGENTS.md`](AGENTS.md).

Each language subdirectory also contains a human-friendly README with targeted overviews and
instructions for developers to get started with working with packages of that specific language.

## Repository structure

Packages are organized by language, with all code for a specific language living under `<language>/`.
Within each language subdirectory, this repository respects language-specific conventions for code
structure to the extent possible.

In all languages except Go, each distributed package is a direct subdirectory of the language,
`<language>/<package>/`. In Go, directory structure instead mirrors package import paths, so a
package with path `go.temporal.io/workerintegrations/a/b/c` is defined within `go/a/b/c`.

Every package includes a typical language-native manifest file, alongside a custom file called
`integration.toml`, which defines some extra metadata used by repository tooling (see
[`scripts/lib/integration_toml.py`](scripts/lib/integration_toml.py) for the precise schema). The
[`LICENSE`](LICENSE) file is copied verbatim into each package, to ensure that it gets bundled in
package distributions by each language's native package management tools.

On top of package code itself, each language subdirectory may also contain special shared resources
starting with `_` or `.`. For example, `<language>/_shared` with shared project config or
`<language>/_template` with language-specific templates for creating new packages.

The top-level `scripts/` directory contains repository-wide tooling scripts. See the
[Repository tooling](#repository-tooling) section for more information.

## Repository tooling

This repository contains extensive tooling for managing packages across all the different languages
in a consistent manner. This includes scripts for running CI tasks and smoke tests, enforcing
repository conventions, publishing releases, automatically setting up new packages, and more.

The `scripts/` directory is itself a standalone (unpublished) Python project, and includes its own
tests.

## Releases

Releases are cut per-package from the `main` branch, and are based on GitHub releases. Tags are
directory-scoped in the Go-style format of `<path>/<to>/<package>/vX.Y.Z`. Release tags are
immutable and cannot be moved or deleted once created.

Release notes are generated automatically from commit history, rather than relying on manual CHANGELOG
files.

The recommended steps to create a new release are as follows:

1. Manually trigger a dry-run release CI workflow for the relevant language with the planned tag name,
   to confirm the validity of the release before the tag is actually created.
   (TODO: these workflows don't exist yet)
2. Generate release notes with the release tool.
   (TODO: this tool doesn't exist yet)
3. Create a draft GitHub release (or pre-release when appropriate), targeting the commit tested in the
   dry run.
4. Publish the release from the draft, letting GitHub create the specified tag.
5. Monitor the CI workflows triggered automatically by the release publication, which will publish a
   new package version to the language-specific package registry (if relevant) and run smoke tests.
   (TODO: these workflows don't exist yet)

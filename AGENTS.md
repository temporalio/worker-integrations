<!-- AGENTS.md is symlinked to CLAUDE.md — they are the same file. -->

# Temporal SDK worker integrations

Thorough, normative guide for humans and coding agents working in this repository.
Also see the human-friendly [README.md](README.md) for a high-level overview.

## Do not

1. Do not add samples for now. Samples currently live in the `samples-<language>` repositories
   and depend on published versions of these packages.
2. Do not reference base SDK code by local path, workspace, `replace` directive or project
   reference. Depend on published SDK releases only.
3. Do not add cross-package dependencies by local path. Packages in this repository depend on each
   other through their published names only.
4. Do not write `CHANGELOG.md` files. Release notes are generated from commit messages.
5. Do not add per-package license files with different terms. The root MIT [`LICENSE`](LICENSE)
   applies to everything, and is copied verbatim into each package folder so every published
   artifact includes it.
6. Do not add a nested `go.mod` inside a Go module for its tests or tooling. Go modules can nest,
   so repository tooling would treat it as a separate package. Keep tests in the package's own
   module. (Other languages only treat top-level folders as packages, so nested manifests such
   as a .NET test project are fine there, as long as the package's own test target runs them.)

## Purpose and layout

Integrations that run Temporal workers on serverless and managed compute platforms (AWS Lambda,
Google Cloud Run, ...). Each package is independently installable, dependency-isolated, tested,
versioned and released.

Layout is `<language>/<package>/`, one folder per published package, following each language's
conventions:

- **Go:** a module's folder mirrors its module path, so `<package>` is a relative path and modules
  can nest, e.g. `go/aws/lambda/` and `go/aws/lambda/otel/`. Intermediate folders without a
  `go.mod` (e.g. `go/aws/`) are not packages.
- **Every other language:** `<package>` is a single folder directly under the language root, named
  after the package (e.g. `python/aws_lambda_worker/`). Import-path nesting belongs inside the
  package's own source tree, not in the repository layout.

Directories under a language root that start with `_` or `.` (e.g. `_shared/`, `_template/`) hold
shared configuration and templates, and never contain packages; neither do `testdata/` folders.

Each package folder contains its native manifest and lockfile (if relevant for the language), a
`README.md`, a copy of the root `LICENSE`, and an `integration.toml` metadata file.

A package's *published name* is the name it is published under in its language's registry: e.g.
its PyPI, npm, NuGet, crates.io or RubyGems name, its Maven `group:artifact`, or its Go module path.

`integration.toml` describes a package in a format that is the same for every language: e.g. its
published name, maturity, and the language runtime versions it supports. Repository-wide tooling,
such as CI and release automation, reads package metadata from this file instead of from each
language's native manifest, so that adding a package doesn't require tooling changes.

`integration.toml` holds metadata only: no owners (ownership is in
[`.github/CODEOWNERS`](.github/CODEOWNERS)) and no secrets. The package's language and folder path
come from its location, so the file doesn't repeat them. Its schema is documented in
[`scripts/lib/integration_toml.py`](scripts/lib/integration_toml.py). Repository tooling reads it
through that module's `IntegrationMeta`, which validates the schema; never index the raw TOML.
`scripts/ci/check_conventions.py` also checks that it agrees with the native manifest.

## Versions and tags

- A new published name starts at `0.0.1` (Pre-release), `0.1.0` (Public Preview) or `1.0.0`
  (Generally Available).
- A published name that already exists (e.g. one previously published from an SDK repository)
  continues from its highest published version.
- Release tags are `<language>/<package>/v<version>`, e.g. `python/aws_lambda_worker/v0.1.0` or
  `go/aws/lambda/otel/v0.1.0`: the first segment is the language, the last is the version, and
  everything in between is the package's folder path. Never move or delete a release tag.
- Each package's `README.md` states the range of base SDK versions it supports. Package versions
  do not imply compatibility with the same-numbered SDK version.

## CI

- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) is the single CI entry point.
  `scripts/ci/detect_changes.py` selects the packages an event touches: a package's own files
  select that package (the innermost one, for nested Go modules); other files under a language
  root select every package of that language; `.github/**`, `scripts/ci/**`, `scripts/lib/**` and
  `LICENSE` select everything.
- Packages are identified by their folder path relative to the language root, which can contain
  `/` for Go. Where `/` isn't allowed (e.g. artifact names), use `Package.slug` from
  `scripts/lib/common.py`.
- `scripts/ci/check_conventions.py` checks repository invariants on every run.
- `ci-status` is the only required check. Every other job in `ci.yml` must be listed in its
  `needs` (enforced by `scripts/tests/test_workflows.py`).
- Pin every third-party action to a full commit SHA with a `# vX.Y.Z` comment.
- Repository tooling lives in `scripts/`, a standalone uv project: CI entry points in
  `scripts/ci/`, shared code in the `scripts/lib/` package (stdlib only, since
  `detect_changes.py` runs before uv is installed). Entry scripts put `scripts/` on `sys.path`
  and import `lib.*`. Run its tests with `uv run --project scripts --locked pytest scripts/tests -q`.

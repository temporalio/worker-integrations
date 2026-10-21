# AGENTS.md — temporalio/worker-integrations

Normative guide for humans and coding agents working in this repository. Other documents
(`README.md`, `CONTRIBUTING.md`) are short and link here.

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

## Purpose and layout

Integrations that run Temporal workers on serverless and managed compute platforms (AWS Lambda,
Google Cloud Run, ...). Each package is independently installable, dependency-isolated, tested,
versioned and released.

Layout is `<language>/<package>/`, one folder per published package. Directories directly under a
language root that start with `_` (e.g. `_shared/`, `_template/`) hold shared configuration and
templates, and are not packages.

Each package folder contains its native manifest and lockfile (if relevant for the language), a
`README.md`, a copy of the root `LICENSE`, and an `integration.toml` metadata file.

A package's *published name* is the name it is published under in its language's registry: e.g.
its PyPI, npm, NuGet, crates.io or RubyGems name, its Maven `group:artifact`, or its Go module path.

`integration.toml` describes a package in a format that is the same for every language: e.g. its
published name, maturity, and the language runtime versions it supports. Repository-wide tooling,
such as CI and release automation, reads package metadata from this file instead of from each
language's native manifest, so that adding a package doesn't require tooling changes.

## Versions and tags

- A new published name starts at `0.0.1` (Pre-release), `0.1.0` (Public Preview) or `1.0.0`
  (Generally Available).
- A published name that already exists (e.g. one previously published from an SDK repository)
  continues from its highest published version.
- Release tags are `<language>/<package>/v<version>`, e.g. `go/lambdaworker/v0.1.0`. Never move or
  delete a release tag.
- Each package's `README.md` states the range of base SDK versions it supports. Package versions
  do not imply compatibility with the same-numbered SDK version.

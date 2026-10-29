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
  (Generally Available), or a pre-release of that version.
- A published name that already exists (e.g. one previously published from an SDK repository)
  continues from its highest published version: every release must be greater than every
  published version, yanked ones included.
- A package's version is always at least the first version for its current maturity (or a
  pre-release of it): raising a package's maturity means its next release starts there, e.g. at
  `1.0.0` once it's Generally Available.
- Release tags are `<language>/<package>/v<version>`, e.g. `python/aws_lambda_worker/v0.1.0` or
  `go/aws/lambda/otel/v0.1.0`: the first segment is the language, the last is the version, and
  everything in between is the package's folder path. The version is spelled exactly as the
  language's registry publishes it (e.g. `0.1.0rc1` for Python), so that the tag matches the
  published version. Never move or delete a release tag.
- `scripts/ci/check_release.py` enforces these rules at the start of every release workflow.
- `scripts/release_notes.py` generates a release's notes from the subjects of the commits that
  changed the package since its previous release (for a final release, the previous final
  release), excluding packages nested inside it. Commit subjects are therefore user-facing: on a
  squash merge, the pull request's title becomes the subject.
- Each package's `README.md` states the range of base SDK versions it supports. Package versions
  do not imply compatibility with the same-numbered SDK version.

## Python conventions

- **Names:** every package's root API (`root-api` in `integration.toml`) is a module under
  `temporalio.worker_integrations`, and its other names derive from it. The folder is the rest of
  the root API with `.` replaced by `_`, and the published name is the whole root API with `.`
  and `_` replaced by `-`. For example, `temporalio.worker_integrations.aws.lambda_worker` lives in
  `python/aws_lambda_worker/` and is published as
  `temporalio-worker-integrations-aws-lambda-worker`.
- **Layout:** the package folder contains `pyproject.toml`, `uv.lock`, `integration.toml`,
  `Makefile`, `README.md`, `LICENSE`, `tests/`, and the root API under `src/` as a directory path
  (e.g. `src/temporalio/worker_integrations/aws/lambda_worker/`).
- **Namespace packages:** only the root API package has an `__init__.py` (and `py.typed`). Never
  add `__init__.py` to the folders above it under `src/`: the SDK wheel owns `temporalio`, and the
  levels below it are shared by every package in this repository.
- **Non-editable installs:** an editable install can't extend the SDK-owned `temporalio`
  package from `src/`, so `python/_shared/python.mk` exports `UV_NO_EDITABLE=1`. Use the `make`
  targets (`make help`) rather than plain `uv sync`/`uv run`. The provenance guard in
  `tests/conftest.py` fails the test run if the installed package isn't a clean, non-editable
  install.
- **Versions:** `[project] version` stays `0.0.0`; release tags supply the published version,
  which release builds set with `uv version --no-sync` before `make sync`. The first
  `[ci] runtime-versions` entry must equal the `requires-python` floor.
- **Release versions** are `X.Y.Z` or a pre-release of it, `X.Y.Z` followed by `a<N>`, `b<N>` or
  `rc<N>` (e.g. `0.1.0rc1`), in canonical PEP 440 spelling. Post, dev and local versions and
  epochs aren't supported: release the next patch version instead.
- **Dependencies:** `exclude-newer = "2 weeks"` (a supply-chain cooldown) with
  `exclude-newer-package = { temporalio = false }`, so a new SDK release can be adopted the day
  it ships. Declare exactly what the package imports at module level; optional integrations go in
  an extra. Keep lower bounds honest: CI also tests with the lowest versions they allow (see
  **CI**).
- **Dependency modes:** the `DEPS` make variable selects what `make sync` installs: `locked`
  (default) is the committed `uv.lock`, `lowest` re-locks with uv's `lowest-direct` resolution, and
  `latest` re-locks to the newest allowed versions. Pass the same `DEPS` to every later target
  (e.g. `make sync test DEPS=lowest`), since a lock re-made with `lowest` is only accepted in that
  mode. Never commit a re-made `uv.lock`; restore it with `git checkout uv.lock`.
- **Tooling:** ruff, pyright, basedpyright, mypy, pydocstyle (google) and pytest with xdist, all
  run through `make lint` and `make test`. `python/_shared/` holds the make targets and shared
  Pyright/Ruff config; it must not contain Python code. Mypy and pydocstyle settings stay in each
  `pyproject.toml`, because those tools can't extend a shared config.
- **Standard test support:** `tests/helpers/package_meta.py`, `tests/helpers/provenance.py` and
  `tests/test_installed_matches_source.py` must stay byte-identical to their
  `python/_template/` versions (enforced by the conventions check). Package-specific fixtures go
  in the package's own `tests/conftest.py`.
- **Smoke test:** CI installs the built wheel and sdist into clean environments, once without
  extras and once with all of them, imports the package's modules and runs the provenance guard.
  Releases run it again on the files published to TestPyPI and PyPI. List submodules that the root API doesn't import (e.g. public entry points), and that must work
  without extras, in `integration.toml`'s `[smoke] imports`.

### Adding a Python package

```bash
uv run --project scripts --locked python scripts/new_package.py \
    --python temporalio.worker_integrations.aws.lambda_worker \
    --description "Temporal worker integration for AWS Lambda" \
    --maturity public-preview
```

`scripts/new_package.py` is shared by every language that has a template. Each language option
takes the name that identifies a package in that language, since naming styles differ by
language; for Python, that's the full root API. This one creates `python/aws_lambda_worker/` from
`python/_template/`, deriving the folder and published name from the root API (see **Names**
above) and the maturity classifier from `--maturity`, and copies the root `LICENSE`. It then
prints the remaining steps: add dependencies, set the real `temporalio` floor, run `make sync`
(which creates `uv.lock`; commit it), `make lint` and `make test`. Check the result with
`uv run --project scripts --locked python scripts/ci/check_conventions.py`.

Template files end in `.tmpl` so that tools ignore the template itself; the script drops the
suffix. If you change the template, keep `python/_template/` and
`scripts/lib/languages/python.py` (naming, conventions checks and scaffolding) in sync.

## CI

- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) is the single CI entry point.
  `scripts/ci/detect_changes.py` selects the packages an event touches: a package's own files
  select that package (the innermost one, for nested Go modules); the language's own
  `<language>/README.md` selects nothing; other files under a language root select every package
  of that language; `.github/**`, `scripts/ci/**`, `scripts/lib/**` and
  `LICENSE` select everything.
- Packages are identified by their folder path relative to the language root, which can contain
  `/` for Go. Where `/` isn't allowed (e.g. artifact names), use `Package.slug` from
  `scripts/lib/common.py`.
- Each language has one reusable workflow (e.g. `_python-package.yml`) that `ci.yml` calls once
  per selected package. It runs the package's `make` targets across a matrix built from
  `integration.toml`'s runtime versions: the minimum and maximum on Ubuntu, and the maximum on
  macOS and Windows. Never add a workflow, job or secret for one package.
- Every cell has a dependency mode (`scripts/ci/matrix.py`). PRs, merge queues and pushes test the
  lockfile in every cell, plus the lowest allowed versions of direct dependencies (for languages
  whose default resolution doesn't already pick them) on Ubuntu at the minimum version. The
  nightly schedule, and a manual run with `latest-deps`, test every package with the newest
  allowed versions in every cell instead.
- After the nightly run, `scripts/ci/nightly_report.py` keeps one open issue labelled `nightly` per
  failing package, and closes it once the package passes again. It finds packages by job name, so
  each language's job in `ci.yml` has its language root as its ID and is listed in
  `nightly_report.GITHUB_JOB_LANGUAGES` (enforced by `scripts/tests/test_nightly_report.py`).
- On the Ubuntu cell at the maximum version (of the lockfile cells, and of the newest-versions
  cells), the Python workflow also runs `make build`, checks the wheel with
  `scripts/ci/python/check_wheel.py`, and smoke-tests the wheel and sdist in clean environments with
  `scripts/ci/python/smoke.py`. The wheel check also checks that both distributions have the
  expected version: `0.0.0`, or the release version.
- Each language has one release dry-run workflow (e.g. `release-python-dry-run.yml`), dispatched
  with a planned release tag. It runs `scripts/ci/check_release.py`, then calls the language's
  reusable workflow with the tag's version and the lockfile cells only. It never publishes
  anything.
- Each language's release workflow (e.g. `release-python.yml`) runs only when a GitHub release is
  published. It calls the dry-run workflow for the release's tag, checks that the tag is on `main`
  and that the release's pre-release flag matches `check_release.py`'s, then publishes the files
  the dry run built and tested (for Python, to TestPyPI and then PyPI, each followed by a smoke
  test). Publishing uses trusted publishing (no stored credentials), so the publish jobs must be
  in the release workflow itself, never in a reusable workflow, and they're the only jobs with
  `id-token: write` (enforced by `scripts/tests/test_workflows.py`). Each package needs its own
  trusted publishers on PyPI and TestPyPI before its first release, set up by a PyPI organization
  admin (see the next steps `scripts/new_package.py` prints). Retry a failed release by
  re-running only its failed jobs ("Re-run jobs" > "Re-run failed jobs" on the run's page in GitHub
  Actions, or `gh run rerun <run ID> --failed`); if the workflow itself needs a fix, release the
  next version. Runs for the same tag share a concurrency group, so they can't overlap.
- `scripts/ci/check_conventions.py` checks repository invariants on every run.
- `ci-status` is the only required check. Every other job in `ci.yml` must be listed in its
  `needs` (enforced by `scripts/tests/test_workflows.py`).
- Pin every third-party action to a full commit SHA with a `# vX.Y.Z` comment.
- Repository tooling lives in `scripts/`, a standalone uv project: CI entry points in
  `scripts/ci/` (those that only one language's workflow runs in `scripts/ci/<language>/`),
  shared code in the `scripts/lib/` package (stdlib only, since `detect_changes.py` runs before
  uv is installed). Entry scripts put `scripts/` on `sys.path` and import `lib.*`. Run its tests
  with `uv run --project scripts --locked pytest scripts/tests -q`.
- Each language's tooling rules (naming, conventions checks, scaffolding, release versions and
  registry lookups) live in one module, `scripts/lib/languages/<language>.py`, as a subclass of
  `Language` (`_base.py`) registered in `TOOLED_LANGUAGES`. Adding tooling for a language means
  adding that module, a `<language>/_template/` if needed, any scripts only its workflow runs in
  `scripts/ci/<language>/`, and their tests. Name language-specific test files
  `test_<language>_*.py` (e.g. `test_python_language.py`).

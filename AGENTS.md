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

Directories and files under a language root that start with `_` or `.` (e.g. `_shared/`,
`_template/`, `typescript/.oxlintrc.json`) hold shared configuration and templates, and never
contain packages; neither do `testdata/` folders.

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
- Each package's `README.md` states the range of base SDK versions it supports (for Go, by
  pointing to `go.mod`, whose requirement is the minimum). Package versions do not imply
  compatibility with the same-numbered SDK version.

## Python conventions

- **Names:** every package's root API (`root-api` in `integration.toml`) is a module under
  `temporalio.worker_integrations` that no other package in this repository uses. The published
  name defaults to `temporalio-` followed by the rest of the root API with `.` and `_` replaced by
  `-`, and the folder is the published name without `temporalio-`, with `-` replaced by `_`, so
  the folder and release tags read like the name users install. For example,
  `temporalio.worker_integrations.aws.lambda_worker` is published as
  `temporalio-aws-lambda-worker` and lives in `python/aws_lambda_worker/`. A package may choose a
  different published name, as long as it starts with `temporalio-`, is in the normalized form PyPI
  shows (lowercase letters and digits separated by single `-`), and isn't used by another package
  in this repository; its folder follows the name, e.g. `temporalio-modal-function-worker` lives in
  `python/modal_function_worker/`. Nothing checks names published from other repositories, so
  before a package's first release, check that its name isn't already on PyPI.
- **Root API naming:** below `temporalio.worker_integrations`, name a package after its provider and
  the compute product it runs on, e.g. `modal.function` or `gcp.cloud_run`. Don't add a `worker`
  suffix, since the namespace already says it, except where the product name is a Python keyword
  and can't be imported: `aws.lambda_worker`.
- **Published name choice:** prefer `temporalio-<provider>-<product>-worker` for worker packages
  (e.g. `temporalio-modal-function-worker`), overriding the default if needed. The suffix marks a
  compute integration, since the published name lacks the `worker_integrations` namespace.
  Non-worker packages, such as shared utilities, can omit it.
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
`python/_template/`, deriving the default published name from the root API and the folder from the
published name (see **Names** above), and the maturity classifier from `--maturity`, and copies the
root `LICENSE`. Pass `--python-published-name` to use a different published name, which also
changes the folder. It then prints the remaining
steps: confirm the published name, add dependencies, set the real `temporalio` floor, run `make sync`
(which creates `uv.lock`; commit it), `make lint` and `make test`. Check the result with
`uv run --project scripts --locked python scripts/ci/check_conventions.py`.

Template files end in `.tmpl` so that tools ignore the template itself; the script drops the
suffix. If you change the template, keep `python/_template/` and
`scripts/lib/languages/python.py` (naming, conventions checks and scaffolding) in sync.

## Go conventions

- **Names:** every module's path (`published-name` in `integration.toml`) is under
  `go.temporal.io/worker-integrations/`, and its folder is the rest of the path, e.g.
  `go.temporal.io/worker-integrations/aws/lambda` lives in `go/aws/lambda/` and is tagged
  `go/aws/lambda/v<version>`. Folders mirror module paths, as Go developers expect, so a module
  path can't be overridden the way a Python published name can. Each path element is lowercase
  letters and digits, starting with a letter; `testdata` and major version suffixes
  (`v2`, ...) aren't allowed. `root-api` is the module path too, since that's the import path of
  the module's root package.
- **Name choice:** name a module after its provider and the compute product it runs on, e.g.
  `aws/lambda` or `gcp/cloudrun`. The module path already says `worker-integrations`, so don't add a
  `worker` suffix.
- **Layout:** the module folder contains `go.mod`, `go.sum`, `integration.toml`, `Makefile`,
  `README.md`, `LICENSE`, and the root package's source. A module nested in another one's folder
  (e.g. `go/aws/lambda/otel/` in `go/aws/lambda/`) is a separate module, with its own files and
  releases.
- **go.mod:** its `go` directive is the minimum supported Go version, and must equal the first
  `[ci] runtime-versions` entry. No `replace` directives.
- **Versions:** release versions are `X.Y.Z`, or `X.Y.Z` followed by `-alpha.<N>`, `-beta.<N>` or
  `-rc.<N>` (e.g. `0.1.0-rc.1`). Major versions 2 and up aren't supported, since Go requires a
  `/vN` suffix on the module path for them.
- **Dependencies:** `go.mod` and `go.sum` are committed, and `make lint` fails if they aren't tidy.
  Go's minimal version selection builds with the lowest versions `go.mod` requires, so the `locked`
  dependency mode already tests them and there's no `lowest` mode; `make sync DEPS=latest`
  upgrades to the newest versions that support `go.mod`'s `go` directive instead (never commit the
  result).
- **Tooling:** `gofmt`, `go vet`, `go test` and `go build`, all run through `make lint`, `make test`
  and `make build`. `go/_shared/go.mk` holds the make targets; a module's `Makefile` is exactly one
  line that includes it, with one `../` per element of the module's folder path.
- **Vanity imports:** `go.temporal.io` serves a static page per module path, so each module needs
  its own page before its first release (see the next steps `scripts/new_package.py` prints).
- **Smoke test:** after a release, CI builds a new module that requires the published version
  and imports its root package. List other packages in the module that users import directly in
  `integration.toml`'s `[smoke] imports`. Since that only runs once the version is public, the
  conventions check makes sure each entry is a folder in the module with Go files, and not in a
  nested module.

### Adding a Go module

```bash
uv run --project scripts --locked python scripts/new_package.py \
    --go go.temporal.io/worker-integrations/aws/lambda \
    --description "Temporal worker integration for AWS Lambda" \
    --maturity public-preview
```

This creates `go/aws/lambda/` from `go/_template/` and copies the root `LICENSE`. The folder
follows the module path, so there's no `--go-published-name`. The script then prints the remaining
steps: write the code, add dependencies with `go get` and run `go mod tidy` (which creates
`go.sum`; commit it), keep the minimum `[ci] runtime-versions` entry equal to `go.mod`'s `go`
directive, `make lint` and `make test`, and request the module's vanity import page. The
`go.temporal.io/sdk` version that `go.mod` requires is the module's supported minimum. If you
change the template, keep `go/_template/` and `scripts/lib/languages/go.py` in sync.

## TypeScript conventions

- **Names:** every package's npm name (`published-name` in `integration.toml`) is
  `@temporalio/<name>`, where `<name>` is lowercase letters and digits in `-`-separated words,
  starting with a letter. Its folder is `<name>`, e.g. `@temporalio/aws-lambda-worker` lives in
  `typescript/aws-lambda-worker/`, so there's no published-name override. `root-api` is the npm
  name too, and `[smoke] imports` entries are its subpath exports (e.g.
  `@temporalio/aws-lambda-worker/otel`), each of which must be in `package.json`'s `exports`.
  Nothing checks names published from other repositories (including the SDK's own `@temporalio/*`
  packages), so before a package's first release, check that its name isn't already on npm.
- **Name choice:** prefer `@temporalio/<provider>-<product>-worker` for worker packages, matching
  the Python published name without `temporalio-`. Packages that moved here from an SDK repository
  keep their existing names (e.g. `@temporalio/lambda-worker`).
- **Layout:** the package folder contains `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`,
  `tsconfig.json`, `integration.toml`, `Makefile`, `README.md`, `LICENSE`, and its source under
  `src/`, with tests in `src/__tests__/` named `*.test.ts`. `tsc` compiles `src/` into `lib/`;
  the published tarball has `src/` and `lib/` without the tests.
- **Independent projects:** each package is its own pnpm project with its own lockfile;
  `pnpm-workspace.yaml` makes the package folder its workspace root and holds its pnpm settings.
  There's no repository-wide workspace. pnpm refuses to install until each dependency's install
  script is allowed or denied in `allowBuilds`: allow only scripts a dependency needs to work
  (e.g. to build or download a native binary), and say why in a comment, as the template does for
  the SDK's dependencies.
- **package.json:** `version` stays `0.0.0`; release tags supply the published version.
  `engines.node` is exactly `>=` the first `[ci] runtime-versions` entry, which is the exact
  minimum supported Node version (e.g. `22.12.0`); the last entry is a major version (e.g. `26`).
  `repository` points at this repository with the package's folder as `directory` (npm provenance
  requires the URL to match), `files` includes `LICENSE`, and `packageManager` is the pnpm version
  `typescript/_template/package.json.tmpl` pins.
- **Release versions** are `X.Y.Z`, or `X.Y.Z` followed by `-alpha.<N>`, `-beta.<N>` or `-rc.<N>`
  (e.g. `0.1.0-rc.1`).
- **Dependencies:** depend on `@temporalio/*` packages (in `dependencies`, `peerDependencies` and
  `optionalDependencies`) with a caret range on the minimum supported version, e.g.
  `"@temporalio/worker": "^1.24.0"`, and state the same range in the README's Compatibility
  section. `pnpm add` would save a caret range on the newest version instead, so write the range
  with `pnpm pkg set` (or by hand), then run `pnpm install`. The SDK's packages need `long` and
  `protobufjs` as peers, so packages declare them as peer and dev dependencies, as the template
  does. No `workspace:`, `file:`, `link:` or `portal:` dependencies. `pnpm-workspace.yaml` sets a
  two-week supply-chain cooldown (`minimumReleaseAge`) that exempts `@temporalio/*`, so a new SDK
  release can be adopted the day it ships. Keep lower bounds honest: CI also tests with the lowest
  versions they allow (see **CI**).
- **Dependency modes:** the `DEPS` make variable selects what `make sync` installs: `locked`
  (default) is the committed `pnpm-lock.yaml`, `lowest` re-locks with pnpm's `lowest-direct`
  resolution, and `latest` re-locks to the newest allowed versions. Both rewrite only the lockfile,
  never `package.json`; never commit the result, and restore it with `git checkout pnpm-lock.yaml`.
  `make sync` installs the lockfile exactly, so after changing dependencies run `pnpm install` to
  update it.
- **Tooling:** `tsc` (TypeScript 7) type-checks and compiles, `oxfmt` checks formatting, and
  `oxlint` lints with type-aware rules (e.g. `no-floating-promises`), following sdk-typescript;
  tests use AVA 6, configured in each `package.json` (with `workerThreads: false`, as in
  sdk-typescript's and ai-integrations' AVA configs). All of them run through `make lint`,
  `make test` and `make build` (`make help` lists every target). `typescript/_shared/` holds the
  make targets and the shared `tsconfig`; a package's `Makefile` is exactly one line that includes
  `typescript.mk`, and its `tsconfig.json` extends `tsconfig.base.json`. The `oxlint` and `oxfmt`
  configs are `typescript/.oxlintrc.json` and `typescript/.oxfmtrc.json` instead, since those tools
  (and their editor extensions) find a config only under its standard name, in the current folder
  or a parent; that way plain `pnpm exec oxlint` and `pnpm exec oxfmt` work in any package.
- **Smoke test:** CI installs the built tarball with `npm install` into new, empty projects and
  loads the package's entry points with both `require()` and `import()`. Optional peer
  dependencies (`peerDependenciesMeta`) are features users opt into, since npm never installs them
  on its own: the first install leaves them out and loads `root-api` and `integration.toml`'s
  `[smoke] imports`, which must work without them; if there are any, a second install adds them
  and loads every subpath in `exports` (without any, the first install loads every subpath). List
  subpath exports that must work without optional peers in `[smoke] imports`. `exports` subpaths
  are listed explicitly: patterns such as `./*` aren't allowed, since the smoke test couldn't load
  them.

### Adding a TypeScript package

```bash
uv run --project scripts --locked python scripts/new_package.py \
    --typescript @temporalio/aws-lambda-worker \
    --description "Temporal worker integration for AWS Lambda" \
    --maturity public-preview
```

This creates `typescript/aws-lambda-worker/` from `typescript/_template/` and copies the root
`LICENSE`. The folder follows the npm name, so there's no `--typescript-published-name`. The
script then prints the remaining steps: check that the name isn't already on npm, set the real
minimum SDK version (a caret range in `package.json`, and the same range in the README), add
other dependencies and run `pnpm install` (which creates `pnpm-lock.yaml`; commit it),
`make lint` and `make test`. If you change the template, keep `typescript/_template/` and
`scripts/lib/languages/typescript.py` in sync.

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
  expected version: `0.0.0`, or the release version. The TypeScript workflow likewise runs
  `make build`, checks the tarball with `scripts/ci/typescript/check_tarball.py` (its name and
  version, `LICENSE`, no tests, every entry point, and `lib/` matching `src/`), and smoke-tests it
  with `scripts/ci/typescript/smoke.py`. Go has no distributions, so the Go workflow
  ignores the matrix's `build` flag; it runs the tests with the race detector in every cell, and
  sets `GOTOOLCHAIN=local`, so each cell tests the Go version it installed.
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
  admin (see the next steps `scripts/new_package.py` prints). Go has nothing to upload: publishing
  the GitHub release creates the tag, which is the release, so `release-go.yml` instead
  smoke-tests the published module with `scripts/ci/go/smoke.py` (its vanity import page, the
  module proxy and checksum database, and a build that imports it). Since a Go version is public
  before its release workflow runs, `check_release.py` leaves the version itself out of the
  published versions it compares against (`Language.tag_publishes`). Retry a failed release by
  re-running only its failed jobs ("Re-run jobs" > "Re-run failed jobs" on the run's page in GitHub
  Actions, or `gh run rerun <run ID> --failed`); if the workflow itself needs a fix, release the
  next version. Runs for the same tag share a concurrency group, so they can't overlap.
- `scripts/ci/check_conventions.py` checks repository invariants on every run.
- `ci-status` is the only required check. Every other job in `ci.yml` must be listed in its
  `needs` (enforced by `scripts/tests/test_workflows.py`).
- Pin every third-party action to a full commit SHA with a `# vX.Y.Z` comment.
- Repository tooling lives in `scripts/`, a standalone uv project: CI entry points in
  `scripts/ci/` (those that only one language's workflow runs in `scripts/ci/<language>/`),
  shared code in the `scripts/lib/` package. CI runs `detect_changes.py` and `nightly_report.py`
  with the runner's system `python3`, before uv is installed, so they and what they import
  (`lib/common.py`) must use only the standard library; everything else runs through `uv run`
  and can use the project's dependencies. Entry scripts put `scripts/` on `sys.path` and import
  `lib.*`. Run its tests with `uv run --project scripts --locked pytest scripts/tests -q`.
- Each language's tooling rules (naming, conventions checks, scaffolding, release versions and
  registry lookups) live in one module, `scripts/lib/languages/<language>.py`, as a subclass of
  `Language` (`_base.py`) registered in `TOOLED_LANGUAGES`. Adding tooling for a language means
  adding that module, a `<language>/_template/` if needed, any scripts only its workflow runs in
  `scripts/ci/<language>/`, and their tests. Name language-specific test files
  `test_<language>_*.py` (e.g. `test_python_language.py`).

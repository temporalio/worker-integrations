"""Go modules: naming, conventions checks, scaffolding and release versions.

Checks (see AGENTS.md, "Go conventions"):
  * published-name is a module path under `go.temporal.io/worker-integrations`, the folder mirrors
    it, and root-api equals it (a module's root package has the module path as its import path)
  * required files exist
  * go.mod declares the published name as its module path, its `go` directive equals the first
    [ci] runtime-versions entry, and it has no `replace` directives
  * every [smoke] imports entry is a package in the module: a folder with Go files, outside any
    nested module
  * the Makefile is exactly the one-line stub that includes go/_shared/go.mk

Release versions are `X.Y.Z`, or a SemVer pre-release of it with phase alpha, beta or rc, e.g.
`X.Y.Z-rc.1`. Major versions 2 and up aren't supported: Go requires a `/vN` suffix on the module
path for them, which the naming rules don't allow yet.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from lib.common import Package
from lib.integration_toml import IntegrationMeta
from lib.languages._base import CheckContext, Language
from lib.release_version import ReleaseVersion, parse_semver_release

MODULE_PREFIX = "go.temporal.io/worker-integrations/"
# One element of the folder path below the prefix: lowercase letters and digits, starting with a
# letter. That keeps folders out of what discovery and the Go toolchain ignore (names starting with
# `_` or `.`), and Go package names (the last element) conventional.
PATH_ELEMENT_RE = re.compile(r"[a-z][a-z0-9]*")
# An element Go reads as a major version suffix (e.g. `/v2`). Major versions 2 and up aren't
# supported yet.
MAJOR_VERSION_ELEMENT_RE = re.compile(r"v[0-9]+")
REQUIRED_FILES = ("go.mod", "go.sum", "Makefile", "README.md")
# go.mod directives this module reads: `module <path>` and `go <version>`, each on its own line.
GO_MOD_DIRECTIVE_RE = re.compile(r"^(module|go)\s+(\S+)\s*$", re.MULTILINE)
# A `replace` directive, on its own line or opening a `replace (...)` block.
GO_MOD_REPLACE_RE = re.compile(r"^replace\b", re.MULTILINE)


def folder_for(module_path: str) -> str:
    """The language-relative folder for a valid module path: the path below MODULE_PREFIX."""
    return module_path.removeprefix(MODULE_PREFIX)


class Go(Language):
    name = "go"
    name_help = f"module path, e.g. {MODULE_PREFIX}aws/lambda"
    next_steps = """\
  1. Write the module's code, then add its dependencies, e.g.:
       cd go/{folder}
       go get go.temporal.io/sdk@<version>   # choose the minimum supported SDK version
       go mod tidy                           # commit the go.sum it creates
  2. If go.mod's go directive went up (a dependency that needs a newer Go version raises it),
     change the minimum (first) [ci] runtime-versions entry in integration.toml to match it.
  3. make lint && make test
  4. Before the module's first release, a member of the temporalio GitHub organization (e.g. a
     reviewer of your PR) needs to add a vanity import page on go.temporal.io for the module path,
     with this go-import tag:
       {published_name} git https://github.com/temporalio/worker-integrations go/{folder}
     Its fourth field, the module's folder, means the page has to be written by hand rather than
     generated."""

    # -- scaffolding -----------------------------------------------------------------------------
    def package_folder(self, requested: str, published_name: str) -> str:
        return folder_for(published_name)

    def default_published_name(self, requested: str) -> str:
        return requested

    def validate_published_name(self, published_name: str) -> None:
        example = f"(e.g. {MODULE_PREFIX}aws/lambda), got {published_name!r}"
        if not published_name.startswith(MODULE_PREFIX):
            raise ValueError(f"Go module path must be under {MODULE_PREFIX.rstrip('/')} {example}")
        for element in published_name.removeprefix(MODULE_PREFIX).split("/"):
            if not PATH_ELEMENT_RE.fullmatch(element):
                raise ValueError(
                    "Go module path must have path elements of lowercase letters and digits, each starting "
                    f"with a letter {example}"
                )
            if element == "testdata":
                raise ValueError(f"Go module path must not have a 'testdata' path element, which Go ignores {example}")
            if MAJOR_VERSION_ELEMENT_RE.fullmatch(element):
                raise ValueError(
                    f"Go module path must not have a {element!r} path element: Go reads it as a major version "
                    f"suffix, and major versions 2 and up aren't supported {example}"
                )

    def substitutions(self, requested: str, published_name: str, description: str, maturity: str) -> dict[str, str]:
        folder = folder_for(published_name)
        return {
            "__MODULE__": published_name,
            "__PACKAGE__": folder.rpartition("/")[2],
            "__LANGUAGE_ROOT__": "/".join([".."] * len(folder.split("/"))),
            "__DESCRIPTION__": description,
            "__MATURITY__": maturity,
        }

    # -- conventions -----------------------------------------------------------------------------
    def check_package(self, ctx: CheckContext, package: Package, meta: IntegrationMeta | None) -> None:
        d, rel = package.path, package.rel
        for required in REQUIRED_FILES:
            if not (d / required).is_file():
                ctx.fail(f"{rel}: missing {required}")

        if meta is None:
            return  # integration.toml problems are already reported

        module_path = meta.published_name
        try:
            self.validate_published_name(module_path)
        except ValueError as exc:
            ctx.fail(f"{rel}/integration.toml: {exc}")
            return
        if package.name != folder_for(module_path):
            ctx.fail(f"{rel}: the folder for published-name {module_path!r} must be go/{folder_for(module_path)}")
            return
        if meta.root_api != module_path:
            ctx.fail(f"{rel}/integration.toml: root-api must equal published-name {module_path!r} (got {meta.root_api!r})")

        for import_path in meta.smoke_imports:
            _check_smoke_import(ctx, package, module_path, import_path)

        makefile = d / "Makefile"
        expected_makefile = f"include {'../' * len(package.name.split('/'))}_shared/go.mk\n"
        if makefile.is_file() and makefile.read_text() != expected_makefile:
            ctx.fail(f"{rel}/Makefile: must be exactly:\n{expected_makefile.rstrip()}")

        _check_go_mod(ctx, package, meta)

    # -- releases --------------------------------------------------------------------------------
    def release_version(self, text: str) -> ReleaseVersion:
        version = parse_semver_release(text)
        if version is None:
            raise ValueError(
                f"{text!r} isn't a supported Go version: use X.Y.Z, or X.Y.Z followed by a pre-release "
                "-alpha.<N>, -beta.<N> or -rc.<N> (e.g. 1.0.0-rc.1)"
            )
        major = version.release[0]
        if major >= 2:
            raise ValueError(
                f"{text!r} isn't a supported Go version: major versions 2 and up need a /v{major} "
                "module path, which isn't supported"
            )
        return version

    def published_versions(self, published_name: str) -> list[str]:
        # The module proxy lists every version it has fetched, retracted ones included. Module paths
        # here are lowercase, so they need none of the proxy's case escaping. The module proxy
        # protocol treats both 404 and 410 as "not found"; any other error propagates, so that an
        # outage fails the release instead of looking like an unpublished module.
        try:
            with urllib.request.urlopen(f"https://proxy.golang.org/{published_name}/@v/list", timeout=30) as response:
                text = response.read().decode()
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                return []
            raise
        return [line.removeprefix("v") for line in text.split()]

    def may_already_be_published(self, version: ReleaseVersion, published: list[ReleaseVersion]) -> bool:
        # A Go version is published by its tag, and publishing the GitHub release creates the tag.
        # The module proxy serves any tagged version as soon as someone requests it, so the proxy
        # may already list the version by the time the release workflow runs (especially on a
        # re-run). Allowing that is still safe, because each version is released at most once. A tag
        # has at most one GitHub release, and the tag ruleset and immutable releases keep the tag
        # from changing.
        return True


def _check_smoke_import(ctx: CheckContext, package: Package, module_path: str, import_path: str) -> None:
    """Check that a [smoke] imports entry is a package in the module, other than its root package.

    The smoke test only runs after a release is public (scripts/ci/go/smoke.py), so this checks
    the entry against the module's folders instead, before anything is released.
    """
    rel = package.rel
    elements = import_path.removeprefix(f"{module_path}/").split("/")
    if not import_path.startswith(f"{module_path}/") or any(e in ("", ".", "..") for e in elements):
        ctx.fail(f"{rel}/integration.toml: [smoke] imports entry {import_path!r} must be a package in {module_path!r}")
        return
    # A folder with its own go.mod starts another module, which the smoke test would fetch at
    # whatever version it resolves to, instead of this release
    for depth in range(1, len(elements) + 1):
        folder = "/".join(elements[:depth])
        if (package.path / folder / "go.mod").is_file():
            ctx.fail(
                f"{rel}/integration.toml: [smoke] imports entry {import_path!r} is in the nested module "
                f"{rel}/{folder}, not in {module_path!r}"
            )
            return
    folder = "/".join(elements)
    if not any(f.is_file() and not f.name.endswith("_test.go") for f in (package.path / folder).glob("*.go")):
        ctx.fail(
            f"{rel}/integration.toml: [smoke] imports entry {import_path!r} has no package: "
            f"{rel}/{folder} has no Go files other than tests"
        )


def _check_go_mod(ctx: CheckContext, package: Package, meta: IntegrationMeta) -> None:
    """Check the package's go.mod against its integration.toml and the repository's rules."""
    rel = f"{package.rel}/go.mod"
    # Drop `//` comments, so that commented-out directives don't count. Module paths and versions
    # can't contain `//`.
    text = re.sub(r"//.*", "", (package.path / "go.mod").read_text(encoding="utf-8"))
    directives = dict(m.groups() for m in GO_MOD_DIRECTIVE_RE.finditer(text))

    if directives.get("module") != meta.published_name:
        ctx.fail(f"{rel}: module must be {meta.published_name!r} (got {directives.get('module')!r})")

    min_version = meta.runtime_versions[0]
    if "go" not in directives:
        ctx.fail(f"{rel}: must have a go directive")
    elif directives["go"] != min_version:
        ctx.fail(
            f"{package.rel}: the first [ci] runtime-versions entry {min_version!r} must equal "
            f"go.mod's go directive {directives['go']!r}"
        )

    # Packages depend on the SDK and on each other through published versions only; a replace
    # directive would also be ignored for anyone depending on this module.
    if GO_MOD_REPLACE_RE.search(text):
        ctx.fail(f"{rel}: replace directives aren't allowed; depend on published versions")

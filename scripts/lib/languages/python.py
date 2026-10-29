"""Python packages: naming, conventions checks, scaffolding and release versions.

Checks (see AGENTS.md, "Python conventions"):
  * python/_shared does not contain Python source or stubs (only configuration, make logic, etc.)
  * required files (including the root-api package's __init__.py and py.typed) exist; root-api is
    under `temporalio.worker_integrations`, and the folder and published name derive from it
  * no __init__.py in the shared namespace levels above the root-api package
  * every [smoke] imports entry in integration.toml is a submodule of root-api
  * the Makefile is exactly the two-line stub that includes python/_shared/python.mk
  * pyproject.toml agrees with integration.toml (name, maturity classifier, requires-python floor,
    module-name) and with repository policy (version placeholder, license, uv settings)
  * standard test support files are byte-identical to python/_template
  * the published README has no relative links (PyPI renders it)

Release versions are a small subset of PEP 440 (Python's version standard), in its canonical
spelling: `X.Y.Z`, or a pre-release such as `X.Y.Zrc1` (phases a, b and rc). Post, dev and local
versions and epochs aren't supported: post releases are rare in practice, and a patch release does
the same job. Non-canonical spellings (e.g. `1.0` or `1.0.0-rc1`) are rejected because PyPI would
publish them normalized, so the tag wouldn't match the published version.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from lib.common import Package, load_toml
from lib.integration_toml import IntegrationMeta
from lib.languages._base import CheckContext, Language
from lib.release_version import ReleaseVersion

PROJECT_NAMESPACE = "temporalio.worker_integrations"
PYTHON_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
# Like PYTHON_MODULE_RE, but segments may also be private (start with `_`).
PYTHON_SUBMODULE_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")
PYPI_MATURITY_CLASSIFIER = {
    "generally-available": "Development Status :: 5 - Production/Stable",
    "public-preview": "Development Status :: 4 - Beta",
    "pre-release": "Development Status :: 3 - Alpha",
}
DEVELOPMENT_VERSION = "0.0.0"
REQUIRED_FILES = ("pyproject.toml", "uv.lock", "Makefile", "README.md")
# Package file -> canonical template file; the package's copy must stay byte-identical.
STANDARD_TEST_SUPPORT = {
    "tests/helpers/package_meta.py": "tests/helpers/package_meta.py.tmpl",
    "tests/helpers/provenance.py": "tests/helpers/provenance.py.tmpl",
    "tests/test_installed_matches_source.py": "tests/test_installed_matches_source.py.tmpl",
}
MARKDOWN_RELATIVE_LINK = re.compile(r"\]\((\.\.?/)")
# One number in a version (e.g. the 2 in 1.2.3 or in 1.0.0rc2), without leading zeros
VERSION_NUMBER_PATTERN = r"(?:0|[1-9][0-9]*)"
RELEASE_VERSION_RE = re.compile(
    rf"(?P<release>{VERSION_NUMBER_PATTERN}\.{VERSION_NUMBER_PATTERN}\.{VERSION_NUMBER_PATTERN})"
    rf"(?:(?P<phase>a|b|rc)(?P<number>{VERSION_NUMBER_PATTERN}))?"
)
PRE_RELEASE_PHASE_NAMES = {"a": "alpha", "b": "beta", "rc": "rc"}


def names(root_api: str) -> tuple[str, str] | None:
    """(folder, published name) for a root API, or None if it isn't a module under PROJECT_NAMESPACE.

    The folder is the root API below the namespace with `.` -> `_`; the published name is the whole
    root API with `.` and `_` -> `-`.
    """
    prefix = f"{PROJECT_NAMESPACE}."
    if not root_api.startswith(prefix) or not PYTHON_MODULE_RE.match(root_api.removeprefix(prefix)):
        return None
    folder = root_api.removeprefix(prefix).replace(".", "_")
    return folder, root_api.replace(".", "-").replace("_", "-")


def _requested_names(root_api: str) -> tuple[str, str]:
    derived = names(root_api)
    if derived is None:
        raise ValueError(
            f"Python root API must be a snake_case module under {PROJECT_NAMESPACE} "
            f"(e.g. {PROJECT_NAMESPACE}.aws.lambda_worker), got {root_api!r}"
        )
    return derived


class Python(Language):
    name = "python"
    name_help = f"full root API, e.g. {PROJECT_NAMESPACE}.aws.lambda_worker"
    next_steps = """\
  1. Add the package's dependencies to pyproject.toml (declare exactly what it imports), and set
     the real temporalio floor there and in README.md's Compatibility section.
  2. cd python/{folder} && make sync   # creates uv.lock; commit it
  3. make lint && make test"""

    # -- scaffolding -----------------------------------------------------------------------------
    def package_folder(self, requested: str) -> str:
        return _requested_names(requested)[0]

    def substitutions(self, requested: str, description: str, maturity: str) -> dict[str, str]:
        folder, published_name = _requested_names(requested)
        return {
            "__NAME__": folder,
            "__PUBLISHED_NAME__": published_name,
            "__MODULE__": requested,
            "__MODULE_PATH__": requested.replace(".", "/"),
            "__DESCRIPTION__": description,
            "__MATURITY__": maturity,
            "__MATURITY_CLASSIFIER__": PYPI_MATURITY_CLASSIFIER[maturity],
        }

    # -- conventions -----------------------------------------------------------------------------
    def check_root(self, ctx: CheckContext) -> None:
        shared = ctx.root / "python" / "_shared"
        if not shared.is_dir():
            return
        for path in sorted(shared.rglob("*")):
            if path.suffix in {".py", ".pyi", ".pyw", ".pyx"}:
                ctx.fail(f"{path.relative_to(ctx.root)}: Python code must be duplicated into each package, not shared")

    def check_package(self, ctx: CheckContext, package: Package, meta: IntegrationMeta | None) -> None:
        d, rel = package.path, package.rel
        for required in REQUIRED_FILES:
            if not (d / required).is_file():
                ctx.fail(f"{rel}: missing {required}")

        _check_standard_test_support(ctx, package)

        if meta is None:
            return  # integration.toml problems are already reported

        # The root API, folder path, and published name should all be consistent
        root_api = meta.root_api
        derived = names(root_api)
        if derived is None:
            ctx.fail(f"{rel}/integration.toml: root-api must be a snake_case module under {PROJECT_NAMESPACE} (got {root_api!r})")
            return
        folder, published_name = derived
        if package.name != folder:
            ctx.fail(f"{rel}: the folder for root-api {root_api!r} must be python/{folder}")
            return
        if meta.published_name != published_name:
            ctx.fail(f"{rel}/integration.toml: published-name must be {published_name!r} (got {meta.published_name!r})")

        # Smoke test imports must be submodules of the root API
        for module in meta.smoke_imports:
            submodule = module.removeprefix(f"{root_api}.")
            if submodule == module or not PYTHON_SUBMODULE_RE.match(submodule):
                ctx.fail(f"{rel}/integration.toml: [smoke] imports entry {module!r} must be a submodule of {root_api!r}")

        # The root API's directory must have __init__.py (and py.typed), but its parents must not
        # since they're shared by multiple different packages (so no individual package here can define it)
        pkg_dir = d / "src" / Path(*root_api.split("."))
        for required in ("__init__.py", "py.typed"):
            if not (pkg_dir / required).is_file():
                ctx.fail(f"{rel}: missing {pkg_dir.relative_to(d).as_posix()}/{required}")
        parents = root_api.split(".")[:-1]
        for depth in range(1, len(parents) + 1):
            init = d / "src" / Path(*parents[:depth]) / "__init__.py"
            if init.exists():
                ctx.fail(
                    f"{rel}: {init.relative_to(d).as_posix()} must not exist "
                    "(the SDK owns temporalio; the levels below it are shared namespace packages)"
                )

        makefile = d / "Makefile"
        expected_makefile = f"DIST := {published_name}\ninclude ../_shared/python.mk\n"
        if makefile.is_file() and makefile.read_text() != expected_makefile:
            ctx.fail(f"{rel}/Makefile: must be exactly:\n{expected_makefile.rstrip()}")

        if not (d / "pyproject.toml").is_file():
            return
        try:
            pyproject = load_toml(d / "pyproject.toml")
        except Exception as exc:  # noqa: BLE001
            ctx.fail(f"{rel}/pyproject.toml: cannot parse: {exc}")
            return
        _check_pyproject(ctx, package, meta, pyproject)

        _check_readme(ctx, package, pyproject)

    # -- releases --------------------------------------------------------------------------------
    def release_version(self, text: str) -> ReleaseVersion:
        m = RELEASE_VERSION_RE.fullmatch(text)
        if not m:
            raise ValueError(
                f"{text!r} isn't a supported Python version: use X.Y.Z, or X.Y.Z followed by a pre-release "
                "a<N>, b<N> or rc<N> (e.g. 1.0.0rc1). Post, dev and local versions aren't supported; "
                "release the next patch version instead"
            )
        major, minor, patch = (int(n) for n in m["release"].split("."))
        pre = (PRE_RELEASE_PHASE_NAMES[m["phase"]], int(m["number"])) if m["phase"] else None
        return ReleaseVersion((major, minor, patch), pre, text)

    def published_versions(self, published_name: str) -> list[str]:
        # PyPI's JSON API lists yanked releases too. Any error other than a 404 propagates, so that
        # a registry outage fails the release instead of looking like an unpublished package.
        try:
            with urllib.request.urlopen(f"https://pypi.org/pypi/{published_name}/json", timeout=30) as response:
                return list(json.load(response)["releases"])
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []
            raise


def _check_pyproject(ctx: CheckContext, package: Package, meta: IntegrationMeta, pyproject: dict[str, Any]) -> None:
    """Check the package's pyproject.toml for correctness and consistency with its integration.toml."""
    rel = f"{package.rel}/pyproject.toml"
    project = pyproject.get("project", {})

    if project.get("name") != meta.published_name:
        ctx.fail(f"{rel}: [project] name must be {meta.published_name!r} (got {project.get('name')!r})")

    if project.get("version") != DEVELOPMENT_VERSION:
        ctx.fail(
            f"{rel}: [project] version must be the development placeholder {DEVELOPMENT_VERSION!r}; "
            f"release tags supply the published version (got {project.get('version')!r})"
        )

    if project.get("license") != "MIT":
        ctx.fail(f'{rel}: [project] license must be the SPDX expression "MIT"')
    if project.get("license-files") != ["LICENSE"]:
        ctx.fail(f'{rel}: [project] license-files must be ["LICENSE"]')

    classifiers = project.get("classifiers", [])
    if any(c.startswith("License ::") for c in classifiers):
        ctx.fail(f"{rel}: drop License :: classifiers; the license expression replaces them")
    expected_classifier = PYPI_MATURITY_CLASSIFIER[meta.maturity]
    status = [c for c in classifiers if c.startswith("Development Status ::")]
    if status != [expected_classifier]:
        ctx.fail(f"{rel}: classifiers must contain exactly {expected_classifier!r} for maturity {meta.maturity!r} (got {status})")

    min_version = meta.runtime_versions[0]
    m = re.search(r">=\s*(\d+\.\d+)", project.get("requires-python", ""))
    if not m:
        ctx.fail(f"{rel}: requires-python must contain a >=X.Y floor")
    elif min_version != m.group(1):
        ctx.fail(
            f"{package.rel}: the first [ci] runtime-versions entry {min_version!r} must equal "
            f"the requires-python floor {m.group(1)!r}"
        )

    tool_uv = pyproject.get("tool", {}).get("uv", {})
    module_name = tool_uv.get("build-backend", {}).get("module-name")
    if module_name != meta.root_api:
        ctx.fail(f"{rel}: [tool.uv.build-backend] module-name must be {meta.root_api!r} (got {module_name!r})")

    # Unlike the base SDK, which publishes a monolithic temporalio wheel, worker integrations are published
    # independently of each other, so path/workspace sources introduce versioning risks; disallow them
    for dep, source in tool_uv.get("sources", {}).items():
        for entry in source if isinstance(source, list) else [source]:
            if isinstance(entry, dict) and ("path" in entry or "workspace" in entry):
                ctx.fail(f"{rel}: [tool.uv.sources] {dep} uses a path/workspace source; depend on published versions")

    # For consistency, keep Python package's uv version in sync with the repo tooling's own uv version
    expected_uv = _scripts_uv_required_version(ctx.root)
    if expected_uv and tool_uv.get("required-version") != expected_uv:
        ctx.fail(f"{rel}: [tool.uv] required-version must equal scripts/pyproject.toml's {expected_uv!r}")

    # The temporalio SDK package should be exempted from exclude-newer, i.e. new versions of temporalio can be used immediately
    if "exclude-newer" in tool_uv and tool_uv.get("exclude-newer-package", {}).get("temporalio") is not False:
        ctx.fail(f"{rel}: exclude-newer is set but temporalio is not exempted (`exclude-newer-package = {{ temporalio = false }}`)")


def _scripts_uv_required_version(root: Path) -> str | None:
    path = root / "scripts" / "pyproject.toml"
    if not path.is_file():
        return None
    return load_toml(path).get("tool", {}).get("uv", {}).get("required-version")


def _check_readme(ctx: CheckContext, package: Package, pyproject: dict[str, Any]) -> None:
    """Check that the package's configured README exists and doesn't contain relative markdown links."""
    configured = pyproject.get("project", {}).get("readme", "README.md")
    filename = configured.get("file") if isinstance(configured, dict) else configured
    if not isinstance(filename, str) or Path(filename).is_absolute() or ".." in Path(filename).parts:
        ctx.fail(f"{package.rel}: [project] readme must name a file inside the package folder")
        return
    readme = package.path / filename
    if not readme.is_file():
        return  # reported as a missing required file

    for lineno, line in enumerate(readme.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if MARKDOWN_RELATIVE_LINK.search(line):
            ctx.fail(f"{package.rel}/{filename}:{lineno}: relative link; use an absolute https:// URL (PyPI renders this file)")


def _check_standard_test_support(ctx: CheckContext, package: Package) -> None:
    """Check that the standard test support files match the templates exactly."""
    template_root = ctx.root / package.language / "_template"
    for package_rel, template_rel in STANDARD_TEST_SUPPORT.items():
        package_file = package.path / package_rel
        template_file = template_root / template_rel
        if not package_file.is_file():
            ctx.fail(f"{package.rel}: missing standard test support file {package_rel}")
        elif not template_file.is_file():
            ctx.fail(f"{package.language}/_template/{template_rel}: missing canonical template")
        elif package_file.read_bytes() != template_file.read_bytes():
            ctx.fail(f"{package.rel}/{package_rel}: differs from {package.language}/_template/{template_rel}")


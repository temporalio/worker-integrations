#!/usr/bin/env python3
"""Smoke-test one Python package's wheel and sdist: as built by `make build`, or as published.

Installs each distribution the way a user would: into a fresh virtual environment, with only the
package's declared dependencies, resolved to the newest compatible versions (for the sdist, uv
first builds a wheel from it). It then checks that the package's modules import successfully, and
that the installation passes the package's own provenance guard (tests/helpers/provenance.py).

Each distribution gets up to two installs, each in its own environment:
  * a base install, without extras, which imports root-api and integration.toml's [smoke] imports
  * if the package declares extras, a second install with all of them, which imports every module
    under root-api (for a package without extras, the base install does this instead)
The provenance guard runs after every install. The checks run in a separate script,
_smoke_in_env.py, under the environment's own Python in isolated mode (`python -I`) and from a
temporary directory, so neither the repository nor PYTHON* environment variables can satisfy an
import.

The package's own tests run in its development environment, which has the dev dependencies and
the versions pinned in its uv.lock. The smoke test runs in an environment where the
package is installed as a user would install it, which catches:
  * a module importing something the package doesn't declare (or declares only in an extra)
  * a module that fails at import time against the newest dependencies
  * a newer dependency shipping files under the package's path, which the provenance guard
    detects

Runs after `make build` on the CI matrix cell that builds distributions (--dist), and again after
release-python.yml publishes them (--index, with --version):
  * --index pypi installs `<published name>==<version>` the way a user would, through PyPI's index:
    once allowing only the wheel, and once allowing only the sdist.
  * --index testpypi installs the files TestPyPI serves for the version, by their URLs, with every
    dependency from PyPI.
Both first wait until the index lists the version's wheel and sdist, since an upload takes a while
to show up.

Exits non-zero with a list of problems.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.common import load_toml  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402

# Runs inside each smoke environment.
IN_ENV = Path(__file__).with_name("_smoke_in_env.py")
INDEX_URLS = {"pypi": "https://pypi.org", "testpypi": "https://test.pypi.org"}
# How long to wait for an upload to show up on the index: up to 10 checks, 30 seconds apart
INDEX_CHECKS = 10
INDEX_CHECK_DELAY = 30


def smoke(package_dir: Path, dist: Path) -> list[str]:
    """Smoke-test the wheel and sdist in `dist`."""
    artifacts = sorted(dist.glob("*.whl")) + sorted(dist.glob("*.tar.gz"))
    if not artifacts:
        return [f"no wheel or sdist in {dist}"]
    return _smoke(package_dir, [(a.name, f" @ {a.resolve().as_uri()}", []) for a in artifacts])


def smoke_index(package_dir: Path, index: str, version: str) -> list[str]:
    """Smoke-test the wheel and sdist of `version` published on `index` ("pypi" or "testpypi")."""
    name = IntegrationMeta.from_file(package_dir / "integration.toml").published_name
    # For PyPI, only to wait until the upload shows up: the installs then go through the index
    files = index_files(index, name, version)
    if files is None:
        return [f"{index} doesn't list both a wheel and an sdist for {name} {version}"]

    if index == "testpypi":
        # Install the uploaded files by URL, rather than through TestPyPI as an index:
        #   * Using TestPyPI as an index would introduce some supply-chain risk. Anyone can upload
        #     packages to it under an unclaimed name, so if we wanted to do this safely, we'd have
        #     to configure uv so that it would only use TestPyPI for this package. This can be done,
        #     but it's fiddly and difficult to verify. It wouldn't be obvious if we got it wrong,
        #     and it would allow a dependency to be installed from whatever package someone uploaded
        #     under its name. That would allow potentially malicious code to run inside the release
        #     workflow, where it could tamper with the files published to PyPI next.
        #   * Installing the files directly by URL means TestPyPI is never used as an index for
        #     dependencies, so every dependency is resolved through the real PyPI.
        # The downside is that this doesn't test how TestPyPI's index resolves the version. That's
        # an acceptable tradeoff: what matters most here is that the files we uploaded are there and
        # work, while index resolution is TestPyPI's own functionality, not something our upload
        # can get wrong. (The PyPI check below also installs through PyPI's index, and so exercises
        # the full installation path like a user would.)
        return _smoke(package_dir, [(f"{filename} from TestPyPI", f" @ {url}", []) for filename, url in files])

    # Make uv revalidate the package's index page, in case it cached one from before the upload
    refresh = ["--refresh-package", name]
    return _smoke(package_dir, [
        ("wheel from PyPI", f"=={version}", ["--only-binary", name, *refresh]),
        ("sdist from PyPI", f"=={version}", ["--no-binary", name, *refresh]),
    ])


def index_files(index: str, name: str, version: str) -> list[tuple[str, str]] | None:
    """(file name, URL) of each of the version's files on the index, once it lists a wheel and an sdist.

    None if it still doesn't after INDEX_CHECKS checks.
    """
    url = f"{INDEX_URLS[index]}/pypi/{name}/{version}/json"
    for check in range(1, INDEX_CHECKS + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                files = sorted((f["filename"], f["url"]) for f in json.load(response)["urls"])
        except urllib.error.HTTPError as exc:
            if exc.code != 404:  # 404: the version isn't listed yet
                raise
            files = []
        names = [filename for filename, _ in files]
        if any(n.endswith(".whl") for n in names) and any(n.endswith(".tar.gz") for n in names):
            return files
        if check < INDEX_CHECKS:
            print(f"{index} doesn't list both files for {name} {version} yet; checking again in {INDEX_CHECK_DELAY}s", flush=True)
            time.sleep(INDEX_CHECK_DELAY)
    return None


def _smoke(package_dir: Path, installs: list[tuple[str, str, list[str]]]) -> list[str]:
    """Run the checks for each (label, version spec, uv arguments) install.

    The version spec is what follows the package's name and extras in the requirement, e.g.
    " @ <url>" or "==1.0.0".
    """
    meta = IntegrationMeta.from_file(package_dir / "integration.toml")
    extras = sorted(load_toml(package_dir / "pyproject.toml").get("project", {}).get("optional-dependencies", {}))
    provenance = package_dir / "tests" / "helpers" / "provenance.py"

    problems: list[str] = []
    for install, spec, uv_args in installs:
        # (label, requirement, whether to import every module)
        runs = [("base", f"{meta.published_name}{spec}", not extras)]
        if extras:
            # If the package defines extras, add a second run that installs them all and
            # tries to import every module, leaving the base run to import just configured modules
            runs.append((f"[{','.join(extras)}]", f"{meta.published_name}[{','.join(extras)}]{spec}", True))
        for label, requirement, import_all in runs:
            print(f"=== {install} {label} ===", flush=True)
            problems += [f"{install} {label}: {p}" for p in _check(requirement, uv_args, import_all, meta, provenance)]
    return problems


def _check(requirement: str, uv_args: list[str], import_all: bool, meta: IntegrationMeta, provenance: Path) -> list[str]:
    """Install `requirement` into a fresh environment and run IN_ENV there."""
    with tempfile.TemporaryDirectory(prefix="smoke-") as tmp:
        venv = Path(tmp) / "venv"
        # The venv python; any commands using it run within the venv
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        try:
            for cmd in (
                # Bootstrap the venv with the current Python executable
                ["uv", "venv", "--quiet", "--python", sys.executable, str(venv)],
                # Install within the venv
                ["uv", "pip", "install", "--quiet", "--python", str(python), *uv_args, requirement],
            ):
                # From the temporary directory, so uv doesn't pick up the package's own settings.
                subprocess.run(cmd, cwd=tmp, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            return [f"install failed: {exc.stderr.strip()}"]

        # Log the resolved versions: they're the newest allowed, not the ones in uv.lock, so a
        # failure caused by a new dependency release shows which version was installed.
        installed = subprocess.run(["uv", "pip", "list", "--python", str(python)], cwd=tmp, capture_output=True, text=True)
        print(installed.stdout, end="", flush=True)

        cmd = [
            str(python), "-I", str(IN_ENV),
            "--provenance", str(provenance), "--published-name", meta.published_name, "--root-api", meta.root_api,
            *(["--all"] if import_all else []), *meta.smoke_imports,
        ]
        result = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
    if result.returncode == 0:
        return []
    return result.stdout.splitlines() or [f"smoke check crashed: {result.stderr.strip()}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--dist", type=Path, default=None, help="defaults to <package-dir>/dist")
    source.add_argument("--index", choices=sorted(INDEX_URLS), help="test a published version instead (needs --version)")
    parser.add_argument("--version", help="the published version to test, with --index")
    args = parser.parse_args(argv)
    if (args.index is None) != (args.version is None):
        parser.error("--index and --version go together")

    if args.index:
        where = f"version {args.version} on {args.index}"
        problems = smoke_index(args.package_dir, args.index, args.version)
    else:
        dist = args.dist or args.package_dir / "dist"
        where = str(dist)
        problems = smoke(args.package_dir, dist)
    if problems:
        print(f"FAIL: {len(problems)} problem(s) smoke-testing the distributions in {where}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: the distributions in {where} pass the smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())

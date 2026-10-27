#!/usr/bin/env python3
"""Smoke-test the wheel and sdist that `make build` wrote for one Python package.

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

Runs after `make build` on the CI matrix cell that builds distributions. Exits non-zero with a
list of problems.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.common import load_toml  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402

# Runs inside each smoke environment.
IN_ENV = Path(__file__).with_name("_smoke_in_env.py")


def smoke(package_dir: Path, dist: Path) -> list[str]:
    meta = IntegrationMeta.from_file(package_dir / "integration.toml")
    extras = sorted(load_toml(package_dir / "pyproject.toml").get("project", {}).get("optional-dependencies", {}))
    provenance = package_dir / "tests" / "helpers" / "provenance.py"

    artifacts = sorted(dist.glob("*.whl")) + sorted(dist.glob("*.tar.gz"))
    if not artifacts:
        return [f"no wheel or sdist in {dist}"]

    problems: list[str] = []
    for artifact in artifacts:
        url = artifact.resolve().as_uri()
        # (label, requirement, whether to import every module)
        runs = [("base", f"{meta.published_name} @ {url}", not extras)]
        if extras:
            # If the package defines extras, add a second run that installs them all and
            # tries to import every module, leaving the base run to import just configured modules
            runs.append((f"[{','.join(extras)}]", f"{meta.published_name}[{','.join(extras)}] @ {url}", True))
        for label, requirement, import_all in runs:
            print(f"=== {artifact.name} {label} ===", flush=True)
            problems += [f"{artifact.name} {label}: {p}" for p in _check(requirement, import_all, meta, provenance)]
    return problems


def _check(requirement: str, import_all: bool, meta: IntegrationMeta, provenance: Path) -> list[str]:
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
                ["uv", "pip", "install", "--quiet", "--python", str(python), requirement],
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
    parser.add_argument("--dist", type=Path, default=None, help="defaults to <package-dir>/dist")
    args = parser.parse_args(argv)
    dist = args.dist or args.package_dir / "dist"
    problems = smoke(args.package_dir, dist)
    if problems:
        print(f"FAIL: {len(problems)} problem(s) smoke-testing the distributions in {dist}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: the distributions in {dist} pass the smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())

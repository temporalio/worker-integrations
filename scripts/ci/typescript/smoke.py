#!/usr/bin/env python3
"""Smoke-test one TypeScript package's npm tarball: as built by `make build`, or as published.

Installs the package the way most users would: with `npm install`, into a new, empty project, with
only the package's declared dependencies, resolved to the newest compatible versions. It then
checks that the package's entry points load, with both require() and import() (see
_smoke_in_project.mjs).

The package's own tests run in its development project, which has the dev dependencies and the
versions pinned in its pnpm-lock.yaml. The smoke test runs where the package is installed as a
user would install it, which catches:
  * a module importing something the package doesn't declare (or declares only as a dev or
    optional peer dependency)
  * an exports map that doesn't resolve, for require() or for import()
  * a module that fails at load time against the newest dependencies

A package's optional peer dependencies (marked `optional` in peerDependenciesMeta) are features
users opt into by installing them: npm installs a package's required peer dependencies on its own,
but never its optional ones. So each smoke test has up to two installs, each in its own project:
  * a base install of just the tarball, which loads root-api and integration.toml's
    [smoke] imports
  * if the package has optional peer dependencies, a second install that adds each of them at
    its declared range, which loads every subpath in exports (for a package without optional peer
    dependencies, the base install does this instead)
The conventions check rejects exports patterns such as "./*", so every subpath can be listed.

Runs after `make build` on the CI matrix cell that builds the tarball (--dist), and again after
release-typescript.yml publishes it (--registry, with --version), which installs
`<published name>@<version>` from npm, once npm lists it.

Exits non-zero with a list of problems.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ci.typescript._registry import wait_for_version  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402

# Runs inside each smoke project.
IN_PROJECT = Path(__file__).with_name("_smoke_in_project.mjs")
# Environment variables that would let modules from outside the smoke project satisfy a require()
# or change how Node loads them
NODE_ENV_VARS = ("NODE_PATH", "NODE_OPTIONS")


def smoke(package_dir: Path, dist: Path) -> list[str]:
    """Smoke-test the tarball in `dist`."""
    tarballs = sorted(dist.glob("*.tgz"))
    if len(tarballs) != 1:
        return [f"expected exactly one tarball in {dist}, found {[t.name for t in tarballs]}"]
    return _smoke(package_dir, tarballs[0].name, str(tarballs[0].resolve()))


def smoke_registry(package_dir: Path, version: str) -> list[str]:
    """Smoke-test `version` of the package as published on npm."""
    name = IntegrationMeta.from_file(package_dir / "integration.toml").published_name
    if wait_for_version(name, version) is None:
        return [f"npm doesn't list {name}@{version}"]
    return _smoke(package_dir, f"{name}@{version} from npm", f"{name}@{version}")


def _smoke(package_dir: Path, label: str, spec: str) -> list[str]:
    """Run the checks for the package installed from `spec`: anything `npm install` takes."""
    meta = IntegrationMeta.from_file(package_dir / "integration.toml")
    manifest = json.loads((package_dir / "package.json").read_text())
    peers = manifest.get("peerDependencies", {})
    optional_peers = sorted(
        name for name, peer_meta in manifest.get("peerDependenciesMeta", {}).items()
        if peer_meta.get("optional") and name in peers
    )
    # Every subpath export, as a module name. ./package.json is commonly exported for tools that read
    # the package's metadata; it isn't code to load. A null target hides a subpath, so there's
    # nothing to load there either.
    subpaths = [
        meta.published_name + subpath.removeprefix(".")
        for subpath, target in manifest.get("exports", {}).items()
        if not subpath.endswith(".json") and target is not None
    ]
    listed = [meta.root_api, *meta.smoke_imports]

    # (label, what to install, modules to load)
    runs = [("base", [spec], listed if optional_peers else _unique(listed + subpaths))]
    if optional_peers:
        runs.append((
            f"with optional peers {', '.join(optional_peers)}",
            [spec, *(f"{name}@{peers[name]}" for name in optional_peers)],
            _unique(listed + subpaths),
        ))
    problems: list[str] = []
    for run_label, installs, modules in runs:
        print(f"=== {label} {run_label} ===", flush=True)
        problems += [f"{label} {run_label}: {p}" for p in _check(installs, modules)]
    return problems


def _check(installs: list[str], modules: list[str]) -> list[str]:
    """Install `installs` into a new project and load `modules` there with IN_PROJECT."""
    env = {k: v for k, v in os.environ.items() if k not in NODE_ENV_VARS}
    # A temporary folder outside the repository, because Node's module resolution also searches every
    # parent folder's node_modules, so a project inside the package folder would find the package's own.
    with tempfile.TemporaryDirectory(prefix="smoke-") as tmp:
        project = Path(tmp)
        (project / "package.json").write_text(json.dumps({"name": "smoke", "private": True}) + "\n")
        shutil.copy(IN_PROJECT, project / "smoke.mjs")
        try:
            subprocess.run(
                # Skip dependencies' install scripts, as pnpm-workspace.yaml's allowBuilds does for the
                # package's own install. npm has no cooldown, so they'd run at every dependency's newest
                # version, and install scripts are how compromised npm packages usually attack. If a
                # package ever needs one, run `npm rebuild <name>` here for each dependency its
                # allowBuilds allows.
                # --prefer-online: revalidate npm's cached package metadata, which can be older than a
                # version that was just published.
                ["npm", "install", "--ignore-scripts", "--prefer-online", "--no-audit", "--no-fund", *installs],
                cwd=project, env=env, check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            return [f"install failed: {exc.stderr.strip()}"]

        # Log the resolved versions, since they're the newest allowed, not the ones in pnpm-lock.yaml.
        # A failure caused by a new dependency release then shows which version was installed.
        installed = subprocess.run(["npm", "ls", "--all"], cwd=project, env=env, capture_output=True, text=True)
        print(installed.stdout, end="", flush=True)

        result = subprocess.run(["node", "smoke.mjs", *modules], cwd=project, env=env, capture_output=True, text=True)
    if result.returncode == 0:
        return []
    return result.stdout.splitlines() or [f"smoke check crashed: {result.stderr.strip()}"]


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--dist", type=Path, default=None, help="defaults to <package-dir>/dist")
    source.add_argument("--registry", action="store_true", help="test a version published on npm instead (needs --version)")
    parser.add_argument("--version", help="the published version to test, with --registry")
    args = parser.parse_args(argv)
    if args.registry != (args.version is not None):
        parser.error("--registry and --version go together")

    if args.registry:
        where = f"version {args.version} on npm"
        problems = smoke_registry(args.package_dir, args.version)
    else:
        dist = args.dist or args.package_dir / "dist"
        where = f"the tarball in {dist}"
        problems = smoke(args.package_dir, dist)
    if problems:
        print(f"FAIL: {len(problems)} problem(s) smoke-testing {where}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: {where} passes the smoke test")
    return 0


if __name__ == "__main__":
    sys.exit(main())

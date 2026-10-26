#!/usr/bin/env python3
"""Repository-invariant checks for temporalio/worker-integrations.

Runs on every CI run (job `conventions`). Exits non-zero with a list of violations.

Checks (see AGENTS.md):
  * no language-level lockfiles (python/uv.lock, ...)
  * in flat-layout languages, every folder directly under the language root is a package or
    starts with `_` / `.`
  * every package has a valid integration.toml
  * every package's LICENSE is a regular file byte-identical to the root LICENSE; no CHANGELOG
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.common import (  # noqa: E402
    LANGUAGE_MANIFESTS,
    LANGUAGES,
    NESTED_LANGUAGES,
    Package,
    discover_packages,
    repo_root,
)
from lib.integration_toml import IntegrationMeta, IntegrationTomlError  # noqa: E402

LANGUAGE_LOCKFILES = (
    "uv.lock", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "go.sum", "gradle.lockfile",
    "packages.lock.json", "Gemfile.lock", "Cargo.lock",
)


class Checker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.violations: list[str] = []

    def fail(self, msg: str) -> None:
        self.violations.append(msg)

    # -- repository-wide ---------------------------------------------------------------------
    def check_language_roots(self, discovered: dict[str, list[Package]]) -> None:
        for language in LANGUAGES:
            lang_dir = self.root / language
            if not lang_dir.is_dir():
                continue

            for lock in LANGUAGE_LOCKFILES:
                if (lang_dir / lock).exists():
                    self.fail(f"{language}/{lock}: language-level lockfiles are forbidden; each package owns its own")

            if language in NESTED_LANGUAGES:
                continue  # intermediate folders (e.g. go/aws/) are expected

            # For languages where nesting isn't allowed (i.e., all except Go),
            # every direct subdirectory of a language must either be a package or start with "_" or "."
            package_paths = {p.path for p in discovered[language]}
            for child in sorted(lang_dir.iterdir()):
                if child.is_dir() and not child.name.startswith(("_", ".")) and child not in package_paths:
                    manifests = " or ".join(LANGUAGE_MANIFESTS[language])
                    self.fail(
                        f"{language}/{child.name}: folder has no {manifests}; "
                        "folders that aren't packages must start with `_`"
                    )

    # -- every package -----------------------------------------------------------------------
    def check_package(self, package: Package) -> IntegrationMeta | None:
        """Language-independent checks. Returns the parsed integration.toml, if valid enough to use."""
        rel = package.rel
        self.check_license(package)
        for path in package.path.iterdir():
            if path.is_file() and path.name.upper().startswith("CHANGELOG"):
                self.fail(f"{rel}/{path.name}: release notes are generated from commit history; no changelog files")

        toml_path = package.path / "integration.toml"
        if not toml_path.is_file():
            # Detected a package (by its language's native manifest file) that doesn't have our custom
            # integration.toml file alongside it. If you're creating a new package, chances are you forgot
            # the integration.toml file. This is the main reason why we discover packages by native manifest
            # rather than by integration.toml.
            hint = ""
            if package.language in NESTED_LANGUAGES:
                hint = (
                    "; if this is a test or tooling module inside another package, remove it and keep "
                    "those tests in the parent module instead"
                )
            self.fail(f"{rel}: has a {package.language} manifest but no integration.toml{hint}")
            return None
        try:
            return IntegrationMeta.from_file(toml_path)
        except IntegrationTomlError as exc:
            self.fail(f"{rel}/integration.toml: {exc}")
            return None

    def check_license(self, package: Package) -> None:
        """Check that the license file in a package is a byte-for-byte copy of the repo-wide license.

        We copy the license file per-package because not all languages' package management systems
        support symlinks or pointers to license files outside the package's own directory, so enforced
        copies are a universal way to ensure that the license is consistently distributed with every package.
        """
        license_path = package.path / "LICENSE"
        if not license_path.is_file() or license_path.is_symlink():
            self.fail(f"{package.rel}: LICENSE must be a regular file (`cp LICENSE {package.rel}/LICENSE`)")
        elif license_path.read_bytes() != (self.root / "LICENSE").read_bytes():
            self.fail(f"{package.rel}: LICENSE differs from the root LICENSE; re-copy it")

    def run(self) -> list[str]:
        discovered = discover_packages(self.root)
        self.check_language_roots(discovered)
        for language in LANGUAGES:
            for package in discovered[language]:
                self.check_package(package)
        return self.violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    violations = Checker(repo_root(args.repo_root)).run()
    if violations:
        print(f"FAIL: {len(violations)} convention violation(s):")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: repository conventions satisfied")
    return 0


if __name__ == "__main__":
    sys.exit(main())

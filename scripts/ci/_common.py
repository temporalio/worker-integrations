"""Shared helpers for the CI scripts (git, package discovery, GITHUB_OUTPUT).

Stdlib only. Imported by the sibling scripts via their own directory on sys.path.
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Language root -> glob patterns for the native manifest that marks a package directory.
#
# Every package must also have an integration.toml, but discovery deliberately doesn't key off
# it: a package missing that file (forgotten, or a stray nested module) should still be
# discovered so that checks can fail loudly on it. Keying off integration.toml would instead
# make such a folder invisible to CI, untested but with a passing ci-status.
LANGUAGE_MANIFESTS: dict[str, tuple[str, ...]] = {
    "dotnet": ("*.csproj",),
    "go": ("go.mod",),
    "java": ("build.gradle", "build.gradle.kts"),
    "python": ("pyproject.toml",),
    "ruby": ("*.gemspec",),
    "rust": ("Cargo.toml",),
    "typescript": ("package.json",),
}
LANGUAGES: tuple[str, ...] = tuple(LANGUAGE_MANIFESTS)

# Languages whose package folders mirror a path-shaped published name, so packages can sit at
# any depth and nest inside each other (a Go module's folder mirrors its module path). Every
# other language has one flat folder per package, directly under the language root.
NESTED_LANGUAGES = frozenset({"go"})

# Directories that never contain packages: names starting with these prefixes, plus `testdata`
# (which the Go toolchain also ignores).
IGNORED_PREFIXES = ("_", ".")
IGNORED_NAMES = frozenset({"testdata"})


@dataclass(frozen=True)
class Package:
    language: str
    name: str  # folder path relative to the language root, e.g. "aws/lambda/otel"
    path: Path

    @property
    def rel(self) -> str:
        return f"{self.language}/{self.name}"

    @property
    def slug(self) -> str:
        """`name` without slashes, for places that don't allow them (e.g. artifact names)."""
        return self.name.replace("/", "__")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def repo_root(start: Path | None = None) -> Path:
    """Locate the repository root (the directory containing the language roots).

    Defaults to the root of the git checkout containing this file.
    """
    if start is None:
        start = Path(git(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel").strip())
    return start.resolve()


def _package_name(language: str, path: str) -> str | None:
    """The package name if `path` (relative to the repo root) is a package's manifest."""
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != language:
        return None
    dirs, filename = parts[1:-1], parts[-1]
    if language not in NESTED_LANGUAGES and len(dirs) != 1:
        return None
    if any(d.startswith(IGNORED_PREFIXES) or d in IGNORED_NAMES for d in dirs):
        return None
    if not any(fnmatch.fnmatchcase(filename, pattern) for pattern in LANGUAGE_MANIFESTS[language]):
        return None
    return "/".join(dirs)


def discover_packages(root: Path) -> dict[str, list[Package]]:
    """Return {language: [Package, ...]} for every language, empty when its root is absent.

    Discovery reads tracked and untracked-but-not-ignored files from git, so ignored build and
    dependency directories (node_modules/, target/, ...) are never searched.
    """
    files = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    found: dict[str, list[Package]] = {}
    for language in LANGUAGES:
        names = sorted({n for f in files if (n := _package_name(language, f)) is not None})
        found[language] = [Package(language, n, root / language / n) for n in names]
        slugs = [p.slug for p in found[language]]
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"{language}: package folder names collide once slashes are replaced: {slugs}")
    return found


def write_github_output(path: str | os.PathLike[str] | None, values: dict[str, Any]) -> None:
    """Append key=value lines to a GITHUB_OUTPUT file (values are JSON-encoded unless str)."""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in values.items():
            text = value if isinstance(value, str) else compact_json(value)
            if "\n" in text:
                raise ValueError(f"multi-line output not supported for {key}")
            fh.write(f"{key}={text}\n")


def compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))

"""Shared fixtures: a temporary git repository shaped like this one."""

from __future__ import annotations

from pathlib import Path

import pytest

from _common import git

# Language -> the manifest file a minimal fake package of that language needs.
FAKE_MANIFESTS = {
    "dotnet": "Fake.csproj",
    "go": "go.mod",
    "java": "build.gradle.kts",
    "python": "pyproject.toml",
    "ruby": "fake.gemspec",
    "rust": "Cargo.toml",
    "typescript": "package.json",
}


def init_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "ci@example.com")
    git(root, "config", "user.name", "CI")
    git(root, "config", "commit.gpgsign", "false")
    (root / "LICENSE").write_text("MIT License\n")
    (root / "README.md").write_text("# repo\n")
    return root


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def make_package(root: Path, language: str, name: str) -> Path:
    """Create the smallest directory that discovery treats as a package."""
    d = root / language / name
    d.mkdir(parents=True, exist_ok=True)
    (d / FAKE_MANIFESTS[language]).write_text("")
    return d


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")

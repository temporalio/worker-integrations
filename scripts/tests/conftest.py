"""Shared fixtures: a temporary git repository shaped like this one."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lib.common import git, repo_root
from ci import check_conventions
from lib.languages import TOOLED_LANGUAGES
from new_package import scaffold

REPO = repo_root()

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


def run_checker(repo: Path) -> list[str]:
    return check_conventions.Checker(repo).run()


def replace_in_file(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new))


def make_package(root: Path, language: str, name: str) -> Path:
    """Create the smallest directory that discovery treats as a package."""
    d = root / language / name
    d.mkdir(parents=True, exist_ok=True)
    (d / FAKE_MANIFESTS[language]).write_text("")
    return d


def copy_python_support(root: Path) -> None:
    """Copy this repository's python/_shared, python/_template, LICENSE and scripts/pyproject.toml into `root`."""
    for rel in ("python/_shared", "python/_template"):
        if not (root / rel).exists():
            shutil.copytree(REPO / rel, root / rel)
    (root / "scripts").mkdir(exist_ok=True)
    shutil.copy(REPO / "scripts" / "pyproject.toml", root / "scripts" / "pyproject.toml")
    shutil.copy(REPO / "LICENSE", root / "LICENSE")


def make_python_package(
    root: Path, root_api: str = "temporalio.worker_integrations.aws.lambda_worker", maturity: str = "public-preview"
) -> Path:
    """Scaffold a Python package in `root` the way a contributor would, plus a stand-in uv.lock.

    The result passes the conventions check exactly as a real package would.
    """
    copy_python_support(root)
    scaffold(root, {"python": root_api}, f"Fake {root_api} integration", maturity)
    d = root / "python" / TOOLED_LANGUAGES["python"].package_folder(root_api)
    (d / "uv.lock").write_text("version = 1\n")
    return d


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")

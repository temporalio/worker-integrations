"""Shared fixtures: a temporary git repository shaped like this one."""

from __future__ import annotations

import shutil
import subprocess
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


def copy_language_support(root: Path, language: str) -> None:
    """Copy what scaffolding and checking `language`'s packages need into `root`.

    That's this repository's <language>/_shared and <language>/_template, LICENSE, and
    scripts/pyproject.toml (whose uv version Python packages must match).
    """
    for rel in (f"{language}/_shared", f"{language}/_template"):
        if not (root / rel).exists():
            shutil.copytree(REPO / rel, root / rel)
    (root / "scripts").mkdir(exist_ok=True)
    shutil.copy(REPO / "scripts" / "pyproject.toml", root / "scripts" / "pyproject.toml")
    shutil.copy(REPO / "LICENSE", root / "LICENSE")


def make_go_package(
    root: Path, module_path: str = "go.temporal.io/worker-integrations/aws/lambda", maturity: str = "public-preview"
) -> Path:
    """Scaffold a Go module in `root` the way a contributor would, plus a stand-in go.sum.

    The result passes the conventions check exactly as a real module would.
    """
    copy_language_support(root, "go")
    scaffold(root, {"go": module_path}, f"Fake {module_path} integration", maturity)
    d = root / "go" / TOOLED_LANGUAGES["go"].package_folder(module_path, module_path)
    (d / "go.sum").write_text("")
    return d


def make_python_package(
    root: Path, root_api: str = "temporalio.worker_integrations.aws.lambda_worker", maturity: str = "public-preview"
) -> Path:
    """Scaffold a Python package in `root` the way a contributor would, plus a stand-in uv.lock.

    The result passes the conventions check exactly as a real package would.
    """
    copy_language_support(root, "python")
    scaffold(root, {"python": root_api}, f"Fake {root_api} integration", maturity)
    python = TOOLED_LANGUAGES["python"]
    d = root / "python" / python.package_folder(root_api, python.published_name(root_api))
    (d / "uv.lock").write_text("version = 1\n")
    return d


def make_typescript_package(
    root: Path, published_name: str = "@temporalio/aws-lambda-worker", maturity: str = "public-preview"
) -> Path:
    """Scaffold a TypeScript package in `root` the way a contributor would, plus a stand-in pnpm-lock.yaml.

    The result passes the conventions check exactly as a real package would.
    """
    copy_language_support(root, "typescript")
    scaffold(root, {"typescript": published_name}, f"Fake {published_name} integration", maturity)
    d = root / "typescript" / TOOLED_LANGUAGES["typescript"].package_folder(published_name, published_name)
    (d / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    return d


def build_python_package(d: Path) -> Path:
    """Build the package's wheel and sdist into dist/, the way `make build` does, and return dist/."""
    subprocess.run(["uv", "build", "--no-sources", "--out-dir", "dist"], cwd=d, check=True, capture_output=True)
    return d / "dist"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return init_repo(tmp_path / "repo")


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly scaffolded Python package, built with build_python_package. Copy it before changing it."""
    d = make_python_package(init_repo(tmp_path_factory.mktemp("built") / "repo"))
    build_python_package(d)
    return d

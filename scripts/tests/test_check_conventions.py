from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from lib.common import repo_root
from conftest import make_package, replace_in_file, run_checker

REPO = repo_root()


def _make_go_package(repo: Path, name: str = "aws/lambda") -> Path:
    """A minimal package with valid language-independent metadata (Go has no language-specific checks yet)."""
    d = make_package(repo, "go", name)
    (d / "integration.toml").write_text(
        "[package]\n"
        f'published-name = "go.temporal.io/workerintegrations/{name}"\n'
        f'root-api = "go.temporal.io/workerintegrations/{name}"\n'
        'maturity = "public-preview"\n'
        "\n[ci]\n"
        'runtime-versions = ["1.26", "1.27"]\n'
    )
    shutil.copy(repo / "LICENSE", d / "LICENSE")
    return d


def test_this_repository_passes() -> None:
    assert run_checker(REPO) == []


def test_repository_without_packages_passes(repo: Path) -> None:
    assert run_checker(repo) == []


def test_valid_package_passes(repo: Path) -> None:
    _make_go_package(repo)
    assert run_checker(repo) == []


@pytest.mark.parametrize("old,new,message", [
    ('maturity = "public-preview"', 'maturity = "beta"', "maturity must be one of"),
    ('root-api = "go.temporal.io/workerintegrations/aws/lambda"', 'root-api = ""', "root-api must be a non-empty string"),
    ('runtime-versions = ["1.26", "1.27"]', "runtime-versions = []", "runtime-versions must be a non-empty list"),
    ("[package]", "[plugin]", "missing [package] table"),
    ("[ci]", '[release]\nallow-final = true\n\n[ci]', "unknown table [release]"),
    ('maturity = "public-preview"', 'maturity = "public-preview"\ndocs = "https://docs.temporal.io"',
     "unknown key(s) in [package]: docs"),
    ("[ci]", '[smoke]\nimport = ["x"]\n\n[ci]', "unknown key(s) in [smoke]: import"),
    ("[ci]", '[smoke]\nimports = "x"\n\n[ci]', "[smoke] imports must be a list of non-empty strings"),
])
def test_integration_toml_schema(repo: Path, old: str, new: str, message: str) -> None:
    d = _make_go_package(repo)
    replace_in_file(d / "integration.toml", old, new)
    assert any(message in v for v in run_checker(repo))


def test_license_must_match_root(repo: Path) -> None:
    d = _make_go_package(repo)
    (d / "LICENSE").write_text("Apache-2.0\n")
    assert any("LICENSE differs from the root LICENSE" in v for v in run_checker(repo))


def test_changelog_is_rejected(repo: Path) -> None:
    d = _make_go_package(repo)
    (d / "CHANGELOG.md").write_text("# Changes\n")
    assert any("no changelog files" in v for v in run_checker(repo))


def test_folder_without_manifest_must_start_with_underscore(repo: Path) -> None:
    (repo / "python" / "helpers").mkdir(parents=True)
    (repo / "python" / "helpers" / "notes.md").write_text("notes\n")
    assert any("python/helpers: folder has no pyproject.toml" in v for v in run_checker(repo))


def test_nested_go_folders_without_go_mod_are_allowed(repo: Path) -> None:
    _make_go_package(repo, "aws/lambda")
    (repo / "go" / "aws" / "README.md").write_text("aws\n")
    assert run_checker(repo) == []


def test_language_level_lockfile_is_rejected(repo: Path) -> None:
    (repo / "python").mkdir()
    (repo / "python" / "uv.lock").write_text("version = 1\n")
    assert any("language-level lockfiles are forbidden" in v for v in run_checker(repo))


def test_stray_nested_go_module_gets_a_hint(repo: Path) -> None:
    _make_go_package(repo, "aws/lambda")
    make_package(repo, "go", "aws/lambda/test")
    violations = run_checker(repo)
    assert any("go/aws/lambda/test: has a go manifest but no integration.toml" in v for v in violations)
    assert any("keep those tests in the parent module" in v for v in violations)

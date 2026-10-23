from __future__ import annotations

from pathlib import Path

import pytest

from ci import detect_changes
from lib.common import LANGUAGES, discover_packages, git
from conftest import FAKE_MANIFESTS, commit_all, make_package


def _setup(repo: Path) -> str:
    make_package(repo, "python", "alpha")
    make_package(repo, "python", "beta")
    (repo / "python" / "_shared").mkdir(parents=True)
    (repo / "python" / "_shared" / "python.mk").write_text("all:\n")
    (repo / "python" / "README.md").write_text("python\n")
    make_package(repo, "go", "gamma")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    (repo / "scripts" / "ci").mkdir(parents=True)
    (repo / "scripts" / "ci" / "x.py").write_text("x = 1\n")
    (repo / "scripts" / "tests").mkdir(parents=True)
    (repo / "scripts" / "tests" / "y.py").write_text("y = 1\n")
    return commit_all(repo, "base")


def _run(repo: Path, base: str, *touch: str, event: str = "pull_request") -> dict:
    for rel in touch:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(p.read_text() + "\n# change\n" if p.exists() else "new\n")
    commit_all(repo, "change")
    return detect_changes.main(["--repo-root", str(repo), "--event", event, "--base", base, "--dry-run"])


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_discovers_packages_by_manifest(repo: Path, language: str) -> None:
    make_package(repo, language, "pkg")
    (repo / language / "_shared").mkdir()
    (repo / language / "_shared" / FAKE_MANIFESTS[language]).write_text("")
    (repo / language / "no_manifest").mkdir()
    assert [p.rel for p in discover_packages(repo)[language]] == [f"{language}/pkg"]


def _setup_nested_go(repo: Path) -> str:
    for name in ("aws/lambda", "aws/lambda/otel", "gcp/cloudrun/id", "otlp"):
        make_package(repo, "go", name)
    (repo / "go" / "aws" / "README.md").write_text("aws\n")
    return commit_all(repo, "base")


def test_go_packages_nest_and_mirror_module_paths(repo: Path) -> None:
    _setup_nested_go(repo)
    make_package(repo, "go", "_shared/tool")
    make_package(repo, "go", "otlp/testdata/fixture")
    make_package(repo, "go", "ignored/mod")
    (repo / ".gitignore").write_text("go/ignored/\n")
    packages = discover_packages(repo)["go"]
    assert [p.name for p in packages] == ["aws/lambda", "aws/lambda/otel", "gcp/cloudrun/id", "otlp"]
    assert packages[1].slug == "aws__lambda__otel"


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "go"])
def test_other_languages_only_discover_top_level_packages(repo: Path, language: str) -> None:
    make_package(repo, language, "pkg")
    make_package(repo, language, "pkg/tests/fixture")
    make_package(repo, language, "group/pkg")
    assert [p.name for p in discover_packages(repo)[language]] == ["pkg"]


def test_slug_collisions_are_rejected(repo: Path) -> None:
    make_package(repo, "go", "a/b")
    make_package(repo, "go", "a__b")
    with pytest.raises(ValueError, match="collide"):
        discover_packages(repo)


@pytest.mark.parametrize("path,expected", [
    ("go/aws/lambda/otel/otel.go", ["aws/lambda/otel"]),
    ("go/aws/lambda/lambda.go", ["aws/lambda"]),
    ("go/aws/lambda/internal/x.go", ["aws/lambda"]),
    ("go/gcp/cloudrun/id/go.mod", ["gcp/cloudrun/id"]),
    ("go/aws/README.md", ["aws/lambda", "aws/lambda/otel", "gcp/cloudrun/id", "otlp"]),
])
def test_nested_package_file_selects_the_innermost_package(repo: Path, path: str, expected: list[str]) -> None:
    base = _setup_nested_go(repo)
    assert _run(repo, base, path)["go"] == expected


@pytest.mark.parametrize("path", ["src/impl.py", "pyproject.toml", "uv.lock", "src/café.py", "src/a b.py"])
def test_package_file_selects_only_that_package(repo: Path, path: str) -> None:
    base = _setup(repo)
    r = _run(repo, base, f"python/alpha/{path}")
    assert r["python"] == ["alpha"]
    assert r["go"] == []
    assert r["any"] is True
    assert r["mode"] == "diff"


def test_shared_language_file_selects_all_packages_of_that_language(repo: Path) -> None:
    base = _setup(repo)
    r = _run(repo, base, "python/_shared/python.mk")
    assert r["python"] == ["alpha", "beta"]
    assert r["go"] == []


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", "scripts/ci/x.py", "scripts/lib/x.py", "LICENSE"])
def test_workflows_ci_scripts_and_license_select_everything(repo: Path, path: str) -> None:
    base = _setup(repo)
    r = _run(repo, base, path)
    assert r["python"] == ["alpha", "beta"]
    assert r["go"] == ["gamma"]
    assert r["mode"] == "all"


@pytest.mark.parametrize("path", ["README.md", "python/README.md", "scripts/tests/y.py"])
def test_other_files_select_nothing(repo: Path, path: str) -> None:
    base = _setup(repo)
    r = _run(repo, base, path)
    assert r["any"] is False
    assert r["mode"] == "none"


def test_new_package_added_in_the_change_is_selected(repo: Path) -> None:
    base = _setup(repo)
    make_package(repo, "python", "delta")
    commit_all(repo, "add delta")
    r = detect_changes.main(["--repo-root", str(repo), "--event", "pull_request", "--base", base, "--dry-run"])
    assert r["python"] == ["delta"]


def test_push_schedule_dispatch_and_unknown_events_run_everything(repo: Path) -> None:
    base = _setup(repo)
    for event in ("push", "schedule", "workflow_dispatch", "mystery"):
        r = detect_changes.main(["--repo-root", str(repo), "--event", event, "--base", base, "--dry-run"])
        assert r["mode"] == "all", event
        assert r["python"] == ["alpha", "beta"], event


def test_unusable_base_falls_back_to_everything(repo: Path) -> None:
    _setup(repo)
    r = detect_changes.main(["--repo-root", str(repo), "--event", "pull_request", "--base", "0" * 40, "--dry-run"])
    assert r["mode"] == "all"


def test_repo_without_packages_selects_nothing(repo: Path) -> None:
    commit_all(repo, "base")
    r = detect_changes.main(["--repo-root", str(repo), "--event", "push", "--dry-run"])
    assert r["any"] is False
    assert all(r[lang] == [] for lang in LANGUAGES)


def test_github_output_format(repo: Path, tmp_path: Path) -> None:
    base = _setup(repo)
    out = tmp_path / "out.txt"
    (repo / "python" / "alpha" / "README.md").write_text("# alpha\n")
    commit_all(repo, "readme")
    detect_changes.main(["--repo-root", str(repo), "--event", "pull_request", "--base", base, "--github-output", str(out)])
    text = out.read_text()
    assert 'python=["alpha"]' in text
    assert "go=[]" in text
    assert "any=true" in text
    assert "mode=diff" in text
    assert git(repo, "status", "--porcelain") == ""

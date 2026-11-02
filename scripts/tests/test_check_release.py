from __future__ import annotations

from pathlib import Path

import pytest

from ci import check_release
from conftest import commit_all, make_python_package
from lib.languages.python import Python
from lib.release_version import ReleaseVersion

TAG = "python/aws_lambda_worker/v0.1.0"


def v(text: str) -> ReleaseVersion:
    return Python().release_version(text)


def publish(monkeypatch: pytest.MonkeyPatch, versions: list[str]) -> None:
    """Make PyPI appear to have these versions of every package."""
    monkeypatch.setattr(Python, "published_versions", lambda self, published_name: versions)


def run(repo: Path, tag: str, *args: str) -> int:
    return check_release.main(["--language", "python", "--repo-root", str(repo), tag, *args])


@pytest.mark.parametrize("maturity,first", [
    ("pre-release", "0.0.1"),
    ("public-preview", "0.1.0"),
    ("generally-available", "1.0.0"),
])
def test_first_release_is_set_by_maturity(maturity: str, first: str) -> None:
    assert check_release.check_version_conventions(v(first), maturity, []) == []
    assert check_release.check_version_conventions(v(f"{first}rc1"), maturity, []) == []


@pytest.mark.parametrize("version", ["0.0.1", "0.1.1", "0.2.0", "1.0.0"])
def test_first_release_must_match_maturity(version: str) -> None:
    assert check_release.check_version_conventions(v(version), "public-preview", []) == [
        f"the first release of a public-preview package must be 0.1.0 or a pre-release of it (got {version})"
    ]


@pytest.mark.parametrize("version", ["0.1.1rc2", "0.1.1", "0.2.0a1", "1.0.0"])
def test_later_release_greater_than_every_published_version_passes(version: str) -> None:
    assert check_release.check_version_conventions(v(version), "public-preview", [v("0.1.1rc1"), v("0.1.0")]) == []


@pytest.mark.parametrize("version", ["0.1.1rc1", "0.1.1a1", "0.1.0", "0.1.0rc1"])
def test_later_release_must_be_greater_than_every_published_version(version: str) -> None:
    assert check_release.check_version_conventions(v(version), "public-preview", [v("0.1.1rc1"), v("0.1.0")]) == [
        f"{version} must be greater than the newest published version, 0.1.1rc1"
    ]


@pytest.mark.parametrize("maturity,version,first", [
    ("public-preview", "0.0.6", "0.1.0"),
    ("generally-available", "0.5.0", "1.0.0"),
])
def test_later_release_must_be_at_least_its_maturitys_first_version(maturity: str, version: str, first: str) -> None:
    assert check_release.check_version_conventions(v(version), maturity, [v("0.0.5")]) == [
        f"a {maturity} package must be at least {first} or a pre-release of it (got {version})"
    ]


@pytest.mark.parametrize("maturity,version", [("public-preview", "0.1.0rc1"), ("generally-available", "1.0.0rc1")])
def test_raised_maturity_allows_a_pre_release_of_its_first_version(maturity: str, version: str) -> None:
    assert check_release.check_version_conventions(v(version), maturity, [v("0.0.5")]) == []


@pytest.mark.parametrize("maturity,tag,prerelease,answer", [
    ("public-preview", TAG, "false", "no"),
    ("public-preview", "python/aws_lambda_worker/v0.1.0rc1", "true", "yes"),
    ("pre-release", "python/aws_lambda_worker/v0.0.1", "true", "yes"),
])
def test_main_writes_outputs_and_summary(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, maturity: str, tag: str, prerelease: str, answer: str
) -> None:
    make_python_package(repo, maturity=maturity)
    sha = commit_all(repo, "add package")
    publish(monkeypatch, [])
    output, summary = tmp_path / "output", tmp_path / "summary"
    assert run(repo, tag, "--github-output", str(output), "--github-step-summary", str(summary)) == 0
    version = tag.rpartition("/v")[2]
    assert output.read_text() == f"package=aws_lambda_worker\nversion={version}\nprerelease={prerelease}\n"
    assert f"Tested commit: `{sha}`" in summary.read_text()
    assert f"Mark the GitHub release as a pre-release: {answer}" in summary.read_text()


def test_main_rejects_another_languages_tag(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_python_package(repo)
    assert check_release.main(["--language", "go", "--repo-root", str(repo), TAG]) == 1
    assert f"FAIL: {TAG} isn't a go release tag" in capsys.readouterr().out


def test_main_rejects_an_invalid_tag(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_python_package(repo)
    assert run(repo, "python/aws_lambda_worker/v0.1") == 1
    assert "FAIL: release tag 'python/aws_lambda_worker/v0.1': '0.1' isn't a supported Python version" in capsys.readouterr().out


def test_main_rejects_a_version_conventions_violation(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_python_package(repo)
    publish(monkeypatch, ["0.1.0"])
    output = tmp_path / "output"
    assert run(repo, TAG, "--github-output", str(output)) == 1
    assert "0.1.0 must be greater than the newest published version, 0.1.0" in capsys.readouterr().out
    assert not output.exists()


def test_main_rejects_an_unorderable_published_version(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    make_python_package(repo)
    publish(monkeypatch, ["0.0.1", "0.0.1.post1"])
    assert run(repo, "python/aws_lambda_worker/v0.1.0") == 1
    assert (
        "FAIL: temporalio-worker-integrations-aws-lambda-worker has a published version this tooling can't order: '0.0.1.post1'"
        in capsys.readouterr().out
    )

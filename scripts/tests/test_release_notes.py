from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import release_notes
from conftest import commit_all, make_package, make_python_package
from lib.common import Package, git
from lib.release_tag import parse_tag

PACKAGE = "python/aws_lambda_worker"
# The real function, which the github_tags fixture replaces in every test
REMOTE_TAGS = release_notes.remote_tags


def change(repo: Path, rel: str, subject: str) -> str:
    """Commit a change to a new file at `rel`, and return the commit's short SHA."""
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(subject)
    commit_all(repo, subject)
    return git(repo, "rev-parse", "--short", "HEAD").strip()


def tag(repo: Path, version: str) -> None:
    git(repo, "tag", f"{PACKAGE}/v{version}")


def notes(repo: Path, version: str, *args: str, capsys: pytest.CaptureFixture[str]) -> str:
    assert release_notes.main(["--repo-root", str(repo), f"{PACKAGE}/v{version}", *args]) == 0
    return capsys.readouterr().out


@pytest.fixture(autouse=True)
def github_tags(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """The tags GitHub appears to have, instead of listing the real repository's. Empty unless a test adds some."""
    tags: set[str] = set()
    monkeypatch.setattr(release_notes, "remote_tags", lambda root, prefix: {t for t in tags if t.startswith(prefix)})
    return tags


@pytest.fixture
def released(repo: Path) -> Path:
    """A repository with the package released at 0.1.0."""
    make_python_package(repo)
    commit_all(repo, "Add package")
    tag(repo, "0.1.0")
    return repo


def test_first_release_lists_every_commit_that_changed_the_package(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_python_package(repo)
    commit_all(repo, "Add package")
    sha = change(repo, f"{PACKAGE}/src/a.py", "Add a")
    change(repo, "python/other/b.py", "Change another package")
    assert notes(repo, "0.1.0", capsys=capsys).splitlines() == [
        "## Changes",
        "",
        f"- Add a ({sha})",
        f"- Add package ({git(repo, 'rev-parse', '--short', 'HEAD~2').strip()})",
    ]


def test_release_lists_commits_since_the_previous_release(released: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sha = change(released, f"{PACKAGE}/src/a.py", "Add a")
    assert notes(released, "0.2.0", capsys=capsys).splitlines() == [
        "## Changes since [v0.1.0](https://github.com/temporalio/worker-integrations/releases/tag/python/aws_lambda_worker/v0.1.0)",
        "",
        f"- Add a ({sha})",
    ]


def test_pull_request_references_are_linked(released: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sha = change(released, f"{PACKAGE}/src/a.py", "Add a (#12)")
    assert f"- Add a ([#12](https://github.com/temporalio/worker-integrations/pull/12)) ({sha})" in notes(
        released, "0.2.0", capsys=capsys
    )


def test_ref_ends_the_range(released: Path, capsys: pytest.CaptureFixture[str]) -> None:
    change(released, f"{PACKAGE}/src/a.py", "Add a")
    change(released, f"{PACKAGE}/src/b.py", "Add b")
    out = notes(released, "0.2.0", "--ref", "HEAD~1", capsys=capsys)
    assert "Add a" in out
    assert "Add b" not in out


def test_no_changes_since_the_previous_release(released: Path, capsys: pytest.CaptureFixture[str]) -> None:
    change(released, "python/other/b.py", "Change another package")
    assert notes(released, "0.1.1", capsys=capsys).splitlines() == [
        "## Changes since [v0.1.0](https://github.com/temporalio/worker-integrations/releases/tag/python/aws_lambda_worker/v0.1.0)",
        "",
        f"No commits changed {PACKAGE}.",
    ]


def test_final_release_skips_earlier_pre_releases(released: Path) -> None:
    for version in ("0.2.0a1", "0.2.0rc1"):
        tag(released, version)
    assert release_notes.previous_tag(released, parse_tag(released, f"{PACKAGE}/v0.2.0")) == f"{PACKAGE}/v0.1.0"


def test_pre_release_follows_the_highest_lower_tag(released: Path) -> None:
    for version in ("0.2.0a1", "0.2.0rc1"):
        tag(released, version)
    assert release_notes.previous_tag(released, parse_tag(released, f"{PACKAGE}/v0.2.0rc2")) == f"{PACKAGE}/v0.2.0rc1"


def test_previous_tag_ignores_higher_unparseable_and_other_packages_tags(released: Path) -> None:
    for name in (f"{PACKAGE}/v0.3.0", f"{PACKAGE}/vnext", f"{PACKAGE}/v0.1.5.post1", "python/other/v0.1.9"):
        git(released, "tag", name)
    assert release_notes.previous_tag(released, parse_tag(released, f"{PACKAGE}/v0.2.0")) == f"{PACKAGE}/v0.1.0"


def test_first_release_has_no_previous_tag(released: Path) -> None:
    assert release_notes.previous_tag(released, parse_tag(released, f"{PACKAGE}/v0.0.9")) is None


def test_nested_packages_are_excluded(repo: Path) -> None:
    # Go modules can nest, and a nested module is released separately from the one containing it
    for name in ("aws/lambda", "aws/lambda/otel", "aws/lambda/otel/extra", "aws/lambdax"):
        make_package(repo, "go", name)
    commit_all(repo, "Add modules")
    change(repo, "go/aws/lambda/worker.go", "Change lambda")
    change(repo, "go/aws/lambda/otel/otel.go", "Change otel")
    change(repo, "go/aws/lambdax/x.go", "Change lambdax")
    lambda_ = Package("go", "aws/lambda", repo / "go" / "aws" / "lambda")
    specs = release_notes.pathspecs(repo, lambda_)
    assert specs == ["go/aws/lambda", ":(exclude)go/aws/lambda/otel", ":(exclude)go/aws/lambda/otel/extra"]
    assert git(repo, "log", "--format=%s", "--", *specs).splitlines() == ["Change lambda", "Add modules"]


def test_invalid_tag_or_ref_fails_on_stderr(released: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert release_notes.main(["--repo-root", str(released), f"{PACKAGE}/v0.2"]) == 1
    assert release_notes.main(["--repo-root", str(released), f"{PACKAGE}/v0.2.0", "--ref", "nope"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "isn't a supported Python version" in captured.err
    assert "FAIL: 'nope' isn't a commit" in captured.err


def test_up_to_date_tags_pass(released: Path, github_tags: set[str], capsys: pytest.CaptureFixture[str]) -> None:
    github_tags.update({f"{PACKAGE}/v0.1.0", "python/other/v0.5.0"})
    assert notes(released, "0.2.0", capsys=capsys).startswith("## Changes since [v0.1.0]")


def test_tags_missing_locally_fail(released: Path, github_tags: set[str], capsys: pytest.CaptureFixture[str]) -> None:
    github_tags.update({f"{PACKAGE}/v0.1.0", f"{PACKAGE}/v0.1.1", f"{PACKAGE}/v0.1.2"})
    assert release_notes.main(["--repo-root", str(released), f"{PACKAGE}/v0.2.0"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"FAIL: 2 of {PACKAGE}'s release tags on GitHub are missing locally; run `git fetch --tags`" in captured.err


def test_unreachable_github_fails(released: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def remote_tags(root: Path, prefix: str) -> set[str]:
        raise subprocess.CalledProcessError(128, ["git", "ls-remote"], stderr="fatal: unable to access\n")

    monkeypatch.setattr(release_notes, "remote_tags", remote_tags)
    assert release_notes.main(["--repo-root", str(released), f"{PACKAGE}/v0.2.0"]) == 1
    assert "FAIL: can't list the release tags on GitHub: fatal: unable to access" in capsys.readouterr().err


def test_remote_tags_lists_the_matching_tag_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def git(root: Path, *args: str) -> str:
        assert args == ("ls-remote", "--tags", "--refs", release_notes.REPO_URL, f"refs/tags/{PACKAGE}/v*")
        return f"aaa\trefs/tags/{PACKAGE}/v0.1.0\nbbb\trefs/tags/{PACKAGE}/v0.2.0rc1\n"

    monkeypatch.setattr(release_notes, "git", git)
    assert REMOTE_TAGS(tmp_path, f"{PACKAGE}/v") == {f"{PACKAGE}/v0.1.0", f"{PACKAGE}/v0.2.0rc1"}


def test_since_overrides_the_previous_release(released: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # E.g. 0.2.0 was tagged but never published, and its fix went out as 0.2.1
    a = change(released, f"{PACKAGE}/src/a.py", "Add a")
    tag(released, "0.2.0")
    out = notes(released, "0.2.1", "--since", f"{PACKAGE}/v0.1.0", capsys=capsys).splitlines()
    assert out[0].startswith("## Changes since [v0.1.0](")
    assert out[2:] == [f"- Add a ({a})"]


@pytest.mark.parametrize("since", [
    f"{PACKAGE}/v0.2.0",  # not below the release
    f"{PACKAGE}/v0.0.5",  # no such tag
    "python/other/v0.1.0",  # not a package
    f"{PACKAGE}/v0.1",  # not a version
])
def test_since_must_be_an_earlier_release_tag_of_the_package(
    released: Path, capsys: pytest.CaptureFixture[str], since: str
) -> None:
    assert release_notes.main(["--repo-root", str(released), f"{PACKAGE}/v0.2.0", "--since", since]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FAIL: --since" in captured.err

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

import pytest

from ci.typescript import _registry, check_published
from conftest import make_typescript_package

NAME = "@temporalio/aws-lambda-worker"
TARBALL = b"tested tarball bytes"
INTEGRITY = "sha512-" + base64.b64encode(hashlib.sha512(TARBALL).digest()).decode()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    d.mkdir()
    (d / "temporalio-aws-lambda-worker-0.1.0.tgz").write_bytes(TARBALL)
    return d


def serve(monkeypatch: pytest.MonkeyPatch, metadata: dict[str, Any] | None) -> list[str]:
    """Make npm appear to have `metadata` for the version (None: not listed). Returns how it was looked up."""
    calls: list[str] = []

    def lookup(how: str) -> Any:
        def look(name: str, version: str) -> dict[str, Any] | None:
            assert (name, version) == (NAME, "0.1.0")
            calls.append(how)
            return metadata
        return look

    monkeypatch.setattr(check_published, "version_metadata", lookup("now"))
    monkeypatch.setattr(check_published, "wait_for_version", lookup("wait"))
    return calls


def test_integrity_is_npms_sha512_format(dist: Path) -> None:
    (tarball,) = dist.glob("*.tgz")
    assert check_published.integrity(tarball) == INTEGRITY


def test_unpublished_version_is_reported_without_waiting(dist: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = serve(monkeypatch, None)
    assert check_published.check(NAME, "0.1.0", dist, wait=False) is False
    assert calls == ["now"]


def test_version_with_the_tested_bytes_is_published(dist: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, {"dist": {"integrity": INTEGRITY}})
    assert check_published.check(NAME, "0.1.0", dist, wait=False) is True


@pytest.mark.parametrize("wait", [False, True])
def test_version_with_other_bytes_fails(dist: Path, monkeypatch: pytest.MonkeyPatch, wait: bool) -> None:
    serve(monkeypatch, {"dist": {"integrity": "sha512-other"}})
    with pytest.raises(check_published.PublishedError, match="npm never replaces a version"):
        check_published.check(NAME, "0.1.0", dist, wait=wait)


def test_wait_requires_the_version(dist: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = serve(monkeypatch, None)
    with pytest.raises(check_published.PublishedError, match="npm still doesn't list"):
        check_published.check(NAME, "0.1.0", dist, wait=True)
    assert calls == ["wait"]


def test_requires_exactly_one_tarball(dist: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, None)
    (dist / "other.tgz").write_bytes(b"")
    with pytest.raises(check_published.PublishedError, match="expected exactly one tarball"):
        check_published.check(NAME, "0.1.0", dist, wait=False)


@pytest.mark.parametrize("metadata,answer", [(None, "false"), ({"dist": {"integrity": INTEGRITY}}, "true")])
def test_main_writes_the_answer(
    repo: Path, dist: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, metadata: Any, answer: str
) -> None:
    d = make_typescript_package(repo)
    serve(monkeypatch, metadata)
    output = tmp_path / "github_output"
    args = ["--package-dir", str(d), "--version", "0.1.0", "--dist", str(dist), "--github-output", str(output)]
    assert check_published.main(args) == 0
    assert output.read_text() == f"published={answer}\n"


def test_main_fails_on_other_bytes(
    repo: Path, dist: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    d = make_typescript_package(repo)
    serve(monkeypatch, {"dist": {"integrity": "sha512-other"}})
    assert check_published.main(["--package-dir", str(d), "--version", "0.1.0", "--dist", str(dist), "--wait"]) == 1
    assert "FAIL: npm has @temporalio/aws-lambda-worker@0.1.0 with integrity 'sha512-other'" in capsys.readouterr().out


def serve_packuments(monkeypatch: pytest.MonkeyPatch, responses: list[dict[str, Any] | None]) -> list[float]:
    """Make npm serve these packuments, one per lookup. Returns the sleeps between lookups."""
    sleeps: list[float] = []
    monkeypatch.setattr(_registry, "fetch_packument", lambda name: responses.pop(0))
    monkeypatch.setattr(_registry.time, "sleep", sleeps.append)
    return sleeps


def test_wait_for_version_waits_until_npm_lists_it(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = {"versions": {"0.1.0": {"version": "0.1.0"}}}
    sleeps = serve_packuments(monkeypatch, [None, {"versions": {}}, listed])
    assert _registry.wait_for_version(NAME, "0.1.0") == {"version": "0.1.0"}
    assert sleeps == [_registry.CHECK_DELAY] * 2


def test_wait_for_version_gives_up_after_the_last_check(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps = serve_packuments(monkeypatch, [None] * _registry.CHECKS)
    assert _registry.wait_for_version(NAME, "0.1.0") is None
    assert len(sleeps) == _registry.CHECKS - 1

from __future__ import annotations

import io
import json
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from ci.go import smoke
from conftest import make_go_package

MODULE = "go.temporal.io/worker-integrations/aws/lambda"
GO_IMPORT = f'<meta name="go-import" content="{MODULE} git https://github.com/temporalio/worker-integrations go/aws/lambda">'

needs_go = pytest.mark.skipif(shutil.which("go") is None, reason="needs the go command")


def file_proxy(tmp_path: Path, module_dir: Path, version: str) -> str:
    """Serve the module in `module_dir` at `version` from a file-based module proxy, and return its GOPROXY URL."""
    versions = tmp_path / "proxy" / MODULE / "@v"
    versions.mkdir(parents=True)
    (versions / "list").write_text(f"v{version}\n")
    (versions / f"v{version}.info").write_text(json.dumps({"Version": f"v{version}"}))
    shutil.copy(module_dir / "go.mod", versions / f"v{version}.mod")
    with zipfile.ZipFile(versions / f"v{version}.zip", "w") as archive:
        for path in sorted(module_dir.rglob("*")):
            if path.is_file():
                archive.write(path, f"{MODULE}@v{version}/{path.relative_to(module_dir).as_posix()}")
    return (tmp_path / "proxy").as_uri()


def serve(monkeypatch: pytest.MonkeyPatch, responses: list[bytes | int]) -> list[str]:
    """Make urlopen return each response in turn (an int is an HTTP error status), and record the URLs."""
    urls: list[str] = []

    def urlopen(url: str, timeout: float) -> io.BytesIO:
        urls.append(url)
        response = responses.pop(0)
        if isinstance(response, int):
            raise urllib.error.HTTPError(url, response, "error", None, None)  # type: ignore[arg-type]
        return io.BytesIO(response)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(smoke, "PROXY_CHECK_DELAY", 0)
    return urls


def test_vanity_page_with_the_go_import_tag_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = serve(monkeypatch, [f"<html><head>{GO_IMPORT}</head></html>".encode()])
    smoke.check_vanity_page(MODULE)
    assert urls == [f"https://{MODULE}?go-get=1"]


@pytest.mark.parametrize("page", [
    b"<html></html>",
    GO_IMPORT.replace("go/aws/lambda", "go/aws").encode(),
    GO_IMPORT.replace("worker-integrations", "sdk-go").encode(),
])
def test_vanity_page_must_have_the_go_import_tag(monkeypatch: pytest.MonkeyPatch, page: bytes) -> None:
    serve(monkeypatch, [page])
    with pytest.raises(smoke.SmokeFailure, match="must have go-import tag"):
        smoke.check_vanity_page(MODULE)


def test_missing_vanity_page_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, [404])
    with pytest.raises(smoke.SmokeFailure, match="returned HTTP 404; the module needs a vanity import page"):
        smoke.check_vanity_page(MODULE)


def test_wait_for_proxy_retries_until_the_version_is_served(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = serve(monkeypatch, [404, 410, b"{}"])
    smoke.wait_for_proxy(MODULE, "0.1.0")
    assert urls == [f"https://proxy.golang.org/{MODULE}/@v/v0.1.0.info"] * 3


def test_wait_for_proxy_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, [404] * smoke.PROXY_CHECKS)
    with pytest.raises(smoke.SmokeFailure, match=f"still wasn't available after {smoke.PROXY_CHECKS} checks"):
        smoke.wait_for_proxy(MODULE, "0.1.0")


def test_wait_for_proxy_fails_on_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, [500])
    with pytest.raises(smoke.SmokeFailure, match="returned HTTP 500"):
        smoke.wait_for_proxy(MODULE, "0.1.0")


@needs_go
def test_published_module_downloads_and_builds(repo: Path, tmp_path: Path) -> None:
    d = make_go_package(repo)
    (d / "client").mkdir()
    (d / "client" / "client.go").write_text("package client\n")
    proxy = file_proxy(tmp_path, d, "0.1.0")
    smoke.download_and_build(MODULE, "0.1.0", [f"{MODULE}/client"], proxy=proxy, sumdb="off")


@needs_go
def test_unpublished_version_fails_to_download(repo: Path, tmp_path: Path) -> None:
    proxy = file_proxy(tmp_path, make_go_package(repo), "0.1.0")
    with pytest.raises(smoke.SmokeFailure, match=f"`go mod download {MODULE}@v0.2.0` failed"):
        smoke.download_and_build(MODULE, "0.2.0", [], proxy=proxy, sumdb="off")


@needs_go
def test_missing_smoke_import_fails_to_build(repo: Path, tmp_path: Path) -> None:
    proxy = file_proxy(tmp_path, make_go_package(repo), "0.1.0")
    with pytest.raises(smoke.SmokeFailure, match=f"failed in a module that imports {MODULE}@v0.1.0"):
        smoke.download_and_build(MODULE, "0.1.0", [f"{MODULE}/client"], proxy=proxy, sumdb="off")


def test_main_runs_every_check_for_the_package(repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    d = make_go_package(repo)
    with (d / "integration.toml").open("a") as fh:
        fh.write(f'\n[smoke]\nimports = ["{MODULE}/client"]\n')
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(smoke, "check_vanity_page", lambda *args: calls.append(("vanity", *args)))
    monkeypatch.setattr(smoke, "wait_for_proxy", lambda *args: calls.append(("proxy", *args)))
    monkeypatch.setattr(smoke, "download_and_build", lambda *args: calls.append(("build", *args)))
    assert smoke.main(["--package-dir", str(d), "--version", "0.1.0"]) == 0
    assert calls == [
        ("vanity", MODULE),
        ("proxy", MODULE, "0.1.0"),
        ("build", MODULE, "0.1.0", [f"{MODULE}/client"]),
    ]
    assert f"OK: {MODULE}@v0.1.0 downloads and builds" in capsys.readouterr().out


def test_main_reports_the_first_failure(repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    d = make_go_package(repo)

    def fail(*args: object) -> None:
        raise smoke.SmokeFailure("no vanity page")

    monkeypatch.setattr(smoke, "check_vanity_page", fail)
    assert smoke.main(["--package-dir", str(d), "--version", "0.1.0"]) == 1
    assert "FAIL: no vanity page" in capsys.readouterr().out

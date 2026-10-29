from __future__ import annotations

import io
import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ci.python import smoke
from conftest import build_python_package, replace_in_file

ROOT_API = "temporalio.worker_integrations.aws.lambda_worker"
PKG_DIR = "src/temporalio/worker_integrations/aws/lambda_worker"


def copy_package(built: Path, tmp_path: Path) -> Path:
    """A copy of the built package, without its dist/."""
    return Path(shutil.copytree(built, tmp_path / built.name, ignore=shutil.ignore_patterns("dist")))


def test_template_build_passes(built: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main(["--package-dir", str(built)]) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    # The resolved versions are logged for each install.
    assert re.search(r"^temporalio-worker-integrations-aws-lambda-worker +0\.0\.0$", out, re.MULTILINE)
    assert re.search(r"^temporalio +\d", out, re.MULTILINE)


def test_every_module_is_imported(built: Path, tmp_path: Path) -> None:
    d = copy_package(built, tmp_path)
    (d / PKG_DIR / "_broken.py").write_text("raise RuntimeError('boom')\n")
    problems = smoke.smoke(d, build_python_package(d))
    assert len(problems) == 2
    assert problems[0].endswith(f".whl base: import {ROOT_API}._broken failed: RuntimeError('boom')")
    assert problems[1].endswith(f".tar.gz base: import {ROOT_API}._broken failed: RuntimeError('boom')")


def test_extras_are_installed_for_the_full_import(built: Path, tmp_path: Path) -> None:
    d = copy_package(built, tmp_path)
    # iniconfig: a small dependency-free package that pytest already pulls into uv's cache.
    replace_in_file(d / "pyproject.toml", "[project.optional-dependencies]\n", '[project.optional-dependencies]\nini = ["iniconfig"]\n')
    (d / PKG_DIR / "ini.py").write_text("import iniconfig\n")
    assert smoke.smoke(d, build_python_package(d)) == []

    # Listed imports must work without extras.
    with (d / "integration.toml").open("a") as fh:
        fh.write(f'\n[smoke]\nimports = ["{ROOT_API}.ini"]\n')
    problems = smoke.smoke(d, d / "dist")
    assert len(problems) == 2
    assert problems[0].endswith(f".whl base: import {ROOT_API}.ini failed: ModuleNotFoundError(\"No module named 'iniconfig'\")")
    assert problems[1].endswith(f".tar.gz base: import {ROOT_API}.ini failed: ModuleNotFoundError(\"No module named 'iniconfig'\")")


def test_provenance_guard_runs(built: Path, tmp_path: Path) -> None:
    d = Path(shutil.copytree(built, tmp_path / built.name))
    (d / "tests/helpers/provenance.py").write_text(
        "class ProvenanceError(Exception):\n"
        "    pass\n"
        "\n"
        "def check_provenance(dist_name, pkg_rel):\n"
        "    raise ProvenanceError(f'{dist_name} {pkg_rel}')\n"
    )
    problems = smoke.smoke(d, d / "dist")
    message = "provenance guard failed: temporalio-worker-integrations-aws-lambda-worker temporalio/worker_integrations/aws/lambda_worker"
    assert len(problems) == 2
    assert problems[0].endswith(f".whl base: {message}")
    assert problems[1].endswith(f".tar.gz base: {message}")


def test_no_distributions(built: Path, tmp_path: Path) -> None:
    assert smoke.smoke(built, tmp_path) == [f"no wheel or sdist in {tmp_path}"]


NAME = "temporalio-worker-integrations-aws-lambda-worker"
WHEEL = (f"{NAME.replace('-', '_')}-0.1.0-py3-none-any.whl", "https://files.example/wheel")
SDIST = (f"{NAME.replace('-', '_')}-0.1.0.tar.gz", "https://files.example/sdist")


def serve_index(monkeypatch: pytest.MonkeyPatch, responses: list[list[tuple[str, str]] | None]) -> list[str]:
    """Make each index check see the next response's files (None: a 404), and skip the waits.

    Returns the URLs requested.
    """
    requested: list[str] = []

    def urlopen(url: str, timeout: float) -> io.BytesIO:
        requested.append(url)
        files = responses[min(len(requested), len(responses)) - 1]
        if files is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return io.BytesIO(json.dumps({"urls": [{"filename": f, "url": u} for f, u in files]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(smoke.time, "sleep", lambda seconds: None)
    return requested


def test_index_files_waits_until_both_files_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    requested = serve_index(monkeypatch, [None, [WHEEL], [SDIST, WHEEL]])
    assert smoke.index_files("testpypi", NAME, "0.1.0") == [WHEEL, SDIST]
    assert requested == [f"https://test.pypi.org/pypi/{NAME}/0.1.0/json"] * 3


def test_index_files_gives_up_after_the_last_check(monkeypatch: pytest.MonkeyPatch) -> None:
    requested = serve_index(monkeypatch, [[WHEEL]])
    assert smoke.index_files("pypi", NAME, "0.1.0") is None
    assert len(requested) == smoke.INDEX_CHECKS


def test_index_files_fails_on_other_index_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        smoke.index_files("pypi", NAME, "0.1.0")


def planned_installs(monkeypatch: pytest.MonkeyPatch) -> list[list[tuple[str, str, list[str]]]]:
    """Record the installs each smoke test plans, instead of running them."""
    planned: list[list[tuple[str, str, list[str]]]] = []
    monkeypatch.setattr(smoke, "_smoke", lambda package_dir, installs: planned.append(installs) or [])
    return planned


def test_testpypi_installs_the_listed_files_by_url(built: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_index(monkeypatch, [[WHEEL, SDIST]])
    planned = planned_installs(monkeypatch)
    assert smoke.smoke_index(built, "testpypi", "0.1.0") == []
    assert planned == [[
        (f"{WHEEL[0]} from TestPyPI", f" @ {WHEEL[1]}", []),
        (f"{SDIST[0]} from TestPyPI", f" @ {SDIST[1]}", []),
    ]]


def test_pypi_installs_the_version_through_the_index(built: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_index(monkeypatch, [[WHEEL, SDIST]])
    planned = planned_installs(monkeypatch)
    assert smoke.smoke_index(built, "pypi", "0.1.0") == []
    assert planned == [[
        ("wheel from PyPI", "==0.1.0", ["--only-binary", NAME, "--refresh-package", NAME]),
        ("sdist from PyPI", "==0.1.0", ["--no-binary", NAME, "--refresh-package", NAME]),
    ]]


def test_unlisted_version_is_a_problem(built: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_index(monkeypatch, [None])
    planned = planned_installs(monkeypatch)
    assert smoke.smoke_index(built, "pypi", "0.1.0") == [f"pypi doesn't list both a wheel and an sdist for {NAME} 0.1.0"]
    assert planned == []


@pytest.mark.parametrize("args", [["--index", "pypi"], ["--version", "0.1.0"]])
def test_index_and_version_go_together(built: Path, args: list[str]) -> None:
    with pytest.raises(SystemExit):
        smoke.main(["--package-dir", str(built), *args])

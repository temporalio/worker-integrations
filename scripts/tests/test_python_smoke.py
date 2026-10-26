from __future__ import annotations

import re
import shutil
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

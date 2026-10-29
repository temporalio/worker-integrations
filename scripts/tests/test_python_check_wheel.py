from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from ci.python import check_wheel
from conftest import build_python_package

ROOT_API_PATH = "temporalio/worker_integrations/aws/lambda_worker"


def rewrite_wheel(built: Path, tmp_path: Path, changes: dict[str, str | None]) -> Path:
    """A copy of the built package whose wheel has each named file set to the text, or dropped if None."""
    d = Path(shutil.copytree(built, tmp_path / built.name))
    (wheel,) = (d / "dist").glob("*.whl")
    original = wheel.rename(wheel.with_suffix(".orig"))
    with zipfile.ZipFile(original) as src, zipfile.ZipFile(wheel, "w") as dst:
        for item in src.infolist():
            if item.filename not in changes:
                dst.writestr(item, src.read(item))
        for name, text in changes.items():
            if text is not None:
                dst.writestr(name, text)
    original.unlink()
    return d


def test_template_build_passes(built: Path) -> None:
    assert check_wheel.check(built, built / "dist") == []


def test_main_defaults_to_the_package_dist(built: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_wheel.main(["--package-dir", str(built)]) == 0
    assert "OK" in capsys.readouterr().out


def test_requires_exactly_one_wheel(built: Path, tmp_path: Path) -> None:
    problems = check_wheel.check(built, tmp_path)
    assert len(problems) == 1
    assert problems[0].startswith("expected exactly one wheel")


def test_requires_exactly_one_sdist(built: Path, tmp_path: Path) -> None:
    for wheel in (built / "dist").glob("*.whl"):
        shutil.copy(wheel, tmp_path)
    problems = check_wheel.check(built, tmp_path)
    assert len(problems) == 1
    assert problems[0].startswith("expected exactly one sdist")


@pytest.mark.parametrize("name", [
    "temporalio/__init__.py",
    "temporalio/worker_integrations/__init__.py",
    "temporalio/worker_integrations/aws/__init__.py",
    "temporalio/worker_integrations/aws/helper.py",
    "tests/__init__.py",
    "conftest.py",
])
def test_wheel_ships_only_the_root_api(built: Path, tmp_path: Path, name: str) -> None:
    d = rewrite_wheel(built, tmp_path, {name: ""})
    problems = check_wheel.check(d, d / "dist")
    assert len(problems) == 1
    assert problems[0].startswith(f"wheel must not ship {name}:")


@pytest.mark.parametrize("name", ["__init__.py", "py.typed"])
def test_wheel_ships_every_source_file(built: Path, tmp_path: Path, name: str) -> None:
    d = rewrite_wheel(built, tmp_path, {f"{ROOT_API_PATH}/{name}": None})
    assert check_wheel.check(d, d / "dist") == [f"wheel missing {ROOT_API_PATH}/{name}, which is in src/"]


def test_wheel_ships_nothing_beyond_the_source(built: Path, tmp_path: Path) -> None:
    d = rewrite_wheel(built, tmp_path, {f"{ROOT_API_PATH}/generated.py": ""})
    assert check_wheel.check(d, d / "dist") == [f"wheel ships {ROOT_API_PATH}/generated.py, which isn't in src/"]


def test_bytecode_caches_are_ignored(built: Path, tmp_path: Path) -> None:
    d = Path(shutil.copytree(built, tmp_path / built.name))
    cache = d / "src" / ROOT_API_PATH / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-314.pyc").write_bytes(b"")
    assert check_wheel.check(d, d / "dist") == []


def test_distributions_must_have_the_expected_version(built: Path) -> None:
    (wheel,) = (built / "dist").glob("*.whl")
    (sdist,) = (built / "dist").glob("*.tar.gz")
    assert check_wheel.check(built, built / "dist", "0.1.0") == [
        f"{wheel.name} has version '0.0.0', expected '0.1.0'",
        f"{sdist.name} has version '0.0.0', expected '0.1.0'",
    ]


def test_injected_release_version_passes(built: Path, tmp_path: Path) -> None:
    # The same command release builds use to set the version (--frozen here, since the test
    # package's uv.lock is a stand-in)
    d = Path(shutil.copytree(built, tmp_path / built.name))
    shutil.rmtree(d / "dist")
    subprocess.run(["uv", "version", "0.1.0rc1", "--frozen"], cwd=d, check=True, capture_output=True)
    build_python_package(d)
    assert check_wheel.check(d, d / "dist", "0.1.0rc1") == []

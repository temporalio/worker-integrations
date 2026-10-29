from __future__ import annotations

from pathlib import Path

import pytest

from ci import matrix
from conftest import make_python_package


def test_locked_runs_min_and_max_on_ubuntu_max_elsewhere() -> None:
    assert matrix.build_matrix(["3.10", "3.14"], {"locked"}) == {
        "include": [
            {"os": "ubuntu-latest", "runtime": "3.10", "deps": "locked", "build": False},
            {"os": "ubuntu-latest", "runtime": "3.14", "deps": "locked", "build": True},
            {"os": "macos-latest", "runtime": "3.14", "deps": "locked", "build": False},
            {"os": "windows-latest", "runtime": "3.14", "deps": "locked", "build": False},
        ]
    }


def test_lowest_is_one_ubuntu_min_cell_without_build() -> None:
    assert matrix.build_matrix(["3.10", "3.14"], {"lowest"}) == {
        "include": [{"os": "ubuntu-latest", "runtime": "3.10", "deps": "lowest", "build": False}]
    }


def test_modes_combine_in_a_fixed_order() -> None:
    cells = matrix.build_matrix(["3.10", "3.14"], {"latest", "lowest", "locked"})["include"]
    assert [c["deps"] for c in cells] == ["locked"] * 4 + ["lowest"] + ["latest"] * 4
    assert [c["deps"] for c in cells if c["build"]] == ["locked", "latest"]


def test_single_version_is_not_duplicated() -> None:
    cells = matrix.build_matrix(["3.12"], {"locked"})["include"]
    assert [(c["os"], c["runtime"]) for c in cells] == [
        ("ubuntu-latest", "3.12"),
        ("macos-latest", "3.12"),
        ("windows-latest", "3.12"),
    ]


def test_empty_versions_are_rejected() -> None:
    with pytest.raises(ValueError):
        matrix.build_matrix([], {"locked"})


def test_unknown_mode_is_rejected(repo: Path) -> None:
    d = make_python_package(repo)
    with pytest.raises(SystemExit):
        matrix.main(["--package-dir", str(d), "--deps", "newest"])


def test_repeated_modes_are_ignored(repo: Path) -> None:
    d = make_python_package(repo)
    assert matrix.main(["--package-dir", str(d), "--deps", "locked", "locked"]) == matrix.main(
        ["--package-dir", str(d), "--deps", "locked"]
    )


def test_reads_the_template_runtime_versions(repo: Path, tmp_path: Path) -> None:
    d = make_python_package(repo)
    out = tmp_path / "out.txt"
    result = matrix.main(["--package-dir", str(d), "--deps", "locked", "lowest", "--github-output", str(out)])
    assert [c["runtime"] for c in result["include"]] == ["3.10", "3.14", "3.14", "3.14", "3.10"]
    assert out.read_text().startswith('matrix={"include":[')

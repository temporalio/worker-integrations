from __future__ import annotations

from pathlib import Path

import pytest

from ci import matrix
from conftest import make_python_package


def test_min_and_max_on_ubuntu_max_elsewhere() -> None:
    assert matrix.build_matrix(["3.10", "3.14"]) == {
        "include": [
            {"os": "ubuntu-latest", "runtime": "3.10", "build": False},
            {"os": "ubuntu-latest", "runtime": "3.14", "build": True},
            {"os": "macos-latest", "runtime": "3.14", "build": False},
            {"os": "windows-latest", "runtime": "3.14", "build": False},
        ]
    }


def test_single_version_is_not_duplicated() -> None:
    cells = matrix.build_matrix(["3.12"])["include"]
    assert [(c["os"], c["runtime"]) for c in cells] == [
        ("ubuntu-latest", "3.12"),
        ("macos-latest", "3.12"),
        ("windows-latest", "3.12"),
    ]


def test_empty_versions_are_rejected() -> None:
    with pytest.raises(ValueError):
        matrix.build_matrix([])


def test_reads_the_template_runtime_versions(repo: Path, tmp_path: Path) -> None:
    d = make_python_package(repo)
    out = tmp_path / "out.txt"
    result = matrix.main(["--package-dir", str(d), "--github-output", str(out)])
    assert [c["runtime"] for c in result["include"]] == ["3.10", "3.14", "3.14", "3.14"]
    assert out.read_text().startswith('matrix={"include":[')

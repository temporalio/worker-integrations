from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ci.typescript import check_tarball
from conftest import copy_typescript_package

TARBALL = "temporalio-aws-lambda-worker-0.0.0.tgz"


def packaged_manifest(built: Path, **changes: object) -> bytes:
    """The built package's package.json with `changes` applied, as tarball bytes."""
    manifest = json.loads((built / "package.json").read_text())
    manifest.update(changes)
    return json.dumps(manifest).encode()


def test_template_build_passes(built_typescript: Path) -> None:
    assert check_tarball.check(built_typescript, built_typescript / "dist") == []


def test_main_defaults_to_the_package_dist(built_typescript: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_tarball.main(["--package-dir", str(built_typescript)]) == 0
    assert "OK" in capsys.readouterr().out


def test_requires_exactly_one_tarball(built_typescript: Path, tmp_path: Path) -> None:
    assert check_tarball.check(built_typescript, tmp_path) == [f"expected exactly one tarball in {tmp_path}, found []"]
    for name in ("a.tgz", "b.tgz"):
        shutil.copy(built_typescript / "dist" / TARBALL, tmp_path / name)
    assert check_tarball.check(built_typescript, tmp_path) == [
        f"expected exactly one tarball in {tmp_path}, found ['a.tgz', 'b.tgz']"
    ]


def test_version_must_be_the_expected_one(built_typescript: Path, tmp_path: Path) -> None:
    assert check_tarball.check(built_typescript, built_typescript / "dist", "1.2.3") == [
        f"{TARBALL} has version '0.0.0', expected '1.2.3'"
    ]
    d = copy_typescript_package(built_typescript, tmp_path, {"package.json": packaged_manifest(built_typescript, version="1.2.3")})
    assert check_tarball.main(["--package-dir", str(d), "--version", "1.2.3"]) == 0


def test_name_must_be_the_published_name(built_typescript: Path, tmp_path: Path) -> None:
    d = copy_typescript_package(built_typescript, tmp_path, {"package.json": packaged_manifest(built_typescript, name="@temporalio/x")})
    assert check_tarball.check(d, d / "dist") == [
        f"{TARBALL} has name '@temporalio/x', expected '@temporalio/aws-lambda-worker'"
    ]


def test_package_json_must_be_readable(built_typescript: Path, tmp_path: Path) -> None:
    d = copy_typescript_package(built_typescript, tmp_path, {"package.json": None})
    (problem,) = check_tarball.check(d, d / "dist")
    assert problem.startswith(f"{TARBALL} has no readable package.json")


@pytest.mark.parametrize("license_text", [None, b"Some other license\n"])
def test_license_must_be_shipped_unchanged(built_typescript: Path, tmp_path: Path, license_text: bytes | None) -> None:
    d = copy_typescript_package(built_typescript, tmp_path, {"LICENSE": license_text})
    assert check_tarball.check(d, d / "dist") == [f"{TARBALL} must ship the package's LICENSE unchanged"]


def test_tests_must_not_be_shipped(built_typescript: Path, tmp_path: Path) -> None:
    d = copy_typescript_package(built_typescript, tmp_path, {
        "lib/__tests__/index.test.js": b"",
        "src/__tests__/index.test.ts": b"",
    })
    assert check_tarball.check(d, d / "dist") == [
        f"{TARBALL} must not ship tests: lib/__tests__/index.test.js",
        f"{TARBALL} must not ship tests: src/__tests__/index.test.ts",
    ]


def test_entry_points_must_be_shipped(built_typescript: Path, tmp_path: Path) -> None:
    d = copy_typescript_package(built_typescript, tmp_path)
    manifest = json.loads((d / "package.json").read_text())
    manifest["exports"]["./otel"] = {"types": "./lib/otel.d.ts", "default": "./lib/otel.js"}
    manifest["exports"]["./blocked"] = None
    (d / "package.json").write_text(json.dumps(manifest))
    assert check_tarball.check(d, d / "dist") == [
        f"{TARBALL} is missing ./lib/otel.d.ts, an entry point in package.json",
        f"{TARBALL} is missing ./lib/otel.js, an entry point in package.json",
    ]


def test_every_source_must_be_compiled(built_typescript: Path, tmp_path: Path) -> None:
    d = copy_typescript_package(built_typescript, tmp_path)
    (d / "src" / "otel").mkdir()
    (d / "src" / "otel" / "index.ts").write_text("export {};\n")
    (d / "src" / "esm.mts").write_text("export {};\n")
    (d / "src" / "ambient.d.ts").write_text("export {};\n")  # declarations compile to nothing
    (d / "src" / "__tests__" / "otel.test.ts").write_text("export {};\n")
    assert check_tarball.check(d, d / "dist") == [
        f"{TARBALL} is missing lib/esm.d.mts, compiled from src/",
        f"{TARBALL} is missing lib/esm.mjs, compiled from src/",
        f"{TARBALL} is missing lib/otel/index.d.ts, compiled from src/",
        f"{TARBALL} is missing lib/otel/index.js, compiled from src/",
    ]


def test_compiled_output_without_a_source_is_a_problem(built_typescript: Path, tmp_path: Path) -> None:
    d = copy_typescript_package(built_typescript, tmp_path, {
        "lib/deleted.js": b"",
        "lib/deleted.d.ts": b"",
        "lib/deleted.js.map": b"",  # only JavaScript and declarations are checked
    })
    assert check_tarball.check(d, d / "dist") == [
        f"{TARBALL} ships lib/deleted.d.ts, which no file in src/ compiles to",
        f"{TARBALL} ships lib/deleted.js, which no file in src/ compiles to",
    ]

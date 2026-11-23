from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from ci.typescript import smoke
from conftest import copy_typescript_package

NAME = "@temporalio/aws-lambda-worker"
TARBALL = "temporalio-aws-lambda-worker-0.0.0.tgz"
# A small dependency-free package to stand in for a dependency
MS = ("ms", "^2.1.3")


def light_copy(built: Path, tmp_path: Path, lib: dict[str, str], edit: Any = None) -> Path:
    """A copy of the built package without its dependencies, so its installs need no SDK download.

    `lib` adds files under lib/ to the tarball, and `edit` changes the manifest in place, in both
    the package folder and the tarball.
    """
    manifest = json.loads((built / "package.json").read_text())
    for table in ("dependencies", "peerDependencies"):
        manifest.pop(table, None)
    if edit:
        edit(manifest)
    data = json.dumps(manifest, indent=2).encode()
    d = copy_typescript_package(built, tmp_path, {"package.json": data, **{f"lib/{k}": v.encode() for k, v in lib.items()}})
    (d / "package.json").write_bytes(data)
    return d


def add_exports(manifest: dict[str, Any], **subpaths: str) -> None:
    manifest["exports"].update({f"./{subpath}": f"./lib/{target}" for subpath, target in subpaths.items()})


def add_optional_peer(manifest: dict[str, Any], name: str, spec: str) -> None:
    manifest.setdefault("peerDependencies", {})[name] = spec
    manifest.setdefault("peerDependenciesMeta", {})[name] = {"optional": True}


def add_smoke_imports(d: Path, *imports: str) -> None:
    with (d / "integration.toml").open("a") as fh:
        fh.write(f"\n[smoke]\nimports = {json.dumps(list(imports))}\n")


def test_template_build_passes(built_typescript: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Unlike the other tests here, this one keeps the template's dependencies, so it downloads the
    # SDK from npm.
    assert smoke.main(["--package-dir", str(built_typescript)]) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    # The resolved versions are logged for each install.
    assert f"{NAME}@0.0.0" in out
    assert re.search(r"@temporalio/worker@\d", out)
    # The template declares protobufjs as a peer dependency and doesn't list it for the smoke test
    # to install, so finding it shows that npm installed the required peer on its own.
    assert re.search(r"protobufjs@\d", out)


def test_relative_package_dir(built_typescript: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # CI passes the package dir relative to the repository root, e.g. typescript/<package>.
    d = light_copy(built_typescript, tmp_path, {})
    monkeypatch.chdir(d.parent)
    assert smoke.main(["--package-dir", d.name]) == 0


def test_no_tarball(built_typescript: Path, tmp_path: Path) -> None:
    assert smoke.smoke(built_typescript, tmp_path) == [f"expected exactly one tarball in {tmp_path}, found []"]


def test_every_subpath_is_loaded_both_ways(built_typescript: Path, tmp_path: Path) -> None:
    d = light_copy(
        built_typescript, tmp_path, {"broken.js": "throw new Error('boom');\n"},
        lambda m: add_exports(m, broken="broken.js"),
    )
    assert smoke.smoke(d, d / "dist") == [
        f"{TARBALL} base: require(\"{NAME}/broken\") failed: Error: boom",
        f"{TARBALL} base: import(\"{NAME}/broken\") failed: Error: boom",
    ]


def test_require_and_import_resolve_exports_separately(built_typescript: Path, tmp_path: Path) -> None:
    d = light_copy(
        built_typescript, tmp_path, {},
        lambda m: m["exports"].update({".": {"import": "./lib/missing.mjs", "default": "./lib/index.js"}}),
    )
    (problem,) = smoke.smoke(d, d / "dist")
    assert problem.startswith(f"{TARBALL} base: import(\"{NAME}\") failed: Error [ERR_MODULE_NOT_FOUND]")


def test_undeclared_dependencies_are_missing(built_typescript: Path, tmp_path: Path) -> None:
    d = light_copy(built_typescript, tmp_path, {"index.js": "require('ms');\n"})
    problems = smoke.smoke(d, d / "dist")
    assert [p.split(" failed: ")[0] for p in problems] == [
        f"{TARBALL} base: require(\"{NAME}\")",
        f"{TARBALL} base: import(\"{NAME}\")",
    ]
    assert all("Cannot find module 'ms'" in p for p in problems)


def test_optional_peers_are_installed_for_the_full_load(built_typescript: Path, tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        add_optional_peer(m, *MS)
        add_exports(m, ms="ms.js")

    d = light_copy(built_typescript, tmp_path, {"ms.js": "require('ms');\n"}, edit)
    assert smoke.smoke(d, d / "dist") == []

    # Listed imports must work without optional peers.
    add_smoke_imports(d, f"{NAME}/ms")
    problems = smoke.smoke(d, d / "dist")
    assert [p.split(" failed: ")[0] for p in problems] == [
        f"{TARBALL} base: require(\"{NAME}/ms\")",
        f"{TARBALL} base: import(\"{NAME}/ms\")",
    ]


@pytest.fixture
def planned(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], list[str]]]:
    """Record each (installs, modules) that _check would run, instead of running it."""
    calls: list[tuple[list[str], list[str]]] = []
    monkeypatch.setattr(smoke, "_check", lambda installs, modules: calls.append((installs, modules)) or [])
    return calls


def test_without_optional_peers_the_base_install_loads_every_subpath(
    built_typescript: Path, tmp_path: Path, planned: list[tuple[list[str], list[str]]]
) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["peerDependencies"] = {"long": "^5.3.2"}  # a required peer: npm installs it on its own
        add_exports(m, otel="otel.js", workflow="workflow.js")
        m["exports"]["./internal"] = None  # hidden, so not loaded

    d = light_copy(built_typescript, tmp_path, {}, edit)
    add_smoke_imports(d, f"{NAME}/workflow")
    assert smoke._smoke(d, "label", "spec") == []
    assert planned == [(["spec"], [NAME, f"{NAME}/workflow", f"{NAME}/otel"])]


def test_with_optional_peers_only_the_full_install_loads_every_subpath(
    built_typescript: Path, tmp_path: Path, planned: list[tuple[list[str], list[str]]]
) -> None:
    def edit(m: dict[str, Any]) -> None:
        add_optional_peer(m, "zed", "^1.0.0")
        add_optional_peer(m, "@opentelemetry/api", "^1.9.0")
        m["peerDependenciesMeta"]["undeclared"] = {"optional": True}  # not a peer, so ignored
        add_exports(m, otel="otel.js")

    d = light_copy(built_typescript, tmp_path, {}, edit)
    assert smoke._smoke(d, "label", "spec") == []
    assert planned == [
        (["spec"], [NAME]),
        (["spec", "@opentelemetry/api@^1.9.0", "zed@^1.0.0"], [NAME, f"{NAME}/otel"]),
    ]

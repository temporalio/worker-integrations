from __future__ import annotations

import io
import json
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import new_package
from conftest import copy_language_support, make_typescript_package, replace_in_file, run_checker
from lib.languages.typescript import TypeScript
from lib.release_version import ReleaseVersion


def edit_package_json(d: Path, edit: Any) -> None:
    """Load the package's package.json, let `edit` change it in place, and write it back."""
    path = d / "package.json"
    manifest = json.loads(path.read_text())
    edit(manifest)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def add_smoke_imports(d: Path, *imports: str) -> None:
    with (d / "integration.toml").open("a") as fh:
        fh.write(f"\n[smoke]\nimports = {json.dumps(list(imports))}\n")


@pytest.mark.parametrize("maturity", ["pre-release", "public-preview", "generally-available"])
def test_typescript_package_rendered_from_template_passes(repo: Path, maturity: str) -> None:
    make_typescript_package(repo, maturity=maturity)
    assert run_checker(repo) == []


def test_typescript_folder_must_be_the_unscoped_published_name(repo: Path) -> None:
    d = make_typescript_package(repo)
    replace_in_file(d / "integration.toml", '"@temporalio/aws-lambda-worker"', '"@temporalio/lambda-worker"')
    assert run_checker(repo) == [
        "typescript/aws-lambda-worker: the folder for published-name '@temporalio/lambda-worker' "
        "must be typescript/lambda-worker"
    ]


@pytest.mark.parametrize("published_name", ["aws-lambda-worker", "@temporal/aws-lambda-worker", "@temporalio/AwsLambda"])
def test_typescript_published_name_must_be_a_valid_scoped_name(repo: Path, published_name: str) -> None:
    d = make_typescript_package(repo)
    replace_in_file(d / "integration.toml", 'published-name = "@temporalio/aws-lambda-worker"',
                    f'published-name = "{published_name}"')
    assert any(
        v.startswith("typescript/aws-lambda-worker/integration.toml: npm package name must be @temporalio/<name>")
        for v in run_checker(repo)
    )


def test_typescript_root_api_must_equal_published_name(repo: Path) -> None:
    d = make_typescript_package(repo)
    replace_in_file(d / "integration.toml", 'root-api = "@temporalio/aws-lambda-worker"', 'root-api = "lambda"')
    assert run_checker(repo) == [
        "typescript/aws-lambda-worker/integration.toml: root-api must equal published-name "
        "'@temporalio/aws-lambda-worker' (got 'lambda')"
    ]


@pytest.mark.parametrize("missing", ["pnpm-lock.yaml", "pnpm-workspace.yaml", "tsconfig.json", "Makefile", "README.md"])
def test_typescript_required_files_must_exist(repo: Path, missing: str) -> None:
    d = make_typescript_package(repo)
    (d / missing).unlink()
    assert f"typescript/aws-lambda-worker: missing {missing}" in run_checker(repo)


def test_typescript_makefile_must_be_the_stub(repo: Path) -> None:
    d = make_typescript_package(repo)
    with (d / "Makefile").open("a") as fh:
        fh.write("extra:\n\techo hi\n")
    assert run_checker(repo) == [
        "typescript/aws-lambda-worker/Makefile: must be exactly:\ninclude ../_shared/typescript.mk"
    ]


def test_typescript_smoke_imports_of_subpath_exports_pass(repo: Path) -> None:
    d = make_typescript_package(repo)
    add_smoke_imports(d, "@temporalio/aws-lambda-worker/otel")
    edit_package_json(d, lambda m: m["exports"].update({"./otel": {"default": "./lib/otel.js"}}))
    assert run_checker(repo) == []


@pytest.mark.parametrize("entry", [
    "@temporalio/aws-lambda-worker",
    "@temporalio/aws-lambda-workerotel",
    "@temporalio/worker",
])
def test_typescript_smoke_imports_must_be_subpaths_of_the_package(repo: Path, entry: str) -> None:
    d = make_typescript_package(repo)
    add_smoke_imports(d, entry)
    assert run_checker(repo) == [
        f"typescript/aws-lambda-worker/integration.toml: [smoke] imports entry {entry!r} must be a subpath of "
        "'@temporalio/aws-lambda-worker'"
    ]


def test_typescript_smoke_imports_must_be_exported(repo: Path) -> None:
    d = make_typescript_package(repo)
    add_smoke_imports(d, "@temporalio/aws-lambda-worker/otel")
    assert run_checker(repo) == [
        "typescript/aws-lambda-worker/package.json: exports must have a './otel' entry for [smoke] imports "
        "entry '@temporalio/aws-lambda-worker/otel'"
    ]


def test_typescript_package_json_must_parse(repo: Path) -> None:
    d = make_typescript_package(repo)
    (d / "package.json").write_text("{")
    assert [v.split(":")[0:2] for v in run_checker(repo)] == [["typescript/aws-lambda-worker/package.json", " cannot parse"]]


@pytest.mark.parametrize("key,value,message", [
    ("name", "@temporalio/x", "name must be '@temporalio/aws-lambda-worker' (got '@temporalio/x')"),
    ("version", "1.0.0", "version must be the development placeholder '0.0.0'; release tags supply the published "
                         "version (got '1.0.0')"),
    ("license", "Apache-2.0", 'license must be "MIT"'),
    ("files", ["lib"], 'files must include "LICENSE"'),
    ("repository", "github:temporalio/worker-integrations",
     'repository must be {"type": "git", "url": "git+https://github.com/temporalio/worker-integrations.git", '
     '"directory": "typescript/aws-lambda-worker"}'),
    ("packageManager", "pnpm@10.27.0", "packageManager must be typescript/_template's 'pnpm@12.18.0'"),
    ("exports", "./lib/index.js", 'exports must be an object with a "." entry'),
])
def test_typescript_package_json_policy(repo: Path, key: str, value: object, message: str) -> None:
    d = make_typescript_package(repo)
    edit_package_json(d, lambda m: m.update({key: value}))
    assert run_checker(repo) == [f"typescript/aws-lambda-worker/package.json: {message}"]


def test_typescript_engines_node_must_match_the_minimum_runtime_version(repo: Path) -> None:
    d = make_typescript_package(repo)
    edit_package_json(d, lambda m: m.update({"engines": {"node": ">= 22.12.0"}}))
    assert run_checker(repo) == [
        "typescript/aws-lambda-worker: package.json's engines.node must be '>=22.12.0', matching the first "
        "[ci] runtime-versions entry (got '>= 22.12.0')"
    ]


@pytest.mark.parametrize("spec", ["workspace:*", "file:../../../sdk-typescript/packages/worker", "link:../x"])
@pytest.mark.parametrize("table", ["dependencies", "devDependencies"])
def test_typescript_local_dependencies_are_rejected(repo: Path, table: str, spec: str) -> None:
    d = make_typescript_package(repo)
    edit_package_json(d, lambda m: m.setdefault(table, {}).update({"@temporalio/worker": spec}))
    assert run_checker(repo) == [
        f"typescript/aws-lambda-worker/package.json: {table} @temporalio/worker uses a local {spec.split(':')[0]}: "
        "spec; depend on published versions"
    ]


@pytest.mark.parametrize("spec", ["1.24.0", ">=1.24.0", "~1.24.0", "^1.24", "*"])
@pytest.mark.parametrize("table", ["dependencies", "peerDependencies"])
def test_typescript_sdk_dependencies_must_be_caret_ranges(repo: Path, table: str, spec: str) -> None:
    d = make_typescript_package(repo)
    edit_package_json(d, lambda m: m.setdefault(table, {}).update({"@temporalio/worker": spec}))
    assert run_checker(repo) == [
        f"typescript/aws-lambda-worker/package.json: {table} @temporalio/worker must be a caret range on its "
        f"minimum supported version, e.g. ^1.24.0 (got {spec!r})"
    ]


def test_typescript_other_dependency_ranges_are_free(repo: Path) -> None:
    d = make_typescript_package(repo)

    def edit(m: dict[str, Any]) -> None:
        m["dependencies"] = {"@temporalio/worker": "^1.24.0", "@aws-lambda-powertools/logger": ">=2.0.0 <3"}
        m["devDependencies"]["@temporalio/testing"] = "1.26.0"

    edit_package_json(d, edit)
    assert run_checker(repo) == []


def test_typescript_new_package_creates_a_package_that_passes_conventions(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    copy_language_support(repo, "typescript")
    args = [
        "--typescript", "@temporalio/aws-lambda-worker",
        "--description", "Temporal worker integration for AWS Lambda", "--repo-root", str(repo),
    ]
    assert new_package.main(args) == 0

    d = repo / "typescript" / "aws-lambda-worker"
    meta = tomllib.loads((d / "integration.toml").read_text())["package"]
    assert meta["published-name"] == meta["root-api"] == "@temporalio/aws-lambda-worker"
    manifest = json.loads((d / "package.json").read_text())
    assert manifest["name"] == "@temporalio/aws-lambda-worker"
    assert manifest["repository"]["directory"] == "typescript/aws-lambda-worker"
    assert (d / "Makefile").read_text() == "include ../_shared/typescript.mk\n"
    assert not list(d.rglob("*.tmpl"))
    for path in d.rglob("*"):
        if path.is_file():
            assert "__" not in path.read_text().replace("__tests__", ""), path
    assert "https://www.npmjs.com/package/@temporalio/aws-lambda-worker" in capsys.readouterr().out

    (d / "pnpm-lock.yaml").write_text("")  # what `pnpm install` creates
    assert run_checker(repo) == []


@pytest.mark.parametrize("name", [
    "aws-lambda-worker",
    "@temporal/aws-lambda-worker",
    "@temporalio/",
    "@temporalio/Aws-lambda",
    "@temporalio/aws_lambda",
    "@temporalio/aws--lambda",
    "@temporalio/aws-lambda-",
    "@temporalio/1aws",
    "@temporalio/_aws",
    "@temporalio/aws/lambda",
])
def test_typescript_new_package_rejects_invalid_names(repo: Path, name: str) -> None:
    copy_language_support(repo, "typescript")
    with pytest.raises(ValueError, match="npm package name must be @temporalio/<name>"):
        new_package.scaffold(repo, {"typescript": name}, "x", "pre-release")
    assert new_package.main(["--typescript", name, "--description", "x", "--repo-root", str(repo)]) == 1
    assert sorted(p.name for p in (repo / "typescript").iterdir()) == ["_shared", "_template"]


def test_typescript_new_package_has_no_published_name_override(repo: Path) -> None:
    copy_language_support(repo, "typescript")
    with pytest.raises(ValueError, match="typescript published names can't be overridden"):
        new_package.scaffold(repo, {"typescript": "@temporalio/x"}, "x", "pre-release", {"typescript": "@temporalio/y"})
    with pytest.raises(SystemExit):
        new_package.main([
            "--typescript", "@temporalio/x", "--typescript-published-name", "@temporalio/y",
            "--description", "x", "--repo-root", str(repo),
        ])


@pytest.mark.parametrize("text,expected", [
    ("0.0.1", ReleaseVersion((0, 0, 1))),
    ("1.27.0", ReleaseVersion((1, 27, 0))),
    ("2.0.0", ReleaseVersion((2, 0, 0))),
    ("1.0.0-alpha.1", ReleaseVersion((1, 0, 0), ("alpha", 1))),
    ("1.0.0-beta.2", ReleaseVersion((1, 0, 0), ("beta", 2))),
    ("2.0.0-rc.0", ReleaseVersion((2, 0, 0), ("rc", 0))),
])
def test_typescript_release_version_parses(text: str, expected: ReleaseVersion) -> None:
    version = TypeScript().release_version(text)
    assert version == expected
    assert str(version) == text


@pytest.mark.parametrize("text", [
    "1.0", "01.0.0", "v1.0.0",  # not X.Y.Z
    "1.0.0rc1", "1.0.0-rc1", "1.0.0-next.1", "1.14.2-canary-release-testing.0",  # unsupported pre-releases
    "1.0.0+build.1",  # build metadata
])
def test_typescript_release_version_rejects_unsupported_versions(text: str) -> None:
    with pytest.raises(ValueError, match="isn't a supported TypeScript version: use X.Y.Z"):
        TypeScript().release_version(text)


def serve_packument(monkeypatch: pytest.MonkeyPatch, packument: dict[str, Any]) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        assert url == "https://registry.npmjs.org/@temporalio%2flambda-worker"
        return io.BytesIO(json.dumps(packument).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_typescript_published_versions_include_unpublished_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_packument(monkeypatch, {
        "versions": {"1.0.0": {}, "1.1.0-rc.1": {}},
        "time": {"created": "t", "modified": "t", "1.0.0": "t", "1.0.1": "t", "1.1.0-rc.1": "t"},
    })
    assert TypeScript().published_versions("@temporalio/lambda-worker") == ["1.0.0", "1.0.1", "1.1.0-rc.1"]


def test_typescript_published_versions_of_an_unpublished_package(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_packument(monkeypatch, {
        "time": {"created": "t", "modified": "t", "unpublished": {"time": "t", "versions": ["0.1.0", "0.2.0"]}},
    })
    assert TypeScript().published_versions("@temporalio/lambda-worker") == ["0.1.0", "0.2.0"]


def test_typescript_published_versions_is_empty_for_an_unknown_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert TypeScript().published_versions("@temporalio/lambda-worker") == []


def test_typescript_published_versions_fails_on_other_registry_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        TypeScript().published_versions("@temporalio/lambda-worker")


def test_typescript_cooldown_must_exempt_the_sdk(repo: Path) -> None:
    d = make_typescript_package(repo)
    replace_in_file(d / "pnpm-workspace.yaml", "  - '@temporalio/*'\n", "  - nexus-rpc\n")
    assert run_checker(repo) == [
        "typescript/aws-lambda-worker/pnpm-workspace.yaml: minimumReleaseAge is set but @temporalio/ packages "
        "are not exempted (add '@temporalio/*' to minimumReleaseAgeExclude)"
    ]


def test_typescript_without_a_cooldown_passes(repo: Path) -> None:
    d = make_typescript_package(repo)
    (d / "pnpm-workspace.yaml").write_text("allowBuilds:\n  protobufjs: false\n")
    assert run_checker(repo) == []


@pytest.mark.parametrize("text,message", [
    ("minimumReleaseAge: [\n", "cannot parse"),
    ("- a\n", "must be a mapping of pnpm settings"),
])
def test_typescript_pnpm_workspace_must_be_a_settings_mapping(repo: Path, text: str, message: str) -> None:
    d = make_typescript_package(repo)
    (d / "pnpm-workspace.yaml").write_text(text)
    assert [v.split(": ", 1)[1].split(":")[0] for v in run_checker(repo)] == [message]

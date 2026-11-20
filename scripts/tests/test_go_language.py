from __future__ import annotations

import io
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import new_package
from conftest import copy_language_support, make_go_package, replace_in_file, run_checker
from lib.languages.go import Go
from lib.release_version import ReleaseVersion


@pytest.mark.parametrize("maturity", ["pre-release", "public-preview", "generally-available"])
def test_go_module_rendered_from_template_passes(repo: Path, maturity: str) -> None:
    make_go_package(repo, maturity=maturity)
    assert run_checker(repo) == []


def test_go_nested_and_single_element_modules_pass(repo: Path) -> None:
    make_go_package(repo)
    make_go_package(repo, "go.temporal.io/worker-integrations/aws/lambda/otel")
    make_go_package(repo, "go.temporal.io/worker-integrations/otlp")
    assert run_checker(repo) == []


def test_go_nested_module_makefile_reaches_shared(repo: Path) -> None:
    d = make_go_package(repo, "go.temporal.io/worker-integrations/aws/lambda/otel")
    assert (d / "Makefile").read_text() == "include ../../../_shared/go.mk\n"
    assert (d / "../../../_shared/go.mk").resolve().is_file()


def test_go_folder_must_mirror_published_name(repo: Path) -> None:
    d = make_go_package(repo)
    for file in ("integration.toml", "go.mod"):
        replace_in_file(d / file, "worker-integrations/aws/lambda", "worker-integrations/aws/lambdaworker")
    assert run_checker(repo) == [
        "go/aws/lambda: the folder for published-name 'go.temporal.io/worker-integrations/aws/lambdaworker' "
        "must be go/aws/lambdaworker"
    ]


@pytest.mark.parametrize("published_name,message", [
    ("go.temporal.io/sdk/contrib/aws/lambdaworker", "must be under go.temporal.io/worker-integrations"),
    ("go.temporal.io/worker-integrations/aws/Lambda", "must have path elements of lowercase letters and digits"),
    ("go.temporal.io/worker-integrations/aws/lambda/v2", "must not have a 'v2' path element"),
])
def test_go_published_name_must_be_a_valid_module_path(repo: Path, published_name: str, message: str) -> None:
    d = make_go_package(repo)
    replace_in_file(d / "integration.toml", 'published-name = "go.temporal.io/worker-integrations/aws/lambda"',
                    f'published-name = "{published_name}"')
    assert any(f"go/aws/lambda/integration.toml: Go module path {message}" in v for v in run_checker(repo))


def test_go_root_api_must_equal_published_name(repo: Path) -> None:
    d = make_go_package(repo)
    replace_in_file(d / "integration.toml", 'root-api = "go.temporal.io/worker-integrations/aws/lambda"', 'root-api = "lambda"')
    assert run_checker(repo) == [
        "go/aws/lambda/integration.toml: root-api must equal published-name "
        "'go.temporal.io/worker-integrations/aws/lambda' (got 'lambda')"
    ]


@pytest.mark.parametrize("missing", ["go.sum", "Makefile", "README.md"])
def test_go_required_files_must_exist(repo: Path, missing: str) -> None:
    d = make_go_package(repo)
    (d / missing).unlink()
    assert f"go/aws/lambda: missing {missing}" in run_checker(repo)


def test_go_makefile_must_be_the_stub(repo: Path) -> None:
    d = make_go_package(repo)
    with (d / "Makefile").open("a") as fh:
        fh.write("extra:\n\techo hi\n")
    assert any("go/aws/lambda/Makefile: must be exactly:\ninclude ../../_shared/go.mk" in v for v in run_checker(repo))


def test_go_mod_module_must_be_the_published_name(repo: Path) -> None:
    d = make_go_package(repo)
    replace_in_file(d / "go.mod", "module go.temporal.io/worker-integrations/aws/lambda", "module go.temporal.io/x")
    assert run_checker(repo) == [
        "go/aws/lambda/go.mod: module must be 'go.temporal.io/worker-integrations/aws/lambda' (got 'go.temporal.io/x')"
    ]


def test_go_directive_must_equal_the_minimum_runtime_version(repo: Path) -> None:
    d = make_go_package(repo)
    replace_in_file(d / "go.mod", "go 1.26.0", "go 1.26.6 // a comment")
    assert run_checker(repo) == [
        "go/aws/lambda: the first [ci] runtime-versions entry '1.26.0' must equal go.mod's go directive '1.26.6'"
    ]


def test_go_directive_is_required(repo: Path) -> None:
    d = make_go_package(repo)
    replace_in_file(d / "go.mod", "go 1.26.0", "")
    assert run_checker(repo) == ["go/aws/lambda/go.mod: must have a go directive"]


@pytest.mark.parametrize("package", [
    "go.temporal.io/worker-integrations/aws/lambda/client",
    "go.temporal.io/worker-integrations/aws/lambda/client/testing",
])
def test_go_smoke_imports_package_in_module_passes(repo: Path, package: str) -> None:
    d = make_go_package(repo)
    with (d / "integration.toml").open("a") as fh:
        fh.write(f'\n[smoke]\nimports = ["{package}"]\n')
    assert run_checker(repo) == []


@pytest.mark.parametrize("package", [
    "go.temporal.io/worker-integrations/aws/lambda",
    "go.temporal.io/worker-integrations/aws/lambdaclient",
    "go.temporal.io/sdk/client",
])
def test_go_smoke_imports_must_be_packages_in_module(repo: Path, package: str) -> None:
    d = make_go_package(repo)
    with (d / "integration.toml").open("a") as fh:
        fh.write(f'\n[smoke]\nimports = ["{package}"]\n')
    assert run_checker(repo) == [
        f"go/aws/lambda/integration.toml: [smoke] imports entry {package!r} must be a package in "
        "'go.temporal.io/worker-integrations/aws/lambda'"
    ]


@pytest.mark.parametrize("replace", [
    "replace go.temporal.io/sdk => ../../../sdk-go\n",
    "replace (\n\tgo.temporal.io/sdk => ../../../sdk-go\n)\n",
])
def test_go_replace_directives_are_rejected(repo: Path, replace: str) -> None:
    d = make_go_package(repo)
    with (d / "go.mod").open("a") as fh:
        fh.write(f"\n{replace}")
    assert run_checker(repo) == ["go/aws/lambda/go.mod: replace directives aren't allowed; depend on published versions"]


def test_go_commented_out_replace_directive_passes(repo: Path) -> None:
    d = make_go_package(repo)
    with (d / "go.mod").open("a") as fh:
        fh.write("\n// replace go.temporal.io/sdk => ../../../sdk-go\n")
    assert run_checker(repo) == []


def test_go_new_package_creates_a_module_that_passes_conventions(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    copy_language_support(repo, "go")
    args = [
        "--go", "go.temporal.io/worker-integrations/aws/lambda",
        "--description", "Temporal worker integration for AWS Lambda", "--repo-root", str(repo),
    ]
    assert new_package.main(args) == 0

    d = repo / "go" / "aws" / "lambda"
    meta = tomllib.loads((d / "integration.toml").read_text())["package"]
    assert meta["published-name"] == "go.temporal.io/worker-integrations/aws/lambda"
    assert meta["root-api"] == "go.temporal.io/worker-integrations/aws/lambda"
    assert (d / "go.mod").read_text().startswith("module go.temporal.io/worker-integrations/aws/lambda\n")
    assert (d / "doc.go").read_text() == (
        "// Package lambda: Temporal worker integration for AWS Lambda.\npackage lambda\n"
    )
    assert (d / "Makefile").read_text() == "include ../../_shared/go.mk\n"
    assert not list(d.rglob("*.tmpl"))
    for path in d.rglob("*"):
        assert "__" not in path.read_text(), path
    assert "go.temporal.io/worker-integrations/aws/lambda git https://github.com/temporalio/worker-integrations go/aws/lambda" in (
        capsys.readouterr().out
    )

    (d / "go.sum").write_text("")  # what `go mod tidy` would create once the module has dependencies
    assert run_checker(repo) == []


@pytest.mark.parametrize("module_path", [
    "go.temporal.io/worker-integrations",
    "go.temporal.io/worker-integrations/",
    "go.temporal.io/sdk/contrib/aws/lambdaworker",
    "go.temporal.io/worker-integrations/aws/Lambda",
    "go.temporal.io/worker-integrations/gcp/cloud-run",
    "go.temporal.io/worker-integrations/gcp/cloud_run",
    "go.temporal.io/worker-integrations/aws//lambda",
    "go.temporal.io/worker-integrations/aws/lambda/",
    "go.temporal.io/worker-integrations/1aws",
    "go.temporal.io/worker-integrations/aws/lambda/v2",
    "go.temporal.io/worker-integrations/otlp/testdata",
])
def test_go_new_package_rejects_invalid_module_paths(repo: Path, module_path: str) -> None:
    copy_language_support(repo, "go")
    with pytest.raises(ValueError, match="Go module path must"):
        new_package.scaffold(repo, {"go": module_path}, "x", "pre-release")
    assert new_package.main(["--go", module_path, "--description", "x", "--repo-root", str(repo)]) == 1
    assert sorted(p.name for p in (repo / "go").iterdir()) == ["_shared", "_template"]


def test_go_new_package_has_no_published_name_override(repo: Path) -> None:
    copy_language_support(repo, "go")
    module_path = "go.temporal.io/worker-integrations/aws/lambda"
    with pytest.raises(ValueError, match="go published names can't be overridden"):
        new_package.scaffold(repo, {"go": module_path}, "x", "pre-release", {"go": "go.temporal.io/worker-integrations/x"})
    with pytest.raises(SystemExit):
        new_package.main(["--go", module_path, "--go-published-name", "x", "--description", "x", "--repo-root", str(repo)])


@pytest.mark.parametrize("text,expected", [
    ("0.0.1", ReleaseVersion((0, 0, 1))),
    ("1.20.30", ReleaseVersion((1, 20, 30))),
    ("1.0.0-alpha.1", ReleaseVersion((1, 0, 0), ("alpha", 1))),
    ("1.0.0-beta.2", ReleaseVersion((1, 0, 0), ("beta", 2))),
    ("1.0.0-rc.0", ReleaseVersion((1, 0, 0), ("rc", 0))),
    ("1.0.0-rc.10", ReleaseVersion((1, 0, 0), ("rc", 10))),
])
def test_go_release_version_parses(text: str, expected: ReleaseVersion) -> None:
    version = Go().release_version(text)
    assert version == expected
    assert str(version) == text


@pytest.mark.parametrize("text", [
    "1.0", "1.0.0.0", "01.0.0", "v1.0.0",  # not X.Y.Z
    "1.0.0rc1", "1.0.0-rc1", "1.0.0-RC.1", "1.0.0-rc.01", "1.0.0-rc", "1.0.0-preview.1",  # unsupported pre-releases
    "1.0.0+build.1", "1.0.0-rc.1+build.1",  # build metadata
])
def test_go_release_version_rejects_unsupported_versions(text: str) -> None:
    with pytest.raises(ValueError, match="isn't a supported Go version: use X.Y.Z"):
        Go().release_version(text)


@pytest.mark.parametrize("text", ["2.0.0", "2.0.0-rc.1", "10.0.0"])
def test_go_release_version_rejects_major_versions_needing_a_module_path_suffix(text: str) -> None:
    with pytest.raises(ValueError, match="major versions 2 and up need a /v"):
        Go().release_version(text)


def test_go_release_versions_order_pre_releases_before_their_release() -> None:
    ordered = ["0.9.0", "1.0.0-alpha.1", "1.0.0-alpha.2", "1.0.0-beta.1", "1.0.0-rc.1", "1.0.0-rc.10", "1.0.0", "1.0.1"]
    versions = sorted(Go().release_version(text) for text in reversed(ordered))
    assert [str(v) for v in versions] == ordered


def test_go_published_versions_reads_the_module_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        assert url == "https://proxy.golang.org/go.temporal.io/worker-integrations/aws/lambda/@v/list"
        return io.BytesIO(b"v0.1.0\nv0.2.0-rc.1\n")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert Go().published_versions("go.temporal.io/worker-integrations/aws/lambda") == ["0.1.0", "0.2.0-rc.1"]


@pytest.mark.parametrize("code", [404, 410])
def test_go_published_versions_is_empty_for_an_unknown_module(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, code, "Not Found", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert Go().published_versions("go.temporal.io/worker-integrations/aws/lambda") == []


def test_go_published_versions_is_empty_for_a_module_without_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: io.BytesIO(b""))
    assert Go().published_versions("go.temporal.io/worker-integrations/aws/lambda") == []


def test_go_published_versions_fails_on_other_proxy_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        Go().published_versions("go.temporal.io/worker-integrations/aws/lambda")

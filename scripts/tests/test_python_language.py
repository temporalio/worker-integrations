from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import make_python_package, replace_in_file, run_checker
from lib.languages.python import Python
from lib.release_version import ReleaseVersion


@pytest.mark.parametrize("maturity", ["pre-release", "public-preview", "generally-available"])
def test_python_package_rendered_from_template_passes(repo: Path, maturity: str) -> None:
    make_python_package(repo, maturity=maturity)
    assert run_checker(repo) == []


def test_python_package_without_vendor_level_passes(repo: Path) -> None:
    make_python_package(repo, "temporalio.worker_integrations.otlp")
    assert run_checker(repo) == []


@pytest.mark.parametrize("level", ["temporalio", "temporalio/worker_integrations", "temporalio/worker_integrations/aws"])
def test_python_namespace_levels_must_not_have_init(repo: Path, level: str) -> None:
    d = make_python_package(repo)
    (d / "src" / level / "__init__.py").write_text("")
    assert any(f"src/{level}/__init__.py must not exist" in v for v in run_checker(repo))


@pytest.mark.parametrize("old,new,message", [
    ("temporalio.worker_integrations.aws.lambda_worker", "temporalio.aws_lambda_worker",
     "root-api must be a snake_case module under temporalio.worker_integrations"),
    ("temporalio.worker_integrations.aws.lambda_worker", "temporalio.worker_integrations.aws.lambda",
     "the folder for root-api 'temporalio.worker_integrations.aws.lambda' must be python/aws_lambda"),
    ('"temporalio-worker-integrations-aws-lambda-worker"', '"temporalio-aws-lambda-worker"',
     "published-name must be 'temporalio-worker-integrations-aws-lambda-worker'"),
])
def test_python_names_must_derive_from_root_api(repo: Path, old: str, new: str, message: str) -> None:
    d = make_python_package(repo)
    replace_in_file(d / "integration.toml", old, new)
    assert any(message in v for v in run_checker(repo))


@pytest.mark.parametrize("module", [
    "temporalio.worker_integrations.aws.lambda_worker.testing",
    "temporalio.worker_integrations.aws.lambda_worker._plugin",
    "temporalio.worker_integrations.aws.lambda_worker.otel._setup",
])
def test_python_smoke_imports_submodule_passes(repo: Path, module: str) -> None:
    d = make_python_package(repo)
    with (d / "integration.toml").open("a") as fh:
        fh.write(f'\n[smoke]\nimports = ["{module}"]\n')
    assert run_checker(repo) == []


@pytest.mark.parametrize("module", [
    "temporalio.worker_integrations.aws.lambda_worker",
    "temporalio.worker_integrations.aws.lambda_worker.",
    "temporalio.worker_integrations.aws.lambda_worker_testing",
    "temporalio.worker_integrations.aws.lambda_worker.Testing",
    "temporalio.worker_integrations.aws.lambda_worker.1x",
    "temporalio.contrib.aws.lambda_worker",
])
def test_python_smoke_imports_must_be_submodules(repo: Path, module: str) -> None:
    d = make_python_package(repo)
    with (d / "integration.toml").open("a") as fh:
        fh.write(f'\n[smoke]\nimports = ["{module}"]\n')
    assert any(f"[smoke] imports entry {module!r} must be a submodule" in v for v in run_checker(repo))


def test_pyproject_must_agree_with_integration_toml(repo: Path) -> None:
    d = make_python_package(repo, maturity="public-preview")
    replace_in_file(d / "pyproject.toml", "Development Status :: 4 - Beta", "Development Status :: 3 - Alpha")
    replace_in_file(d / "pyproject.toml", 'requires-python = ">=3.10"', 'requires-python = ">=3.11"')
    replace_in_file(d / "pyproject.toml", 'version = "0.0.0"', 'version = "0.1.0"')
    violations = run_checker(repo)
    assert any("classifiers must contain exactly" in v for v in violations)
    assert any("must equal the requires-python floor" in v for v in violations)
    assert any("development placeholder" in v for v in violations)


def test_python_path_sources_are_rejected(repo: Path) -> None:
    d = make_python_package(repo)
    with (d / "pyproject.toml").open("a") as fh:
        fh.write('\n[tool.uv.sources]\ntemporalio = { path = "../../../sdk-python" }\n')
    assert any("path/workspace source" in v for v in run_checker(repo))


def test_python_standard_test_support_must_match_template(repo: Path) -> None:
    d = make_python_package(repo)
    with (d / "tests" / "helpers" / "provenance.py").open("a") as fh:
        fh.write("# local edit\n")
    assert any("tests/helpers/provenance.py: differs from python/_template" in v for v in run_checker(repo))


def test_python_readme_relative_links_are_rejected(repo: Path) -> None:
    d = make_python_package(repo)
    with (d / "README.md").open("a") as fh:
        fh.write("See [the guide](../../AGENTS.md).\n")
    assert any("relative link" in v for v in run_checker(repo))


def test_python_source_in_shared_is_rejected(repo: Path) -> None:
    make_python_package(repo)
    (repo / "python" / "_shared" / "helpers.py").write_text("x = 1\n")
    assert any("must be duplicated into each package" in v for v in run_checker(repo))


@pytest.mark.parametrize("text,expected", [
    ("0.0.1", ReleaseVersion((0, 0, 1))),
    ("10.20.30", ReleaseVersion((10, 20, 30))),
    ("1.0.0a1", ReleaseVersion((1, 0, 0), ("alpha", 1))),
    ("1.0.0b2", ReleaseVersion((1, 0, 0), ("beta", 2))),
    ("1.0.0rc0", ReleaseVersion((1, 0, 0), ("rc", 0))),
    ("1.0.0rc10", ReleaseVersion((1, 0, 0), ("rc", 10))),
])
def test_python_release_version_parses(text: str, expected: ReleaseVersion) -> None:
    version = Python().release_version(text)
    assert version == expected
    assert str(version) == text


@pytest.mark.parametrize("text", [
    "1.0", "1.0.0.0", "01.0.0", "v1.0.0",  # not X.Y.Z
    "1.0.0-rc1", "1.0.0.rc1", "1.0.0RC1", "1.0.0c1", "1.0.0rc01", "1.0.0rc",  # non-canonical pre-releases
    "1.0.0.post1", "1.0.0.dev1", "1.0.0+local", "1!1.0.0",  # unsupported PEP 440 features
])
def test_python_release_version_rejects_unsupported_versions(text: str) -> None:
    with pytest.raises(ValueError, match="isn't a supported Python version"):
        Python().release_version(text)


def test_python_release_versions_order_pre_releases_before_their_release() -> None:
    ordered = ["0.9.0", "1.0.0a1", "1.0.0a2", "1.0.0b1", "1.0.0rc1", "1.0.0rc10", "1.0.0", "1.0.1rc1", "1.0.1"]
    versions = sorted(Python().release_version(text) for text in reversed(ordered))
    assert [str(v) for v in versions] == ordered
    assert [str(v) for v in versions if v.is_prerelease] == ["1.0.0a1", "1.0.0a2", "1.0.0b1", "1.0.0rc1", "1.0.0rc10", "1.0.1rc1"]


def test_python_published_versions_reads_pypi(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        assert url == "https://pypi.org/pypi/temporalio-worker-integrations-x/json"
        return io.BytesIO(json.dumps({"releases": {"0.1.0": [], "0.1.1": []}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert Python().published_versions("temporalio-worker-integrations-x") == ["0.1.0", "0.1.1"]


def test_python_published_versions_is_empty_for_an_unpublished_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert Python().published_versions("temporalio-worker-integrations-x") == []


def test_python_published_versions_fails_on_other_registry_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(url: str, timeout: float) -> io.BytesIO:
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        Python().published_versions("temporalio-worker-integrations-x")

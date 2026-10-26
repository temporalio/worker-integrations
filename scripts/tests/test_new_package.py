from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import new_package
from ci import check_conventions
from conftest import copy_python_support


@pytest.mark.parametrize("maturity", ["pre-release", "public-preview", "generally-available"])
def test_cli_creates_a_python_package_that_passes_conventions(repo: Path, maturity: str) -> None:
    copy_python_support(repo)
    args = [
        "--python", "temporalio.worker_integrations.aws.lambda_worker",
        "--description", "Lambda worker", "--maturity", maturity, "--repo-root", str(repo),
    ]
    assert new_package.main(args) == 0

    d = repo / "python" / "aws_lambda_worker"
    meta = tomllib.loads((d / "integration.toml").read_text())["package"]
    assert meta["published-name"] == "temporalio-worker-integrations-aws-lambda-worker"
    assert meta["root-api"] == "temporalio.worker_integrations.aws.lambda_worker"
    assert meta["maturity"] == maturity
    assert (d / "src/temporalio/worker_integrations/aws/lambda_worker/__init__.py").is_file()
    assert not list(d.rglob("*.tmpl"))
    for path in d.rglob("*"):
        assert "__" not in path.relative_to(d).as_posix().replace("__init__", ""), path
        if path.is_file():
            assert not any(p in path.read_text() for p in ("__NAME__", "__MODULE__", "__PUBLISHED_NAME__")), path

    (d / "uv.lock").write_text("version = 1\n")  # what `make sync` would create
    assert check_conventions.Checker(repo).run() == []


@pytest.mark.parametrize("root_api", [
    "aws_lambda_worker",
    "temporalio.aws_lambda_worker",
    "temporalio.worker_integrations",
    "temporalio.worker_integrations.",
    "temporalio.worker_integrations.AWS.lambda",
    "temporalio.worker_integrations.aws-lambda",
    "temporalio.worker_integrations.aws..lambda",
    "temporalio.worker_integrations.1aws",
])
def test_invalid_python_root_apis_are_rejected(repo: Path, root_api: str) -> None:
    copy_python_support(repo)
    with pytest.raises(ValueError, match="module under temporalio.worker_integrations"):
        new_package.scaffold(repo, {"python": root_api}, "x", "pre-release")
    assert new_package.main(["--python", root_api, "--description", "x", "--repo-root", str(repo)]) == 1
    assert sorted(p.name for p in (repo / "python").iterdir()) == ["_shared", "_template"]


def test_existing_package_is_not_overwritten(repo: Path) -> None:
    copy_python_support(repo)
    root_api = "temporalio.worker_integrations.aws.lambda_worker"
    new_package.scaffold(repo, {"python": root_api}, "x", "pre-release")
    with pytest.raises(ValueError, match="python/aws_lambda_worker already exists"):
        new_package.scaffold(repo, {"python": root_api}, "x", "pre-release")


def test_at_least_one_language_is_required(repo: Path) -> None:
    with pytest.raises(ValueError, match="--python"):
        new_package.scaffold(repo, {}, "x", "pre-release")
    assert new_package.main(["--description", "x", "--repo-root", str(repo)]) == 1

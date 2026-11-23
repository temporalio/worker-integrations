from __future__ import annotations

from pathlib import Path

import pytest

import new_package
from ci import check_conventions
from conftest import copy_language_support
from lib.languages import TOOLED_LANGUAGES

# Tooled language -> a valid name for its new_package.py option, and the lockfile the package's next
# steps create (scaffolding doesn't)
EXAMPLES = {
    "go": ("go.temporal.io/worker-integrations/aws/lambda", "go.sum"),
    "python": ("temporalio.worker_integrations.aws.lambda_worker", "uv.lock"),
    "typescript": ("@temporalio/aws-lambda-worker", "pnpm-lock.yaml"),
}


def test_existing_package_is_not_overwritten(repo: Path) -> None:
    copy_language_support(repo, "python")
    root_api = "temporalio.worker_integrations.aws.lambda_worker"
    new_package.scaffold(repo, {"python": root_api}, "x", "pre-release")
    with pytest.raises(ValueError, match="python/aws_lambda_worker already exists"):
        new_package.scaffold(repo, {"python": root_api}, "x", "pre-release")


def test_at_least_one_language_is_required(repo: Path) -> None:
    with pytest.raises(ValueError, match="--python"):
        new_package.scaffold(repo, {}, "x", "pre-release")
    assert new_package.main(["--description", "x", "--repo-root", str(repo)]) == 1


def test_published_name_override_needs_its_language(repo: Path) -> None:
    with pytest.raises(ValueError, match="--python-published-name needs --python"):
        new_package.scaffold(repo, {}, "x", "pre-release", {"python": "temporalio-modal"})


def test_examples_cover_every_tooled_language() -> None:
    assert sorted(EXAMPLES) == sorted(TOOLED_LANGUAGES)


def test_every_language_can_be_created_at_once(repo: Path) -> None:
    args: list[str] = []
    for language, (name, _) in EXAMPLES.items():
        copy_language_support(repo, language)
        args += [f"--{language}", name]
    assert new_package.main([*args, "--description", "x", "--repo-root", str(repo)]) == 0

    for language, (name, lockfile) in EXAMPLES.items():
        spec = TOOLED_LANGUAGES[language]
        (repo / language / spec.package_folder(name, spec.published_name(name)) / lockfile).write_text("")
    assert check_conventions.Checker(repo).run() == []


@pytest.mark.parametrize("invalid", sorted(EXAMPLES))
def test_an_invalid_name_in_any_language_writes_nothing(repo: Path, invalid: str) -> None:
    names = {language: name for language, (name, _) in EXAMPLES.items()}
    names[invalid] = "x"
    for language in names:
        copy_language_support(repo, language)
    with pytest.raises(ValueError):
        new_package.scaffold(repo, names, "x", "pre-release")
    for language in names:
        assert [p.name for p in (repo / language).iterdir() if not p.name.startswith(("_", "."))] == []

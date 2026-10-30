from __future__ import annotations

from pathlib import Path

import pytest

from conftest import make_package, make_python_package
from lib.release_tag import parse_tag
from lib.release_version import ReleaseVersion


def test_valid_tag_names_the_package_and_version(repo: Path) -> None:
    make_python_package(repo)
    tag = parse_tag(repo, "python/aws_lambda_worker/v0.1.0rc1")
    assert tag.package.rel == "python/aws_lambda_worker"
    assert tag.version == ReleaseVersion((0, 1, 0), ("rc", 1))
    assert str(tag.version) == "0.1.0rc1"


@pytest.mark.parametrize("tag,message", [
    ("aws_lambda_worker/v0.1.0", "must be <language>/<package>/v<version>"),
    ("python/aws_lambda_worker/0.1.0", "must be <language>/<package>/v<version>"),
    ("python/v0.1.0", "must be <language>/<package>/v<version>"),
    ("python/aws_lambda_worker/v0.1.0/extra", "must be <language>/<package>/v<version>"),
    ("go/aws/lambda/v0.1.0", "'go' is not a language with release tooling"),
    ("python/aws_lambda/v0.1.0", "python/aws_lambda is not a package"),
    ("python/_template/v0.1.0", "python/_template is not a package"),
    ("python/aws_lambda_worker/v1.0.0-rc1", "'1.0.0-rc1' isn't a supported Python version"),
])
def test_invalid_tag_is_rejected(repo: Path, tag: str, message: str) -> None:
    make_python_package(repo)
    make_package(repo, "go", "aws/lambda")
    with pytest.raises(ValueError, match="^release tag ") as exc:
        parse_tag(repo, tag)
    assert message in str(exc.value)

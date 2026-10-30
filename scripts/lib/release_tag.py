"""Parsing of release tags.

A release tag is `<language>/<folder>/v<version>`, e.g. `python/aws_lambda_worker/v0.1.0` or
`go/aws/lambda/otel/v0.1.0`: the first segment is the language root, the version follows the last
`/v`, and everything in between is the package's folder. The version is spelled exactly as the
language's registry publishes it (e.g. Python's `1.0.0rc1`, not SemVer's `1.0.0-rc.1`), so that
the tag matches the published version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lib.common import Package, discover_packages
from lib.languages import TOOLED_LANGUAGES
from lib.release_version import ReleaseVersion

TAG_RE = re.compile(r"(?P<language>[^/]+)/(?P<folder>.+)/v(?P<version>[^/]+)")


@dataclass(frozen=True)
class ReleaseTag:
    package: Package
    version: ReleaseVersion


def parse_tag(root: Path, tag: str) -> ReleaseTag:
    """Parse a release tag for a package in the repository at `root`. Raises ValueError if it's invalid."""
    m = TAG_RE.fullmatch(tag)
    if not m:
        raise ValueError(f"release tag {tag!r} must be <language>/<package>/v<version>")
    language = TOOLED_LANGUAGES.get(m["language"])
    if language is None:
        raise ValueError(f"release tag {tag!r}: {m['language']!r} is not a language with release tooling")
    package = next((p for p in discover_packages(root)[language.name] if p.name == m["folder"]), None)
    if package is None:
        raise ValueError(f"release tag {tag!r}: {language.name}/{m['folder']} is not a package")
    try:
        version = language.release_version(m["version"])
    except ValueError as exc:
        raise ValueError(f"release tag {tag!r}: {exc}") from exc
    return ReleaseTag(package, version)

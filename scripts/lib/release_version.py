"""The release version type every language's versions are parsed into, and its ordering.

Each language parses its registry's own spelling (e.g. Python's `1.0.0rc1`) with
`Language.release_version`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import total_ordering

PRE_RELEASE_PHASES = ("alpha", "beta", "rc")
# One number in a version (e.g. the 2 in 1.2.3 or in 1.0.0-rc.2), without leading zeros
VERSION_NUMBER_PATTERN = r"(?:0|[1-9][0-9]*)"
# The SemVer versions we release where registries use SemVer (Go, npm): `X.Y.Z`, optionally
# followed by a pre-release -alpha.<N>, -beta.<N> or -rc.<N>
SEMVER_RELEASE_RE = re.compile(
    rf"(?P<release>{VERSION_NUMBER_PATTERN}\.{VERSION_NUMBER_PATTERN}\.{VERSION_NUMBER_PATTERN})"
    rf"(?:-(?P<phase>alpha|beta|rc)\.(?P<number>{VERSION_NUMBER_PATTERN}))?"
)


@total_ordering
@dataclass(frozen=True)
class ReleaseVersion:
    """A version as `X.Y.Z`, optionally a pre-release of it.

    Versions compare by release, then pre-release phase (in PRE_RELEASE_PHASES order) and number,
    and a final release comes after all of its pre-releases.
    """

    release: tuple[int, int, int]
    pre: tuple[str, int] | None = None
    """(phase, number), e.g. ("rc", 1); the phase is one of PRE_RELEASE_PHASES."""
    text: str = field(default="", compare=False)
    """The version as spelled after the release tag's "v", e.g. "1.0.0-rc.1" (SemVer) or "1.0.0rc1" (Python)."""

    def __str__(self) -> str:
        return self.text

    def __lt__(self, other: ReleaseVersion) -> bool:
        return self._key() < other._key()

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None

    def _key(self) -> tuple[tuple[int, int, int], bool, int, int]:
        if self.pre is None:
            return (self.release, True, 0, 0)
        return (self.release, False, PRE_RELEASE_PHASES.index(self.pre[0]), self.pre[1])


def parse_semver_release(text: str) -> ReleaseVersion | None:
    """Parse a version matching SEMVER_RELEASE_RE, or return None if it doesn't match."""
    m = SEMVER_RELEASE_RE.fullmatch(text)
    if not m:
        return None
    major, minor, patch = (int(n) for n in m["release"].split("."))
    pre = (m["phase"], int(m["number"])) if m["phase"] else None
    return ReleaseVersion((major, minor, patch), pre, text)

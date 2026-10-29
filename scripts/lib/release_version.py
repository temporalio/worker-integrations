"""The release version type every language's versions are parsed into, and its ordering.

Each language parses its registry's own spelling (e.g. Python's `1.0.0rc1`) with
`Language.release_version`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import total_ordering

PRE_RELEASE_PHASES = ("alpha", "beta", "rc")


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

"""Read the package's ``integration.toml`` (the machine-readable metadata every package carries)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Each branch is unreachable under one interpreter version; basedpyright fails on that warning.
if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[reportUnreachable]
else:  # Python 3.10: tomllib arrived in 3.11
    import tomli as tomllib  # type: ignore[reportUnreachable]


@dataclass(frozen=True)
class PackageMeta:
    published_name: str
    root_api: str

    @property
    def package_relpath(self) -> str:
        """Root API as a path relative to site-packages, e.g. ``temporalio/worker_integrations/aws/lambda_worker``."""
        return self.root_api.replace(".", "/")


def load_package_meta(package_root: Path) -> PackageMeta:
    data = tomllib.loads(
        (package_root / "integration.toml").read_text(encoding="utf-8")
    )
    package = data["package"]
    return PackageMeta(
        published_name=package["published-name"],
        root_api=package["root-api"],
    )

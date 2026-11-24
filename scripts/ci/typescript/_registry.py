"""Looking up one version of a package on npm, for check_published.py and smoke.py."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.languages.typescript import fetch_packument  # noqa: E402

# How long to wait for an upload to show up on npm: up to 10 checks, 30 seconds apart
CHECKS = 10
CHECK_DELAY = 30


def version_metadata(published_name: str, version: str) -> dict[str, Any] | None:
    """npm's metadata for one version of a package, or None if npm doesn't have that version."""
    packument = fetch_packument(published_name)
    return None if packument is None else packument.get("versions", {}).get(version)


def wait_for_version(published_name: str, version: str) -> dict[str, Any] | None:
    """version_metadata, once npm lists the version. None if it still doesn't after CHECKS checks.

    npm serves package metadata through a CDN, so a new version can take a while to show up.
    """
    for check in range(1, CHECKS + 1):
        if (metadata := version_metadata(published_name, version)) is not None:
            return metadata
        if check < CHECKS:
            print(f"npm doesn't list {published_name}@{version} yet; checking again in {CHECK_DELAY}s", flush=True)
            time.sleep(CHECK_DELAY)
    return None

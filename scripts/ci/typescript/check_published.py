#!/usr/bin/env python3
"""Check whether npm has a version of one TypeScript package, and if so, that it's the tested tarball.

Runs in release-typescript.yml on the tarball the dry run tested, both before uploading it (in the
publish job) and after (in the verify-npm job). npm never lets a version be replaced, so a version
npm already has is only fine if it has exactly the tested bytes. That happens in two cases:
  * a new package's first version, which a maintainer published by hand from the dry run's
    tarball, since npm can only set up trusted publishing for a package that exists
  * "Re-run failed jobs" after an earlier attempt uploaded the tarball but then failed
pnpm pack builds the same bytes from the same commit, so the release run's own build matches a
tarball published by hand from its dry run.

npm records each version's sha512 as its `dist.integrity`, which npm install also verifies
downloads against, so this compares that with the tested tarball's.

Without --wait (before uploading): prints and writes `published=true` if npm has the version with
the tested bytes, so the upload can be skipped, or `published=false` if npm doesn't have it.
With --wait (after uploading): waits until npm lists the version, and fails unless it has the
tested bytes.

Fails if npm has the version with different bytes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ci.typescript._registry import version_metadata, wait_for_version  # noqa: E402
from lib.common import write_github_output  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402


class PublishedError(Exception):
    """npm's copy of the version isn't the tested tarball. The message says why."""


def integrity(tarball: Path) -> str:
    """The tarball's sha512, in npm's Subresource Integrity format."""
    return "sha512-" + base64.b64encode(hashlib.sha512(tarball.read_bytes()).digest()).decode()


def check(published_name: str, version: str, dist: Path, wait: bool) -> bool:
    """Whether npm has `version` with the tested tarball's bytes. Raises PublishedError if it has other bytes."""
    tarballs = sorted(dist.glob("*.tgz"))
    if len(tarballs) != 1:
        raise PublishedError(f"expected exactly one tarball in {dist}, found {[t.name for t in tarballs]}")
    metadata = wait_for_version(published_name, version) if wait else version_metadata(published_name, version)
    if metadata is None:
        if wait:
            raise PublishedError(f"npm still doesn't list {published_name}@{version}")
        return False
    expected = integrity(tarballs[0])
    actual = metadata.get("dist", {}).get("integrity")
    if actual != expected:
        raise PublishedError(
            f"npm has {published_name}@{version} with integrity {actual!r}, but the tested tarball "
            f"{tarballs[0].name} has {expected!r}. npm never replaces a version, so release the next one."
        )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist", type=Path, default=None, help="defaults to <package-dir>/dist")
    parser.add_argument("--wait", action="store_true", help="wait for npm to list the version, and require it")
    parser.add_argument("--github-output", default=None)
    args = parser.parse_args(argv)

    name = IntegrationMeta.from_file(args.package_dir / "integration.toml").published_name
    try:
        published = check(name, args.version, args.dist or args.package_dir / "dist", args.wait)
    except PublishedError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"published={'true' if published else 'false'}")
    print(
        f"OK: npm has {name}@{args.version}, with the tested tarball's bytes" if published
        else f"OK: npm doesn't have {name}@{args.version} yet"
    )
    write_github_output(
        args.github_output or os.environ.get("GITHUB_OUTPUT"), {"published": "true" if published else "false"}
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

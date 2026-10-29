#!/usr/bin/env python3
"""Verify the wheel that `make build` wrote for one Python package.

Runs after `make build` on the CI cell that builds distributions. Exits non-zero with a list of
problems.

These checks exist to catch issues that checks on the source tree can't see, in case the build
backend does something unexpected:
  * the wheel must ship only the root-api package and its .dist-info, nothing else like
    test code, anything in the higher-level shared namespaces that we don't own, etc. E.g.,
    an __init__.py for the SDK-owned `temporalio` package or a shared namespace level would
    cause conflicts with other packages and break installations.
  * the wheel's root-api package contains exactly the files in src/<root-api>/ (apart from
    __pycache__ and .pyc files)
  * the wheel's and sdist's metadata version is the expected version: the release version that
    release builds inject from the tag, or the development placeholder 0.0.0 in ordinary CI

The second check overlaps with the package's own tests/test_installed_matches_source.py, which
compares the installed package with src/<root-api>/, but the two see different wheels. The
package's test runs on a wheel built directly from src/ by `make sync`, and is meant for
in-development testing. This check runs on the wheel built via `make build`, which produces the
actual artifacts to be published. `make build` builds an sdist first and then builds the wheel
from that sdist, so if the build backend silently leaves a file out of the sdist, the published
wheel would lack it while every package test still passes. Backends differ in what they leave
out and some are rather notorious, so this is a real concern: e.g. data files such as py.typed,
files matched by .gitignore, or subpackages without an __init__.py.

The version check catches a release whose version injection silently didn't take effect, which
would otherwise publish the package under the wrong version.
"""

from __future__ import annotations

import argparse
import email
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.integration_toml import IntegrationMeta  # noqa: E402
from lib.languages.python import DEVELOPMENT_VERSION  # noqa: E402


def check(package_dir: Path, dist: Path, version: str = DEVELOPMENT_VERSION) -> list[str]:
    meta = IntegrationMeta.from_file(package_dir / "integration.toml")
    pkg_path = meta.root_api.replace(".", "/")

    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        return [f"expected exactly one wheel in {dist}, found {[w.name for w in wheels]}"]
    wheel = wheels[0]
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(sdists) != 1:
        return [f"expected exactly one sdist in {dist}, found {[s.name for s in sdists]}"]
    sdist = sdists[0]

    # Make sure the wheel doesn't ship anything outside the root-api package, such as
    # test code or stray files in the shared namespace levels
    with zipfile.ZipFile(wheel) as whl:
        files = {name for name in whl.namelist() if not name.endswith("/")}
        metadata = [whl.read(name).decode() for name in files if name.endswith(".dist-info/METADATA")]
    problems: list[str] = []
    for name in sorted(files):
        top = name.split("/")[0]
        if not name.startswith(f"{pkg_path}/") and not top.endswith(".dist-info"):
            problems.append(
                f"wheel must not ship {name}: only {pkg_path}/ is ours (the SDK owns temporalio, "
                "and the levels below it are shared namespace packages)"
            )

    # Make sure the wheel source contents match what's in src/
    src_dir = package_dir / "src" / pkg_path
    expected = {
        f"{pkg_path}/{path.relative_to(src_dir).as_posix()}"
        for path in src_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    shipped = {name for name in files if name.startswith(f"{pkg_path}/")}
    for name in sorted(expected - shipped):
        problems.append(f"wheel missing {name}, which is in src/")
    for name in sorted(shipped - expected):
        problems.append(f"wheel ships {name}, which isn't in src/")

    # Make sure both distributions carry the expected version in their metadata. An sdist's
    # metadata is the PKG-INFO in its top-level folder.
    pkg_info: list[str] = []
    with tarfile.open(sdist) as tar:
        for member in tar.getmembers():
            if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO") and (f := tar.extractfile(member)):
                pkg_info.append(f.read().decode())
    for name, found in ((wheel.name, metadata), (sdist.name, pkg_info)):
        if len(found) != 1:
            problems.append(f"{name} must have exactly one metadata file (found {len(found)})")
        # Note: We aren't dealing with actual emails.
        # The METADATA/PKG-INFO files just follow the email header format
        elif (actual := email.message_from_string(found[0])["Version"]) != version:
            problems.append(f"{name} has version {actual!r}, expected {version!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--dist", type=Path, default=None, help="defaults to <package-dir>/dist")
    parser.add_argument("--version", default="", help=f"expected version; empty or omitted means {DEVELOPMENT_VERSION}")
    args = parser.parse_args(argv)
    dist = args.dist or args.package_dir / "dist"
    problems = check(args.package_dir, dist, args.version or DEVELOPMENT_VERSION)
    if problems:
        print(f"FAIL: {len(problems)} problem(s) with the wheel in {dist}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: the wheel in {dist} passes all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())

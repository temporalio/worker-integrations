#!/usr/bin/env python3
"""Verify the npm tarball that `make build` wrote for one TypeScript package.

Runs after `make build` on the CI cell that builds the tarball. Exits non-zero with a list of
problems.

The package's own tests run on lib/ in the package folder, but users get only what `pnpm pack`
puts in the tarball, which `files` in package.json selects. These checks catch a tarball that
differs from what was tested:
  * its package.json has the package's name and the expected version: the release version that
    release builds set from the tag, or the development placeholder 0.0.0 in ordinary CI. This
    catches a release whose version injection silently didn't take effect.
  * it ships the package's LICENSE, and no tests (anything under a __tests__ folder)
  * every entry point that package.json names (main, types, and every exports target) is in it,
    so `files` can't leave out something a user's import resolves to
  * lib/ has exactly the compiled output of src/: a .js and .d.ts file for every source file
    outside __tests__ (or .mjs/.d.mts and .cjs/.d.cts for .mts and .cts sources), and no
    JavaScript without a source, e.g. the output of a deleted source left over from an earlier
    build
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.integration_toml import IntegrationMeta  # noqa: E402
from lib.languages.typescript import DEVELOPMENT_VERSION  # noqa: E402

# Source suffix -> the JavaScript and declaration suffixes tsc compiles it to
COMPILED_SUFFIXES = {".ts": (".js", ".d.ts"), ".mts": (".mjs", ".d.mts"), ".cts": (".cjs", ".d.cts")}
DECLARATION_SUFFIXES = (".d.ts", ".d.mts", ".d.cts")


def check(package_dir: Path, dist: Path, version: str = DEVELOPMENT_VERSION) -> list[str]:
    meta = IntegrationMeta.from_file(package_dir / "integration.toml")
    manifest = json.loads((package_dir / "package.json").read_text())

    tarballs = sorted(dist.glob("*.tgz"))
    if len(tarballs) != 1:
        return [f"expected exactly one tarball in {dist}, found {[t.name for t in tarballs]}"]
    tarball = tarballs[0]
    # npm tarballs keep every file under a top-level package/ folder
    files: dict[str, bytes] = {}
    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile() and (f := tar.extractfile(member)):
                files[member.name.removeprefix("package/")] = f.read()

    problems: list[str] = []
    try:
        packaged = json.loads(files["package.json"])
    except (KeyError, ValueError) as exc:
        return [f"{tarball.name} has no readable package.json ({exc!r})"]
    if packaged.get("name") != meta.published_name:
        problems.append(f"{tarball.name} has name {packaged.get('name')!r}, expected {meta.published_name!r}")
    if packaged.get("version") != version:
        problems.append(f"{tarball.name} has version {packaged.get('version')!r}, expected {version!r}")

    if files.get("LICENSE") != (package_dir / "LICENSE").read_bytes():
        problems.append(f"{tarball.name} must ship the package's LICENSE unchanged")
    for name in sorted(files):
        if "__tests__" in PurePosixPath(name).parts:
            problems.append(f"{tarball.name} must not ship tests: {name}")

    # Read the entry points from the package folder's package.json. The tarball's copy names the same
    # ones, since we don't use anything pnpm pack would rewrite (e.g. workspace: specs, which the
    # conventions check forbids).
    for target in sorted(set(_entry_points(manifest))):
        if target.removeprefix("./") not in files:
            problems.append(f"{tarball.name} is missing {target}, an entry point in package.json")

    src_dir = package_dir / "src"
    expected: set[str] = set()
    for source in src_dir.rglob("*"):
        rel = source.relative_to(src_dir)
        compiled = COMPILED_SUFFIXES.get(source.suffix)
        if not source.is_file() or compiled is None or "__tests__" in rel.parts or source.name.endswith(DECLARATION_SUFFIXES):
            continue
        stem = rel.as_posix().removesuffix(source.suffix)
        expected.update(f"lib/{stem}{suffix}" for suffix in compiled)
    shipped = {
        name for name in files
        if name.startswith("lib/") and name.endswith((".js", ".mjs", ".cjs", *DECLARATION_SUFFIXES))
    }
    for name in sorted(expected - shipped):
        problems.append(f"{tarball.name} is missing {name}, compiled from src/")
    for name in sorted(shipped - expected):
        if "__tests__" not in PurePosixPath(name).parts:  # already reported above
            problems.append(f"{tarball.name} ships {name}, which no file in src/ compiles to")
    return problems


def _entry_points(manifest: dict[str, object]) -> list[str]:
    """The file paths that main, types and exports name (exports targets can nest in conditions)."""
    def targets(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [t for v in value.values() for t in targets(v)]
        if isinstance(value, list):
            return [t for v in value for t in targets(v)]
        return []  # e.g. null, which blocks a subpath

    return targets([manifest.get("main"), manifest.get("types"), manifest.get("exports")])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--dist", type=Path, default=None, help="defaults to <package-dir>/dist")
    parser.add_argument("--version", default="", help=f"expected version; empty or omitted means {DEVELOPMENT_VERSION}")
    args = parser.parse_args(argv)
    dist = args.dist or args.package_dir / "dist"
    problems = check(args.package_dir, dist, args.version or DEVELOPMENT_VERSION)
    if problems:
        print(f"FAIL: {len(problems)} problem(s) with the tarball in {dist}:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: the tarball in {dist} passes all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())

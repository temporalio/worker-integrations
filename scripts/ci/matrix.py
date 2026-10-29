#!/usr/bin/env python3
"""Emit the GitHub Actions test matrix for one package.

Each cell has these fields:

  os       the runner: ubuntu-latest, macos-latest or windows-latest
  runtime  the minimum or maximum version from integration.toml's `[ci] runtime-versions`
           (first = minimum, last = maximum)
  deps     the dependency mode, which the workflow passes to the package's build tool:
           locked (the lockfile), lowest (the lowest allowed versions of direct
           dependencies) or latest (the newest allowed versions)
  build    whether CI should also build and check the package's distributions

Each mode passed to --deps adds its own cells (multiple may be passed at once):

  locked, latest  ubuntu-latest at min and max, macos-latest and windows-latest at max;
                  build=True only on ubuntu-latest at max
  lowest          ubuntu-latest at min only, build=False

Output: matrix={"include":[...]}.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.common import compact_json, write_github_output  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402

DEPS_MODES = ("locked", "lowest", "latest")


def build_matrix(runtime_versions: Sequence[str], deps: set[str]) -> dict[str, list[dict[str, object]]]:
    """Build the GitHub Actions matrix from the given min/max versions and dependency modes.

    The GitHub Actions matrix format expects one top-level "include" property with
    a list of objects as its value.
    """
    if not runtime_versions:
        raise ValueError("[ci] runtime-versions must list at least one version")
    lo, hi = runtime_versions[0], runtime_versions[-1]
    include: list[dict[str, object]] = []
    for mode in DEPS_MODES:
        if mode not in deps:  # exhaustive loop + existence check so ordering is deterministic
            continue
        if mode == "lowest":
            include.append({"os": "ubuntu-latest", "runtime": lo, "deps": mode, "build": False})
            continue
        if lo != hi:
            include.append({"os": "ubuntu-latest", "runtime": lo, "deps": mode, "build": False})
        include.append({"os": "ubuntu-latest", "runtime": hi, "deps": mode, "build": True})
        for runner in ("macos-latest", "windows-latest"):
            include.append({"os": runner, "runtime": hi, "deps": mode, "build": False})
    return {"include": include}


def main(argv: list[str] | None = None) -> dict[str, list[dict[str, object]]]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--deps", nargs="+", choices=DEPS_MODES, required=True)
    parser.add_argument("--github-output", default=None)
    args = parser.parse_args(argv)

    meta = IntegrationMeta.from_file(args.package_dir / "integration.toml")
    matrix = build_matrix(meta.runtime_versions, set(args.deps))
    text = compact_json(matrix)
    print(f"matrix={text}")
    write_github_output(args.github_output or os.environ.get("GITHUB_OUTPUT"), {"matrix": text})
    return matrix


if __name__ == "__main__":
    main()

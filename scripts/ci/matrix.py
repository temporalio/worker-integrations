#!/usr/bin/env python3
"""Emit the GitHub Actions test matrix for one package.

Reads `[ci] runtime-versions` from the package's integration.toml
(first = minimum, last = maximum supported runtime) and emits:

  ubuntu-latest x {min, max}, macos-latest and windows-latest at max

Only the ubuntu/max matrix cell is marked with build=True, so CI will build the package's
distributions only on that one cell.

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


def build_matrix(runtime_versions: Sequence[str]) -> dict[str, list[dict[str, object]]]:
    """Build the GitHub Actions matrix from the given min/max versions.

    The GitHub Actions matrix format expects one top-level "include" property with
    a list of objects as its value.
    """
    if not runtime_versions:
        raise ValueError("[ci] runtime-versions must list at least one version")
    lo, hi = runtime_versions[0], runtime_versions[-1]
    include: list[dict[str, object]] = []
    if lo != hi:
        include.append({"os": "ubuntu-latest", "runtime": lo, "build": False})
    include.append({"os": "ubuntu-latest", "runtime": hi, "build": True})
    for runner in ("macos-latest", "windows-latest"):
        include.append({"os": runner, "runtime": hi, "build": False})
    return {"include": include}


def main(argv: list[str] | None = None) -> dict[str, list[dict[str, object]]]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--github-output", default=None)
    args = parser.parse_args(argv)

    meta = IntegrationMeta.from_file(args.package_dir / "integration.toml")
    matrix = build_matrix(meta.runtime_versions)
    text = compact_json(matrix)
    print(f"matrix={text}")
    write_github_output(args.github_output or os.environ.get("GITHUB_OUTPUT"), {"matrix": text})
    return matrix


if __name__ == "__main__":
    main()

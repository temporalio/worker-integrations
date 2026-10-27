"""The part of smoke.py that runs inside a smoke environment, under `python -I`.

Standard library only: the environment contains just the installed package and its dependencies.

Imports the package's modules, then runs the package's provenance guard. Prints one line per
problem and exits non-zero if there were any.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path


def import_modules(root_api: str, imports: list[str], import_all: bool) -> list[str]:
    """Import `root_api` and `imports` (and with `import_all`, every module under `root_api`)."""
    problems: list[str] = []

    def try_import(name: str) -> bool:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"import {name} failed: {exc!r}")
            return False
        return True

    root_ok = try_import(root_api)
    for name in imports:
        try_import(name)
    if root_ok and import_all:
        root_path = sys.modules[root_api].__path__
        # walk_packages imports each subpackage to look inside it. try_import has already recorded
        # any failure by then, so walk_packages' own error hook ignores it.
        for info in pkgutil.walk_packages(root_path, f"{root_api}.", onerror=lambda _name: None):
            try_import(info.name)
    return problems


def check_provenance(provenance_py: Path, published_name: str, root_api: str) -> list[str]:
    """Run `check_provenance` from the package's provenance.py, which isn't importable here."""
    spec = importlib.util.spec_from_file_location("provenance", provenance_py)
    assert spec is not None and spec.loader is not None
    provenance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provenance)
    try:
        provenance.check_provenance(published_name, root_api.replace(".", "/"))
    except provenance.ProvenanceError as exc:
        return [f"provenance guard failed: {exc}"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provenance", type=Path, required=True, help="the package's tests/helpers/provenance.py")
    parser.add_argument("--published-name", required=True)
    parser.add_argument("--root-api", required=True)
    parser.add_argument("--all", action="store_true", help="also import every module under --root-api")
    parser.add_argument("imports", nargs="*", help="more modules to import, besides --root-api")
    args = parser.parse_args(argv)

    problems = import_modules(args.root_api, args.imports, args.all)
    problems += check_provenance(args.provenance, args.published_name, args.root_api)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Create new package folders from each language's template (<language>/_template).

Usage:
    uv run --project scripts --locked python scripts/new_package.py \\
        --description "..." \\
        [--maturity pre-release|public-preview|generally-available] \\
        [--python <root API>]

Each language option takes the name that identifies a package in that language, since naming
styles differ by language; the package's other relevant names/identifiers derive from it
(see AGENTS.md). Every requested name is validated before anything is written.
  - Python: the full root API; --python temporalio.worker_integrations.aws.lambda_worker
    creates python/aws_lambda_worker published as temporalio-worker-integrations-aws-lambda-worker.

At least one language option is required. Multiple language options may be passed at once to
create analogous packages across multiple languages simultaneously; this has the same effect
as calling the script multiple times, once per language.

Once a package has been created, a list of created files will be printed alongside suggested
next steps for a developer to perform manually.

Per-language rules live in scripts/lib/languages/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import repo_root  # noqa: E402
from lib.integration_toml import MATURITIES  # noqa: E402
from lib.languages import TOOLED_LANGUAGES  # noqa: E402


def scaffold(root: Path, names: dict[str, str], description: str, maturity: str) -> list[Path]:
    """Create one package per {language: name}. Validates every name before writing anything."""
    if not names:
        options = ", ".join(f"--{lang}" for lang in TOOLED_LANGUAGES)
        raise ValueError(f"name at least one language to create a package for: {options}")
    if maturity not in MATURITIES:
        raise ValueError(f"maturity must be one of {sorted(MATURITIES)}, got {maturity!r}")
    for language, name in names.items():
        folder = TOOLED_LANGUAGES[language].package_folder(name)
        if (root / language / folder).exists():
            raise ValueError(f"{language}/{folder} already exists")
    written: list[Path] = []
    for language, name in names.items():
        written += TOOLED_LANGUAGES[language].scaffold(root, name, description, maturity)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for language, spec in TOOLED_LANGUAGES.items():
        parser.add_argument(f"--{language}", metavar="NAME", help=spec.name_help)
    parser.add_argument("--description", required=True, help="one-line package description")
    parser.add_argument("--maturity", choices=sorted(MATURITIES), default="pre-release")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)

    names = {lang: getattr(args, lang) for lang in TOOLED_LANGUAGES if getattr(args, lang) is not None}
    root = repo_root(args.repo_root)
    try:
        written = scaffold(root, names, args.description, args.maturity)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote   {path.relative_to(root).as_posix()}")
    for language, name in names.items():
        spec = TOOLED_LANGUAGES[language]
        folder = spec.package_folder(name)
        print(f"\nNext steps for {language}/{folder}:\n{spec.next_steps.format(folder=folder)}")
    print("\nThen open the PR. CI discovers new packages automatically; no workflow edits are needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

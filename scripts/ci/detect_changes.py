#!/usr/bin/env python3
"""Decide which packages CI must run for the current event.

Stdlib only (runs with the runner's system python3 before uv is installed).

Rules:
  * push, schedule, workflow_dispatch, FORCE_ALL, unknown events, or an
    unusable diff base                      -> every package of every language
  * .github/**, scripts/ci/** or LICENSE    -> every package of every language
  * <lang>/<package>/**                     -> that package (the innermost one, if packages nest)
  * any other <lang>/** file                -> every package of that language (shared resources)
  * anything else (root files, scripts/**)  -> nothing

Outputs, written as key=value lines to GITHUB_OUTPUT (for later jobs) and to stdout:
  * <lang>  one key per language, e.g. go=["aws/lambda","aws/lambda/otel"]: a sorted JSON array
            of the selected package folder paths (relative to the language root) in that
            language, or [] if none were selected.
            Per-language CI jobs run once per name and are skipped on [].
  * any     true if at least one package in any language was selected, else false.
  * mode    why the selection is what it is:
              all   every package was selected (by event type, a fan-out rule, or a fail-safe)
              diff  only the packages matched by the changed files were selected
              none  the changed files matched no package
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import LANGUAGES, compact_json, discover_packages, git, repo_root, write_github_output  # noqa: E402


def changed_files(root: Path, base: str, head: str, three_dot: bool) -> list[str]:
    spec = [f"{base}...{head}"] if three_dot else [base, head]
    # -z: NUL-separated and unquoted, so paths with non-ASCII or special characters come through verbatim.
    # This should really never happen, but handling this correctly is basically free ¯\_(ツ)_/¯
    out = git(root, "diff", "--name-only", "--no-renames", "-z", *spec)
    return [path for path in out.split("\0") if path]


def select(files: list[str], packages: dict[str, list[str]]) -> tuple[dict[str, set[str]], bool]:
    """Apply the path rules. Returns (selected-by-language, run_all)."""
    selected: dict[str, set[str]] = {lang: set() for lang in LANGUAGES}
    for f in files:
        parts = f.split("/")
        top = parts[0]
        if top == ".github" or f == "LICENSE" or parts[:2] == ["scripts", "ci"]:
            # Workflow/tooling changes affect every package; so does the root
            # LICENSE, which every package copies.
            return selected, True
        if top in packages:
            rest = "/".join(parts[1:])
            owners = [name for name in packages[top] if rest.startswith(name + "/")]
            if owners:
                # Specific package; the innermost one when packages nest
                selected[top].add(max(owners, key=len))
            else:
                # All packages of a language
                selected[top].update(packages[top])
        # Other root-level files (README.md, AGENTS.md, ...) select nothing.
    return selected, False


def main(argv: list[str] | None = None) -> dict[str, object]:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--base", default=None, help="diff base ref (defaults from the event)")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--all", action="store_true", help="select every package")
    parser.add_argument("--github-output", default=None)
    parser.add_argument("--dry-run", action="store_true", help="print only; do not write GITHUB_OUTPUT")
    args = parser.parse_args(argv)

    root = repo_root(args.repo_root)
    packages = {lang: [p.name for p in ps] for lang, ps in discover_packages(root).items()}

    run_all = args.all or os.environ.get("FORCE_ALL", "").lower() in {"1", "true", "yes"}
    files: list[str] = []
    if not run_all:
        event = args.event
        try:
            if event == "pull_request":
                base = args.base or f"origin/{os.environ.get('GITHUB_BASE_REF', 'main')}"
                files = changed_files(root, base, args.head, three_dot=True)
            elif event == "merge_group":
                base = args.base or os.environ.get("MERGE_GROUP_BASE_SHA", "")
                head = os.environ.get("MERGE_GROUP_HEAD_SHA") or args.head
                if not base:
                    raise ValueError("MERGE_GROUP_BASE_SHA missing")
                files = changed_files(root, base, head, three_dot=False)
            elif not event and args.base:  # local use: detect_changes.py --base origin/main
                files = changed_files(root, args.base, args.head, three_dot=True)
            else:  # push, schedule, workflow_dispatch, unknown events, or no diff base
                run_all = True
        except (subprocess.CalledProcessError, ValueError) as exc:  # fail safe: run everything
            print(f"::warning::change detection could not compute a diff ({exc}); running everything", file=sys.stderr)
            run_all = True

    if not run_all:
        selected, run_all = select(files, packages)
    if run_all:
        selected = {lang: set(names) for lang, names in packages.items()}
        mode = "all"
    else:
        mode = "diff" if any(selected.values()) else "none"

    result: dict[str, object] = {lang: sorted(selected[lang]) for lang in LANGUAGES}
    result["any"] = any(selected.values())
    result["mode"] = mode

    outputs = {lang: compact_json(result[lang]) for lang in LANGUAGES}
    outputs["any"] = "true" if result["any"] else "false"
    outputs["mode"] = mode
    for key, value in outputs.items():
        print(f"{key}={value}")
    if files and mode != "all":
        print(f"changed files considered: {len(files)}", file=sys.stderr)
    if not args.dry_run:
        write_github_output(args.github_output or os.environ.get("GITHUB_OUTPUT"), outputs)
    return result


if __name__ == "__main__":
    main()

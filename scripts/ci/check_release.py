#!/usr/bin/env python3
"""Check that a release tag can be released, and output the package and version it names.

Runs first in each language's release dry run (e.g. release-python-dry-run.yml), before anything
is built. Checks:
  * the tag is `<language>/<package>/v<version>` for a package in this repository, in the
    workflow's language (--language), with the version spelled the way the language's registry
    publishes it (see lib/release_tag.py)
  * the repository's version conventions, against every version already in the registry
    (yanked ones included):
      - a package's first version is 0.0.1 (pre-release maturity), 0.1.0 (public-preview) or
        1.0.0 (generally-available), or a pre-release of it
      - every later version is greater than every published version, and at least the first
        version for the package's current maturity (or a pre-release of it)

Registries refuse to replace a published version, and users' version ranges assume versions only
increase, so each release must be greater than every version already published.

Outputs, for the jobs that test and build the release:

  package  the package's folder, relative to the language root (e.g. aws_lambda_worker)
  version  the version, as spelled after the tag's "v" (e.g. 0.1.0)

The step summary lists the tested commit and whether to mark the GitHub release as a pre-release
(if the version is a pre-release or the maturity is pre-release), for creating the release.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.common import git, repo_root, write_github_output  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402
from lib.languages import TOOLED_LANGUAGES  # noqa: E402
from lib.release_tag import parse_tag  # noqa: E402
from lib.release_version import ReleaseVersion  # noqa: E402

FIRST_RELEASES = {
    "pre-release": (0, 0, 1),
    "public-preview": (0, 1, 0),
    "generally-available": (1, 0, 0),
}


def check_version_conventions(version: ReleaseVersion, maturity: str, published: list[ReleaseVersion]) -> list[str]:
    """Violations of the version conventions by the `version` to be released, given every published version."""
    first = FIRST_RELEASES[maturity]
    first_text = ".".join(map(str, first))
    if not published:
        if version.release != first:
            return [f"the first release of a {maturity} package must be {first_text} or a pre-release of it (got {version})"]
        return []

    problems: list[str] = []
    if version <= (newest := max(published)):
        problems.append(f"{version} must be greater than the newest published version, {newest}")
    # E.g. after a package's maturity is raised, its next release starts at the new maturity's first version
    if version.release < first:
        problems.append(f"a {maturity} package must be at least {first_text} or a pre-release of it (got {version})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tag", help="e.g. python/aws_lambda_worker/v0.1.0")
    parser.add_argument("--language", required=True, help="the language the calling workflow releases")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--github-output", default=None)
    parser.add_argument("--github-step-summary", default=None)
    args = parser.parse_args(argv)
    root = repo_root(args.repo_root)

    try:
        tag = parse_tag(root, args.tag)
        meta = IntegrationMeta.from_file(tag.package.path / "integration.toml")
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    # We could just derive the language from the tag itself, but specifying it explicitly on input
    # allows for better tag validation
    if tag.package.language != args.language:
        print(f"FAIL: {args.tag} isn't a {args.language} release tag")
        return 1
    language = TOOLED_LANGUAGES[tag.package.language]

    # Every published version must parse, or the conventions can't be checked against it
    published: list[ReleaseVersion] = []
    for text in language.published_versions(meta.published_name):
        try:
            published.append(language.release_version(text))
        except ValueError:
            print(f"FAIL: {meta.published_name} has a published version this tooling can't order: {text!r}")
            return 1

    problems = check_version_conventions(tag.version, meta.maturity, published)
    if problems:
        print(f"FAIL: {len(problems)} problem(s) with releasing {args.tag}:")
        for p in problems:
            print(f"  - {p}")
        return 1

    write_github_output(args.github_output, {"package": tag.package.name, "version": str(tag.version)})
    prerelease = tag.version.is_prerelease or meta.maturity == "pre-release"
    if args.github_step_summary:
        with open(args.github_step_summary, "a", encoding="utf-8") as fh:
            fh.write(
                f"Release tag: `{args.tag}`\n\n"
                f"Tested commit: `{git(root, 'rev-parse', 'HEAD').strip()}`\n\n"
                f"Mark the GitHub release as a pre-release: {'yes' if prerelease else 'no'}\n"
            )
    print(f"OK: {args.tag} can be released ({meta.published_name} {tag.version}, pre-release: {prerelease})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

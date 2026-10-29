#!/usr/bin/env python3
"""Print the release notes for a package release, for the body of its GitHub release.

Usage:
    uv run --project scripts --locked python scripts/release_notes.py \\
        <language>/<package>/v<version> [--ref <commit>] [--since <tag>]

The notes are a Markdown list of the subjects of the commits that changed the package since its
previous release, each with its short SHA, under a "Changes since <previous version>" heading
that links to the previous release (or just "Changes" for a first release). Pull request
references in the subjects, e.g. `(#12)` from a squash merge, link to the pull request.

The commits are those in <previous tag>..<ref>:
  * --ref is the commit being released, normally the one the dry run tested (default: HEAD).
  * The previous tag is the package's highest release tag below this version. A final release
    skips earlier pre-release tags, so its notes cover everything since the previous final
    release. A first release has no previous tag, so its notes list every commit up to --ref.
  * --since overrides the previous tag with an earlier release tag of the package. This is for
    when the previous release was never published (e.g. its release workflow failed, and the fix
    went out as the next version): its tag still exists, but its changes reach users only in this
    release, so pass the last published release's tag.
  * Only commits that changed the package's folder count, apart from packages nested inside it
    (e.g. a Go module inside another), which are released separately.

Reads the package's release tags locally, and fails if any of the package's tags on GitHub are
missing locally (run `git fetch --tags` to get them). Without them, the notes could start from an
older release and repeat changes that were already released. The check only lists GitHub's tags
(`git ls-remote`), so it changes nothing in the local repository.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import Package, discover_packages, git, repo_root  # noqa: E402
from lib.languages import TOOLED_LANGUAGES  # noqa: E402
from lib.release_tag import ReleaseTag, parse_tag  # noqa: E402
from lib.release_version import ReleaseVersion  # noqa: E402

REPO_URL = "https://github.com/temporalio/worker-integrations"
PULL_REQUEST_REF_RE = re.compile(r"\(#(\d+)\)")


def remote_tags(root: Path, prefix: str) -> set[str]:
    """The names of the release tags on GitHub that start with `prefix`."""
    out = git(root, "ls-remote", "--tags", "--refs", REPO_URL, f"refs/tags/{prefix}*")
    return {line.partition("\trefs/tags/")[2] for line in out.splitlines()}


def previous_tag(root: Path, tag: ReleaseTag) -> str | None:
    """The package's previous release tag, or None for a first release."""
    language = TOOLED_LANGUAGES[tag.package.language]
    prefix = f"{tag.package.rel}/v"
    previous: tuple[ReleaseVersion, str] | None = None
    for name in git(root, "tag", "--list", f"{prefix}*").splitlines():
        try:
            version = language.release_version(name.removeprefix(prefix))
        except ValueError:
            # Not one of this package's release versions: e.g. a nested package's tag (if its
            # folder starts with "v"), or a malformed tag
            continue
        if version >= tag.version or (version.is_prerelease and not tag.version.is_prerelease):
            continue
        if previous is None or version > previous[0]:
            previous = (version, name)
    return previous[1] if previous else None


def pathspecs(root: Path, package: Package) -> list[str]:
    """Git pathspecs for the package's folder, excluding packages nested inside it."""
    nested = [p for p in discover_packages(root)[package.language] if p.name.startswith(f"{package.name}/")]
    return [package.rel, *(f":(exclude){p.rel}" for p in nested)]


def release_notes(root: Path, tag: ReleaseTag, ref: str, previous: str | None) -> str:
    """The notes for releasing `ref` as `tag`, with the changes since the `previous` release tag (None: all)."""
    # Commits since the previous release, or all of ref's history if there's no previous release
    revisions = f"{previous}..{ref}" if previous else ref
    log = git(root, "log", "--format=%h %s", revisions, "--", *pathspecs(root, tag.package))

    if previous:
        # The version as it appears at the end of the tag, e.g. "v0.1.0"
        lines = [f"## Changes since [{previous.rpartition('/')[2]}]({REPO_URL}/releases/tag/{previous})", ""]
    else:
        lines = ["## Changes", ""]
    for entry in log.splitlines():
        sha, _, subject = entry.partition(" ")
        subject = PULL_REQUEST_REF_RE.sub(lambda m: f"([#{m[1]}]({REPO_URL}/pull/{m[1]}))", subject)
        lines.append(f"- {subject} ({sha})")
    if not log:
        lines.append(f"No commits changed {tag.package.rel}.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tag", help="the release tag, e.g. python/aws_lambda_worker/v0.1.0")
    parser.add_argument("--ref", default="HEAD", help="the commit being released (default: HEAD)")
    parser.add_argument("--since", help="the release tag to list changes since (default: the previous release's)")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = repo_root(args.repo_root)

    try:
        tag = parse_tag(root, args.tag)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    try:
        ref = git(root, "rev-parse", "--verify", "--quiet", f"{args.ref}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        print(f"FAIL: {args.ref!r} isn't a commit", file=sys.stderr)
        return 1

    # Make sure the local tags are up to date, or the previous release could be missed
    prefix = f"{tag.package.rel}/v"
    try:
        local = set(git(root, "tag", "--list", f"{prefix}*").splitlines())
        missing = remote_tags(root, prefix) - local
    except subprocess.CalledProcessError as exc:
        print(f"FAIL: can't list the release tags on GitHub: {exc.stderr.strip()}", file=sys.stderr)
        return 1
    if missing:
        print(f"FAIL: {len(missing)} of {tag.package.rel}'s release tags on GitHub are missing locally; run `git fetch --tags`", file=sys.stderr)
        return 1

    if args.since:
        # Must be an earlier release tag of the same package, so that a typo fails instead of
        # silently listing the wrong changes
        try:
            since = parse_tag(root, args.since)
        except ValueError as exc:
            print(f"FAIL: --since: {exc}", file=sys.stderr)
            return 1
        if since.package != tag.package or since.version >= tag.version or args.since not in local:
            print(f"FAIL: --since must be an existing release tag of {tag.package.rel} below {tag.version}", file=sys.stderr)
            return 1
        previous: str | None = args.since
    else:
        previous = previous_tag(root, tag)

    print(release_notes(root, tag, ref, previous), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

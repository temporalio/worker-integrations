#!/usr/bin/env python3
"""Open, update or close one GitHub issue per failing package after a nightly run.

Reads the jobs of the current workflow run through `gh api` and groups them by package, using the
job names that GitHub gives reusable workflow jobs: e.g. `Python (aws_lambda_worker) / ...` comes
from ci.yml's `python` job, called with that package. A package fails if any of its jobs failed or
timed out, and passes if all of them succeeded; otherwise (e.g. a cancelled job) its issue is left
alone. Each failing package gets one open issue labelled `nightly`, commented on with each further
failing run. A passing package's open issue is closed.

The nightly run tests with the newest allowed dependencies, so these failures usually come from
upstream releases rather than from changes in this repository, and nothing else would surface them.

Stdlib only; needs `gh` with a token that can read Actions and write issues.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# ci.yml job name -> language root. test_nightly_report.py checks these against ci.yml.
GITHUB_JOB_LANGUAGES = {"Python": "python"}
# GitHub names a reusable workflow's jobs `<caller job name> (<matrix values>) / <called job name>`, e.g.
# `Python (aws_lambda_worker) / aws_lambda_worker (ubuntu-latest, py3.14, latest)`, where job=Python
# and package=aws_lambda_worker.
GITHUB_JOB_RE = re.compile(r"^(?P<job>[^ ]+) \((?P<package>[^)]+)\) / ")
GITHUB_LABEL = "nightly"


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def classify(jobs: list[dict[str, object]]) -> tuple[set[str], set[str]]:
    """Return the failing and passing packages (`<language>/<package>`) among the run's jobs."""
    conclusions: dict[str, set[object]] = {}
    for job in jobs:
        m = GITHUB_JOB_RE.match(str(job.get("name", "")))
        if not m or m.group("job") not in GITHUB_JOB_LANGUAGES:
            continue
        package = f"{GITHUB_JOB_LANGUAGES[m.group('job')]}/{m.group('package')}"
        conclusions.setdefault(package, set()).add(job.get("conclusion"))
    failing = {p for p, c in conclusions.items() if c & {"failure", "timed_out"}}
    passing = {p for p, c in conclusions.items() if c == {"success"}}
    return failing, passing


def title_for(package: str) -> str:
    return f"nightly: {package} failing with the newest allowed dependencies"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID"))
    parser.add_argument("--dry-run", action="store_true", help="print the classification without changing issues")
    args = parser.parse_args(argv)
    if not args.repo or not args.run_id:
        parser.error("--repo and --run-id are required (or GITHUB_REPOSITORY and GITHUB_RUN_ID)")

    # Determine which jobs succeeded/failed in the current run
    pages = json.loads(_gh("api", "--paginate", "--slurp", f"repos/{args.repo}/actions/runs/{args.run_id}/jobs?per_page=100"))
    failing, passing = classify([job for page in pages for job in page["jobs"]])
    run_url = f"https://github.com/{args.repo}/actions/runs/{args.run_id}"
    print(f"failing: {sorted(failing)}\npassing: {sorted(passing)}")
    if args.dry_run:
        return 0

    # Ensure the GitHub label exists/is up-to-date
    _gh("label", "create", GITHUB_LABEL, "--repo", args.repo, "--force", "--color", "B60205",
        "--description", "Nightly CI with the newest allowed dependencies is failing")

    # Get an existing list of open nightly issues.
    # Safety limit of 1000 open issues, but we should never hit it; if we do we have other problems
    open_issues = json.loads(_gh("issue", "list", "--repo", args.repo, "--label", GITHUB_LABEL, "--state", "open",
                                 "--limit", "1000", "--json", "number,title"))
    by_title = {issue["title"]: issue["number"] for issue in open_issues}

    for package in sorted(failing):
        title = title_for(package)
        if title in by_title:
            # Already an open issue for this package, just add a comment about this run
            _gh("issue", "comment", str(by_title[title]), "--repo", args.repo, "--body", f"Still failing: {run_url}")
            print(f"commented on #{by_title[title]}: {title}")
        else:
            # Create a new issue for this failing package
            body = (f"The nightly CI run with the newest allowed dependencies is failing for `{package}`.\n\n"
                    f"Run: {run_url}\n\n"
                    "This issue is updated by `scripts/ci/nightly_report.py`, and is closed automatically once the "
                    "package passes again.")
            out = _gh("issue", "create", "--repo", args.repo, "--title", title, "--label", GITHUB_LABEL, "--body", body)
            print(f"opened {out.strip()}: {title}")
    for package in sorted(passing):
        title = title_for(package)
        if title in by_title:
            # Close the open issue for the now-passing package
            _gh("issue", "close", str(by_title[title]), "--repo", args.repo, "--comment", f"Passing again: {run_url}")
            print(f"closed #{by_title[title]}: {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

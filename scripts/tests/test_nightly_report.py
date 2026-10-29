from __future__ import annotations

import json

import pytest
import yaml

from ci import nightly_report
from lib.common import repo_root


def _job(name: str, conclusion: str | None) -> dict[str, object]:
    return {"name": name, "conclusion": conclusion}


def test_classify_groups_jobs_by_package() -> None:
    failing, passing = nightly_report.classify(
        [
            _job("Python (aws_lambda_worker) / matrix", "success"),
            _job("Python (aws_lambda_worker) / aws_lambda_worker (ubuntu-latest, py3.14, latest)", "success"),
            _job("Python (aws_lambda_worker) / aws_lambda_worker (ubuntu-latest, py3.10, latest)", "failure"),
            _job("Python (gcp_cloud_run) / matrix", "success"),
            _job("Python (gcp_cloud_run) / gcp_cloud_run (macos-latest, py3.14, latest)", "timed_out"),
            _job("Python (azure_functions) / azure_functions (ubuntu-latest, py3.14, latest)", "success"),
        ]
    )
    assert failing == {"python/aws_lambda_worker", "python/gcp_cloud_run"}
    assert passing == {"python/azure_functions"}


def test_classify_leaves_unfinished_or_cancelled_packages_alone() -> None:
    failing, passing = nightly_report.classify(
        [
            _job("Python (aws_lambda_worker) / aws_lambda_worker (ubuntu-latest, py3.14, latest)", "success"),
            _job("Python (aws_lambda_worker) / aws_lambda_worker (macos-latest, py3.14, latest)", "cancelled"),
            _job("Python (gcp_cloud_run) / gcp_cloud_run (ubuntu-latest, py3.14, latest)", None),
        ]
    )
    assert failing == set()
    assert passing == set()


def test_classify_ignores_jobs_that_are_not_package_jobs() -> None:
    failing, passing = nightly_report.classify(
        [
            _job("Repository tooling tests", "failure"),
            _job("ci-status", "failure"),
            _job("Unknown (thing) / job", "failure"),
        ]
    )
    assert failing == set()
    assert passing == set()


def test_job_languages_match_ci_workflow() -> None:
    # We map the "pretty" job names in ci.yml to language subdirectories in `nightly_report`,
    # so ensure this mapping remains up to date with name changes, otherwise `nightly_report`
    # would break.
    jobs = yaml.safe_load((repo_root() / ".github/workflows/ci.yml").read_text())["jobs"]
    package_jobs = {
        job_id: job for job_id, job in jobs.items() if str(job.get("uses", "")).startswith("./.github/workflows/_")
    }
    assert {job["name"]: job_id for job_id, job in package_jobs.items()} == nightly_report.GITHUB_JOB_LANGUAGES
    assert set(package_jobs) <= set(jobs["nightly-report"]["needs"])


def test_main_opens_comments_and_closes_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = [
        _job("Python (new_failure) / new_failure (ubuntu-latest, py3.14, latest)", "failure"),
        _job("Python (still_failing) / still_failing (ubuntu-latest, py3.14, latest)", "failure"),
        _job("Python (fixed) / fixed (ubuntu-latest, py3.14, latest)", "success"),
    ]
    open_issues = [
        {"number": 1, "title": nightly_report.title_for("python/still_failing")},
        {"number": 2, "title": nightly_report.title_for("python/fixed")},
    ]
    calls: list[tuple[str, ...]] = []

    def fake_gh(*args: str) -> str:
        calls.append(args)
        if args[0] == "api":
            return json.dumps([{"jobs": jobs[:2]}, {"jobs": jobs[2:]}])
        if args[:2] == ("issue", "list"):
            return json.dumps(open_issues)
        return ""

    monkeypatch.setattr(nightly_report, "_gh", fake_gh)
    assert nightly_report.main(["--repo", "o/r", "--run-id", "7"]) == 0

    actions = [c[:3] for c in calls if c[0] == "issue" and c[1] != "list"]
    assert actions == [("issue", "create", "--repo"), ("issue", "comment", "1"), ("issue", "close", "2")]
    create = next(c for c in calls if c[:2] == ("issue", "create"))
    assert nightly_report.title_for("python/new_failure") in create


def test_dry_run_changes_no_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_gh(*args: str) -> str:
        calls.append(args)
        return json.dumps([{"jobs": [_job("Python (p) / p (ubuntu-latest, py3.14, latest)", "failure")]}])

    monkeypatch.setattr(nightly_report, "_gh", fake_gh)
    assert nightly_report.main(["--repo", "o/r", "--run-id", "7", "--dry-run"]) == 0
    assert [c[0] for c in calls] == ["api"]

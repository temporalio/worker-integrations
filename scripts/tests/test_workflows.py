"""Static workflow checks: pinned actions, least privilege, and the ci-status fan-in."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from lib.common import repo_root

REPO = repo_root()
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))
USES_LINE = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)(?:\s+#\s*(?P<comment>.*))?\s*$")
SHA_REF = re.compile(r"^[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-f]{40}$")
ALLOWED_UNPINNED = ("./.github/",)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_sha_pinned_with_version_comments(path: Path) -> None:
    for line in path.read_text().splitlines():
        m = USES_LINE.match(line)
        if not m or m.group("ref").startswith(ALLOWED_UNPINNED):
            continue
        ref, comment = m.group("ref"), m.group("comment")
        assert SHA_REF.match(ref), f"{path.name}: {ref} must be pinned to a 40-hex commit SHA"
        assert comment and comment.startswith("v"), f"{path.name}: {ref} needs a '# vN' comment"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflows_parse_and_are_least_privilege(path: Path) -> None:
    doc = yaml.safe_load(path.read_text())
    assert isinstance(doc, dict) and "jobs" in doc
    perms = doc.get("permissions")
    assert perms is not None, f"{path.name} must declare top-level permissions"
    assert perms == {} or all(v == "read" for v in perms.values()), path.name
    text = path.read_text()
    assert "secrets: inherit" not in text, f"{path.name} must not inherit secrets"
    assert "cancel-in-progress: true" not in text, f"{path.name} must not cancel in-progress runs (required checks)"


def test_ci_status_is_the_fan_in() -> None:
    # ci-status is the only required check, so it must wait on every other CI job.
    jobs = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())["jobs"]
    status = jobs["ci-status"]
    assert status["if"] == "always()"
    assert set(status["needs"]) == set(jobs) - {"ci-status"}


def test_release_python_dry_run_tests_the_checked_package_and_version() -> None:
    # The test job builds what the check job validated, so its inputs must come from the check's outputs.
    jobs = yaml.safe_load((REPO / ".github/workflows/release-python-dry-run.yml").read_text())["jobs"]
    assert set(jobs["check"]["outputs"]) == {"package", "version", "prerelease"}
    assert jobs["test"]["uses"] == "./.github/workflows/_python-package.yml"
    assert jobs["test"]["with"]["package"] == "${{ needs.check.outputs.package }}"
    assert jobs["test"]["with"]["version"] == "${{ needs.check.outputs.version }}"


def test_release_python_only_runs_for_published_releases() -> None:
    # No manual trigger: publishing a GitHub release is the only way to publish a package
    doc = yaml.safe_load((REPO / ".github/workflows/release-python.yml").read_text())
    assert doc[True] == {"release": {"types": ["published"]}}  # PyYAML reads the `on` key as True


def test_only_the_publish_jobs_can_publish() -> None:
    # PyPI's trusted publishing needs a job in the publishing workflow itself (not a reusable
    # workflow) with an OIDC token. No other job gets one, and no job can change the repository or
    # its releases.
    token_jobs: set[str] = set()
    for path in WORKFLOWS:
        for name, job in yaml.safe_load(path.read_text())["jobs"].items():
            permissions = job.get("permissions", {})
            assert permissions.get("contents") != "write", f"{path.name}: {name}"
            if permissions.get("id-token") == "write":
                token_jobs.add(f"{path.name}:{name}")
                assert "uses" not in job, f"{path.name}: {name}"
                assert job["environment"] in ("testpypi", "pypi"), f"{path.name}: {name}"
    assert token_jobs == {"release-python.yml:publish-testpypi", "release-python.yml:publish-pypi"}


def test_release_python_reads_outputs_the_dry_run_provides() -> None:
    release = (REPO / ".github/workflows/release-python.yml").read_text()
    dry_run = yaml.safe_load((REPO / ".github/workflows/release-python-dry-run.yml").read_text())
    outputs = dry_run[True]["workflow_call"]["outputs"]
    assert set(re.findall(r"needs\.dry-run\.outputs\.([\w-]+)", release)) <= set(outputs)
    for name, output in outputs.items():
        assert output["value"] == f"${{{{ jobs.check.outputs.{name} }}}}"
        assert name in dry_run["jobs"]["check"]["outputs"]

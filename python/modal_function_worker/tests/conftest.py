"""Common pytest hooks and fixtures for this package."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.package_meta import load_package_meta
from tests.helpers.provenance import ProvenanceError, check_provenance

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart(session: pytest.Session) -> None:
    """Abort unless the installed package is a clean, non-editable install."""
    if hasattr(session.config, "workerinput"):
        return
    meta = load_package_meta(PACKAGE_ROOT)
    try:
        check_provenance(meta.published_name, meta.package_relpath)
    except ProvenanceError as exc:
        pytest.exit(f"provenance guard failed: {exc}", returncode=1)

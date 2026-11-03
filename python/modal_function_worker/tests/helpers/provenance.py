"""Prove that the installed package is a clean, non-editable install of its distribution.

The package's root API (e.g. ``temporalio.worker_integrations.foo.bar``) is nested inside
namespaces it doesn't own: ``temporalio`` is a regular package installed by the SDK, and the
levels below it are shared with the repository's other packages. Python only looks for
``temporalio``'s submodules next to the SDK's installed copy, so an editable install can't expose
the current version of the root API from ``src/`` that a developer may be working on. Tests
therefore run against a regular, non-editable install in the virtual environment, which means
the code under test is whatever is installed there. That may not match ``src/``: it could be a
stale build, have leftover or overwritten files, or overlap with another distribution that ships
the same paths.

The conftest runs this guard before any test, and aborts if anything about the installed package
being tested is incorrect:

- the package isn't installed
- the package is installed in editable mode
- a file the distribution installed is missing, or no longer matches the hash in its RECORD
  (e.g. another distribution overwrote it)
- the package directory contains files the distribution doesn't own (e.g. leftovers from an
  earlier install)
- another installed distribution ships files under the same package path

This provenance guard tests what's installed for self-consistency, but it can't identify whether
the installation actually matches the current state of ``src/``; it could be a self-consistent
but outdated version of the package. This gap is covered by the ``test_installed_matches_source``
test.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import re
from pathlib import Path


class ProvenanceError(RuntimeError):
    """The installed package is not a clean build of ``src/``."""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def check_provenance(
    dist_name: str,
    pkg_rel: str,
) -> Path:
    """Verify the installed distribution and return the installed package directory.

    Args:
        dist_name: Distribution name, e.g. ``temporalio-worker-integrations-aws-lambda-worker``.
        pkg_rel: Root API as a relative path, e.g. ``temporalio/worker_integrations/aws/lambda_worker``.

    Raises:
        ProvenanceError: on an editable install, a RECORD mismatch, files under the package
            directory that this distribution does not own, or a second
            distribution shipping the same paths.
    """
    try:
        dist = importlib_metadata.distribution(dist_name)
    except importlib_metadata.PackageNotFoundError as exc:
        raise ProvenanceError(f"{dist_name} is not installed; run `make sync`") from exc

    # Not editable: an editable install can't extend the SDK-owned temporalio package from src/.
    direct_url = dist.read_text("direct_url.json")
    if direct_url and json.loads(direct_url).get("dir_info", {}).get("editable"):
        raise ProvenanceError(
            f"{dist_name} is installed editable, so temporalio.* cannot resolve to src/; "
            "run `make sync` (it exports UV_NO_EDITABLE=1)"
        )

    files = dist.files
    if files is None:
        raise ProvenanceError(f"{dist_name} has no RECORD; reinstall with `make sync`")

    # Files match RECORD: every file the wheel installed still exists with its recorded hash, so
    # nothing has overwritten it since.
    owned: set[str] = set()
    for record_path in files:
        if record_path.hash is None or str(record_path).endswith(".pyc"):
            continue
        path = Path(str(record_path.locate()))
        owned.add(os.path.normpath(str(path)))
        if not path.is_file():
            raise ProvenanceError(
                f"{record_path} is in RECORD but missing on disk; run `make sync`"
            )
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
            .rstrip(b"=")
            .decode()
        )
        if record_path.hash.mode != "sha256" or digest != record_path.hash.value:
            raise ProvenanceError(
                f"{record_path} differs from RECORD (overwritten by another distribution?); run `make sync`"
            )

    # No extra files: everything under the package directory is in RECORD, so no leftovers from an
    # earlier install or files written by another distribution.
    pkg_dir = Path(str(dist.locate_file(pkg_rel)))
    if not pkg_dir.is_dir():
        raise ProvenanceError(f"{pkg_dir} does not exist; run `make sync`")
    extras = {
        os.path.normpath(str(path))
        for path in pkg_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not path.name.endswith(".pyc")
    } - owned
    if extras:
        raise ProvenanceError(
            f"files under {pkg_dir} are not owned by {dist_name}: {sorted(extras)}; run `make sync`"
        )

    # No other owner: no other installed distribution ships files under the same package path.
    prefix = pkg_rel.rstrip("/") + "/"
    others = sorted(
        {
            other.metadata["Name"]
            for other in importlib_metadata.distributions()
            if _normalize(other.metadata["Name"]) != _normalize(dist_name)
            and any(
                str(f).replace(os.sep, "/").startswith(prefix)
                for f in (other.files or [])
            )
        }
    )
    if others:
        message = f"{prefix} is also shipped by {others}"
        raise ProvenanceError(message)
    return pkg_dir

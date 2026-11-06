"""The installed, non-editable copy of this package must be byte-identical to ``src/``.

Tests run against the package installed in the virtual environment, not ``src/`` (see
``tests/helpers/provenance.py`` for why). The provenance guard that ``conftest.py`` runs checks
that the installation is self-consistent: nothing is missing, modified, or shipped by another
distribution. It can't tell whether that installation was built from the current ``src/``, though;
e.g. it could be a stale build from before your latest edits. This test closes that gap by
requiring the installed package directory and ``src/`` to contain the same files with the same
contents.

``make test`` rebuilds the installation whenever ``src/`` changes, so this test normally fails only
when something bypasses that, e.g. running ``.venv/bin/pytest`` directly.
"""

import hashlib
import importlib.metadata as importlib_metadata
import os
from pathlib import Path

from tests.helpers.package_meta import load_package_meta

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
META = load_package_meta(PACKAGE_ROOT)


def _digests(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)).replace(os.sep, "/"): hashlib.sha256(
            path.read_bytes()
        ).digest()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not path.name.endswith(".pyc")
    }


def test_installed_matches_source() -> None:
    src_dir = PACKAGE_ROOT / "src" / META.package_relpath
    installed_dir = Path(
        str(
            importlib_metadata.distribution(META.published_name).locate_file(
                META.package_relpath
            )
        )
    )
    expected = _digests(src_dir)
    actual = _digests(installed_dir)
    assert set(actual) == set(expected), (
        f"installed file set differs from src/: missing={sorted(set(expected) - set(actual))} "
        f"extra={sorted(set(actual) - set(expected))}; run `make sync`"
    )
    mismatched = sorted(rel for rel in expected if expected[rel] != actual[rel])
    assert not mismatched, (
        f"installed files differ from src/: {mismatched}; run `make sync`"
    )

"""Parsing and validation of a package's integration.toml.

Schema:

    [package]
    published-name = "temporalio-worker-integrations-aws-lambda-worker"
    root-api = "temporalio.worker_integrations.aws.lambda_worker"   # root import path / namespace
    maturity = "public-preview"               # pre-release | public-preview | generally-available

    [ci]
    runtime-versions = ["3.10", "3.14"]       # first = minimum, last = maximum supported runtime

    [smoke]                                   # optional
    # Entry points under root-api (e.g. Python modules, TypeScript subpath exports, Java classes)
    # that the smoke test imports from a base install (without optional features such as Python
    # extras), in addition to root-api itself.
    imports = ["temporalio.worker_integrations.aws.lambda_worker.testing"]

Unknown tables and keys are errors, so that a misspelled optional key can't be silently ignored.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.common import load_toml

MATURITIES = ("generally-available", "public-preview", "pre-release")
# Table -> the keys it may contain.
SCHEMA = {
    "package": {"published-name", "root-api", "maturity"},
    "ci": {"runtime-versions"},
    "smoke": {"imports"},
}


class IntegrationTomlError(ValueError):
    """An integration.toml that doesn't match the schema. The message names the first problem."""


@dataclass(frozen=True)
class IntegrationMeta:
    published_name: str
    root_api: str
    maturity: str
    runtime_versions: tuple[str, ...]
    """Supported language runtime versions: first = minimum, last = maximum."""
    smoke_imports: tuple[str, ...] = ()
    """Entry points under `root_api` that the smoke test imports from a base install."""

    @classmethod
    def from_file(cls, path: Path) -> IntegrationMeta:
        try:
            data = load_toml(path)
        except tomllib.TOMLDecodeError as exc:
            raise IntegrationTomlError(f"cannot parse: {exc}") from exc
        package = _table(data, "package")
        ci = _table(data, "ci")
        smoke = _table(data, "smoke") if "smoke" in data else {}
        for name, table in data.items():
            if name not in SCHEMA:
                raise IntegrationTomlError(f"unknown table [{name}]")
            unknown = sorted(set(table) - SCHEMA[name]) if isinstance(table, dict) else []
            if unknown:
                raise IntegrationTomlError(f"unknown key(s) in [{name}]: {', '.join(unknown)}")

        maturity = _string(package, "maturity")
        if maturity not in MATURITIES:
            raise IntegrationTomlError(f"maturity must be one of {sorted(MATURITIES)} (got {maturity!r})")
        versions = ci.get("runtime-versions")
        if not isinstance(versions, list) or not versions or not all(isinstance(v, str) for v in versions):
            raise IntegrationTomlError("[ci] runtime-versions must be a non-empty list of strings")
        imports = smoke.get("imports", [])
        if not isinstance(imports, list) or not all(isinstance(i, str) and i for i in imports):
            raise IntegrationTomlError("[smoke] imports must be a list of non-empty strings")

        return cls(
            published_name=_string(package, "published-name"),
            root_api=_string(package, "root-api"),
            maturity=maturity,
            runtime_versions=tuple(versions),
            smoke_imports=tuple(imports),
        )


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    table = data.get(name)
    if not isinstance(table, dict):
        raise IntegrationTomlError(f"missing [{name}] table")
    return table


def _string(table: dict[str, Any], key: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise IntegrationTomlError(f"{key} must be a non-empty string (got {value!r})")
    return value

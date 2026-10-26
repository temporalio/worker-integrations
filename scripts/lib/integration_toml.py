"""Parsing and validation of a package's integration.toml.

Schema:

    [package]
    published-name = "temporalio-worker-integrations-aws-lambda-worker"
    root-api = "temporalio.worker_integrations.aws.lambda_worker"   # root import path / namespace
    maturity = "public-preview"               # pre-release | public-preview | generally-available

    [ci]
    runtime-versions = ["3.10", "3.14"]       # first = minimum, last = maximum supported runtime
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.common import load_toml

MATURITIES = ("generally-available", "public-preview", "pre-release")


class IntegrationTomlError(ValueError):
    """An integration.toml that doesn't match the schema. The message names the first problem."""


@dataclass(frozen=True)
class IntegrationMeta:
    published_name: str
    root_api: str
    maturity: str
    runtime_versions: tuple[str, ...]
    """Supported language runtime versions: first = minimum, last = maximum."""

    @classmethod
    def from_file(cls, path: Path) -> IntegrationMeta:
        try:
            data = load_toml(path)
        except tomllib.TOMLDecodeError as exc:
            raise IntegrationTomlError(f"cannot parse: {exc}") from exc
        package = _table(data, "package")
        ci = _table(data, "ci")

        maturity = _string(package, "maturity")
        if maturity not in MATURITIES:
            raise IntegrationTomlError(f"maturity must be one of {sorted(MATURITIES)} (got {maturity!r})")
        versions = ci.get("runtime-versions")
        if not isinstance(versions, list) or not versions or not all(isinstance(v, str) for v in versions):
            raise IntegrationTomlError("[ci] runtime-versions must be a non-empty list of strings")

        return cls(
            published_name=_string(package, "published-name"),
            root_api=_string(package, "root-api"),
            maturity=maturity,
            runtime_versions=tuple(versions),
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

"""The base class each language implements, and helpers shared between languages."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Protocol

from lib.common import Package
from lib.integration_toml import IntegrationMeta
from lib.release_version import ReleaseVersion


class CheckContext(Protocol):
    """What language checks need from the conventions checker."""

    root: Path

    def fail(self, msg: str) -> None: ...


class Language(ABC):
    """Everything the repository tooling knows about one language's packages."""

    name: ClassVar[str]
    """Language root folder, e.g. "python"."""
    name_help: ClassVar[str]
    """Help for new_package.py's --<name> option: what name it takes."""
    next_steps: ClassVar[str]
    """Printed after scaffolding a package with new_package.py.

    The {folder} placeholder will be replaced with the language-relative folder path
    of the newly scaffolded package when printed.
    """

    # -- scaffolding (scripts/new_package.py) ----------------------------------------------------
    @abstractmethod
    def package_folder(self, requested: str) -> str:
        """The language-relative package folder for a name passed to new_package.py's --<name> option.

        Raises ValueError if the name is invalid.
        """

    @abstractmethod
    def substitutions(self, requested: str, description: str, maturity: str) -> dict[str, str]:
        """Substitutions (placeholder -> value) to apply to template file contents and paths."""

    def scaffold(self, root: Path, requested: str, description: str, maturity: str) -> list[Path]:
        """Create the package from <name>/_template. Returns the files written."""
        folder = self.package_folder(requested)
        return render_template(root, self.name, folder, self.substitutions(requested, description, maturity))

    # -- conventions (scripts/ci/check_conventions.py) -------------------------------------------
    def check_root(self, ctx: CheckContext) -> None:
        """Checks the language root itself (e.g. its _shared/ folder)."""

    @abstractmethod
    def check_package(self, ctx: CheckContext, package: Package, meta: IntegrationMeta | None) -> None:
        """Language-specific checks for one package. `meta` is None if its integration.toml is invalid."""

    # -- releases (scripts/ci/check_release.py) --------------------------------------------------
    @abstractmethod
    def release_version(self, text: str) -> ReleaseVersion:
        """Parse a version as spelled in this language's registry and release tags.

        Without the release tag's "v": e.g. "1.2.3" for the tag python/<package>/v1.2.3.

        Raises ValueError if it isn't a version we release.
        """

    @abstractmethod
    def published_versions(self, published_name: str) -> list[str]:
        """Every version of a package in this language's registry.

        Spelled the way `release_version` takes them, e.g. without the "v" Go's module proxy uses.

        Includes versions that can't be installed anymore but can't be reused either (e.g. yanked
        ones). Empty if the package has never been published.
        """


def render_template(root: Path, language: str, folder: str, substitutions: dict[str, str]) -> list[Path]:
    """Copy <language>/_template to <language>/<folder>, dropping `.tmpl` and filling in placeholders."""
    template = root / language / "_template"
    target = root / language / folder
    written: list[Path] = []
    for src in sorted(template.rglob("*.tmpl")):
        rel = src.relative_to(template).as_posix().removesuffix(".tmpl")
        text = src.read_text(encoding="utf-8")
        for placeholder, value in substitutions.items():
            rel = rel.replace(placeholder, value)
            text = text.replace(placeholder, value)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written.append(dest)
    shutil.copyfile(root / "LICENSE", target / "LICENSE")  # committed copy; the conventions check will catch any drift
    written.append(target / "LICENSE")
    return written

"""Per-language repository rules: naming, conventions checks, and scaffolding (see AGENTS.md).

One module per language that has tooling, each defining a `Language` subclass. `lib.common.LANGUAGES`
lists every language root; `TOOLED_LANGUAGES` holds only the languages with a module here.
"""

from __future__ import annotations

from lib.languages._base import Language
from lib.languages.python import Python

TOOLED_LANGUAGES: dict[str, Language] = {language.name: language for language in (Python(),)}

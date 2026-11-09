"""Locale catalogs: one JSON file per locale in `locales/`, keyed by code.

Every catalog has exactly the same keys (a test checks it), so a code that
renders in one language renders in all of them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Final

LOCALES: Final = ("zh-CN", "en")


@dataclass(frozen=True, slots=True)
class Catalog:
    locale: str
    entries: dict[str, str]

    def text(self, key: str, **values: object) -> str:
        """The entry for `key` with `values` filled in; a missing key raises."""
        return self.entries[key].format(**values)

    def has(self, key: str) -> bool:
        return key in self.entries


@cache
def load_catalog(locale: str) -> Catalog:
    if locale not in LOCALES:
        raise ValueError(f"locale must be one of {LOCALES}")
    path = resources.files("weiqi.explain") / "locales" / f"{locale}.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in entries.items()
    ):
        raise ValueError(f"catalog {locale} must map strings to strings")
    return Catalog(locale, entries)

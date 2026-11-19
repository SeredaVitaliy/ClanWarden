"""Minimal i18n: string catalogs per language and a translator callable.

Every user-facing string lives in a catalog (``en.py``, ``ru.py``) under a key.
Code never contains UI text directly — it calls ``t("key", **params)``.
Adding a language means adding one file with the same keys; missing keys
fall back to English, so a partial translation never breaks the bot.
"""

from __future__ import annotations

from clanwarden.i18n import en, ru

DEFAULT_LANGUAGE = "en"

CATALOGS: dict[str, dict[str, str]] = {
    "en": en.STRINGS,
    "ru": ru.STRINGS,
}

LANGUAGE_NAMES = {code: catalog["language_name"] for code, catalog in CATALOGS.items()}


def normalize_language(code: str | None) -> str | None:
    """Map a Telegram ``language_code`` ('ru', 'en-US', 'uk') to a supported language."""
    if not code:
        return None
    base = code.lower().split("-")[0]
    return base if base in CATALOGS else None


class Translator:
    def __init__(self, language: str | None = None) -> None:
        self.language = language if language in CATALOGS else DEFAULT_LANGUAGE
        self._catalog = CATALOGS[self.language]

    def __call__(self, key: str, /, **params: object) -> str:
        template = self._catalog.get(key) or CATALOGS[DEFAULT_LANGUAGE][key]
        return template.format(**params) if params else template

    def __repr__(self) -> str:
        return f"Translator({self.language!r})"

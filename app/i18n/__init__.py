"""Internationalization support — simple key-based translations for zh_CN, en_US, ja_JP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_current_lang: str = "zh_CN"
_SUPPORTED = ("zh_CN", "en_US", "ja_JP")
_I18N_DIR = Path(__file__).parent

# Lazy-loaded translation cache: lang → dict
_cache: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    """Load and cache a language JSON file."""
    if lang not in _cache:
        fp = _I18N_DIR / f"{lang}.json"
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                _cache[lang] = json.load(f)
        else:
            _cache[lang] = {}
    return _cache[lang]


def set_language(lang: str) -> None:
    """Set the active language.  Falls back to zh_CN if unsupported."""
    global _current_lang
    _current_lang = lang if lang in _SUPPORTED else "zh_CN"


def current_language() -> str:
    """Return the current active language code."""
    return _current_lang


def supported_languages() -> tuple[str, ...]:
    """Return tuple of supported language codes."""
    return _SUPPORTED


def t(key: str, **kwargs: Any) -> str:
    """Translate *key* to the current language.

    Supports ``{name}``-style placeholders via keyword arguments::

        t("scan.found_n_games", count=42)
        # → "共 42 个游戏" (zh_CN)
        # → "Found 42 game(s)" (en_US)
    """
    table = _load(_current_lang)
    text = table.get(key)
    if text is None:
        # Fall back to zh_CN, then raw key
        text = _load("zh_CN").get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text

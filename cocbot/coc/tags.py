"""Теги игроков и кланов.

Тег в игре состоит из символов 0289PYLQGRJCUV. Игроки часто путают
букву O с нулём, пишут в нижнем регистре и забывают #, поэтому приводим
ввод к каноничному виду и проверяем алфавит до похода в API.
"""

from __future__ import annotations

import re
from urllib.parse import quote

TAG_ALPHABET = "0289PYLQGRJCUV"
_TAG_RE = re.compile(rf"^#[{TAG_ALPHABET}]{{3,12}}$")


def normalize_tag(raw: str | None) -> str | None:
    """'  #abc ' -> '#ABC'; 'O' меняем на '0'. Возвращает None, если тег невалиден."""
    if not raw:
        return None
    tag = raw.strip().upper().replace("O", "0")
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag if _TAG_RE.match(tag) else None


def encode_tag(tag: str) -> str:
    """'#ABC' -> '%23ABC' для подстановки в URL."""
    return quote(tag, safe="")

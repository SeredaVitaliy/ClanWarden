"""Player and clan tags.

In-game tags only use the characters 0289PYLQGRJCUV. People often type the
letter O instead of zero, use lowercase, or forget the #, so input is
normalized and validated before it ever reaches the API.
"""

from __future__ import annotations

import re
from urllib.parse import quote

TAG_ALPHABET = "0289PYLQGRJCUV"
_TAG_RE = re.compile(rf"^#[{TAG_ALPHABET}]{{3,12}}$")


def normalize_tag(raw: str | None) -> str | None:
    """'  #2pp ' -> '#2PP'; letter 'O' becomes '0'. Returns None for an invalid tag."""
    if not raw:
        return None
    tag = raw.strip().upper().replace("O", "0")
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag if _TAG_RE.match(tag) else None


def encode_tag(tag: str) -> str:
    """'#2PP' -> '%232PP' for use in a URL path."""
    return quote(tag, safe="")

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr)[^>]*>", re.I)
_SPACES = re.compile(r"[ \t ]+")
_NEWLINES = re.compile(r"\n\s*\n+")


def html_to_text(raw: str | None) -> str:
    """Convert (possibly double-escaped) HTML into readable plain text."""
    if not raw:
        return ""
    text = html.unescape(raw)
    if "&lt;" in text or "&amp;" in text:  # Greenhouse double-escapes content
        text = html.unescape(text)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub("", text)
    text = _SPACES.sub(" ", text)
    return _NEWLINES.sub("\n\n", text).strip()


def parse_datetime(value) -> datetime | None:
    """Parse ISO strings and epoch milliseconds into aware UTC datetimes."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def slugify(value: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:max_len].rstrip("-")

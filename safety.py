"""Small redaction, URL and local-path boundaries shared by the CLI."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def clean_text(value: str, limit: int) -> str:
    """Redact common credential patterns and remove terminal control characters."""
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)
    value = re.sub(
        r"(?i)\b(api[_ -]?key|password|secret|access[_ -]?token)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]", value,
    )
    return value[:limit]


def safe_url(value: str) -> str | None:
    """Accept public HTTP(S) source links, without credentials or control codes."""
    if not isinstance(value, str) or len(value) > 2000 or clean_text(value, 2000) != value:
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
            return None
        if any(char.isspace() for char in value) or host == "localhost" or host.endswith(".localhost"):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if "." not in host:
                return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
    except ValueError:
        return None


def validate_local_path(path: Path, approved: Path) -> None:
    """Reject escapes, symbolic links and Windows junctions before a write."""
    path = path.absolute()
    approved = approved.absolute()
    if not path.resolve().is_relative_to(approved) or not path.is_relative_to(approved):
        raise ValueError("Path outside approved directory")
    current = path
    while True:
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("Linked paths are not allowed")
        if current == approved.parent:
            break
        if current.parent == current:
            raise ValueError("Invalid approved path")
        current = current.parent

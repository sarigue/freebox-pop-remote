"""Pure helper functions."""

import re


def decode_mdns_property(value: bytes | str | None) -> str:
    """Decode a zeroconf TXT property without raising on invalid UTF-8."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def safe_host_dir(host: str) -> str:
    """Return a filesystem-safe directory component for an IP/hostname."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", host)

"""The one place that decides which IP a request came from. Implements D-045.

Used for EVERY rate-limit key and for the IP written into audit events; nothing else in the
code base reads `X-Forwarded-For` (uvicorn's `--proxy-headers` is off, so `request.client` is
always the real socket peer).

- `TRUSTED_PROXY_HOPS=0` (development, tests): the header is ignored; the socket peer is used.
- `TRUSTED_PROXY_HOPS=N` (production: 1, behind Render's proxy): the client is the N-th entry
  counted from the RIGHT of `X-Forwarded-For`. A client can prepend fake values on the left,
  but cannot change what the trusted proxy appends on the right.
- A missing, short or malformed header falls back to the socket peer.

Diagnostic (temporary, D-045 live verification): when the fallback happens while hops > 0, one
WARNING line records the header shape: line and entry counts, the rightmost entry as received
(max 64 chars) and the NAMES of proxy-related headers present. No header values other than that
one entry, and never cookies or tokens.
"""

import ipaddress
import logging

from fastapi import Request

UNKNOWN = "unknown"
logger = logging.getLogger("frontdesk.client_ip")

# Proxy-related headers whose presence (name only) is reported by the fallback diagnostic.
_PROXY_HEADER_NAMES = ("x-forwarded-for", "x-real-ip", "true-client-ip", "forwarded",
                       "x-forwarded-proto", "cf-connecting-ip")
_PROXY_HEADER_PREFIX = "x-render-"


def _peer(request: Request) -> str:
    return request.client.host if request.client else UNKNOWN


def _parse(value: str) -> str | None:
    """A canonical IP string, or None when `value` is not an IPv4/IPv6 address."""
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """Client address per D-045 (see module docstring)."""
    hops = request.app.state.settings.trusted_proxy_hops
    if hops <= 0:
        return _peer(request)
    # Several X-Forwarded-For header lines count as one list, in the order they were added.
    lines = request.headers.getlist("x-forwarded-for")
    entries = [part for line in lines for part in line.split(",")]
    parsed = _parse(entries[-hops]) if len(entries) >= hops else None
    if parsed is None:
        _log_fallback(request, len(lines), entries)
        return _peer(request)
    return parsed


def _log_fallback(request: Request, line_count: int, entries: list[str]) -> None:
    """One diagnostic line for a hops > 0 fallback: header shape and names only (see module doc)."""
    names = sorted({name for name in request.headers.keys()
                    if name in _PROXY_HEADER_NAMES or name.startswith(_PROXY_HEADER_PREFIX)})
    rightmost = repr(entries[-1][:64]) if entries else "none"
    logger.warning("client_ip fallback to peer: xff_lines=%d xff_entries=%d rightmost=%s "
                   "proxy_headers=%s", line_count, len(entries), rightmost,
                   ",".join(names) or "none")

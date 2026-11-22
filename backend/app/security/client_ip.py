"""The one place that decides which IP a request came from. Implements D-045 / D-046.

Used for EVERY rate-limit key and for the IP written into audit events; nothing else in the
code base reads `X-Forwarded-For`, `CF-Connecting-IP` or the raw peer (uvicorn's `--proxy-headers`
is off, so `request.client` is always the real socket peer).

- `TRUSTED_PROXY_HOPS=0` (development, tests): the header is ignored; the socket peer is used.
- `TRUSTED_PROXY_HOPS=N`: the client is the N-th entry counted from the RIGHT of
  `X-Forwarded-For`. Production on Render is 3 (D-046): Render delivers
  `<client>, <Cloudflare edge>, <Render internal 10.x>`. A client can prepend fake values on the
  left, but cannot change what the proxies append on the right.
- A missing, short or malformed header falls back to the socket peer.

Tripwire (D-046): when hops > 0 and the request carries `CF-Connecting-IP`, a chosen IP that
differs from it logs one WARNING without IP values ("proxy chain may have changed").
`CF-Connecting-IP` is compared, never used.

Diagnostic (DEBUG, kept from the D-045/D-046 live diagnosis): on a fallback to the peer or a
non-global chosen entry, one line records the header shape: line and entry counts, the kind of
each entry (global/private/invalid, no values), the rightmost entry as received (max 64 chars),
whether the result equals the peer, and the NAMES of proxy-related headers present. Never
cookies or tokens.
"""

import ipaddress
import logging

from fastapi import Request

UNKNOWN = "unknown"
logger = logging.getLogger("frontdesk.client_ip")

TRIPWIRE_MESSAGE = "client-ip mismatch: proxy chain may have changed"

# Proxy-related headers whose presence (name only) is reported by the diagnostic.
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
    """Client address per D-045 / D-046 (see module docstring)."""
    hops = request.app.state.settings.trusted_proxy_hops
    if hops <= 0:
        return _peer(request)
    # Several X-Forwarded-For header lines count as one list, in the order they were added.
    lines = request.headers.getlist("x-forwarded-for")
    entries = [part for line in lines for part in line.split(",")]
    parsed = _parse(entries[-hops]) if len(entries) >= hops else None
    result = parsed or _peer(request)
    if parsed is None or not ipaddress.ip_address(parsed).is_global:
        _log_diagnostic(request, "fallback to peer" if parsed is None else "non-global entry",
                        len(lines), entries, result)
    _tripwire(request, result)
    return result


def _tripwire(request: Request, result: str) -> None:
    """D-046: WARNING (no IP values) when the chosen IP differs from CF-Connecting-IP."""
    cf = request.headers.get("cf-connecting-ip")
    if cf is not None and _parse(cf) != result:
        logger.warning(TRIPWIRE_MESSAGE)


def _kind(entry: str) -> str:
    parsed = _parse(entry)
    if parsed is None:
        return "invalid"
    return "global" if ipaddress.ip_address(parsed).is_global else "private"


def _log_diagnostic(request: Request, reason: str, line_count: int, entries: list[str],
                    result: str) -> None:
    """One DEBUG line (hops > 0): header shape and header names only (see module doc)."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    names = sorted({name for name in request.headers.keys()
                    if name in _PROXY_HEADER_NAMES or name.startswith(_PROXY_HEADER_PREFIX)})
    rightmost = repr(entries[-1][:64]) if entries else "none"
    logger.debug("client_ip %s: xff_lines=%d xff_entries=%d rightmost=%s kinds=%s "
                 "peer_match=%s proxy_headers=%s", reason, line_count, len(entries), rightmost,
                 ",".join(_kind(e) for e in entries) or "none", result == _peer(request),
                 ",".join(names) or "none")

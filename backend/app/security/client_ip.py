"""The one place that decides which IP a request came from. Implements D-045.

Used for EVERY rate-limit key and for the IP written into audit events; nothing else in the
code base reads `X-Forwarded-For` (uvicorn's `--proxy-headers` is off, so `request.client` is
always the real socket peer).

- `TRUSTED_PROXY_HOPS=0` (development, tests): the header is ignored; the socket peer is used.
- `TRUSTED_PROXY_HOPS=N` (production: 1, behind Render's proxy): the client is the N-th entry
  counted from the RIGHT of `X-Forwarded-For`. A client can prepend fake values on the left,
  but cannot change what the trusted proxy appends on the right.
- A missing, short or malformed header falls back to the socket peer.
"""

import ipaddress

from fastapi import Request

UNKNOWN = "unknown"


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
    entries = [part for line in request.headers.getlist("x-forwarded-for")
               for part in line.split(",")]
    if len(entries) < hops:
        return _peer(request)
    return _parse(entries[-hops]) or _peer(request)

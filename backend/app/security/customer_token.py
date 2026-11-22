"""32-byte customer ticket token, hash storage, one-ticket scope. Implements: LEAK-1, IN-1,
SECURITY §1, §3, D-005, D-017.

The token is shown once (secret link, carried in the URL fragment) and sent back by the
customer page in the `X-Ticket-Token` header. Only sha256(token) is stored, in
tickets.customer_token_hash; a token resolves to exactly one ticket.
"""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from app.db import RequestContext, Tx
from app.models import Ticket

_MAX_TOKEN_LEN = 128


def generate_token() -> tuple[str, bytes]:
    """New customer token and the hash to store: (token, sha256(token))."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def customer_link(public_base_url: str, token: str) -> str:
    """The secret link PUBLIC_BASE_URL/t#<token>. The token is in the fragment, which browsers
    never send to a server (or in a Referer); the customer page moves it into the header."""
    return public_base_url.rstrip("/") + "/t#" + token


def hash_token(token: str) -> bytes:
    """sha256 of the token (the only stored form)."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def find_ticket(ctx: RequestContext, token: str | None) -> Ticket | None:
    """The single ticket this token opens, or None."""
    if not token or len(token) > _MAX_TOKEN_LEN:
        return None
    return ctx.session.scalars(
        select(Ticket).where(Ticket.customer_token_hash == hash_token(token))
    ).one_or_none()


def require_customer_ticket(
    ctx: Tx,
    x_ticket_token: Annotated[str | None, Header(alias="X-Ticket-Token")] = None,
) -> Ticket:
    """SECURITY §3: the ticket for the X-Ticket-Token header, else 404 (I-14: a wrong token
    is indistinguishable from a missing ticket)."""
    ticket = find_ticket(ctx, x_ticket_token)
    if ticket is None:
        raise HTTPException(404, detail={"error": "not_found", "message": "Ticket not found."})
    return ticket


CustomerTicket = Annotated[Ticket, Depends(require_customer_ticket)]

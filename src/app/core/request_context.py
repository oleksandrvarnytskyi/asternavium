# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-request context shared by middleware, logging and error handlers."""

import re
import uuid
from contextvars import ContextVar
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER: Final = "X-Request-ID"
_VALID_REQUEST_ID: Final = re.compile(r"[A-Za-z0-9._-]{1,64}")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the ID of the request being handled, or ``None`` outside a request."""
    return _request_id.get()


def _resolve_request_id(incoming: str | None) -> str:
    """Reuse a well-formed upstream request ID, otherwise generate a new one."""
    if incoming is not None and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestIdMiddleware:
    """Assign a request ID to every HTTP request and echo it in the response headers.

    The context variable is deliberately not reset after the request: the server error
    handler runs outside this middleware and still needs it. Each request runs in its own
    copied context, so the value does not leak between requests.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI call."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(REQUEST_ID_HEADER.lower().encode("latin-1"))
        request_id = _resolve_request_id(incoming.decode("latin-1") if incoming else None)
        _request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1"))
                )
            await send(message)

        await self._app(scope, receive, send_with_request_id)

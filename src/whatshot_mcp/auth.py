"""Request-scoped Developer API credential handling."""

from __future__ import annotations

import re
from contextvars import ContextVar

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_DEVELOPER_API_KEY_PATTERN = re.compile(r"wh_live_[A-Za-z0-9_-]{43}\Z")
_current_developer_api_key: ContextVar[str | None] = ContextVar(
    "whatshot_current_developer_api_key",
    default=None,
)


def current_developer_api_key() -> str | None:
    """Return the Developer API key bound to the current HTTP request."""

    return _current_developer_api_key.get()


class BearerPassthroughAuthMiddleware:
    """Require a WhatsHot Developer API key and bind it to this request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        api_key = _extract_developer_api_key(scope)
        if api_key is None:
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={
                    "Cache-Control": "no-store",
                    "WWW-Authenticate": "Bearer",
                },
            )
            await response(scope, receive, send)
            return

        context_token = _current_developer_api_key.set(api_key)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_developer_api_key.reset(context_token)


def _extract_developer_api_key(scope: Scope) -> str | None:
    values = [
        value
        for name, value in scope.get("headers", [])
        if name.lower() == b"authorization"
    ]
    if len(values) != 1:
        return None
    authorization = values[0].decode("latin-1")
    scheme, separator, credential = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer":
        return None
    if not _DEVELOPER_API_KEY_PATTERN.fullmatch(credential):
        return None
    return credential

"""Bearer-token gate for the streamable-HTTP transport.

stdio needs no auth -- the client is whoever spawned the process. HTTP exposes
the tools to the network, so it sits behind the same static bearer keys the
sibling services use (constant-time comparison; 401 with ``WWW-Authenticate``
otherwise). A plain ASGI wrapper, not the SDK's OAuth machinery: the
platform's auth layer is a shared demo key, not an authorization server.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_UNAUTHORIZED_BODY = json.dumps(
    {"error": "missing or invalid API key (send 'Authorization: Bearer <key>')"}
).encode()


class BearerAuthMiddleware:
    """Reject HTTP requests whose ``Authorization`` header matches no known key.

    Non-HTTP scopes (lifespan) pass through untouched -- the wrapped app owns
    its own startup/shutdown.
    """

    def __init__(self, app: AsgiApp, api_keys: frozenset[str]) -> None:
        self._app = app
        self._api_keys = api_keys

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers: dict[bytes, bytes] = dict(scope.get("headers") or [])
        scheme, _, token = headers.get(b"authorization", b"").decode("latin-1").partition(" ")
        token = token.strip()
        authorized = scheme.lower() == "bearer" and any(
            secrets.compare_digest(token, key) for key in self._api_keys
        )
        if authorized:
            await self._app(scope, receive, send)
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                    (b"content-length", str(len(_UNAUTHORIZED_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})

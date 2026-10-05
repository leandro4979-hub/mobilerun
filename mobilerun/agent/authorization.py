"""Optional CARINA authorization gate for agent tool execution.

When CARINA_AUTH_URL is configured, every ToolRegistry execution is submitted
to CARINA before the underlying tool is called. The integration is fail-closed:
network errors, timeouts, malformed responses, and non-AUTHORIZED decisions all
block execution.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse

if TYPE_CHECKING:
    from mobilerun.agent.action_context import ActionContext


@dataclass(frozen=True)
class AuthorizationDecision:
    authorized: bool
    reason: str = ""
    decision_id: str | None = None


class ActionAuthorizer(Protocol):
    async def authorize(
        self, action: str, arguments: dict[str, Any], ctx: "ActionContext"
    ) -> AuthorizationDecision: ...


class CarinaHTTPAuthorizer:
    """Authorize Mobilerun tool calls through CARINA's local policy endpoint."""

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        timeout: float = 2.0,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("CARINA authorization URL must be an absolute http(s) URL")
        if timeout <= 0:
            raise ValueError("CARINA authorization timeout must be greater than zero")
        self.url = url
        self.token = token
        self.timeout = timeout

    async def authorize(
        self, action: str, arguments: dict[str, Any], ctx: "ActionContext"
    ) -> AuthorizationDecision:
        payload = self._build_payload(action, arguments, ctx)
        return await asyncio.to_thread(self._authorize_sync, payload)

    def _build_payload(
        self, action: str, arguments: dict[str, Any], ctx: "ActionContext"
    ) -> dict[str, Any]:
        shared_state = getattr(ctx, "shared_state", None)
        return {
            "intent": {
                "action": action,
                "arguments": arguments,
            },
            "context": {
                "platform": getattr(shared_state, "platform", None),
                "current_app": getattr(shared_state, "current_app", None),
            },
            "requested_transition": "RESERVED->AUTHORIZED",
            "executor": "mobilerun",
        }

    def _authorize_sync(self, payload: dict[str, Any]) -> AuthorizationDecision:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            self.url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"CARINA authorization request failed: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CARINA returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("CARINA returned a non-object authorization response")

        authorized = data.get("authorized") is True
        decision = str(data.get("decision", "")).upper()
        state = str(data.get("state", "")).upper()
        authorized = authorized or decision == "AUTHORIZED" or state == "AUTHORIZED"

        reason = str(data.get("reason") or data.get("message") or "")
        decision_id = data.get("decision_id") or data.get("id")
        if decision_id is not None:
            decision_id = str(decision_id)

        if not authorized and not reason:
            reason = decision or state or "CARINA did not return AUTHORIZED"

        return AuthorizationDecision(
            authorized=authorized,
            reason=reason,
            decision_id=decision_id,
        )


def authorizer_from_env() -> ActionAuthorizer | None:
    """Build the CARINA authorizer when CARINA_AUTH_URL is configured."""

    url = os.getenv("CARINA_AUTH_URL", "").strip()
    if not url:
        return None

    token = os.getenv("CARINA_AUTH_TOKEN") or None
    timeout_raw = os.getenv("CARINA_AUTH_TIMEOUT", "2.0")
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise ValueError("CARINA_AUTH_TIMEOUT must be a number") from exc

    return CarinaHTTPAuthorizer(url, token=token, timeout=timeout)

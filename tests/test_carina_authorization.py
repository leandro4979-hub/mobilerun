from types import SimpleNamespace

import pytest

from mobilerun.agent.authorization import AuthorizationDecision, authorizer_from_env
from mobilerun.agent.tool_registry import ToolRegistry


class FakeAuthorizer:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.calls = []

    async def authorize(self, action, arguments, ctx):
        self.calls.append((action, arguments, ctx))
        if self.error:
            raise self.error
        return self.decision


def make_ctx():
    return SimpleNamespace(
        shared_state=SimpleNamespace(platform="ios", current_app="Settings")
    )


@pytest.mark.asyncio
async def test_authorized_action_executes():
    called = []
    authorizer = FakeAuthorizer(AuthorizationDecision(authorized=True))
    registry = ToolRegistry(authorizer=authorizer)

    async def action(value, *, ctx):
        called.append(value)
        return "ok"

    registry.register("tap", action, {}, "tap")
    result = await registry.execute("tap", {"value": 7}, make_ctx())

    assert result.success is True
    assert called == [7]
    assert authorizer.calls[0][0] == "tap"


@pytest.mark.asyncio
async def test_denied_action_never_executes():
    called = []
    authorizer = FakeAuthorizer(
        AuthorizationDecision(authorized=False, reason="policy denied")
    )
    registry = ToolRegistry(authorizer=authorizer)

    async def action(*, ctx):
        called.append(True)
        return "should not run"

    registry.register("tap", action, {}, "tap")
    result = await registry.execute("tap", {}, make_ctx())

    assert result.success is False
    assert "policy denied" in result.summary
    assert called == []


@pytest.mark.asyncio
async def test_authorizer_failure_is_fail_closed():
    called = []
    authorizer = FakeAuthorizer(error=RuntimeError("offline"))
    registry = ToolRegistry(authorizer=authorizer)

    async def action(*, ctx):
        called.append(True)
        return "should not run"

    registry.register("tap", action, {}, "tap")
    result = await registry.execute("tap", {}, make_ctx())

    assert result.success is False
    assert "blocked" in result.summary.lower()
    assert "offline" in result.summary
    assert called == []


def test_authorizer_from_env_is_opt_in(monkeypatch):
    monkeypatch.delenv("CARINA_AUTH_URL", raising=False)
    assert authorizer_from_env() is None


def test_authorizer_from_env_rejects_bad_timeout(monkeypatch):
    monkeypatch.setenv("CARINA_AUTH_URL", "http://127.0.0.1:51001/authorize")
    monkeypatch.setenv("CARINA_AUTH_TIMEOUT", "not-a-number")
    with pytest.raises(ValueError, match="CARINA_AUTH_TIMEOUT"):
        authorizer_from_env()

"""FakeProvider behavior — the test workhorse."""

from __future__ import annotations

import pytest

from wulin_mud.llm import FakeProvider, FakeProviderExhausted


async def test_default_response_is_returned_for_every_call() -> None:
    fp = FakeProvider(default="hello")
    assert await fp.generate(system="s", user="u") == "hello"
    assert await fp.generate(system="s", user="u") == "hello"
    assert len(fp.calls) == 2


async def test_queue_drains_in_order_then_falls_back_to_default() -> None:
    fp = FakeProvider(default="default", responses=["first", "second"])
    assert await fp.generate(system="s", user="u") == "first"
    assert await fp.generate(system="s", user="u") == "second"
    assert await fp.generate(system="s", user="u") == "default"


async def test_queue_without_default_raises_after_exhaustion() -> None:
    fp = FakeProvider(responses=["only"])
    assert await fp.generate(system="s", user="u") == "only"
    with pytest.raises(FakeProviderExhausted):
        await fp.generate(system="s", user="u")


async def test_calls_record_the_arguments() -> None:
    fp = FakeProvider(default="x")
    await fp.generate(system="SYS", user="USR", model="m", temperature=0.3, max_tokens=42)
    assert len(fp.calls) == 1
    call = fp.calls[0]
    assert call.system == "SYS"
    assert call.user == "USR"
    assert call.model == "m"
    assert call.temperature == 0.3
    assert call.max_tokens == 42


def test_queue_extends() -> None:
    fp = FakeProvider(default=None)
    fp.queue("a", "b", "c")
    assert fp.responses == ["a", "b", "c"]


def test_reset_clears_state() -> None:
    fp = FakeProvider(responses=["a", "b"])
    fp.calls.append(object())  # type: ignore[arg-type]
    fp.reset()
    assert fp.responses == []
    assert fp.calls == []

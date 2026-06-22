"""Tests for the streaming deliberate variant."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from magi.config import ResolvedAgent
from magi.deliberation import AgentVote, deliberate_streaming


def _make_agent(name: str) -> ResolvedAgent:
    return ResolvedAgent(
        name=name,
        provider_key="anthropic",
        base_url="https://example.invalid/v1/",
        api_key="test",
        model="claude-haiku-4-5",
        temperature=0.4,
        max_tokens=220,
        timeout=60.0,
        system_prompt="test prompt",
    )


def _vote(name: str, verdict: str = "APPROVE") -> AgentVote:
    return AgentVote(
        name=name, verdict=verdict, confidence=80,  # type: ignore[arg-type]
        reasoning="stub", provider="anthropic", model="claude-haiku-4-5",
    )


@pytest.mark.asyncio
async def test_streaming_invokes_callback_per_vote():
    """on_vote fires once for each completed agent."""
    agents = [_make_agent(n) for n in ("CASPER-3", "MELCHIOR-1", "BALTHASAR-2")]

    async def fake_deliberate_one(agent, query):
        return _vote(agent.name)

    seen: list[str] = []

    with patch("magi.deliberation.deliberate_one", side_effect=fake_deliberate_one):
        votes = await deliberate_streaming(
            agents, "test query", on_vote=lambda v: seen.append(v.name)
        )

    assert sorted(seen) == ["BALTHASAR-2", "CASPER-3", "MELCHIOR-1"]
    assert [v.name for v in votes] == ["CASPER-3", "MELCHIOR-1", "BALTHASAR-2"]


@pytest.mark.asyncio
async def test_streaming_preserves_input_order_under_arrival_skew():
    """Even if agents finish out of order, returned votes match input order."""
    agents = [_make_agent(n) for n in ("CASPER-3", "MELCHIOR-1", "BALTHASAR-2")]
    delays = {"CASPER-3": 0.03, "MELCHIOR-1": 0.0, "BALTHASAR-2": 0.015}

    async def fake_deliberate_one(agent, query):
        await asyncio.sleep(delays[agent.name])
        return _vote(agent.name)

    arrivals: list[str] = []

    with patch("magi.deliberation.deliberate_one", side_effect=fake_deliberate_one):
        votes = await deliberate_streaming(
            agents, "test", on_vote=lambda v: arrivals.append(v.name)
        )

    # Arrival order reflects completion time, not declaration order.
    assert arrivals == ["MELCHIOR-1", "BALTHASAR-2", "CASPER-3"]
    # Return order still matches input order.
    assert [v.name for v in votes] == ["CASPER-3", "MELCHIOR-1", "BALTHASAR-2"]


@pytest.mark.asyncio
async def test_streaming_without_callback_still_returns_votes():
    """on_vote is optional."""
    agents = [_make_agent("CASPER-3")]

    async def fake_deliberate_one(agent, query):
        return _vote(agent.name)

    with patch("magi.deliberation.deliberate_one", side_effect=fake_deliberate_one):
        votes = await deliberate_streaming(agents, "test")

    assert len(votes) == 1 and votes[0].name == "CASPER-3"

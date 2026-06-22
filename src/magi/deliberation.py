"""Three-agent fan-out and vote tallying."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from openai import APIError, AsyncOpenAI

from .config import ResolvedAgent

Verdict = Literal["APPROVE", "REJECT", "CONDITIONAL"]


@dataclass
class AgentVote:
    """A single agent's verdict, ready to render or serialize."""

    name: str
    verdict: Verdict
    confidence: int
    reasoning: str
    provider: str
    model: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass
class Outcome:
    """The aggregated MAGI verdict across all agents."""

    label: str
    color: str  # rich style hint; see palette
    approves: int
    rejects: int
    conditionals: int
    votes: list[AgentVote]

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.label,
            "tally": {
                "approve": self.approves,
                "reject": self.rejects,
                "conditional": self.conditionals,
            },
            "votes": [v.to_dict() for v in self.votes],
        }


def extract_json(raw: str) -> dict:
    """Pull a JSON object out of model output that may be wrapped or noisy."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    if not s.startswith("{"):
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j > i:
            s = s[i:j + 1]
    return json.loads(s)


async def deliberate_one(agent: ResolvedAgent, query: str) -> AgentVote:
    """Send the query to a single agent and parse its verdict."""
    client = AsyncOpenAI(
        base_url=agent.base_url,
        api_key=agent.api_key,
        timeout=agent.timeout,
    )

    def fault(label: str) -> AgentVote:
        return AgentVote(
            name=agent.name,
            verdict="CONDITIONAL",
            confidence=0,
            reasoning=label,
            provider=agent.provider_key,
            model=agent.model,
        )

    try:
        resp = await client.chat.completions.create(
            model=agent.model,
            messages=[
                {"role": "system", "content": agent.system_prompt},
                {"role": "user", "content": f"QUERY: {query}"},
            ],
            max_tokens=agent.max_tokens,
            temperature=agent.temperature,
        )
    except APIError as e:
        return fault(f"API FAULT :: {type(e).__name__}")
    except Exception as e:  # noqa: BLE001
        return fault(f"TRANSPORT FAULT :: {type(e).__name__}")

    raw = (resp.choices[0].message.content or "").strip()
    try:
        data = extract_json(raw)
        verdict_raw = str(data.get("verdict", "")).upper()
        verdict: Verdict = (
            verdict_raw if verdict_raw in ("APPROVE", "REJECT", "CONDITIONAL")
            else "CONDITIONAL"
        )  # type: ignore[assignment]
        return AgentVote(
            name=agent.name,
            verdict=verdict,
            confidence=max(0, min(100, int(data.get("confidence", 50)))),
            reasoning=str(data.get("reasoning", "")).strip() or "(no reasoning returned)",
            provider=agent.provider_key,
            model=agent.model,
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        return fault(f"MALFORMED RESPONSE :: {type(e).__name__}")


async def deliberate(agents: list[ResolvedAgent], query: str) -> list[AgentVote]:
    """Fan the query out to all agents in parallel."""
    return await asyncio.gather(*(deliberate_one(a, query) for a in agents))


async def deliberate_streaming(
    agents: list[ResolvedAgent],
    query: str,
    on_vote: Callable[[AgentVote], None] | None = None,
) -> list[AgentVote]:
    """Like :func:`deliberate`, but invoke ``on_vote`` as each vote arrives.

    The callback runs synchronously on the event loop thread, so it must
    be fast and non-blocking — typically just a state-dict update plus a
    ``Live.update()`` call.

    Returned votes preserve the original ``agents`` order regardless of
    completion order.
    """
    async def _one(agent: ResolvedAgent) -> AgentVote:
        vote = await deliberate_one(agent, query)
        if on_vote is not None:
            on_vote(vote)
        return vote

    return await asyncio.gather(*(_one(a) for a in agents))


def tally(votes: list[AgentVote]) -> Outcome:
    """Aggregate votes into a final MAGI outcome with majority rule."""
    from .render import GOLD, GREEN, RED  # local import to avoid cycle

    approves = sum(1 for v in votes if v.verdict == "APPROVE")
    rejects = sum(1 for v in votes if v.verdict == "REJECT")
    conds = sum(1 for v in votes if v.verdict == "CONDITIONAL")
    threshold = len(votes) // 2 + 1

    if approves >= threshold:
        label, color = "SOLUTION ADOPTED", GREEN
    elif rejects >= threshold:
        label, color = "SOLUTION REJECTED", RED
    elif conds >= threshold:
        label, color = "DELIBERATION ONGOING", GOLD
    else:
        label, color = "TRIPLEX DEADLOCK :: MANUAL OVERRIDE REQUIRED", RED

    return Outcome(
        label=label,
        color=color,
        approves=approves,
        rejects=rejects,
        conditionals=conds,
        votes=votes,
    )

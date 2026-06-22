"""Terminal rendering for MAGI deliberation results.

The palette is exposed at module scope so other modules (e.g. tally
colour selection) can reference the same constants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from .deliberation import AgentVote, Outcome, Verdict, deliberate_streaming

if TYPE_CHECKING:
    from .config import ResolvedAgent

# ── NERV palette ─────────────────────────────────────────────────────────
AMBER = "#ff6b00"
GOLD = "#ffaa00"
GREEN = "#00ff66"
RED = "#ff0033"
DIM = "#663300"


def verdict_color(v: Verdict) -> str:
    return {"APPROVE": GREEN, "REJECT": RED, "CONDITIONAL": GOLD}[v]


def render_header(query: str, console: Console) -> None:
    console.print(Panel(
        Align.center(Group(
            Text("MAGI SYSTEM // DELIBERATION", style=f"bold {AMBER}"),
            Text(f'QUERY: "{query}"', style=GOLD),
        )),
        border_style=AMBER,
        padding=(0, 2),
    ))
    console.print()


def render_agent_panel(v: AgentVote) -> Panel:
    vc = verdict_color(v.verdict)
    body = Group(
        Text.assemble(("verdict     ", GOLD), ("│ ", DIM), (v.verdict, f"bold {vc}")),
        Text.assemble(("confidence  ", GOLD), ("│ ", DIM), (f"{v.confidence}%", AMBER)),
        Text.assemble(("backend     ", GOLD), ("│ ", DIM), (v.provider, AMBER)),
        Text.assemble(("model       ", GOLD), ("│ ", DIM), (v.model, DIM)),
        Text(""),
        Text(v.reasoning, style=AMBER),
    )
    return Panel(
        body,
        title=f"[bold {AMBER}]◢ {v.name} ◣[/]",
        border_style=AMBER,
        width=42,
        padding=(1, 2),
    )


def render_verdict(outcome: Outcome, console: Console) -> None:
    tally = Text.assemble(
        (f"  {outcome.approves} APPROVE  ", GREEN), ("//", DIM),
        (f"  {outcome.rejects} REJECT  ", RED), ("//", DIM),
        (f"  {outcome.conditionals} CONDITIONAL  ", GOLD),
    )
    console.print(Panel(
        Align.center(Group(
            tally, Text(""),
            Text(f"▸▸  {outcome.label}  ◂◂", style=f"bold {outcome.color}"),
        )),
        title=f"[bold {AMBER}]MAGI VERDICT[/]",
        border_style=outcome.color,
        padding=(0, 2),
    ))


def render(query: str, outcome: Outcome, console: Console) -> None:
    """Render the full MAGI deliberation panel for a completed outcome."""
    render_header(query, console)
    console.print(
        Columns([render_agent_panel(v) for v in outcome.votes], equal=True, expand=False)
    )
    console.print()
    render_verdict(outcome, console)


# ── Live streaming render ────────────────────────────────────────────────
def render_pending_panel(name: str) -> Panel:
    """Placeholder panel for an agent whose vote hasn't arrived yet."""
    body = Group(
        Spinner("dots", text=Text("DELIBERATING...", style=AMBER), style=AMBER),
        Text(""),
        Text("awaiting transmission from NERV", style=DIM),
    )
    return Panel(
        body,
        title=f"[bold {DIM}]◢ {name} ◣[/]",
        border_style=DIM,
        width=42,
        padding=(1, 2),
    )


def _build_live_renderable(
    query: str,
    agent_names: list[str],
    votes_state: dict[str, AgentVote | None],
) -> Group:
    """Build the header + columns of (pending or filled) panels."""
    header = Panel(
        Align.center(Group(
            Text("MAGI SYSTEM // DELIBERATION", style=f"bold {AMBER}"),
            Text(f'QUERY: "{query}"', style=GOLD),
        )),
        border_style=AMBER,
        padding=(0, 2),
    )
    panels = [
        render_agent_panel(v) if (v := votes_state.get(name)) is not None
        else render_pending_panel(name)
        for name in agent_names
    ]
    return Group(header, Text(""), Columns(panels, equal=True, expand=False))


async def render_live(
    agents: "list[ResolvedAgent]",
    query: str,
    console: Console,
) -> list[AgentVote]:
    """Stream the deliberation, lighting up each panel as its vote lands.

    Returns the completed votes in the original agent order. Does NOT
    render the final verdict tally — call :func:`render_verdict` after
    :func:`~magi.deliberation.tally`.
    """
    agent_names = [a.name for a in agents]
    votes_state: dict[str, AgentVote | None] = {name: None for name in agent_names}

    with Live(
        _build_live_renderable(query, agent_names, votes_state),
        console=console,
        refresh_per_second=12.5,
        transient=False,
    ) as live:
        def on_vote(vote: AgentVote) -> None:
            votes_state[vote.name] = vote
            live.update(_build_live_renderable(query, agent_names, votes_state))

        votes = await deliberate_streaming(agents, query, on_vote=on_vote)

    console.print()
    return votes

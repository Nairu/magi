"""Command-line interface for MAGI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from rich.console import Console

from . import __version__
from .config import build_agents
from .deliberation import deliberate, tally
from .render import AMBER, DIM, GOLD, render

SAMPLE_CONFIG_TOML = """\
# MAGI configuration. Drop at ~/.config/magi/config.toml.
# Any agent can be backed by any OpenAI-compatible endpoint.

[defaults]
temperature = 0.4
max_tokens  = 220
timeout     = 60.0

# ── Providers ────────────────────────────────────────────────
# Each provider is just a base URL + which env var holds its key.

[providers.anthropic]
base_url    = "https://api.anthropic.com/v1/"
api_key_env = "ANTHROPIC_API_KEY"

[providers.openai]
base_url    = "https://api.openai.com/v1/"
api_key_env = "OPENAI_API_KEY"

[providers.ollama]
base_url        = "http://localhost:11434/v1/"
api_key_env     = "OLLAMA_API_KEY"
api_key_default = "ollama"

[providers.openrouter]
base_url    = "https://openrouter.ai/api/v1/"
api_key_env = "OPENROUTER_API_KEY"

[providers.groq]
base_url    = "https://api.groq.com/openai/v1/"
api_key_env = "GROQ_API_KEY"

# ── Agents ───────────────────────────────────────────────────
# Three are canonical. Mix providers freely:
# claude in the cloud, llama at home, gpt for the vibes.

[agents."CASPER-3"]
provider    = "anthropic"
model       = "claude-haiku-4-5"
temperature = 0.2                  # cold rationalist
# Optional: override the personality prompt.
# Either inline:
#   system_prompt = \"\"\"You are CASPER...\"\"\"
# Or as a file:
#   system_prompt_file = "~/.config/magi/prompts/casper.md"

[agents."MELCHIOR-1"]
provider    = "ollama"
model       = "llama3.2:3b"
temperature = 0.5                  # cautious, runs locally

[agents."BALTHASAR-2"]
provider    = "openai"
model       = "gpt-4o-mini"
temperature = 0.7                  # warmest, most intuitive
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="magi",
        description="Three-agent MAGI deliberation system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Precedence (highest wins):\n"
            "  1. --set AGENT.KEY=VALUE\n"
            "  2. Env vars (MAGI_AGENT_<SLUG>_<KEY>, MAGI_DEFAULT_<KEY>)\n"
            "  3. ~/.config/magi/config.toml (or $MAGI_CONFIG)\n"
            "  4. Built-in defaults\n"
        ),
    )
    parser.add_argument("query", nargs="*", help="The question to deliberate.")
    parser.add_argument("-c", "--config", help="Path to a config TOML file.")
    parser.add_argument(
        "-s", "--set", dest="overrides", action="append", default=[],
        metavar="AGENT.KEY=VALUE",
        help="Override a config value. Repeatable. "
             "Examples: --set CASPER-3.model=claude-opus-4-7  "
             "--set MELCHIOR-1.temperature=0.8  "
             "--set defaults.max_tokens=300",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Emit a JSON document instead of the styled panel.",
    )
    parser.add_argument(
        "--no-spinner", action="store_true",
        help="Suppress the deliberation spinner (useful for CI).",
    )
    parser.add_argument(
        "--show-config", action="store_true",
        help="Print resolved agent configuration and exit.",
    )
    parser.add_argument(
        "--print-default-config", action="store_true",
        help="Print an example config TOML to stdout and exit.",
    )
    parser.add_argument("--version", action="version", version=f"magi {__version__}")
    return parser


def _show_config(agents, console: Console) -> None:
    for a in agents:
        console.print(
            f"[bold {AMBER}]{a.name}[/]  ←  "
            f"[{GOLD}]{a.provider_key}[/]:[{AMBER}]{a.model}[/]  "
            f"[{DIM}](T={a.temperature}, max={a.max_tokens}, "
            f"timeout={a.timeout}s, {a.base_url})[/]"
        )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.print_default_config:
        print(SAMPLE_CONFIG_TOML, end="")
        return 0

    try:
        agents = build_agents(config_path=args.config, cli_overrides=args.overrides)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    console = Console()

    if args.show_config:
        _show_config(agents, console)
        return 0

    if not args.query:
        parser.print_help()
        return 1

    query = " ".join(args.query)

    async def _run():
        return await deliberate(agents, query)

    if args.no_spinner or args.as_json:
        votes = asyncio.run(_run())
    else:
        with console.status(
            f"[{AMBER}]MAGI :: TRIPLEX DELIBERATION IN PROGRESS...[/]",
            spinner="dots",
            spinner_style=AMBER,
        ):
            votes = asyncio.run(_run())

    outcome = tally(votes)

    if args.as_json:
        print(json.dumps({"query": query, **outcome.to_dict()}, indent=2))
    else:
        render(query, outcome, console)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Configuration loading and resolution.

Precedence (highest wins):
    1. Command-line ``--set AGENT.KEY=VALUE`` overrides
    2. Environment variables (``MAGI_AGENT_<NAME>_<KEY>``, ``MAGI_DEFAULT_<KEY>``)
    3. TOML config file
    4. Built-in defaults

The TOML schema:

    [defaults]
    temperature = 0.4
    max_tokens  = 220
    timeout     = 60.0

    [providers.<name>]
    base_url        = "https://..."
    api_key_env     = "ENV_VAR_NAME"
    api_key_default = "optional fallback"

    [agents."<NAME>"]
    provider           = "anthropic"
    model              = "claude-haiku-4-5"
    temperature        = 0.2
    max_tokens         = 220
    timeout            = 60.0
    system_prompt      = "..."             # inline override
    system_prompt_file = "/path/to/file"   # OR file-based override
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .personalities import SYSTEM_PROMPTS

# ── Built-in defaults ────────────────────────────────────────────────────
DEFAULT_CONFIG: dict[str, Any] = {
    "defaults": {"temperature": 0.4, "max_tokens": 220, "timeout": 60.0},
    "providers": {
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1/",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1/",
            "api_key_env": "OPENAI_API_KEY",
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1/",
            "api_key_env": "OLLAMA_API_KEY",
            "api_key_default": "ollama",
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1/",
            "api_key_env": "OPENROUTER_API_KEY",
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1/",
            "api_key_env": "GROQ_API_KEY",
        },
        "lmstudio": {
            "base_url": "http://localhost:1234/v1/",
            "api_key_env": "LMSTUDIO_API_KEY",
            "api_key_default": "lmstudio",
        },
    },
    "agents": {
        "CASPER-3":    {"provider": "anthropic", "model": "claude-haiku-4-5", "temperature": 0.2},
        "MELCHIOR-1":  {"provider": "anthropic", "model": "claude-haiku-4-5", "temperature": 0.4},
        "BALTHASAR-2": {"provider": "anthropic", "model": "claude-haiku-4-5", "temperature": 0.7},
    },
}

# Keys that may be overridden per-agent via env vars or --set
SETTABLE_AGENT_KEYS = {
    "provider", "model", "temperature", "max_tokens", "timeout",
    "system_prompt", "system_prompt_file",
}
SETTABLE_DEFAULT_KEYS = {"temperature", "max_tokens", "timeout"}

# Numeric coercion hints
_FLOAT_KEYS = {"temperature", "timeout"}
_INT_KEYS = {"max_tokens"}


# ── Dataclasses ──────────────────────────────────────────────────────────
@dataclass
class ResolvedAgent:
    """An agent after all configuration sources have been merged."""

    name: str
    provider_key: str
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int
    timeout: float
    system_prompt: str


# ── Helpers ──────────────────────────────────────────────────────────────
def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _coerce(key: str, value: str) -> Any:
    if key in _FLOAT_KEYS:
        return float(value)
    if key in _INT_KEYS:
        return int(value)
    return value


def _agent_env_slug(name: str) -> str:
    """``CASPER-3`` -> ``CASPER_3`` for env var lookup."""
    return name.upper().replace("-", "_").replace(".", "_")


# ── Config discovery & loading ───────────────────────────────────────────
def find_config_path(explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit).expanduser()
    if env := os.environ.get("MAGI_CONFIG"):
        return Path(env).expanduser()
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    p = xdg / "magi" / "config.toml"
    return p if p.exists() else None


def load_config_file(explicit: str | None) -> dict[str, Any]:
    """Merge DEFAULT_CONFIG with user TOML (if present)."""
    path = find_config_path(explicit)
    if path is None or not path.exists():
        return _deep_merge(DEFAULT_CONFIG, {})
    with path.open("rb") as f:
        user = tomllib.load(f)
    return _deep_merge(DEFAULT_CONFIG, user)


# ── Override application ─────────────────────────────────────────────────
def apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply ``MAGI_*`` env vars on top of the config dict.

    Recognised forms:
        MAGI_DEFAULT_<KEY>=<value>            -> defaults.<key>
        MAGI_AGENT_<SLUG>_<KEY>=<value>       -> agents.<NAME>.<key>

    Agent names are matched against their slugged form (``CASPER-3`` ->
    ``CASPER_3``). Unknown agents are silently ignored to avoid surprises.
    """
    out = _deep_merge(cfg, {})
    agent_slugs = {_agent_env_slug(name): name for name in out["agents"]}

    for env_key, raw in os.environ.items():
        if not env_key.startswith("MAGI_"):
            continue

        if env_key.startswith("MAGI_DEFAULT_"):
            key = env_key[len("MAGI_DEFAULT_"):].lower()
            if key in SETTABLE_DEFAULT_KEYS:
                out.setdefault("defaults", {})[key] = _coerce(key, raw)
            continue

        if env_key.startswith("MAGI_AGENT_"):
            tail = env_key[len("MAGI_AGENT_"):]
            # Greedy: longest matching slug wins so we handle multi-word keys.
            match: tuple[str, str] | None = None
            for slug, name in agent_slugs.items():
                pfx = slug + "_"
                if tail.startswith(pfx):
                    key = tail[len(pfx):].lower()
                    if match is None or len(slug) > len(match[0]):
                        match = (slug, key)
            if match is None:
                continue
            _, key = match
            name = agent_slugs[match[0]]
            if key in SETTABLE_AGENT_KEYS:
                out["agents"].setdefault(name, {})[key] = _coerce(key, raw)

    return out


def apply_cli_overrides(cfg: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Apply ``--set AGENT.KEY=VALUE`` strings.

    Also accepts ``defaults.KEY=VALUE``.
    """
    out = _deep_merge(cfg, {})
    for spec in overrides:
        if "=" not in spec:
            raise ValueError(f"--set expects KEY=VALUE, got: {spec!r}")
        path, value = spec.split("=", 1)
        parts = path.split(".")
        if len(parts) != 2:
            raise ValueError(
                f"--set expects '<AGENT_OR_defaults>.<KEY>=VALUE', got: {spec!r}"
            )
        target, key = parts
        if target == "defaults":
            if key not in SETTABLE_DEFAULT_KEYS:
                raise ValueError(f"--set: unknown default key '{key}'")
            out.setdefault("defaults", {})[key] = _coerce(key, value)
        else:
            if target not in out["agents"]:
                raise ValueError(f"--set: unknown agent '{target}'")
            if key not in SETTABLE_AGENT_KEYS:
                raise ValueError(f"--set: unsettable key '{key}' for agent '{target}'")
            out["agents"][target][key] = _coerce(key, value)
    return out


# ── Final resolution ─────────────────────────────────────────────────────
def _resolve_system_prompt(name: str, agent_cfg: dict[str, Any]) -> str:
    """Pick the prompt to use, in order: inline > file > canonical default."""
    if "system_prompt" in agent_cfg and agent_cfg["system_prompt"]:
        return str(agent_cfg["system_prompt"])
    if path := agent_cfg.get("system_prompt_file"):
        p = Path(str(path)).expanduser()
        if not p.exists():
            raise ValueError(
                f"agent {name}: system_prompt_file '{p}' does not exist"
            )
        return p.read_text(encoding="utf-8").strip()
    if canonical := SYSTEM_PROMPTS.get(name):
        return canonical
    raise ValueError(
        f"agent {name}: no system prompt found. Either name the agent "
        f"one of {sorted(SYSTEM_PROMPTS)}, set system_prompt directly, "
        f"or set system_prompt_file."
    )


def resolve_agents(cfg: dict[str, Any]) -> list[ResolvedAgent]:
    """Turn a merged config dict into a list of fully-resolved agents."""
    defaults = cfg.get("defaults", {})
    providers = cfg["providers"]
    out: list[ResolvedAgent] = []

    for name, a in cfg["agents"].items():
        prov_key = a.get("provider")
        if not prov_key:
            raise ValueError(f"agent {name}: missing 'provider'")
        if prov_key not in providers:
            raise ValueError(
                f"agent {name}: unknown provider '{prov_key}'. "
                f"Known: {sorted(providers)}"
            )

        prov = providers[prov_key]
        env = prov.get("api_key_env")
        api_key = (os.environ.get(env, "") if env else "") or prov.get("api_key_default", "")
        if not api_key:
            raise ValueError(
                f"agent {name}: provider '{prov_key}' needs ${env} to be set "
                f"(or provide api_key_default in the provider config)"
            )

        out.append(ResolvedAgent(
            name=name,
            provider_key=prov_key,
            base_url=prov["base_url"],
            api_key=api_key,
            model=a["model"],
            temperature=float(a.get("temperature", defaults.get("temperature", 0.4))),
            max_tokens=int(a.get("max_tokens", defaults.get("max_tokens", 220))),
            timeout=float(a.get("timeout", defaults.get("timeout", 60.0))),
            system_prompt=_resolve_system_prompt(name, a),
        ))

    return out


# ── Convenience: build everything in one call ────────────────────────────
def build_agents(
    *,
    config_path: str | None = None,
    cli_overrides: list[str] | None = None,
) -> list[ResolvedAgent]:
    cfg = load_config_file(config_path)
    cfg = apply_env_overrides(cfg)
    if cli_overrides:
        cfg = apply_cli_overrides(cfg, cli_overrides)
    return resolve_agents(cfg)

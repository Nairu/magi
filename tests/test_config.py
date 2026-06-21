"""Tests for the config loading and override pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from magi.config import (
    DEFAULT_CONFIG,
    apply_cli_overrides,
    apply_env_overrides,
    build_agents,
    load_config_file,
    resolve_agents,
)


@pytest.fixture
def clean_env(monkeypatch):
    """Strip MAGI_* and provider key env vars so tests are deterministic."""
    for k in list(os.environ):
        if k.startswith(("MAGI_", "ANTHROPIC_", "OPENAI_", "GROQ_", "OPENROUTER_", "OLLAMA_", "LMSTUDIO_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-anthropic")
    return monkeypatch


def test_defaults_load_without_config(clean_env, tmp_path, monkeypatch):
    """No config file present -> built-in defaults are used."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = load_config_file(None)
    assert cfg["defaults"]["temperature"] == DEFAULT_CONFIG["defaults"]["temperature"]
    assert "CASPER-3" in cfg["agents"]


def test_toml_overrides_defaults(clean_env, tmp_path):
    p = tmp_path / "magi.toml"
    p.write_text(
        '[defaults]\ntemperature = 0.9\n'
        '[agents."CASPER-3"]\nprovider = "anthropic"\nmodel = "claude-opus-4-7"\n'
    )
    cfg = load_config_file(str(p))
    assert cfg["defaults"]["temperature"] == 0.9
    assert cfg["agents"]["CASPER-3"]["model"] == "claude-opus-4-7"
    # Other agents inherited from defaults
    assert cfg["agents"]["MELCHIOR-1"]["model"] == "claude-haiku-4-5"


def test_env_overrides_apply(clean_env, monkeypatch):
    monkeypatch.setenv("MAGI_DEFAULT_TEMPERATURE", "0.55")
    monkeypatch.setenv("MAGI_AGENT_CASPER_3_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("MAGI_AGENT_MELCHIOR_1_TEMPERATURE", "0.1")
    cfg = apply_env_overrides(load_config_file(None))
    assert cfg["defaults"]["temperature"] == 0.55
    assert cfg["agents"]["CASPER-3"]["model"] == "claude-opus-4-8"
    assert cfg["agents"]["MELCHIOR-1"]["temperature"] == 0.1


def test_cli_overrides_apply(clean_env):
    cfg = load_config_file(None)
    cfg = apply_cli_overrides(cfg, [
        "CASPER-3.model=gpt-4o-mini",
        "MELCHIOR-1.temperature=0.95",
        "defaults.max_tokens=400",
    ])
    assert cfg["agents"]["CASPER-3"]["model"] == "gpt-4o-mini"
    assert cfg["agents"]["MELCHIOR-1"]["temperature"] == 0.95
    assert cfg["defaults"]["max_tokens"] == 400


def test_cli_unknown_agent_rejected(clean_env):
    cfg = load_config_file(None)
    with pytest.raises(ValueError, match="unknown agent"):
        apply_cli_overrides(cfg, ["GHOST-99.model=anything"])


def test_cli_unsettable_key_rejected(clean_env):
    cfg = load_config_file(None)
    with pytest.raises(ValueError, match="unsettable key"):
        apply_cli_overrides(cfg, ["CASPER-3.base_url=https://nope"])


def test_precedence_cli_beats_env_beats_file(clean_env, tmp_path, monkeypatch):
    p = tmp_path / "magi.toml"
    p.write_text('[agents."CASPER-3"]\nmodel = "from-file"\n')
    monkeypatch.setenv("MAGI_AGENT_CASPER_3_MODEL", "from-env")

    cfg = load_config_file(str(p))
    assert cfg["agents"]["CASPER-3"]["model"] == "from-file"

    cfg = apply_env_overrides(cfg)
    assert cfg["agents"]["CASPER-3"]["model"] == "from-env"

    cfg = apply_cli_overrides(cfg, ["CASPER-3.model=from-cli"])
    assert cfg["agents"]["CASPER-3"]["model"] == "from-cli"


def test_resolve_agents_requires_api_key(clean_env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config_file(None)
    with pytest.raises(ValueError, match="needs \\$ANTHROPIC_API_KEY"):
        resolve_agents(cfg)


def test_resolve_agents_canonical_prompts(clean_env):
    cfg = load_config_file(None)
    agents = resolve_agents(cfg)
    by_name = {a.name: a for a in agents}
    assert "CASPER-3" in by_name
    assert "SCIENTIST" in by_name["CASPER-3"].system_prompt
    assert "MOTHER" in by_name["MELCHIOR-1"].system_prompt
    assert "WOMAN" in by_name["BALTHASAR-2"].system_prompt


def test_inline_prompt_override(clean_env):
    cfg = load_config_file(None)
    cfg["agents"]["CASPER-3"]["system_prompt"] = "You are a haiku poet."
    agents = resolve_agents(cfg)
    casper = next(a for a in agents if a.name == "CASPER-3")
    assert casper.system_prompt == "You are a haiku poet."


def test_file_prompt_override(clean_env, tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("You evaluate via vibes only.\n")
    cfg = load_config_file(None)
    cfg["agents"]["BALTHASAR-2"]["system_prompt_file"] = str(prompt_file)
    agents = resolve_agents(cfg)
    bal = next(a for a in agents if a.name == "BALTHASAR-2")
    assert bal.system_prompt == "You evaluate via vibes only."


def test_build_agents_end_to_end(clean_env, tmp_path, monkeypatch):
    p = tmp_path / "magi.toml"
    p.write_text(
        '[agents."CASPER-3"]\nprovider = "anthropic"\nmodel = "from-file"\n'
    )
    monkeypatch.setenv("MAGI_AGENT_MELCHIOR_1_TEMPERATURE", "0.95")
    agents = build_agents(
        config_path=str(p),
        cli_overrides=["BALTHASAR-2.model=gpt-4o-mini-from-cli"],
    )
    by_name = {a.name: a for a in agents}
    assert by_name["CASPER-3"].model == "from-file"
    assert by_name["MELCHIOR-1"].temperature == 0.95
    assert by_name["BALTHASAR-2"].model == "gpt-4o-mini-from-cli"

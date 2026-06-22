# MAGI

> *GOD'S IN HIS HEAVEN. ALL'S RIGHT WITH THE WORLD.*

A three-agent deliberation system in the style of the MAGI supercomputer
cluster from *Neon Genesis Evangelion*. Pose a question; three agents
(CASPER, MELCHIOR, BALTHASAR — the scientist, mother, and woman aspects
of Naoko Akagi) deliberate in parallel and return a tallied verdict
formatted like the show's iconic deliberation panels.

Each agent can be backed by **any OpenAI-compatible endpoint**, mixed and
matched freely: Anthropic Claude, OpenAI, Ollama, Groq, OpenRouter, LM
Studio, vLLM, your own gateway. Use a frontier model for one agent and a
local 3B for another — heterogeneity makes the disagreements more
interesting.

```
╭─ MAGI SYSTEM // DELIBERATION ─────────────────────────────────────╮
│                  QUERY: "should I deploy on a friday"             │
╰───────────────────────────────────────────────────────────────────╯

┌─ ◢ CASPER-3 ◣ ─────┐ ┌─ ◢ MELCHIOR-1 ◣ ───┐ ┌─ ◢ BALTHASAR-2 ◣ ──┐
│ verdict    │ REJECT │ │ verdict    │ REJECT │ │ verdict   │ COND. │
│ confidence │ 87%    │ │ confidence │ 92%    │ │ confidence │ 64%  │
│ backend    │ anthrop│ │ backend    │ ollama │ │ backend    │ openai│
│ ...                │ │ ...                │ │ ...                │
└────────────────────┘ └────────────────────┘ └────────────────────┘

╭─ MAGI VERDICT ────────────────────────────────────────────────────╮
│       2 APPROVE  //  0 REJECT  //  1 CONDITIONAL                  │
│              ▸▸  SOLUTION REJECTED  ◂◂                            │
╰───────────────────────────────────────────────────────────────────╯
```

## Install

### With uv (recommended)

```bash
git clone https://github.com/Nairu/magi
cd magi
uv sync
uv run magi --help
```

Or invoke directly without cloning, via the PEP 723 single-file variant
in the gist linked in the wiki.

### With pipx

```bash
pipx install git+https://github.com/Nairu/magi
```

### With Nix

The flake exposes both a package and a home-manager module — see
[Nix integration](#nix-integration) below.

## Quick start

```bash
export ANTHROPIC_API_KEY=sk-ant-...
magi "Should I refactor the parser before shipping?"
```

Out of the box, all three agents run on `claude-haiku-4-5` via Anthropic.
To use a heterogeneous setup, write a config:

```bash
mkdir -p ~/.config/magi
magi --print-default-config > ~/.config/magi/config.toml
$EDITOR ~/.config/magi/config.toml
magi --show-config           # verify what's wired up
magi "your question"
```

## Configuration

There are three places to configure MAGI, with the following **precedence
(highest wins)**:

1. Command-line `--set AGENT.KEY=VALUE` overrides
2. Environment variables (`MAGI_AGENT_<SLUG>_<KEY>`, `MAGI_DEFAULT_<KEY>`)
3. TOML config file (`$MAGI_CONFIG`, then `$XDG_CONFIG_HOME/magi/config.toml`)
4. Built-in defaults

### Config file

```toml
[defaults]
temperature = 0.4
max_tokens  = 220
timeout     = 60.0

[providers.anthropic]
base_url    = "https://api.anthropic.com/v1/"
api_key_env = "ANTHROPIC_API_KEY"

[providers.ollama]
base_url        = "http://localhost:11434/v1/"
api_key_default = "ollama"   # Ollama ignores keys but the SDK requires one

[agents."CASPER-3"]
provider    = "anthropic"
model       = "claude-haiku-4-5"
temperature = 0.2

[agents."MELCHIOR-1"]
provider    = "ollama"
model       = "llama3.2:3b"
temperature = 0.5

[agents."BALTHASAR-2"]
provider           = "openai"
model              = "gpt-4o-mini"
system_prompt_file = "~/.config/magi/prompts/balthasar.md"
```

Per-agent prompts can be:

- omitted (uses the canonical default for CASPER-3 / MELCHIOR-1 / BALTHASAR-2),
- inline via `system_prompt = """..."""`, or
- file-based via `system_prompt_file = "/path/to/prompt.md"`.

See [`examples/`](./examples) for prompt samples.

### Environment variables

```bash
# Override the global config path
export MAGI_CONFIG=/path/to/config.toml

# Override a default
export MAGI_DEFAULT_TEMPERATURE=0.6
export MAGI_DEFAULT_MAX_TOKENS=300

# Override per-agent settings (agent name with - replaced by _, uppercased)
export MAGI_AGENT_CASPER_3_MODEL=claude-opus-4-7
export MAGI_AGENT_MELCHIOR_1_PROVIDER=ollama
export MAGI_AGENT_BALTHASAR_2_TEMPERATURE=0.9

# Custom prompt inline or by file
export MAGI_AGENT_CASPER_3_SYSTEM_PROMPT="You are CASPER. Be brief."
export MAGI_AGENT_MELCHIOR_1_SYSTEM_PROMPT_FILE=~/prompts/melchior.md
```

### Command-line overrides

```bash
magi --set CASPER-3.model=claude-opus-4-7 \
     --set MELCHIOR-1.temperature=0.95 \
     --set defaults.max_tokens=300 \
     "your question"
```

### JSON output

For piping into other tools:

```bash
magi --json "your question" | jq '.outcome'
```

## Nix integration

The flake exposes:

- `packages.<system>.magi` — the runnable package
- `overlays.default` — adds `magi` to nixpkgs and attaches the
  home-manager module as `pkgs.magi.homeManagerModule`

There is no separate `homeManagerModules` output: adding the overlay is
enough to pick up both the binary and the module.

### Add to a flake-based system

```nix
# flake.nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";
    magi.url = "github:Nairu/magi";
  };

  outputs = { self, nixpkgs, home-manager, magi, ... }:
    let
      pkgs = import nixpkgs {
        system = "x86_64-linux";
        overlays = [ magi.overlays.default ];
      };
    in
    {
      homeConfigurations.you = home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        modules = [
          pkgs.magi.homeManagerModule
          ./home.nix
        ];
      };
    };
}
```

### Configure declaratively

```nix
# home.nix
{ ... }:
{
  programs.magi = {
    enable = true;

    settings.defaults = {
      temperature = 0.4;
      max_tokens = 220;
    };

    agents = {
      "CASPER-3" = {
        provider = "anthropic";
        model = "claude-haiku-4-5";
        temperature = 0.2;
      };

      "MELCHIOR-1" = {
        provider = "ollama";
        model = "llama3.2:3b";
        temperature = 0.5;
        systemPrompt = ''
          You are MELCHIOR, augmented with senior staff engineer
          instincts. Err toward caution when the change is irreversible
          or paged-at-3am-able.
          ...
          Respond with ONE JSON object: {"verdict": "...", "confidence":
          <0-100>, "reasoning": "..."}
        '';
      };

      "BALTHASAR-2" = {
        provider = "openai";
        model = "gpt-4o-mini";
        temperature = 0.7;
      };
    };
  };
}
```

The module writes a config file to `$XDG_CONFIG_HOME/magi/config.toml`
and drops any inline `systemPrompt` values into separate prompt files
under `$XDG_CONFIG_HOME/magi/prompts/`, wiring `system_prompt_file`
references for you.

API keys should be supplied through your secrets manager
([sops-nix](https://github.com/Mic92/sops-nix),
[agenix](https://github.com/ryantm/agenix)) and exported as
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc. — not in plain Nix.

## Development

```bash
git clone https://github.com/Nairu/magi
cd magi
uv sync --all-extras
uv run pytest
uv run ruff check
```

Or in the dev shell:

```bash
nix develop
uv sync
uv run pytest
```

## Backends tested

| Provider     | Base URL                              | Notes                                |
|--------------|---------------------------------------|--------------------------------------|
| Anthropic    | `https://api.anthropic.com/v1/`       | Prompt caching not available via OAI compat |
| OpenAI       | `https://api.openai.com/v1/`          |                                      |
| Ollama       | `http://localhost:11434/v1/`          | Use models 7B+ for reliable JSON     |
| Groq         | `https://api.groq.com/openai/v1/`     | Fast                                 |
| OpenRouter   | `https://openrouter.ai/api/v1/`       | Routes across providers              |
| LM Studio    | `http://localhost:1234/v1/`           |                                      |
| vLLM         | Your endpoint                         |                                      |

Anything that speaks `POST /v1/chat/completions` should work.

## Caveats

- **JSON output is prompt-discipline, not protocol-enforced.** Smaller
  local models (1–3B) sometimes confabulate the schema. If MELCHIOR-on-
  Ollama keeps faulting, bump to `llama3.2:8b`, raise `max_tokens`, or
  drop temperature. The fault label will tell you which agent.
- **Anthropic's OpenAI-compat path doesn't support prompt caching.**
  For three short fan-out calls it doesn't matter, but if you extend to
  long-context deliberations consider the native Anthropic SDK there.

## License

MIT. See [`LICENSE`](./LICENSE).

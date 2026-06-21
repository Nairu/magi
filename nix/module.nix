{ config, lib, pkgs, ... }:

let
  cfg = config.programs.magi;

  tomlFormat = pkgs.formats.toml { };

  # Build settings, automatically converting any inline `systemPrompt` to a
  # generated prompt file referenced via `system_prompt_file`. This keeps the
  # generated TOML clean and lets each agent's prompt live as its own file
  # under $XDG_CONFIG_HOME/magi/prompts/, which is much nicer to edit by hand.
  agentNames = lib.attrNames cfg.agents;

  promptFiles = lib.listToAttrs (lib.concatMap
    (name:
      let
        a = cfg.agents.${name};
      in
      lib.optional (a.systemPrompt != null) {
        name = "magi/prompts/${name}.md";
        value = { text = a.systemPrompt; };
      })
    agentNames);

  # Build the per-agent settings sub-table, dropping our internal `systemPrompt`
  # and replacing it with `system_prompt_file` pointing at the generated file.
  renderAgent = name: a:
    (lib.filterAttrs (k: _: k != "systemPrompt") a)
    // (lib.optionalAttrs (a.systemPrompt != null) {
      system_prompt_file = "${config.xdg.configHome}/magi/prompts/${name}.md";
    });

  renderedAgents = lib.mapAttrs renderAgent cfg.agents;

  mergedSettings = cfg.settings // {
    agents = (cfg.settings.agents or { }) // renderedAgents;
  };

  configFile = tomlFormat.generate "magi-config.toml" mergedSettings;
in
{
  options.programs.magi = {
    enable = lib.mkEnableOption "MAGI three-agent deliberation system";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.magi;
      defaultText = lib.literalExpression "pkgs.magi";
      description = "The magi package to install.";
    };

    settings = lib.mkOption {
      type = tomlFormat.type;
      default = { };
      example = lib.literalExpression ''
        {
          defaults = { temperature = 0.4; max_tokens = 220; };
          providers.ollama = {
            base_url = "http://localhost:11434/v1/";
            api_key_default = "ollama";
          };
        }
      '';
      description = ''
        Free-form settings merged into the generated
        <filename>$XDG_CONFIG_HOME/magi/config.toml</filename>. Use this for
        anything not covered by the typed <option>agents</option> option.
      '';
    };

    agents = lib.mkOption {
      default = { };
      description = ''
        Per-agent overrides. Each entry becomes a row under
        <literal>[agents."NAME"]</literal>. Set <option>systemPrompt</option>
        to drop a prompt file into <filename>$XDG_CONFIG_HOME/magi/prompts/</filename>
        and wire <literal>system_prompt_file</literal> for you.
      '';
      example = lib.literalExpression ''
        {
          "CASPER-3" = {
            provider = "anthropic";
            model = "claude-haiku-4-5";
            temperature = 0.2;
          };
          "MELCHIOR-1" = {
            provider = "ollama";
            model = "llama3.2:3b";
            systemPrompt = '''
              You are MELCHIOR. Be cautious...
            ''';
          };
        }
      '';
      type = lib.types.attrsOf (lib.types.submodule ({ name, ... }: {
        freeformType = tomlFormat.type;
        options = {
          provider = lib.mkOption {
            type = lib.types.str;
            description = "Provider key (must exist in providers.* table).";
          };
          model = lib.mkOption {
            type = lib.types.str;
            description = "Model identifier as the provider expects it.";
          };
          temperature = lib.mkOption {
            type = lib.types.nullOr (lib.types.numbers.between 0.0 2.0);
            default = null;
            description = "Sampling temperature.";
          };
          max_tokens = lib.mkOption {
            type = lib.types.nullOr lib.types.ints.positive;
            default = null;
            description = "Maximum completion tokens.";
          };
          timeout = lib.mkOption {
            type = lib.types.nullOr lib.types.numbers.positive;
            default = null;
            description = "Request timeout in seconds.";
          };
          systemPrompt = lib.mkOption {
            type = lib.types.nullOr lib.types.lines;
            default = null;
            description = ''
              Inline system prompt for this agent. Written to
              <filename>$XDG_CONFIG_HOME/magi/prompts/NAME.md</filename> and
              wired automatically. Leave null to use the canonical default
              (for CASPER-3 / MELCHIOR-1 / BALTHASAR-2) or to set
              <literal>system_prompt_file</literal> manually via
              <option>settings</option>.
            '';
          };
        };
      }));
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    xdg.configFile = {
      "magi/config.toml".source = configFile;
    } // promptFiles;
  };
}

{
  description = "MAGI :: three-agent deliberation system in the style of Neon Genesis Evangelion";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # Overlay that exposes `magi` on top of nixpkgs.
      # Add this to your system's overlays to pick up the package directly.
      overlay = final: prev: {
        magi = final.callPackage ./nix/package.nix { };
      };
    in
    {
      overlays.default = overlay;

      # Home-manager module. Import with:
      #   imports = [ inputs.magi.homeManagerModules.default ];
      homeManagerModules.default = import ./nix/module.nix;
      homeManagerModules.magi = self.homeManagerModules.default;
    }
    //
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
      in
      {
        packages = {
          default = pkgs.magi;
          magi = pkgs.magi;
        };

        apps.default = {
          type = "app";
          program = "${pkgs.magi}/bin/magi";
        };

        devShells.default = pkgs.mkShell {
          name = "magi-dev";
          packages = with pkgs; [
            uv
            python313
            ruff
            mypy
          ];
          shellHook = ''
            export UV_PYTHON_PREFERENCE=only-system
            echo ":: magi dev shell — try 'uv sync' then 'uv run magi --help'"
          '';
        };

        checks = {
          inherit (self.packages.${system}) magi;
        };
      });
}

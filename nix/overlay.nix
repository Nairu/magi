# Overlay that adds `magi` to nixpkgs.
# Import directly with:
#   nixpkgs.overlays = [ (import ./overlay.nix) ];
# Or pull from the flake:
#   nixpkgs.overlays = [ inputs.magi.overlays.default ];
final: prev: {
  magi = final.callPackage ./package.nix { };
}

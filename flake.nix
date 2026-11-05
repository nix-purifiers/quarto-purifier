{
  description = "Locked, Nix-resolved Quarto extensions";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        quarto-purifier = import ./nix/scope.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (system: {
        default = (pkgsFor system).quarto-purifier.cli;
        cli = self.packages.${system}.default;
      });
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/quarto-purifier";
          meta.description = "Lock native Quarto extensions";
        };
      });
      lib.quarto-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = pkgsFor system;
          b = p.quarto-purifier.buildQuartoProject {
            src = ./examples/minimal;
            resourceRoots = {
              "index.html" = "index.html";
              "index_files" = "index_files";
            };
            doCheck = true;
            checkCommand = "grep -q fa-check index.html";
          };
        in
        {
          inherit (b.packages) environment project;
          release = b.release;
          resources = import ./tests/resource-consumer.nix {
            pkgs = p;
            projection = b.projections.resources;
          };
          cli = self.packages.${system}.default;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}

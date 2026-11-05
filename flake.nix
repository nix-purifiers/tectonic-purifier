{
  description = "Locked, Nix-resolved TeX resources for Tectonic";
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
        tectonic-purifier = import ./nix/scope.nix {
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
        default = (pkgsFor system).tectonic-purifier.cli;
        cli = self.packages.${system}.default;
      });
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/tectonic-purifier";
          meta.description = "Lock native Tectonic resources";
        };
      });
      lib.tectonic-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = pkgsFor system;
          b = p.tectonic-purifier.buildTectonicProject {
            src = ./examples/minimal;
            resourceRoots."default/default.pdf" = "default/default.pdf";
            doCheck = true;
            nativeBuildInputs = [ p.poppler-utils ];
            checkCommand = ''pdftotext "$out/default/default.pdf" text; test "$(head -n 1 text)" = 42'';
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

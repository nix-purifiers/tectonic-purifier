{ root, lockFile }:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  scope = import ./scope.nix {
    inherit pkgs nixpkgsSrc;
    purifierSrc = /. + "@purifier@";
  };
in
(scope.buildTectonicProject {
  src = /. + root;
  lockFile = /. + lockFile;
}).release

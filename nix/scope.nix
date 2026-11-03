{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  tool = scope.callPackage ./toolchain.nix { };
  original = pkgs.tectonic;
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  sdkVersion = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      tectonic = toString pkgs.tectonic-unwrapped.src;
      patch = builtins.hashFile "sha256" ../native/patch-native.py;
      fonts = builtins.hashFile "sha256" ../tectonic_purifier/fonts.py;
      core = builtins.hashFile "sha256" ../native/latex-resources.json;
      archive = builtins.hashFile "sha256" ../tectonic_purifier/pack.py;
    }
  );
  coreData = builtins.fromJSON (builtins.readFile ../native/latex-resources.json);
  coreEnvironment = scope.callPackage ./environment.nix { } {
    lock = {
      purifier = "tectonic";
      entries = scope.coreData.entries;
      outputs = { };
      problems = [ ];
      data = scope.coreData // {
        sdk = scope.sdkVersion;
      };
    };
  };
  nativeFetch = scope.callPackage ./fetch.nix { };
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  buildTectonicProject = scope.callPackage ./build-project.nix { };
})

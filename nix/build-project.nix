{
  lib,
  runCommand,
  fetchgit,
  writeText,
  python3,
  unzip,
  zstd,
  purifier,
  nativeFetch,
  sdkVersion,
  tool,
  gnutar,
  gzip,
}@scope:
{
  src,
  lockFile ? src + "/tectonic-purifier.lock.json",
  fetchers ? { },
  resourceRoots ? { },
  resourceDependencies ? [ ],
  nativeBuildInputs ? [ ],
  doCheck ? false,
  checkCommand ? "",
}:
let
  lock = purifier.checkLock (import ./read-lock.nix { inherit lib; } { inherit src lockFile; });
  prepared = import ./environment.nix scope { inherit lock fetchers; };
  source = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        "build"
        "result"
        "__pycache__"
      ]);
  };
  builtProject =
    runCommand "tectonic-project" { nativeBuildInputs = [ tool ] ++ nativeBuildInputs; }
      ''
        cp -pr ${source} source
        chmod -R u+w source
        cd source
        export SOURCE_DATE_EPOCH=1 TECTONIC_CACHE_DIR="$TMPDIR/cache" TECTONIC_PURIFIER_BUNDLE=${prepared.bundle}
        mkdir -p "$TECTONIC_CACHE_DIR/formats" "$out"
        for file in ${prepared.formats}/*; do ln -s "$file" "$TECTONIC_CACHE_DIR/formats/"; done
        ${python3}/bin/python3 ${../tectonic_purifier/fonts.py} ${prepared.bundle} "$TMPDIR/font-cache" "$TMPDIR/fonts.conf"
        export FONTCONFIG_FILE="$TMPDIR/fonts.conf"
        unset FONTCONFIG_PATH FONTCONFIG_SYSROOT
        ${
          if lock.data.target.kind == "workspace" then
            ''
              tectonic -X build --only-cached
              cp -pr build/. "$out/"
            ''
          else
            lib.concatMapStrings (input: ''
              tectonic --only-cached --outdir "$out" ${lib.escapeShellArg input}
            '') lock.data.target.inputs
        }
        ${lib.optionalString doCheck checkCommand}
        mkdir -p "$out/source"
        cp -pr ${source}/. "$out/source/"
      '';
  projections = lib.optionalAttrs (resourceRoots != { }) (
    purifier.resourceProjections {
      producer = builtProject;
      roots = resourceRoots;
      dependencies = resourceDependencies;
      inherit runCommand python3;
    }
  );
  project = builtProject // {
    inherit projections;
  };
  release =
    runCommand "tectonic-native-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir -p "$out" source/project
        cp -pr ${source}/. source/project/
        chmod -R u+rwX source
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf "$out/tectonic-source.tar.gz" -C source project
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = prepared.output;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}

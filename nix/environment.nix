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
  ...
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  indexEntry = builtins.elemAt checked.entries 0;
  resourceEntry = builtins.elemAt checked.entries 1;
  index = nativeFetch { entry = indexEntry; };
  archive = nativeFetch {
    entry = resourceEntry;
    inherit index;
  };
  nativeURLFetch =
    args:
    if builtins.elem indexEntry.url args.urls && args.hash == indexEntry.hash then
      index
    else
      assert lib.assertMsg (
        builtins.elem resourceEntry.archive.url args.urls && args.hash == resourceEntry.hash
      ) "Unexpected Tectonic fetch";
      archive;
  tree = purifier.tree (
    {
      name = "tectonic-locked-resources";
      entries = checked.entries;
      fetchurl = nativeURLFetch;
      inherit
        runCommand
        fetchgit
        writeText
        python3
        unzip
        zstd
        ;
    }
    // fetchers
  );
  bundle = "${tree}/bundle";
  formats = runCommand "tectonic-native-formats" { nativeBuildInputs = [ tool ]; } ''
    export SOURCE_DATE_EPOCH=1 TECTONIC_CACHE_DIR="$TMPDIR/cache"
    mkdir -p "$TECTONIC_CACHE_DIR" "$out" outputs
    python3=${python3}/bin/python3
    "$python3" ${../tectonic_purifier/fonts.py} ${bundle} "$TMPDIR/font-cache" "$TMPDIR/fonts.conf"
    export FONTCONFIG_FILE="$TMPDIR/fonts.conf"
    unset FONTCONFIG_PATH FONTCONFIG_SYSROOT
    cp ${writeText "primer.tex" ''
      \documentclass{article}
      \begin{document}
      42
      \end{document}
    ''} primer.tex
    tectonic --only-cached --bundle ${bundle} --outdir outputs primer.tex
    cp "$TECTONIC_CACHE_DIR/formats/${checked.data.fingerprint}-latex-${toString checked.data.formatSerial}.fmt" "$out/"
  '';
  manifest = writeText "tectonic-environment.json" (
    builtins.toJSON {
      inherit tree bundle formats;
      sdk = sdkVersion;
      fingerprint = checked.data.fingerprint;
    }
  );
  output =
    runCommand "tectonic-locked-environment"
      {
        passthru = {
          rawFetches = { inherit index archive; };
          inherit formats;
        };
      }
      ''
        mkdir -p "$out"
        ln -s ${manifest} "$out/manifest.json"
      '';
in
assert lib.assertMsg (checked.data.sdk == sdkVersion) "Tectonic SDK changed; update the lock";
{
  inherit
    output
    tree
    bundle
    formats
    archive
    ;
}

{
  lib,
  runCommand,
  writeText,
  original,
  python3,
  curl,
  gzip,
  cacert,
}:
{
  entry,
  index ? null,
}:
let
  native = entry.tectonic;
  isIndex = native.kind == "index";
  config = writeText "Tectonic.toml" ''
    [doc]
    name = "purifier-fetch"
    bundle = ${builtins.toJSON native.bundle}
    [[output]]
    name = "default"
    type = "pdf"
    inputs = ["main.tex"]
  '';
  chunks = lib.genList (n: lib.sublist (n * 512) 512 (builtins.attrNames native.files)) (
    (builtins.length (builtins.attrNames native.files) + 511) / 512
  );
in
runCommand (if isIndex then "tectonic-native-index" else "tectonic-native-working-set.zip")
  {
    nativeBuildInputs = [
      original
      python3
      curl
      gzip
    ];
    outputHashMode = "flat";
    outputHashAlgo = "sha256";
    outputHash = entry.hash;
    impureEnvVars = lib.fetchers.proxyImpureEnvVars;
    SSL_CERT_FILE = "${cacert}/etc/ssl/certs/ca-bundle.crt";
  }
  (
    ''
      export HOME="$TMPDIR/home" TECTONIC_CACHE_DIR="$TMPDIR/cache"
      mkdir -p "$HOME" "$TECTONIC_CACHE_DIR"
      if [ -f "''${NIX_SSL_CERT_FILE:-}" ]; then export SSL_CERT_FILE="$NIX_SSL_CERT_FILE"; fi
    ''
    + (
      if isIndex then
        ''
          curl --silent --show-error --fail --location --retry 5 --retry-delay 2 \
            ${lib.escapeShellArg (native.bundle + ".index.gz")} | gzip -d > "$out"
        ''
      else
        ''
          cp ${config} Tectonic.toml
          mkdir -p "$TECTONIC_CACHE_DIR/bundles/hashes" "$TECTONIC_CACHE_DIR/bundles/data"
          printf '%s\n' ${lib.escapeShellArg native.digest} > "$TECTONIC_CACHE_DIR/bundles/hashes/${native.cacheKey}"
          date +%s > "$TECTONIC_CACHE_DIR/bundles/hashes/${native.checkKey}"
          ln -s ${index} "$TECTONIC_CACHE_DIR/bundles/data/${native.digest}.index"
          complete=false
          for delay in 1 2 4 8 16; do
            ${lib.concatMapStrings (names: ''
              cp ${
                writeText "tectonic-prefetch.names" ((lib.concatStringsSep "\n" names) + "\n")
              } "$TECTONIC_CACHE_DIR/bundles/data/${native.cacheKey}.prefetch"
              tectonic -X bundle cat -- ${lib.escapeShellArg (builtins.head names)} > /dev/null
            '') chunks}
            if python3 ${../../tectonic_purifier/pack.py} "$TECTONIC_CACHE_DIR/bundles/data/${native.digest}" ${writeText "tectonic-working-set.json" (builtins.toJSON native)} "$out"; then
              complete=true
              break
            fi
            sleep "$delay"
          done
          $complete
        ''
    )
  )

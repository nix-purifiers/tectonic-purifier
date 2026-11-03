{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  gh,
  git,
  cacert,
  curl,
  original,
  tool,
  sdkVersion,
  coreEnvironment,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "tectonic-purifier";
  version = "0.1.0";
  src = ../.;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/tectonic-purifier"
    cp -r tectonic_purifier nix native "$out/lib/tectonic-purifier/"
    install -m755 bin/tectonic-purifier "$out/bin/tectonic-purifier"
    for file in realize release; do
      substituteInPlace "$out/lib/tectonic-purifier/nix/$file.nix" --replace-fail '@nixpkgs@' '${nixpkgsSrc}' --replace-fail '@purifier@' '${purifierSrc}'
    done
    wrapProgram "$out/bin/tectonic-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          gh
          git
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default TECTONIC_PURIFIER_GH ${gh}/bin/gh \
      --set TECTONIC_PURIFIER_ORIGINAL ${lib.getExe original} \
      --set TECTONIC_PURIFIER_SCOPED ${lib.getExe tool} \
      --set TECTONIC_PURIFIER_CURL ${lib.getExe curl} \
      --set TECTONIC_PURIFIER_DEFAULT_BUNDLE ${lib.escapeShellArg original.unwrapped.TECTONIC_BUNDLE_LOCKED} \
      --set TECTONIC_PURIFIER_CORE ${coreEnvironment.output}/manifest.json \
      --set TECTONIC_PURIFIER_SDK_VERSION ${sdkVersion} \
      --set TECTONIC_PURIFIER_SDK "$out"
    for program in tectonic nextonic; do
      makeWrapper "$out/bin/tectonic-purifier" "$out/bin/$program" --add-flags "--native=$program"
    done
  '';
  meta = {
    description = "Native Tectonic with locked Nix-resolved TeX resources";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "tectonic-purifier";
  };
}

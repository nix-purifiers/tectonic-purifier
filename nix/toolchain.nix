{
  tectonic,
  tectonic-unwrapped,
  python3,
}:
let
  unwrapped = tectonic-unwrapped.overrideAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      ${python3}/bin/python3 ${../native/patch-native.py}
    '';
  });
in
tectonic.override { tectonic-unwrapped = unwrapped; }

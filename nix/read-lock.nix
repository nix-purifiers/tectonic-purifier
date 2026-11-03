{ lib }:
{
  src,
  lockFile ? src + "/tectonic-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  relative =
    s:
    builtins.isString s
    && s != ""
    && !(lib.hasPrefix "/" s)
    && !(builtins.elem ".." (lib.splitString "/" s))
    && builtins.match ".*[\n\r].*" s == null;
  hex = s: builtins.isString s && builtins.match "[a-f0-9]{64}" s != null;
  sri = s: builtins.isString s && builtins.match "sha256-[A-Za-z0-9+/]{43}=" s != null;
  shape =
    (data.version or null) == 1
    && (data.purifier or null) == "tectonic"
    && builtins.isString (data.sdk or null)
    && builtins.isString (data.bundle or null)
    && builtins.isAttrs (data.target or null)
    && builtins.elem (data.target.kind or null) [
      "workspace"
      "files"
    ]
    && (
      data.target.kind != "files"
      || (
        builtins.isList (data.target.inputs or null)
        && data.target.inputs != [ ]
        && builtins.all relative data.target.inputs
      )
    )
    && hex (data.fingerprint or null)
    && builtins.isInt (data.formatSerial or null)
    && builtins.isAttrs (data.inputs or null)
    && builtins.isList (data.extraInputs or null)
    && builtins.all relative data.extraInputs
    && builtins.isList entries
    && builtins.length entries == 2
    && builtins.all (
      e:
      builtins.isAttrs e
      && sri (e.hash or null)
      && builtins.isAttrs (e.tectonic or null)
      && e.tectonic.bundle == data.bundle
      && hex (e.tectonic.digest or null)
      && relative (e.tectonic.cacheKey or null)
      && baseNameOf e.tectonic.cacheKey == e.tectonic.cacheKey
      && relative (e.tectonic.checkKey or null)
      && baseNameOf e.tectonic.checkKey == e.tectonic.checkKey
    ) entries;
  index = builtins.elemAt entries 0;
  resources = builtins.elemAt entries 1;
  hasConfig = builtins.pathExists (src + "/Tectonic.toml");
  native = if hasConfig then builtins.fromTOML (builtins.readFile (src + "/Tectonic.toml")) else null;
  valid =
    shape
    && data.native == native
    && (data.target.kind != "workspace" || (native != null && native.doc.bundle == data.bundle))
    && index.path == "metadata/index"
    && index.tectonic.kind == "index"
    && index.url == "tectonic-index:${data.bundle}"
    && index.mirrors == [ ]
    && resources.path == "bundle"
    && resources.tectonic.kind == "working-set"
    &&
      resources.archive == {
        url = "tectonic-resources:${data.bundle}#${data.fingerprint}";
        mirrors = [ ];
        stripTop = false;
      }
    &&
      builtins.removeAttrs index.tectonic [ "kind" ] == builtins.removeAttrs resources.tectonic [
        "kind"
        "files"
        "fingerprint"
      ]
    && builtins.isAttrs resources.tectonic.files
    && builtins.attrNames resources.tectonic.files != [ ]
    && builtins.all (
      name: relative name && name != "SHA256SUM" && hex resources.tectonic.files.${name}
    ) (builtins.attrNames resources.tectonic.files)
    && resources.tectonic.fingerprint == data.fingerprint
    && builtins.hashString "sha256" (builtins.toJSON resources.tectonic.files) == data.fingerprint
    &&
      builtins.attrNames data.inputs == builtins.sort builtins.lessThan (
        lib.unique ((lib.optional hasConfig "Tectonic.toml") ++ data.extraInputs)
      )
    && builtins.all (
      name:
      relative name
      && builtins.pathExists (src + "/${name}")
      && builtins.hashFile "sha256" (src + "/${name}") == (data.inputs.${name}.sha256 or null)
    ) (builtins.attrNames data.inputs);
in
{
  purifier = "tectonic";
  inherit data entries;
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
  problems = lib.optional (!valid) "Invalid or stale Tectonic lock; update the lock";
}

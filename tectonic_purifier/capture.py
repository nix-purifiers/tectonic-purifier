import base64
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from .common import (
    environment,
    fingerprint,
    inputs,
    load,
    native_config,
    relative,
    run,
    write,
)
from .fonts import configure


def sri(file):
    return (
        "sha256-"
        + base64.b64encode(hashlib.sha256(file.read_bytes()).digest()).decode()
    )


def capture(root, companion, update=False, extra=(), targets=(), bundle=None):
    if companion.exists() and not update:
        load(root, companion)
        return
    previous = json.loads(companion.read_text()) if companion.exists() else {}
    extra = list(extra or previous.get("extraInputs", []))
    native = native_config(root)
    target = (
        {"kind": "files", "inputs": list(targets)}
        if targets
        else previous.get("target", {"kind": "workspace"})
    )
    if target["kind"] == "workspace":
        if native is None:
            raise ValueError(
                "Pass the standalone TeX inputs, or use a native Tectonic.toml workspace"
            )
        uri = native["doc"]["bundle"]
        if bundle and bundle != uri:
            raise ValueError("Change the workspace bundle in Tectonic.toml")
    else:
        if not target["inputs"] or any(
            not relative(name) or not (root / name).is_file()
            for name in target["inputs"]
        ):
            raise ValueError("Standalone TeX inputs must be project files")
        uri = bundle or previous.get(
            "bundle", os.environ["TECTONIC_PURIFIER_DEFAULT_BUNDLE"]
        )
    if not uri.startswith(("https://", "http://")) or uri.endswith(".ttb"):
        raise ValueError("The initial integration supports public indexed-tar bundles")
    original = os.environ["TECTONIC_PURIFIER_SCOPED"]
    with tempfile.TemporaryDirectory(prefix="tectonic-capture-") as temporary:
        state = Path(temporary)
        env = environment(state)
        core_data = json.loads(
            (Path(__file__).parent.parent / "native/latex-resources.json").read_text()
        )
        if uri == core_data["bundle"]:
            core = json.loads(Path(os.environ["TECTONIC_PURIFIER_CORE"]).read_text())
            metadata = core_data["entries"][1]["tectonic"]
            cache = Path(env["TECTONIC_CACHE_DIR"])
            hashes = cache / "bundles/hashes"
            hashes.mkdir(parents=True)
            (hashes / metadata["cacheKey"]).write_text(metadata["digest"] + "\n")
            (hashes / metadata["checkKey"]).write_text(str(int(time.time())))
            data = cache / "bundles/data"
            source = data / metadata["digest"]
            source.mkdir(parents=True)
            native_index = Path(core["tree"]) / "metadata/index"
            (data / (metadata["digest"] + ".index")).symlink_to(native_index)
            for name in metadata["files"]:
                alias = source / name
                alias.parent.mkdir(parents=True, exist_ok=True)
                alias.symlink_to(Path(core["bundle"]) / name)
        else:
            compressed_index = state / "index.gz"
            run(
                [
                    os.environ["TECTONIC_PURIFIER_CURL"],
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--location",
                    "--retry",
                    "5",
                    "--retry-delay",
                    "2",
                    uri + ".index.gz",
                    "--output",
                    str(compressed_index),
                ]
            )
            native_index = state / "native.index"
            with gzip.open(compressed_index, "rb") as stream:
                native_index.write_bytes(stream.read())
        env["TECTONIC_PURIFIER_INDEX_FILE"] = str(native_index)
        # Prime the standard LaTeX format independently of the user's document.
        primer = state / "primer.tex"
        primer.write_text(
            "\\documentclass{article}\n\\begin{document}\n42\n\\end{document}\n"
        )
        run(
            [original, "--bundle", uri, "--outdir", str(state), str(primer)],
            cwd=state,
            env=env,
        )
        if target["kind"] == "workspace":
            run([original, "-X", "build"], cwd=root, env=env)
        else:
            for name in target["inputs"]:
                run([original, "--bundle", uri, name], cwd=root, env=env)
        cache = Path(env["TECTONIC_CACHE_DIR"])
        hashes = [
            p for p in (cache / "bundles/hashes").iterdir() if p.suffix != ".lock"
        ]
        if len(hashes) != 1:
            raise ValueError("Capture must use one native bundle")
        hash_file = hashes[0]
        digest = hash_file.read_text().strip()
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid native bundle digest")
        source = cache / "bundles/data" / digest
        files = {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*")
            if p.is_file() and p.name != "SHA256SUM"
        }
        fp = fingerprint(files)
        formats = list((cache / "formats").iterdir())
        pattern = re.compile(re.escape(digest) + r"-latex-([0-9]+)\.fmt")
        if len(formats) != 1 or not (match := pattern.fullmatch(formats[0].name)):
            raise ValueError("The initial integration supports the native LaTeX format")
        metadata = {
            "bundle": uri,
            "digest": digest,
            "cacheKey": hash_file.name,
            "checkKey": hash_file.with_suffix(".lock").name,
        }
        index = cache / "bundles/data" / (digest + ".index")
        spec = state / "collection.json"
        spec.write_text(json.dumps({"files": files, "fingerprint": fp}))
        archive = state / "bundle.zip"
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("pack.py")),
                str(source),
                str(spec),
                str(archive),
            ],
            check=True,
        )
        # Validate the working set with local-only native resolution and the
        # same font boundary used by the installed integration.
        frozen_bundle = state / "frozen-bundle"
        frozen_bundle.mkdir()
        for name in files:
            alias = frozen_bundle / name
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.symlink_to(source / name)
        (frozen_bundle / "SHA256SUM").write_text(fp + "\n")
        verified = environment(state / "verified")
        for name in ("FONTCONFIG_FILE", "FONTCONFIG_PATH", "FONTCONFIG_SYSROOT"):
            verified.pop(name, None)
        configure(frozen_bundle, state / "font-cache", state / "fonts.conf")
        verified["FONTCONFIG_FILE"] = str(state / "fonts.conf")
        verified["TECTONIC_PURIFIER_BUNDLE"] = str(frozen_bundle)
        scoped = os.environ["TECTONIC_PURIFIER_SCOPED"]
        if target["kind"] == "workspace":
            run([scoped, "-X", "build", "--only-cached"], cwd=root, env=verified)
        else:
            for name in target["inputs"]:
                run([scoped, "--only-cached", name], cwd=root, env=verified)
        entries = [
            {
                "path": "metadata/index",
                "url": "tectonic-index:" + uri,
                "mirrors": [],
                "hash": sri(index),
                "tectonic": dict(metadata, kind="index"),
            },
            {
                "path": "bundle",
                "archive": {
                    "url": "tectonic-resources:" + uri + "#" + fp,
                    "mirrors": [],
                    "stripTop": False,
                },
                "hash": sri(archive),
                "tectonic": dict(
                    metadata, kind="working-set", files=files, fingerprint=fp
                ),
            },
        ]
        data = {
            "version": 1,
            "purifier": "tectonic",
            "sdk": os.environ["TECTONIC_PURIFIER_SDK_VERSION"],
            "native": native,
            "target": target,
            "bundle": uri,
            "fingerprint": fp,
            "formatSerial": int(match[1]),
            "entries": entries,
            "extraInputs": extra,
            "inputs": inputs(root, extra),
        }
        write(companion, json.dumps(data, indent=2, sort_keys=True) + "\n")
        # Reuse the native capture bytes locally; fixed-output declarations still
        # describe and verify cold-cache fetching on another machine.
        for name, file in (
            ("tectonic-native-index", index),
            ("tectonic-native-working-set.zip", archive),
        ):
            run(["nix", "store", "add-file", "--name", name, str(file.resolve())])

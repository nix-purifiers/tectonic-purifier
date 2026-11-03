"""Native workspace/standalone rendering, SyncTeX and ordinary source consumer."""

import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)
expression = (
    "let f=builtins.getFlake "
    + json.dumps(str(repo))
    + ";p=import f.inputs.nixpkgs {};in p.poppler-utils"
)
pdf_tools = Path(
    subprocess.check_output(
        [
            "nix",
            "build",
            "--impure",
            "--expr",
            expression,
            "--no-link",
            "--print-out-paths",
        ],
        text=True,
    ).strip()
)


def text(file):
    return subprocess.check_output(
        [pdf_tools / "bin/pdftotext", file, "-"], text=True
    ).split()[0]


def call(root, *args, env=None, expected=0):
    print("native", args, flush=True)
    result = subprocess.run(
        [sdk / "bin" / args[0], *args[1:]],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == expected, (args, result)
    return result


with tempfile.TemporaryDirectory(prefix="tectonic proof with spaces ") as temporary:
    temp = Path(temporary)
    root = temp / "project"
    shutil.copytree(
        repo / "examples/minimal", root, ignore=shutil.ignore_patterns("build")
    )
    cache_home = temp / "xdg-cache"
    env = dict(
        os.environ,
        XDG_CACHE_HOME=str(cache_home),
        SOURCE_DATE_EPOCH="1",
        TECTONIC_CACHE_DIR=str(temp / "host-poison"),
        FONTCONFIG_FILE="/missing/host-fonts.conf",
        FONTCONFIG_SYSROOT="/missing/host-font-root",
    )
    call(root, "tectonic", "-X", "build", env=env)
    pdf = root / "build/default/default.pdf"
    assert text(pdf) == "42"
    source = root / "src/index.tex"
    original = source.read_text()
    source.write_text("43\n")
    call(root, "tectonic", "-X", "build", env=env)
    assert text(pdf) == "43"
    source.write_text(original)
    call(root, "nextonic", "build", env=env)
    assert text(pdf) == "42"
    profile = next(cache_home.glob("tectonic-purifier/*/*/environment-profile"))
    metadata = json.loads(profile.resolve().read_text())
    manifest = json.loads((Path(metadata["output"]) / "manifest.json").read_text())
    formats = profile.parent / "cache/formats"
    assert all(
        f.is_symlink() and str(f.resolve()).startswith("/nix/store/")
        for f in formats.iterdir()
    )
    refs = subprocess.check_output(
        ["nix-store", "-q", "--requisites", str(profile.resolve())], text=True
    )
    assert str(sdk) in refs and manifest["formats"] in refs and manifest["tree"] in refs
    assert (Path(manifest["bundle"]) / "article.cls").is_file()
    standalone = root / "standalone.tex"
    standalone.write_text(
        "\\documentclass{article}\n\\begin{document}\n42\n\\end{document}\n"
    )
    call(root, "tectonic", "--synctex", "standalone.tex", env=env)
    assert text(root / "standalone.pdf") == "42"
    sync = gzip.decompress((root / "standalone.synctex.gz").read_bytes()).decode()
    assert "standalone.tex" in sync and "Input:" in sync, sync
    preamble = root / "src/_preamble.tex"
    before = preamble.read_text()
    preamble.write_text(
        before.replace(
            "\\begin{document}",
            "\\usepackage{purifier_missing_package}\n\\begin{document}",
        )
    )
    missing = call(root, "tectonic", "-X", "build", env=env, expected=1)
    assert (
        "purifier_missing_package" in missing.stderr
        and "downloading" not in missing.stderr
    ), missing
    preamble.write_text(before)
    call(root, "tectonic", "-X", "build", env=env)
    config = root / "Tectonic.toml"
    config_text = config.read_text()
    config.write_text(config_text + "\n# stale\n")
    assert (
        "Selection inputs changed"
        in call(root, "tectonic", "-X", "build", env=env, expected=1).stderr
    )
    config.write_text(config_text)
    call(
        root,
        "tectonic",
        "--bundle",
        "https://unlocked.example/bundle.tar",
        "standalone.tex",
        env=env,
        expected=1,
    )
    subdir = root / "subdir"
    subdir.mkdir()
    call(subdir, "tectonic", "-X", "build", env=env)
    companion = temp / "external.json"
    (root / "tectonic-purifier.lock.json").rename(companion)
    external = dict(
        env, TECTONIC_PURIFIER_PROJECT=str(root), TECTONIC_PURIFIER_LOCK=str(companion)
    )
    call(subdir, "tectonic", "-X", "build", env=external)
    archive = Path(
        call(
            root, "tectonic-purifier", "bundle", "--lock", str(companion)
        ).stdout.strip()
    )
    fake_gh = temp / "fake-gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\nimport pathlib,sys\n"
        "assert sys.argv[1:4]==['release','upload','v0.1.0']\n"
        "pathlib.Path(__file__).with_suffix('.uploaded').write_bytes(pathlib.Path(sys.argv[4]).read_bytes())\n"
    )
    fake_gh.chmod(0o755)
    call(
        root,
        "tectonic-purifier",
        "publish",
        "--lock",
        str(companion),
        "--tag",
        "v0.1.0",
        env=dict(env, TECTONIC_PURIFIER_GH=str(fake_gh)),
    )
    assert fake_gh.with_suffix(".uploaded").read_bytes() == archive.read_bytes()
    consumer = temp / "consumer"
    consumer.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(consumer, filter="data")
    # Supply the locked files through Tectonic's original native cache namespace.
    data = json.loads(companion.read_text())
    native = data["entries"][1]["tectonic"]
    ordinary_cache = temp / "ordinary-cache"
    hashes = ordinary_cache / "bundles/hashes"
    hashes.mkdir(parents=True)
    (hashes / native["cacheKey"]).write_text(native["digest"] + "\n")
    (hashes / native["checkKey"]).write_text(str(int(time.time())))
    storage = ordinary_cache / "bundles/data"
    storage.mkdir()
    (storage / (native["digest"] + ".index")).symlink_to(
        Path(manifest["tree"]) / "metadata/index"
    )
    resources = storage / native["digest"]
    resources.mkdir()
    for name in native["files"]:
        alias = resources / name
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.symlink_to((Path(manifest["bundle"]) / name).resolve())
    original_tool = (
        Path(
            subprocess.check_output(
                [
                    "nix",
                    "build",
                    "--impure",
                    "--expr",
                    "let f=builtins.getFlake "
                    + json.dumps(str(repo))
                    + ";p=import f.inputs.nixpkgs {};in p.tectonic",
                    "--no-link",
                    "--print-out-paths",
                ],
                text=True,
            ).strip()
        )
        / "bin/tectonic"
    )
    ordinary = dict(
        os.environ,
        SOURCE_DATE_EPOCH="1",
        TECTONIC_CACHE_DIR=str(ordinary_cache),
        FONTCONFIG_FILE=str(profile.parent / "fonts.conf"),
    )
    result = subprocess.run(
        [original_tool, "-X", "build", "--only-cached"],
        cwd=consumer / "project",
        env=ordinary,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result
    assert text(consumer / "project/build/default/default.pdf") == "42"
    fallback = temp / "fallback"
    fallback.mkdir()
    assert "ordinary impure" in call(fallback, "tectonic", "--version").stderr
    fake = temp / "fake-native"
    fake.write_text("#!/bin/sh\nprintf native-out\nprintf native-err >&2\nexit 7\n")
    fake.chmod(0o755)
    direct = dict(
        os.environ,
        PYTHONPATH=str(sdk / "lib/tectonic-purifier"),
        TECTONIC_PURIFIER_ORIGINAL=str(fake),
        TECTONIC_PURIFIER_SCOPED=str(fake),
    )
    result = subprocess.run(
        ["python3", "-m", "tectonic_purifier.cli", "--native=tectonic"],
        cwd=fallback,
        env=direct,
        text=True,
        capture_output=True,
    )
    assert (
        result.returncode == 7
        and result.stdout == "native-out"
        and result.stderr.endswith("native-err")
    ), result
print(
    "Native Tectonic PDF/SyncTeX, readonly resources/formats, font isolation, source consumer, publication and fallback passed"
)

import fcntl
import hashlib
import json
import os
from pathlib import Path

from .common import environment, load, run
from .fonts import configure


def prepare(root, companion):
    data = load(root, companion)
    generation = hashlib.sha256(
        companion.read_bytes() + os.environ["TECTONIC_PURIFIER_SDK"].encode()
    ).hexdigest()[:20]
    key = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    state = cache_home / "tectonic-purifier" / key / generation
    state.mkdir(parents=True, exist_ok=True)
    expression = (
        "import "
        + json.dumps(
            os.environ["TECTONIC_PURIFIER_SDK"]
            + "/lib/tectonic-purifier/nix/realize.nix"
        )
        + " {root="
        + json.dumps(str(root))
        + ";lockFile="
        + json.dumps(str(companion))
        + ";sdk="
        + json.dumps(os.environ["TECTONIC_PURIFIER_SDK"])
        + ";}"
    )
    profile = Path(
        run(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--out-link",
                str(state / "environment-profile"),
                "--print-out-paths",
            ]
        ).strip()
    )
    manifest = json.loads(
        (Path(json.loads(profile.read_text())["output"]) / "manifest.json").read_text()
    )
    if manifest["sdk"] != data["sdk"]:
        raise ValueError("Prepared Tectonic SDK differs from the lock")
    env = environment(state)
    for name in ("FONTCONFIG_FILE", "FONTCONFIG_PATH", "FONTCONFIG_SYSROOT"):
        env.pop(name, None)
    configure(manifest["bundle"], state / "font-cache", state / "fonts.conf")
    env["FONTCONFIG_FILE"] = str(state / "fonts.conf")
    formats = Path(env["TECTONIC_CACHE_DIR"]) / "formats"
    formats.mkdir(parents=True, exist_ok=True)
    with (state / "initialization.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        for file in Path(manifest["formats"]).iterdir():
            alias = formats / file.name
            if alias.is_symlink():
                if alias.resolve() != file.resolve():
                    raise ValueError("Private Tectonic format differs from the Nix SDK")
            elif alias.exists():
                raise ValueError(
                    "Unexpected mutable format in the private Tectonic cache"
                )
            else:
                alias.symlink_to(file)
    env["TECTONIC_PURIFIER_BUNDLE"] = manifest["bundle"]
    env["PATH"] = (
        str(Path(os.environ["TECTONIC_PURIFIER_SDK"]) / "bin")
        + os.pathsep
        + env["PATH"]
    )
    return env

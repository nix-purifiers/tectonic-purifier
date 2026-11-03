import hashlib
import json
import os
from pathlib import Path
import subprocess
import tomllib


def run(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stdout + result.stderr)
    return result.stdout


def write(path, text):
    path = Path(path)
    if path.is_file() and path.read_text() == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def relative(name):
    return (
        isinstance(name, str)
        and name
        and not Path(name).is_absolute()
        and ".." not in Path(name).parts
        and "\n" not in name
        and "\r" not in name
    )


def native_config(root):
    file = root / "Tectonic.toml"
    return tomllib.loads(file.read_text()) if file.exists() else None


def inputs(root, extra):
    names = list(extra)
    if (root / "Tectonic.toml").exists():
        names.append("Tectonic.toml")
    result = {}
    for name in sorted(set(names)):
        path = root / name
        if not relative(name) or not path.is_file() or path.is_symlink():
            raise ValueError("Selection inputs must be regular project files")
        result[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def fingerprint(files):
    return hashlib.sha256(
        json.dumps(
            files, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def environment(state):
    env = dict(os.environ)
    env.pop("TECTONIC_PURIFIER_BUNDLE", None)
    env.pop("TECTONIC_PURIFIER_INDEX_FILE", None)
    cache = state / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    env["TECTONIC_CACHE_DIR"] = str(cache)
    return env


def load(root, companion):
    data = json.loads(companion.read_text())
    if data.get("version") != 1 or data.get("purifier") != "tectonic":
        raise ValueError("Unsupported Tectonic lock")
    if data["sdk"] != os.environ["TECTONIC_PURIFIER_SDK_VERSION"]:
        raise ValueError("Tectonic frontend SDK changed; update the lock")
    if (
        inputs(root, data["extraInputs"]) != data["inputs"]
        or native_config(root) != data["native"]
    ):
        raise ValueError("Selection inputs changed; update the lock")
    for entry in data["entries"]:
        native = entry["tectonic"]
        if native["kind"] == "working-set":
            if (
                any(not relative(name) for name in native["files"])
                or fingerprint(native["files"]) != data["fingerprint"]
            ):
                raise ValueError("Tectonic resource fingerprint differs from the lock")
    return data

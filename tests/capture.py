"""Capture through native Tectonic builds for workspace and standalone inputs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)


def call(root, *args, env):
    result = subprocess.run(
        [sdk / "bin" / args[0], *args[1:]],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert result.returncode == 0, result
    return result.stdout


with tempfile.TemporaryDirectory(prefix="tectonic native capture ") as temporary:
    temp = Path(temporary)
    root = temp / "workspace"
    shutil.copytree(
        repo / "examples/minimal", root, ignore=shutil.ignore_patterns("build")
    )
    env = dict(
        os.environ, XDG_CACHE_HOME=str(temp / "xdg-cache"), SOURCE_DATE_EPOCH="1"
    )
    companion = root / "tectonic-purifier.lock.json"
    original = json.loads(companion.read_text())
    companion.unlink()
    call(root, "tectonic-purifier", "lock", env=env)
    data = json.loads(companion.read_text())
    assert data["entries"] == original["entries"]
    assert len(data["entries"][1]["tectonic"]["files"]) >= 200
    before = companion.read_bytes()
    call(root, "tectonic-purifier", "lock", env=env)
    assert companion.read_bytes() == before
    call(root, "tectonic", "-X", "build", env=env)
    single = temp / "standalone"
    single.mkdir()
    source = single / "main.tex"
    source.write_text(
        "\\documentclass{article}\n\\begin{document}\n42\n\\end{document}\n"
    )
    call(single, "tectonic-purifier", "lock", "main.tex", env=env)
    data = json.loads((single / "tectonic-purifier.lock.json").read_text())
    assert data["native"] is None and data["target"] == {
        "kind": "files",
        "inputs": ["main.tex"],
    }
    assert data["inputs"] == {}
    call(single, "tectonic", "--synctex", "main.tex", env=env)
    assert (single / "main.pdf").is_file() and (single / "main.synctex.gz").is_file()
    source.write_text(source.read_text().replace("42", "43"))
    call(single, "tectonic", "main.tex", env=env)
print("Native Tectonic workspace and standalone capture passed")

"""Inspect native support-file declarations without IFD."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / "project"
    shutil.copytree(
        repo / "examples/minimal", root, ignore=shutil.ignore_patterns("build")
    )
    companion = root / "tectonic-purifier.lock.json"
    original = json.loads(companion.read_text())

    def inspect():
        expression = f"let f=builtins.getFlake {json.dumps(str(repo))};lock=f.lib.tectonic-purifier.readLock {{src=/. + {json.dumps(str(root))};}};in {{inherit(lock)problems outputs;}}"
        return json.loads(
            subprocess.check_output(
                [
                    "nix",
                    "eval",
                    "--impure",
                    "--json",
                    "--option",
                    "allow-import-from-derivation",
                    "false",
                    "--expr",
                    expression,
                ],
                text=True,
            )
        )

    assert inspect()["problems"] == []
    assert inspect()["outputs"]["packages"] == ["default", "environment", "project"]
    (root / "src/index.tex").write_text("43\n")
    assert inspect()["problems"] == []
    companion.unlink()
    assert inspect()["problems"]
    for mutation in [
        lambda d: d.update(purifier="other"),
        lambda d: d["entries"][0].update(hash="invalid"),
        lambda d: d["entries"][1].update(path="../escape"),
        lambda d: d["entries"][1]["tectonic"]["files"].update(
            {"article.cls": "0" * 64}
        ),
        lambda d: d.update(sdk=None),
    ]:
        data = copy.deepcopy(original)
        mutation(data)
        companion.write_text(json.dumps(data))
        assert inspect()["problems"]
    companion.write_text(json.dumps(original))
    config = root / "Tectonic.toml"
    config.write_text(config.read_text() + "\n# stale\n")
    assert inspect()["problems"]
print("Native Tectonic resource declarations passed without IFD")

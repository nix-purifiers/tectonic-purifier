"""Re-fetch native data and regenerate the precompiled LaTeX format."""

from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parent.parent
system = subprocess.check_output(
    ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"], text=True
).strip()
base = str(repo) + "#checks." + system + ".environment"
subprocess.run(
    [
        "nix",
        "build",
        "--rebuild",
        "--no-link",
        base + ".rawFetches.index",
        base + ".rawFetches.archive",
        base + ".formats",
    ],
    check=True,
)
print("Native Tectonic index, working-set ZIP and LaTeX format reproduced identically")

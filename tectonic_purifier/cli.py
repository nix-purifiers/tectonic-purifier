import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .capture import capture
from .common import load, run
from .runtime import prepare


def locate(project=None, companion=None, start=None):
    root = Path(
        project or os.environ.get("TECTONIC_PURIFIER_PROJECT", start or Path.cwd())
    ).resolve()
    external = companion or os.environ.get("TECTONIC_PURIFIER_LOCK")
    if external:
        return root, Path(external).resolve()
    if project or os.environ.get("TECTONIC_PURIFIER_PROJECT"):
        return root, root / "tectonic-purifier.lock.json"
    for directory in [root, *root.parents]:
        if (directory / "tectonic-purifier.lock.json").exists():
            return directory, directory / "tectonic-purifier.lock.json"
    return root, root / "tectonic-purifier.lock.json"


def guard(args, data):
    for i, value in enumerate(args):
        if value in ("-b", "--bundle"):
            if i + 1 == len(args) or args[i + 1] != data["bundle"]:
                raise ValueError("Bundle selection changed; update the lock")
        elif value.startswith("--bundle=") and value.split("=", 1)[1] != data["bundle"]:
            raise ValueError("Bundle selection changed; update the lock")
        if value in ("-f", "--format"):
            if i + 1 == len(args) or args[i + 1] != "latex":
                raise ValueError(
                    "The initial integration supplies the native LaTeX format"
                )
    if args[:2] == ["-X", "new"]:
        raise ValueError(
            "Create a new document outside the locked project, then lock it"
        )


def main_impl():
    args = sys.argv[1:]
    if args and args[0].startswith("--native="):
        name = args[0].split("=", 1)[1]
        rest = args[1:]
        start = next(
            (
                Path(a).resolve().parent
                for a in rest
                if a.endswith(".tex") and Path(a).is_file()
            ),
            None,
        )
        root, companion = locate(start=start)
        original = os.environ["TECTONIC_PURIFIER_SCOPED"]
        if name == "nextonic":
            rest = ["-X", *rest]
        if not companion.exists():
            print(
                "tectonic-purifier: no lockfile; using ordinary impure " + name,
                file=sys.stderr,
            )
            env = dict(os.environ)
            env.pop("TECTONIC_PURIFIER_BUNDLE", None)
            env.pop("TECTONIC_PURIFIER_INDEX_FILE", None)
            os.execve(
                os.environ["TECTONIC_PURIFIER_ORIGINAL"],
                [os.environ["TECTONIC_PURIFIER_ORIGINAL"], *rest],
                env,
            )
        data = load(root, companion)
        guard(rest, data)
        env = prepare(root, companion)
        os.execve(original, [original, *rest], env)
    parser = argparse.ArgumentParser(
        description="Lock native Tectonic support resources"
    )
    parser.add_argument(
        "action", choices=["lock", "prefetch", "exec", "bundle", "publish"]
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--bundle")
    parser.add_argument("--tag")
    opts, remaining = parser.parse_known_args(args)
    root, companion = locate(opts.project, opts.lock)
    if opts.action == "lock":
        capture(root, companion, opts.update, opts.input, remaining, opts.bundle)
    elif opts.action in ("prefetch", "exec"):
        env = prepare(root, companion)
        if opts.action == "exec":
            if remaining and remaining[0] == "--":
                remaining = remaining[1:]
            if not remaining:
                parser.error("exec requires a command")
            env.update(
                TECTONIC_PURIFIER_PROJECT=str(root),
                TECTONIC_PURIFIER_LOCK=str(companion),
            )
            os.execvpe(remaining[0], remaining, env)
    else:
        load(root, companion)
        expression = (
            "import "
            + json.dumps(
                os.environ["TECTONIC_PURIFIER_SDK"]
                + "/lib/tectonic-purifier/nix/release.nix"
            )
            + " {root="
            + json.dumps(str(root))
            + ";lockFile="
            + json.dumps(str(companion))
            + ";}"
        )
        result = run(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--no-link",
                "--print-out-paths",
            ]
        )
        artifact = Path(result.strip()) / "tectonic-source.tar.gz"
        if opts.action == "bundle":
            print(artifact)
        else:
            if not opts.tag:
                parser.error("publish requires --tag")
            subprocess.run(
                [
                    os.environ.get("TECTONIC_PURIFIER_GH", "gh"),
                    "release",
                    "upload",
                    opts.tag,
                    str(artifact),
                    "--clobber",
                ],
                cwd=root,
                check=True,
            )


def main():
    try:
        main_impl()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print("tectonic-purifier: " + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

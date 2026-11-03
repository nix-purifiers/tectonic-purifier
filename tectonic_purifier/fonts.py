"""Use declared bundle fonts instead of ambient system font collections."""

from html import escape
import os
from pathlib import Path
import sys


def configure(bundle, cache, file):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    text = (
        "<fontconfig><dir>"
        + escape(str(bundle))
        + "</dir><cachedir>"
        + escape(str(cache))
        + "</cachedir></fontconfig>\n"
    )
    file = Path(file)
    if file.is_file() and file.read_text() == text:
        return
    temporary = file.with_name(file.name + ".tmp." + str(os.getpid()))
    temporary.write_text(text)
    temporary.replace(file)


if __name__ == "__main__":
    configure(*sys.argv[1:])

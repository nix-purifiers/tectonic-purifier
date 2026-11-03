import hashlib
import json
from pathlib import Path
import sys
import zipfile

source, spec, output = map(Path, sys.argv[1:])
metadata = json.loads(spec.read_text())
with zipfile.ZipFile(
    output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
) as archive:
    for name, expected in sorted(metadata["files"].items()):
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Native bundle resource changed: " + name)
        info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, data)
    info = zipfile.ZipInfo("SHA256SUM", (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, metadata["fingerprint"] + "\n")

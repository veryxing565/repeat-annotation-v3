#!/usr/bin/env python3
"""Build allowlisted source archives; no network, installation or publication."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = {"README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "VERSION", "CHANGELOG.md",
       "CITATION.cff", "CONTRIBUTING.md", "SECURITY.md", ".gitignore",
       ".gitattributes", "requirements.txt", "environment.yml", "run_te_annotation_v3.sh"}
FOLDERS = {"scripts", "patched_tools", "tests", "config", "examples", "docs", "provenance", ".github"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sources():
    result = {}
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_symlink():
            raise ValueError("Release tree must not contain symlinks: " + str(rel))
        if not p.is_file() or "__pycache__" in rel.parts:
            continue
        if (len(rel.parts) == 1 and rel.name not in TOP) or (len(rel.parts) > 1 and rel.parts[0] not in FOLDERS):
            continue
        if p.suffix in {".pyc", ".pyo"} or ".local." in p.name:
            continue
        data = p.read_bytes()
        if len(data) > 2_000_000 or b"\0" in data:
            raise ValueError("Unexpected binary/large source file: " + str(rel))
        data.decode("utf-8")
        result[rel.as_posix()] = data
    if not TOP.issubset(result):
        raise ValueError("Missing required release sources: " + repr(TOP - set(result)))
    return result


def executable(name):
    return name.endswith((".sh", ".py", ".pl")) or name.rsplit("/", 1)[-1] in {"LTR_FINDER_parallel", "LTR_HARVEST_parallel"}


def build(output):
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Use an output directory outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    version = (ROOT / "VERSION").read_text().strip()
    if not version or any(c not in "0123456789.abcdefghijklmnopqrstuvwxyz-" for c in version):
        raise ValueError("Unsafe release version")
    stem = "repeat-annotation-v3-" + version
    names = [stem + ".zip", stem + ".tar.gz", stem + ".files.json", "SHA256SUMS"]
    if any((output / n).exists() for n in names):
        raise FileExistsError("Release artifact already exists; choose a new output directory")
    files = sources()
    manifest = "".join(digest(data) + "  " + name + "\n" for name, data in files.items())
    file_record = {"version": version, "source_only": True,
                   "files": [{"path": n, "bytes": len(d), "sha256": digest(d)} for n, d in files.items()]}
    files["MANIFEST.sha256"] = manifest.encode()
    with zipfile.ZipFile(output / names[0], "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files.items():
            item = zipfile.ZipInfo(stem + "/" + name, date_time=(2026, 10, 29, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (0o100755 if executable(name) else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    with (output / names[1]).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, data in files.items():
                    item = tarfile.TarInfo(stem + "/" + name)
                    item.size, item.mtime, item.mode = len(data), 0, 0o755 if executable(name) else 0o644
                    item.uid = item.gid = 0
                    item.uname = item.gname = ""
                    archive.addfile(item, io.BytesIO(data))
    (output / names[2]).write_text(json.dumps(file_record, indent=2) + "\n", encoding="utf-8")
    checks = "".join(digest((output / n).read_bytes()) + "  " + n + "\n" for n in names[:3])
    (output / names[3]).write_text(checks, encoding="ascii")
    print(json.dumps({"version": version, "source_files": len(file_record["files"]),
                      "artifacts": [str(output / n) for n in names]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)

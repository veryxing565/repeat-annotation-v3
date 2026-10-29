#!/usr/bin/env python3
"""Local ownership, provenance and CPU guards; no scientific tool invocation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime

SCHEMA = "repeat-annotation-v3-portable-1"
ROOT_MARKER = ".te-v3-root.json"
SAMPLE_MARKER = ".te-v3-sample.json"


def fail(message):
    raise ValueError(message)


def stamp():
    return datetime.now().astimezone().isoformat()


def no_links(path):
    """Reject symlinks in the path itself and every existing ancestor."""
    path = Path(path)
    if not path.is_absolute():
        fail("Path must be absolute: " + str(path))
    for p in [path, *path.parents]:
        if p.is_symlink():
            fail("Symlink not permitted for owned paths: " + str(p))
    return path


def dedicated(path):
    if any(c in str(path) for c in "\r\n\t"):
        fail("Control characters are not permitted in workspace roots")
    if not Path(path).is_absolute() or any(x in {".", ".."} for x in str(path).split("/")):
        fail("Use an absolute workspace path without . or .. components")
    path = Path(os.path.abspath(os.path.expanduser(path)))
    no_links(path)
    broad = {Path(x) for x in ("/", "/home", "/tmp", "/var", "/var/tmp", "/media",
                               "/mnt", "/scratch", "/data", "/work", "/usr", "/opt")}
    broad.add(Path.home().resolve())
    if path in broad or len(path.parts) < 3 or (path.exists() and path.is_mount()):
        fail("Use a dedicated project subdirectory, not a broad root: " + str(path))
    if path.exists() and not path.is_dir():
        fail("Workspace is not a directory: " + str(path))
    return path


def under(path, parent):
    return path == parent or parent in path.parents


def roots(result, temporary):
    result, temporary = dedicated(result), dedicated(temporary)
    if under(result, temporary) or under(temporary, result):
        fail("RESULT_ROOT and TMP_ROOT must be disjoint, not nested")
    # The retained upstream Perl wrappers use shell strings internally.
    if not re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(temporary)):
        fail("TMP_ROOT must use only ASCII letters, digits, / _ . + - for upstream Perl wrappers")
    return result, temporary


def sample_id(value):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value)
            or ".." in value):
        fail("Unsafe sample ID (not sanitized automatically): " + repr(value))
    return value


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8388608), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    no_links(path)
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    no_links(path)
    part = path.with_name(path.name + ".partial")
    no_links(part)
    with part.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    part.replace(path)


def root_record(path, kind, result, temporary):
    return {"schema": SCHEMA, "kind": kind, "result_root": str(result),
            "temporary_root": str(temporary)}


def own_root(path, kind, result, temporary, create=False):
    record = root_record(path, kind, result, temporary)
    marker = path / ROOT_MARKER
    no_links(marker)
    if marker.exists():
        if read_json(marker) != record:
            fail("Workspace owner mismatch: " + str(marker))
    elif create:
        if path.exists() and any(path.iterdir()):
            fail("Refusing to claim a nonempty, unowned workspace: " + str(path))
        path.mkdir(parents=True, exist_ok=True)
        atomic_json(marker, record)
    else:
        fail("Workspace ownership marker missing: " + str(marker))


def manifest(path, result, temporary, script_dir):
    seen = set()
    script_dir = Path(script_dir).resolve()
    if under(script_dir, temporary):
        fail("Workflow source cannot be inside TMP_ROOT")
    if not re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(script_dir)):
        fail("Workflow source path contains characters unsafe for upstream Perl shell commands")
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for number, text in enumerate(stream, 1):
            text = text.rstrip("\n")
            if text.endswith("\r"):
                fail("Use Unix LF line endings in manifest (line %d)" % number)
            if not text.strip() or text.startswith("#"):
                continue
            columns = text.split("\t")
            if len(columns) != 2:
                fail("Manifest line %d must contain exactly two tab-separated columns" % number)
            sample, raw = columns
            sample_id(sample)
            if sample in seen:
                fail("Duplicate sample ID: " + sample)
            seen.add(sample)
            genome = Path(raw)
            if not genome.is_absolute() or not genome.is_file() or not genome.stat().st_size:
                fail("Genome must be an absolute, nonempty file: " + raw)
            if any(c in raw for c in "\r\n\t"):
                fail("Control characters in input path")
            if under(genome.resolve(), temporary):
                fail("Genome input must not be inside TMP_ROOT: " + raw)
            print("OK\t%s\t%s" % (sample, genome))
    if not seen:
        fail("Manifest has no genomes")
    print("PRECHECK_OK genomes=%d" % len(seen))


def sample_work(result, temporary, sample):
    sample_id(sample)
    work = temporary / sample
    no_links(work)
    if work.parent != temporary:
        fail("Unexpected sample work path")
    return work


def verify_export(directory):
    no_links(directory)
    for p in directory.rglob("*"):
        if p.is_symlink():
            fail("Symlink in published results: " + str(p))
    checksums = directory / "qc/result_sha256.txt"
    no_links(checksums)
    count = 0
    seen = set()
    for line in checksums.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not match:
            fail("Malformed SHA256 manifest: " + str(checksums))
        expected, relative = match.groups()
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            fail("Checksum path escapes result directory")
        p = directory / relative
        no_links(p)
        if p in seen or not p.is_file() or sha(p) != expected.lower():
            fail("Result checksum mismatch/duplicate/missing file: " + str(p))
        seen.add(p)
        count += 1
    if count == 0:
        fail("Empty result checksum manifest")
    actual = {p for p in directory.rglob("*") if p.is_file() and p != checksums}
    if actual != seen:
        fail("Result manifest does not cover every retained result file")


def verify_complete(result, sample, genome):
    sample_id(sample)
    marker = result / "state" / (sample + ".complete")
    no_links(marker)
    directory = result / "results" / sample
    text = marker.read_text()
    if text.lstrip().startswith("{"):
        record = json.loads(text)
        if (record.get("schema") != SCHEMA or record.get("sample") != sample
                or record.get("result") != str(directory)
                or sha(genome) != record.get("input_sha256")):
            fail("Completed sample provenance mismatch: " + sample)
    else:
        # Read-only compatibility with old v3 output. Never trust a marker alone.
        values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        if values.get("sample") != sample or values.get("result") != str(directory):
            fail("Legacy completion marker does not match sample/results")
        original = Path(values.get("genome", ""))
        recorded = None
        for line in (directory / "qc/input_sha256.txt").read_text().splitlines():
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
            if match and Path(match[2]) == original:
                recorded = match[1].lower()
        if not recorded or sha(genome) != recorded:
            fail("Legacy input checksum missing or different")
    verify_export(directory)
    print("VERIFIED_COMPLETE\t" + sample)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["roots", "guard-tool-path", "manifest", "prepare", "init-sample", "validate-sample", "complete",
                                          "cleanup-sample", "cleanup-root", "verify-complete", "cpus"])
    parser.add_argument("--result")
    parser.add_argument("--temporary")
    parser.add_argument("--sample")
    parser.add_argument("--genome")
    parser.add_argument("--manifest")
    parser.add_argument("--script-dir")
    parser.add_argument("--threads", type=int)
    parser.add_argument("--path")
    args = parser.parse_args()
    if args.action == "guard-tool-path":
        if not re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(Path(args.path).resolve())):
            fail("Tool path contains characters unsafe for upstream Perl shell commands: " + args.path)
        return
    if args.action == "cpus":
        allowed = sorted(os.sched_getaffinity(0))
        if not args.threads or args.threads < 4 or args.threads % 4 or args.threads > len(allowed):
            fail("THREADS must be >=4, divisible by 4, and <= current allowed CPUs (%d)" % len(allowed))
        print(",".join(map(str, allowed[:args.threads])))
        return
    if args.action == "verify-complete":
        result = dedicated(args.result)
        verify_complete(result, args.sample, Path(args.genome).resolve())
        return
    result, temporary = roots(args.result, args.temporary)
    if args.action == "roots":
        print(result)
        print(temporary)
        return
    if args.action == "manifest":
        manifest(args.manifest, result, temporary, args.script_dir)
        return
    if args.action == "prepare":
        own_root(result, "results", result, temporary, create=True)
        own_root(temporary, "temporary", result, temporary, create=True)
        for name in ("results", "logs", "state", "workflow_snapshot"):
            p = result / name
            no_links(p)
            p.mkdir(exist_ok=True)
        return
    own_root(result, "results", result, temporary)
    own_root(temporary, "temporary", result, temporary)
    if args.action == "cleanup-root":
        if set(temporary.iterdir()) == {temporary / ROOT_MARKER}:
            (temporary / ROOT_MARKER).unlink()
            temporary.rmdir()
            print("Owned empty temporary root removed")
        else:
            print("Temporary root contains retained files; not removed")
        return
    work = sample_work(result, temporary, args.sample)
    marker = work / SAMPLE_MARKER
    if args.action == "init-sample":
        if work.exists():
            fail("Sample workspace already exists; inspect before retry: " + str(work))
        genome = Path(args.genome).resolve()
        if under(genome, temporary):
            fail("Input cannot be inside temporary root")
        work.mkdir()
        atomic_json(marker, dict(schema=SCHEMA, result_root=str(result), temporary_root=str(temporary),
                                sample=args.sample, input=str(genome), input_sha256=sha(genome)))
        return
    record = read_json(marker)
    if (record.get("schema") != SCHEMA or record.get("sample") != args.sample
            or record.get("result_root") != str(result) or record.get("temporary_root") != str(temporary)):
        fail("Sample ownership mismatch: " + str(marker))
    if args.action == "validate-sample":
        genome = Path(args.genome).resolve()
        if record.get("input") != str(genome) or record.get("input_sha256") != sha(genome):
            fail("Resume input differs from sample ownership record")
        return
    completion = result / "state" / (args.sample + ".complete")
    if args.action == "complete":
        genome = Path(args.genome).resolve()
        if record.get("input") != str(genome) or record.get("input_sha256") != sha(genome):
            fail("Input changed during annotation")
        directory = result / "results" / args.sample
        verify_export(directory)
        if completion.exists() or completion.is_symlink():
            fail("Refusing to overwrite completion marker")
        atomic_json(completion, dict(schema=SCHEMA, sample=args.sample, input=str(genome),
                                    input_sha256=record["input_sha256"], result=str(directory),
                                    completed=stamp(), temp_removed=False))
    elif args.action == "cleanup-sample":
        verify_complete(result, args.sample, Path(args.genome).resolve())
        if not shutil.rmtree.avoids_symlink_attacks:
            fail("This Python lacks fd-based safe rmtree support")
        shutil.rmtree(work)
        completed = read_json(completion)
        completed.update(temp_removed=True, temporary_cleanup=stamp())
        atomic_json(completion, completed)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("SAFETY_ERROR: " + str(exc), file=sys.stderr)
        sys.exit(2)

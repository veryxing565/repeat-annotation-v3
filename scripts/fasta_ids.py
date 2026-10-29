#!/usr/bin/env python3
"""Preserve safe IDs within the LTR_retriever 3.0.5 length limit."""

import argparse
import gzip
import hashlib
import re
from pathlib import Path

from Bio import SeqIO


SAFE_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def compliant(name, limit):
    return len(name) <= limit and SAFE_ID.fullmatch(name) is not None


def id_limit(max_length):
    limit = 44 - 4 * len(str(max_length))
    if limit < 1:
        raise ValueError("longest sequence leaves no room for LTR_retriever IDs")
    return limit


def inspect_input(path):
    opener = gzip.open if str(path).lower().endswith(".gz") else open
    ids = set()
    longest = bases = 0
    with opener(path, "rt", encoding="ascii") as handle:
        for record in SeqIO.parse(handle, "fasta"):
            if record.id in ids:
                raise ValueError(f"duplicate original FASTA id: {record.id}")
            if not len(record.seq):
                raise ValueError(f"empty sequence: {record.id}")
            ids.add(record.id)
            longest = max(longest, len(record.seq))
            bases += len(record.seq)
    if not ids:
        raise ValueError("input FASTA has no sequences")
    limit = id_limit(longest)
    return ids, longest, bases, limit


def base36(number):
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while number:
        number, digit = divmod(number, 36)
        result = alphabet[digit] + result
    return result or "0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--map")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    sample = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.sample).strip("_")
    if not sample:
        raise SystemExit("sample name becomes empty after sanitizing")

    original_ids, longest, input_bases, limit = inspect_input(args.input)
    rename_count = sum(not compliant(name, limit) for name in original_ids)
    summary = (f"id_policy=preserve_compliant_rename_unsafe_or_overlong\tid_limit={limit}"
               f"\tmax_sequence_length={longest}\tmax_original_id_length={max(map(len, original_ids))}"
               f"\tids_preserved={len(original_ids)-rename_count}\tids_renamed={rename_count}")
    if args.check_only:
        print(f"records={len(original_ids)}\tbases={input_bases}\t{summary}")
        return
    if not args.output or not args.map:
        parser.error("--output and --map required unless --check-only")
    if len({Path(p).resolve() for p in (args.input, args.output, args.map)}) != 3:
        parser.error("input, output and map must be distinct paths")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    reserved = set(original_ids)
    next_code = 1
    seen = set()
    count = 0
    bases = 0
    digest = hashlib.sha256()
    with open(args.output, "w", encoding="ascii") as out_fh, open(
        args.map, "w", encoding="utf-8"
    ) as map_fh:
        map_fh.write("short_id\toriginal_id\toriginal_description\tlength\n")
        opener = gzip.open if str(args.input).lower().endswith(".gz") else open
        with opener(args.input, "rt", encoding="ascii", errors="replace") as input_fh:
            records = SeqIO.parse(input_fh, "fasta")
            for count, record in enumerate(records, 1):
                short_id = record.id
                if not compliant(short_id, limit):
                    while True:
                        short_id = "s" + base36(next_code)
                        next_code += 1
                        if len(short_id) > limit:
                            raise ValueError("not enough unique short IDs within limit")
                        if short_id not in reserved:
                            reserved.add(short_id)
                            break
                if record.id in seen:
                    raise SystemExit(f"duplicate original FASTA id: {record.id}")
                seen.add(record.id)
                sequence = str(record.seq).upper()
                bases += len(sequence)
                digest.update(f">{short_id}\n{sequence}\n".encode("ascii"))
                out_fh.write(f">{short_id}\n")
                for start in range(0, len(sequence), 60):
                    out_fh.write(sequence[start : start + 60] + "\n")
                description = record.description.replace("\t", " ").replace("\n", " ")
                map_fh.write(f"{short_id}\t{record.id}\t{description}\t{len(sequence)}\n")

    if count == 0:
        raise SystemExit("input FASTA has no sequences")
    print(f"records={count}\tbases={bases}\tcanonical_sha256={digest.hexdigest()}\t{summary}")


if __name__ == "__main__":
    main()

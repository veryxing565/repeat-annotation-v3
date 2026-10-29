#!/usr/bin/env python3
"""Normalize, classify and conservatively deduplicate TE consensus libraries."""

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord


CLASS_MAP = {
    "Copia": "LTR/Copia",
    "Crypton": "DNA/Crypton",
    "ERV": "LTR/ERV",
    "Gypsy": "LTR/Gypsy",
    "hAT": "DNA/hAT",
    "Helitron": "RC/Helitron",
    "Jockey": "LINE/Jockey",
    "L1_L2": "LINE/L1",
    "Maverick": "DNA/Maverick",
    "Merlin": "DNA/Merlin",
    "P": "DNA/P",
    "Pao": "LTR/Pao",
    "RTE": "LINE/RTE",
    "SINE": "SINE",
    "TcMar": "DNA/TcMar",
    "Transib": "DNA/Transib",
}

SOURCE_PRIORITY = {
    "LTRstruct": 0,
    "RepeatModeler_known": 1,
    "TEClass2_high": 2,
    "RepeatModeler_unknown": 3,
    "Unknown": 4,
}


def class_specificity_penalty(te_class: str) -> int:
    """Prefer a specific TE label without ever discarding Unknown records."""
    value = (te_class or "Unknown").strip().lower()
    if value in {"unknown", "unclassified", "uncategorized"}:
        return 2
    if value.endswith("/unknown") or value.startswith("unknown/"):
        return 1
    return 0


def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.|:-]+", "_", value).strip("_") or "item"


def split_header(record: SeqRecord, default_class: str = "Unknown") -> tuple[str, str]:
    rid = record.id
    if "#" in rid:
        name, te_class = rid.rsplit("#", 1)
    else:
        name, te_class = rid, default_class
    te_class = te_class.strip() or default_class
    return name, te_class


def write_record(handle, record: SeqRecord, rid: str, te_class: str) -> None:
    sequence = str(record.seq).upper()
    handle.write(f">{rid}#{te_class}\n")
    for start in range(0, len(sequence), 60):
        handle.write(sequence[start : start + 60] + "\n")


def write_metadata(path: str, rows: list[dict]) -> None:
    fields = [
        "record_id",
        "species",
        "source",
        "original_id",
        "original_class",
        "teclass2_class",
        "teclass2_score",
        "final_class",
        "decision",
        "cluster_id",
        "member_count",
        "member_ids",
        "length",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize(args) -> None:
    rows = []
    with open(args.output, "w", encoding="ascii") as out:
        for index, record in enumerate(SeqIO.parse(args.input, "fasta"), 1):
            original_id, te_class = split_header(record, args.default_class)
            rid = f"{safe(args.species)}|{safe(args.tag)}|{index:07d}"
            write_record(out, record, rid, te_class)
            rows.append(
                {
                    "record_id": rid,
                    "species": args.species,
                    "source": args.source,
                    "original_id": original_id,
                    "original_class": te_class,
                    "final_class": te_class,
                    "decision": "source_class",
                    "length": len(record.seq),
                }
            )
    if not rows:
        raise SystemExit(f"empty library: {args.input}")
    write_metadata(args.metadata, rows)


def split_repeatmodeler(args) -> None:
    rows = []
    known_n = unknown_n = 0
    with open(args.known, "w", encoding="ascii") as known, open(
        args.unknown, "w", encoding="ascii"
    ) as unknown:
        for index, record in enumerate(SeqIO.parse(args.input, "fasta"), 1):
            original_id, te_class = split_header(record)
            rid = f"{safe(args.species)}|RM|{index:07d}"
            is_unknown = te_class.lower().startswith("unknown")
            source = "RepeatModeler_unknown" if is_unknown else "RepeatModeler_known"
            write_record(unknown if is_unknown else known, record, rid, "Unknown" if is_unknown else te_class)
            known_n += int(not is_unknown)
            unknown_n += int(is_unknown)
            rows.append(
                {
                    "record_id": rid,
                    "species": args.species,
                    "source": source,
                    "original_id": original_id,
                    "original_class": te_class,
                    "final_class": "Unknown" if is_unknown else te_class,
                    "decision": "send_to_teclass2" if is_unknown else "repeatmodeler_known",
                    "length": len(record.seq),
                }
            )
    if not rows:
        raise SystemExit(f"empty RepeatModeler library: {args.input}")
    write_metadata(args.metadata, rows)
    print(f"known={known_n}\tunknown={unknown_n}")


def read_predictions(path: str) -> dict[str, tuple[str, float]]:
    result = {}
    with open(path, encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"name", "class", "max_probability"}
        if not required.issubset(reader.fieldnames or []):
            raise SystemExit(f"TEClass2 output lacks columns {sorted(required)}: {path}")
        for row in reader:
            name = row["name"]
            score = float(row["max_probability"])
            if not name or name in result:
                raise SystemExit(f"empty or duplicate TEClass2 prediction name: {name!r}")
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise SystemExit(f"invalid TEClass2 probability for {name}: {score}")
            result[name] = (row["class"], score)
    return result


def apply_teclass(args) -> None:
    predictions = read_predictions(args.predictions)
    rows = []
    accepted_n = unknown_n = 0
    with open(args.accepted, "w", encoding="ascii") as accepted, open(
        args.unknown, "w", encoding="ascii"
    ) as unknown:
        for record in SeqIO.parse(args.input, "fasta"):
            rid, original_class = split_header(record)
            prediction = predictions.get(record.id) or predictions.get(rid)
            if prediction is None:
                predicted_class, score = "", 0.0
            else:
                predicted_class, score = prediction
            mapped = CLASS_MAP.get(predicted_class, "Unknown")
            if score >= args.threshold and mapped != "Unknown":
                final_class = mapped
                decision = "accepted"
                source = "TEClass2_high"
                accepted_n += 1
                target = accepted
            else:
                final_class = "Unknown"
                decision = "candidate_only" if score >= args.candidate_threshold else "retained_unknown"
                source = "RepeatModeler_unknown"
                unknown_n += 1
                target = unknown
            write_record(target, record, rid, final_class)
            rows.append(
                {
                    "record_id": rid,
                    "species": args.species,
                    "source": source,
                    "original_id": rid,
                    "original_class": original_class,
                    "teclass2_class": predicted_class,
                    "teclass2_score": f"{score:.6f}",
                    "final_class": final_class,
                    "decision": decision,
                    "length": len(record.seq),
                }
            )
    write_metadata(args.metadata, rows)
    print(f"accepted={accepted_n}\tretained_unknown={unknown_n}")


def load_metadata(paths: list[str]) -> dict[str, dict]:
    rows = {}
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                key = row.get("record_id", "")
                if key:
                    rows[key] = row
    return rows


def parse_clusters(path: str) -> list[list[str]]:
    clusters = []
    current = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(">Cluster"):
                if current:
                    clusters.append(current)
                current = []
                continue
            match = re.search(r">(.+?)\.\.\.", line)
            if match:
                current.append(match.group(1).split("#", 1)[0])
    if current:
        clusters.append(current)
    return clusters


def dedup_select(args) -> None:
    records = {}
    classes = {}
    for record in SeqIO.parse(args.input, "fasta"):
        rid, te_class = split_header(record)
        if rid in records:
            raise SystemExit(f"duplicate library id before CD-HIT: {rid}")
        records[rid] = record
        classes[rid] = te_class
    metadata = load_metadata(args.metadata)
    clusters = parse_clusters(args.clusters)
    flat_ids = [rid for cluster in clusters for rid in cluster]
    clustered_ids = set(flat_ids)
    if len(flat_ids) != len(clustered_ids):
        raise SystemExit("duplicate record membership in CD-HIT clusters")
    unexpected = clustered_ids - set(records)
    if unexpected:
        raise SystemExit(f"{len(unexpected)} unexpected IDs in CD-HIT clusters")
    missing = set(records) - clustered_ids
    if missing:
        raise SystemExit(f"{len(missing)} input records are absent from CD-HIT clusters")

    output_rows = []
    with open(args.output, "w", encoding="ascii") as out:
        for index, members in enumerate(clusters, 1):
            def rank(rid: str):
                row = metadata.get(rid, {})
                source = row.get("source") or row.get("selected_source") or "Unknown"
                specificity = class_specificity_penalty(classes.get(rid, "Unknown"))
                return (specificity, SOURCE_PRIORITY.get(source, 9), -len(records[rid].seq), rid)

            selected = min(members, key=rank)
            selected_row = metadata.get(selected, {})
            species = selected_row.get("species", selected.split("|", 1)[0])
            source = selected_row.get("source", "Unknown")
            final_id = f"{safe(args.scope)}|TE|{index:07d}"
            final_class = classes[selected]
            write_record(out, records[selected], final_id, final_class)
            output_rows.append(
                {
                    "record_id": final_id,
                    "species": species,
                    "source": source,
                    "original_id": selected,
                    "original_class": selected_row.get("original_class", ""),
                    "teclass2_class": selected_row.get("teclass2_class", ""),
                    "teclass2_score": selected_row.get("teclass2_score", ""),
                    "final_class": final_class,
                    "decision": "cdhit_cluster_representative",
                    "cluster_id": index - 1,
                    "member_count": len(members),
                    "member_ids": ",".join(members),
                    "length": len(records[selected].seq),
                }
            )
    if not output_rows:
        raise SystemExit("CD-HIT produced no clusters")
    write_metadata(args.output_metadata, output_rows)
    print(f"input={len(records)}\tclusters={len(output_rows)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("normalize")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--metadata", required=True)
    p.add_argument("--species", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--default-class", default="Unknown")
    p.set_defaults(func=normalize)

    p = sub.add_parser("split-repeatmodeler")
    p.add_argument("--input", required=True)
    p.add_argument("--known", required=True)
    p.add_argument("--unknown", required=True)
    p.add_argument("--metadata", required=True)
    p.add_argument("--species", required=True)
    p.set_defaults(func=split_repeatmodeler)

    p = sub.add_parser("apply-teclass")
    p.add_argument("--input", required=True)
    p.add_argument("--predictions", required=True)
    p.add_argument("--accepted", required=True)
    p.add_argument("--unknown", required=True)
    p.add_argument("--metadata", required=True)
    p.add_argument("--species", required=True)
    p.add_argument("--threshold", type=float, default=0.80)
    p.add_argument("--candidate-threshold", type=float, default=0.70)
    p.set_defaults(func=apply_teclass)

    p = sub.add_parser("dedup-select")
    p.add_argument("--input", required=True)
    p.add_argument("--clusters", required=True)
    p.add_argument("--metadata", nargs="+", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--output-metadata", required=True)
    p.add_argument("--scope", required=True)
    p.set_defaults(func=dedup_select)
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    parsed.func(parsed)

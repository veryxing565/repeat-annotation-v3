"""Test library decisions without running TE classifiers or CD-HIT binaries."""

import argparse
import contextlib
import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

from Bio import SeqIO

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import library_ops as ops


class LibraryTests(unittest.TestCase):
    def test_invalid_prediction_probabilities_are_rejected(self):
        for score in ("nan", "inf", "-0.1", "1.1"):
            with self.subTest(score=score), self.assertRaises(SystemExit):
                self.classify(">item#Unknown\nACGT\n", "item\tGypsy\t" + score + "\n")

    def test_duplicate_prediction_names_are_rejected(self):
        with self.assertRaisesRegex(SystemExit, "duplicate"):
            self.classify(">item#Unknown\nACGT\n", "item\tGypsy\t0.9\nitem\tCopia\t0.8\n")

    def test_duplicate_cluster_membership_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "duplicate record membership"):
            self.dedup(">a#Unknown\nACGT\n", ">Cluster 0\n0 4nt, >a#Unknown... *\n>Cluster 1\n0 4nt, >a#Unknown... *\n", [])

    def test_unexpected_cluster_id_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "unexpected IDs"):
            self.dedup(">a#Unknown\nACGT\n", ">Cluster 0\n0 4nt, >other#Unknown... *\n", [])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def path(self, name):
        return self.root / name

    def write(self, name, text):
        path = self.path(name)
        path.write_text(text, encoding="utf-8")
        return path

    def records(self, name):
        with self.path(name).open(encoding="ascii") as handle:
            return list(SeqIO.parse(handle, "fasta"))

    def metadata(self, name):
        with self.path(name).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def run_command(self, arguments):
        args = ops.build_parser().parse_args(arguments)
        with contextlib.redirect_stdout(io.StringIO()):
            args.func(args)

    def split_rm(self, text):
        self.write("rm.fa", text)
        self.run_command([
            "split-repeatmodeler", "--input", str(self.path("rm.fa")),
            "--known", str(self.path("known.fa")),
            "--unknown", str(self.path("unknown.fa")),
            "--metadata", str(self.path("rm.tsv")), "--species", "Example_species",
        ])

    def classify(self, fasta, predictions):
        self.write("input.fa", fasta)
        self.write("predictions.tsv", "name\tclass\tmax_probability\n" + predictions)
        self.run_command([
            "apply-teclass", "--input", str(self.path("input.fa")),
            "--predictions", str(self.path("predictions.tsv")),
            "--accepted", str(self.path("accepted.fa")),
            "--unknown", str(self.path("retained.fa")),
            "--metadata", str(self.path("classified.tsv")), "--species", "Example_species",
        ])

    def dedup(self, fasta, clusters, metadata):
        self.write("merged.fa", fasta)
        self.write("clusters.clstr", clusters)
        fields = ["record_id", "species", "source", "original_class"]
        with self.path("merged.tsv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(metadata)
        self.run_command([
            "dedup-select", "--input", str(self.path("merged.fa")),
            "--clusters", str(self.path("clusters.clstr")),
            "--metadata", str(self.path("merged.tsv")),
            "--output", str(self.path("final.fa")),
            "--output-metadata", str(self.path("final.tsv")), "--scope", "Example_species",
        ])

    def test_split_sends_only_repeatmodeler_unknown_to_classifier(self):
        self.split_rm(
            ">known#DNA/hAT description\nacgt\n"
            ">unknown#Unknown\nggtt\n>unlabelled\nccaa\n"
        )
        self.assertEqual([r.id for r in self.records("known.fa")], ["Example_species|RM|0000001#DNA/hAT"])
        self.assertEqual([r.id for r in self.records("unknown.fa")], [
            "Example_species|RM|0000002#Unknown", "Example_species|RM|0000003#Unknown",
        ])
        self.assertEqual([r["decision"] for r in self.metadata("rm.tsv")], [
            "repeatmodeler_known", "send_to_teclass2", "send_to_teclass2",
        ])
        self.assertEqual(sum(len(self.records(n)) for n in ("known.fa", "unknown.fa")), 3)

    def test_known_predictions_do_not_enter_unknown_only_stage(self):
        self.split_rm(">known#LTR/Gypsy\nacgt\n>unknown#Unknown\ntgca\n")
        known_before = self.path("known.fa").read_bytes()
        unknown = self.path("unknown.fa").read_text()
        self.classify(unknown, "Example_species|RM|0000001\tCopia\t1.0\n")
        self.assertEqual(self.path("known.fa").read_bytes(), known_before)
        self.assertEqual(self.records("accepted.fa"), [])
        self.assertEqual(len(self.records("retained.fa")), 1)
        self.assertEqual(self.metadata("classified.tsv")[0]["decision"], "retained_unknown")

    def test_acceptance_and_candidate_boundaries(self):
        fasta = "".join(f">r{i}#Unknown\nacgt\n" for i in range(1, 7))
        self.classify(fasta, "\n".join([
            "r1#Unknown\tGypsy\t0.8", "r2\thAT\t0.799999",
            "r3\tCopia\t0.7", "r4\tSINE\t0.699999",
            "r5\tUnsupportedLabel\t0.99",
        ]) + "\n")
        self.assertEqual([r.id for r in self.records("accepted.fa")], ["r1#LTR/Gypsy"])
        self.assertEqual(len(self.records("retained.fa")), 5)
        rows = self.metadata("classified.tsv")
        self.assertEqual([r["decision"] for r in rows], [
            "accepted", "candidate_only", "candidate_only", "retained_unknown",
            "candidate_only", "retained_unknown",
        ])
        self.assertTrue(all(r["final_class"] == "Unknown" for r in rows[1:]))
        self.assertEqual(rows[0]["source"], "TEClass2_high")
        self.assertTrue(all(r["source"] == "RepeatModeler_unknown" for r in rows[1:]))
        self.assertEqual(len(rows), 6, "No uncertain or unpredicted sequence may be discarded")

    def test_parser_threshold_defaults_are_eighty_and_seventy_percent(self):
        args = ops.build_parser().parse_args([
            "apply-teclass", "--input", "in", "--predictions", "pred",
            "--accepted", "yes", "--unknown", "no", "--metadata", "meta", "--species", "sp",
        ])
        self.assertEqual((args.threshold, args.candidate_threshold), (0.8, 0.7))

    def test_prediction_table_requires_explicit_columns(self):
        path = self.write("bad.tsv", "id\tprediction\nfoo\tGypsy\n")
        with self.assertRaisesRegex(SystemExit, "lacks columns"):
            ops.read_predictions(str(path))

    def test_normalized_headers_are_repeatmasker_compatible_and_uppercase(self):
        self.write("ltr.fa", ">original#LTR/Copia annotation\n" + "acgt" * 17 + "\n>other\nacnn\n")
        self.run_command([
            "normalize", "--input", str(self.path("ltr.fa")), "--output", str(self.path("normalized.fa")),
            "--metadata", str(self.path("normalized.tsv")), "--species", "Example species",
            "--source", "LTRstruct", "--tag", "LTR source",
        ])
        records = self.records("normalized.fa")
        self.assertEqual([r.id for r in records], [
            "Example_species|LTR_source|0000001#LTR/Copia", "Example_species|LTR_source|0000002#Unknown",
        ])
        self.assertTrue(all(r.description == r.id for r in records))
        self.assertTrue(all(str(r.seq) == str(r.seq).upper() for r in records))
        self.assertTrue(all(len(line) <= 60 for line in self.path("normalized.fa").read_text().splitlines() if not line.startswith(">")))
        self.assertEqual(self.metadata("normalized.tsv")[0]["original_id"], "original")

    def test_classified_record_beats_unknown_even_with_lower_source_priority(self):
        self.dedup(
            ">u#Unknown\n" + "A" * 100 + "\n>k#DNA/hAT\nACGT\n",
            ">Cluster 0\n0 100nt, >u#Unknown... *\n1 4nt, >k#DNA/hAT... at +/99%\n",
            [{"record_id": "u", "species": "sp", "source": "LTRstruct"},
             {"record_id": "k", "species": "sp", "source": "RepeatModeler_known"}],
        )
        self.assertEqual(self.records("final.fa")[0].id, "Example_species|TE|0000001#DNA/hAT")
        self.assertEqual(self.metadata("final.tsv")[0]["original_id"], "k")
        self.assertEqual(self.metadata("final.tsv")[0]["member_ids"], "u,k")

    def test_unknown_near_duplicates_can_collapse_but_unknown_singletons_remain(self):
        # CD-HIT is not executed here: this fixture explicitly supplies its cluster membership.
        self.dedup(
            ">u1#Unknown\nAAAA\n>u2#Unknown\nAAAAA\n>u3#Unknown\nCCCC\n",
            ">Cluster 0\n0 4nt, >u1#Unknown... at +/99%\n1 5nt, >u2#Unknown... *\n"
            ">Cluster 1\n0 4nt, >u3#Unknown... *\n",
            [{"record_id": x, "source": "RepeatModeler_unknown"} for x in ("u1", "u2", "u3")],
        )
        self.assertEqual(len(self.records("final.fa")), 2)
        self.assertTrue(all(r.id.endswith("#Unknown") for r in self.records("final.fa")))
        self.assertEqual([r["original_id"] for r in self.metadata("final.tsv")], ["u2", "u3"])
        self.assertEqual([r["member_count"] for r in self.metadata("final.tsv")], ["2", "1"])

    def test_conflicting_known_classes_choose_one_representative_not_one_per_class(self):
        self.dedup(
            ">dna#DNA/hAT\nAAAA\n>ltr#LTR/Gypsy\nAAAAA\n",
            ">Cluster 0\n0 4nt, >dna#DNA/hAT... at +/99%\n1 5nt, >ltr#LTR/Gypsy... *\n",
            [{"record_id": "dna", "source": "LTRstruct"},
             {"record_id": "ltr", "source": "RepeatModeler_known"}],
        )
        self.assertEqual(len(self.records("final.fa")), 1)
        row = self.metadata("final.tsv")[0]
        self.assertEqual((row["original_id"], row["final_class"]), ("dna", "DNA/hAT"))
        self.assertEqual(row["member_ids"], "dna,ltr")

    def test_specific_class_beats_partially_unknown_label(self):
        self.assertEqual(ops.class_specificity_penalty("DNA/hAT"), 0)
        self.assertEqual(ops.class_specificity_penalty("LTR/Unknown"), 1)
        for name in ("Unknown", "unclassified", "uncategorized"):
            self.assertEqual(ops.class_specificity_penalty(name), 2)
        self.dedup(
            ">broad#LTR/Unknown\nAAAAA\n>specific#LTR/Gypsy\nAAAA\n",
            ">Cluster 0\n0 5nt, >broad#LTR/Unknown... *\n1 4nt, >specific#LTR/Gypsy... at +/99%\n",
            [{"record_id": "broad", "source": "LTRstruct"},
             {"record_id": "specific", "source": "TEClass2_high"}],
        )
        self.assertEqual(self.metadata("final.tsv")[0]["original_id"], "specific")

    def test_input_record_missing_from_clusters_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "absent from CD-HIT"):
            self.dedup(">a#Unknown\nAAAA\n>b#Unknown\nCCCC\n", ">Cluster 0\n0 4nt, >a#Unknown... *\n", [])

    def test_duplicate_precluster_ids_are_rejected_even_if_classes_differ(self):
        with self.assertRaisesRegex(SystemExit, "duplicate library id"):
            self.dedup(">a#Unknown\nAAAA\n>a#DNA/hAT\nCCCC\n", ">Cluster 0\n0 4nt, >a#Unknown... *\n", [])


if __name__ == "__main__":
    unittest.main()

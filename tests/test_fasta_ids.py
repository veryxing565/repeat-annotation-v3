"""Validate selective ID shortening and uppercase output before LTR discovery."""

import csv
import gzip
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Bio import SeqIO

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from fasta_ids import id_limit


class FastaIdTests(unittest.TestCase):
    def test_unsafe_ids_are_remapped_without_changing_bases(self):
        result, output, mapping = self.run_case(">chr|one\nacgt\n>bad;id\ntgca\n>chr_3\ncccc\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.records(output)
        self.assertEqual([r.id for r in records], ["s1", "s2", "chr_3"])
        self.assertEqual([str(r.seq) for r in records], ["ACGT", "TGCA", "CCCC"])
        self.assertIn("chr|one", mapping.read_text())
        self.assertIn("bad;id", mapping.read_text())

    def run_case(self, text, compressed=False, check_only=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / ("input.fa.gz" if compressed else "input.fa")
        if compressed:
            with gzip.open(source, "wt", encoding="ascii") as handle:
                handle.write(text)
        else:
            source.write_text(text, encoding="ascii")
        output, mapping = root / "out.fa", root / "map.tsv"
        command = [sys.executable, str(SCRIPTS / "fasta_ids.py"), "--input", str(source),
                   "--sample", "a_very_long_sample_name"]
        if check_only:
            command.append("--check-only")
        else:
            command += ["--output", str(output), "--map", str(mapping)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=30)
        return result, output, mapping

    @staticmethod
    def records(output):
        with output.open() as handle:
            return list(SeqIO.parse(handle, "fasta"))

    def test_ltr_retriever_length_dependent_limits(self):
        for maximum, expected in [(1, 40), (99, 36), (100, 32), (43697336, 12),
                                  (999999999, 8), (1000000000, 4)]:
            with self.subTest(maximum=maximum):
                self.assertEqual(id_limit(maximum), expected)
        with self.assertRaises(ValueError):
            id_limit(10000000000)

    def test_preserve_compliant_ids_uppercase_bases_and_lengths(self):
        result, output, mapping = self.run_case(">smchr01 desc\nacgtN\n>smscf00001\naaGg\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.records(output)
        self.assertEqual([r.id for r in records], ["smchr01", "smscf00001"])
        self.assertEqual([str(r.seq) for r in records], ["ACGTN", "AAGG"])
        self.assertEqual([len(r.seq) for r in records], [5, 4])
        self.assertIn("ids_renamed=0", result.stdout)
        with mapping.open() as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(rows[0]["original_description"], "smchr01 desc")
        self.assertEqual(rows[0]["length"], "5")

    def test_exact_boundary_preserved_and_overlong_id_collision_avoided(self):
        boundary = "x" * 40  # Two-base sequences permit IDs up to 40 characters.
        result, output, _ = self.run_case(f">{boundary}\nac\n>{boundary}x\ngt\n>s1\naa\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([r.id for r in self.records(output)], [boundary, "s2", "s1"])
        self.assertIn("ids_renamed=1", result.stdout)

    def test_limit_uses_longest_sequence_not_first_sequence(self):
        old_id = "x" * 37
        result, output, _ = self.run_case(f">{old_id}\naa\n>longchr\n" + "a" * 100 + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("id_limit=32", result.stdout)
        self.assertEqual([r.id for r in self.records(output)], ["s1", "longchr"])

    def test_duplicate_ids_rejected_before_output(self):
        result, output, mapping = self.run_case(">a\naa\n>a description\ngg\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate original FASTA id", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(mapping.exists())

    def test_empty_input_and_empty_sequence_rejected_before_output(self):
        for text in ("", ">empty\n>nonempty\nAA\n"):
            with self.subTest(text=text):
                result, output, mapping = self.run_case(text)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
                self.assertFalse(mapping.exists())

    def test_gzip_input(self):
        result, output, _ = self.run_case(">chr1 description\nacgt\n", compressed=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.records(output)[0].id, "chr1")
        self.assertEqual(str(self.records(output)[0].seq), "ACGT")

    def test_check_only_does_not_create_outputs(self):
        result, output, mapping = self.run_case(">chr1\nacgt\n", check_only=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("records=1\tbases=4", result.stdout)
        self.assertFalse(output.exists())
        self.assertFalse(mapping.exists())


if __name__ == "__main__":
    unittest.main()

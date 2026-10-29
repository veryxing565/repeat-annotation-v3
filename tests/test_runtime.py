"""Exercise ownership and provenance guards only; no bioinformatics programs."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import runtime as guards


class SampleNameTests(unittest.TestCase):
    def test_valid_sample_names_are_not_rewritten(self):
        for value in ("Example_species", "s1", "Species-v1.2", "a" * 120):
            with self.subTest(value=value):
                self.assertEqual(guards.sample_id(value), value)

    def test_unsafe_or_ambiguous_sample_names_are_rejected(self):
        for value in ("", ".", "..", "../escape", "a/b", "a b", "a;touch_x", "a..b", "-start", "a" * 121):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guards.sample_id(value)


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux ownership and affinity semantics")
class RuntimeGuardTests(unittest.TestCase):
    def test_workspace_roots_reject_control_characters(self):
        for path in ("/tmp/result\nother", "/tmp/result\tother", "/tmp/result\rother"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Control characters"):
                guards.dedicated(path)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="te_v3_runtime_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.result = self.root / "results"
        self.work = self.root / "work"
        self.genome = self.root / "input.fa"
        self.genome.write_text(">chr1\nACGT\n", encoding="ascii")

    def action(self, action, *extra):
        argv = ["runtime.py", action, "--result", str(self.result), "--temporary", str(self.work), *extra]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            return guards.main()

    def prepare_sample(self):
        self.action("prepare")
        self.action("init-sample", "--sample", "sample", "--genome", str(self.genome))

    def publish_fixture(self):
        directory = self.result / "results/sample"
        (directory / "qc").mkdir(parents=True)
        data = directory / "mock_result.txt"
        data.write_text("Mock output, not biological annotation.\n")
        (directory / "qc/result_sha256.txt").write_text(guards.sha(data) + "  mock_result.txt\n")
        return directory

    def complete_fixture(self):
        self.prepare_sample()
        directory = self.publish_fixture()
        self.action("complete", "--sample", "sample", "--genome", str(self.genome))
        return directory

    def test_roots_reject_broad_and_nested_targets(self):
        for broad in ("/", "/home", "/tmp", str(Path.home())):
            with self.subTest(path=broad), self.assertRaises(ValueError):
                guards.dedicated(broad)
        for result, work in ((self.result, self.result / "work"), (self.work / "out", self.work)):
            with self.subTest(result=result, work=work), self.assertRaises(ValueError):
                guards.roots(str(result), str(work))

    def test_roots_refuse_symlink_ancestors(self):
        actual = self.root / "actual"
        actual.mkdir()
        link = self.root / "link"
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            guards.roots(str(link / "results"), str(self.work))

    def test_prepare_is_idempotent_for_matching_owned_roots(self):
        self.action("prepare")
        self.action("prepare")
        for path in (self.result, self.work):
            self.assertTrue((path / guards.ROOT_MARKER).is_file())

    def test_nonempty_unowned_workspace_is_never_claimed(self):
        self.result.mkdir()
        sentinel = self.result / "user_data"
        sentinel.write_text("keep")
        with self.assertRaisesRegex(ValueError, "nonempty, unowned"):
            self.action("prepare")
        self.assertEqual(sentinel.read_text(), "keep")
        self.assertFalse((self.result / guards.ROOT_MARKER).exists())

    def test_root_owner_mismatch_is_refused(self):
        self.action("prepare")
        path = self.work / guards.ROOT_MARKER
        record = json.loads(path.read_text())
        record["result_root"] = "/different/project"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "owner mismatch"):
            self.action("prepare")

    def test_duplicate_manifest_sample_and_crlf_are_refused(self):
        manifest = self.root / "manifest.tsv"
        for payload in (
            f"sample\t{self.genome}\nsample\t{self.genome}\n",
            f"sample\t{self.genome}\r\n",
        ):
            with self.subTest(payload=payload):
                manifest.write_bytes(payload.encode())
                with self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
                    guards.manifest(str(manifest), self.result, self.work, str(SCRIPTS.parent))

    def test_manifest_forbids_genome_inside_temporary_workspace(self):
        self.work.mkdir()
        genome = self.work / "input.fa"
        genome.write_text(">chr1\nACGT\n")
        manifest = self.root / "manifest.tsv"
        manifest.write_text(f"sample\t{genome}\n")
        with self.assertRaisesRegex(ValueError, "inside TMP_ROOT"):
            guards.manifest(str(manifest), self.result, self.work, str(SCRIPTS.parent))

    def test_init_and_resume_validate_exact_input_digest(self):
        self.prepare_sample()
        self.action("validate-sample", "--sample", "sample", "--genome", str(self.genome))
        self.genome.write_text(">chr1\nACGA\n")
        with self.assertRaisesRegex(ValueError, "Resume input differs"):
            self.action("validate-sample", "--sample", "sample", "--genome", str(self.genome))

    def test_complete_verify_and_safe_owned_cleanup(self):
        self.complete_fixture()
        marker = self.result / "state/sample.complete"
        self.assertFalse(json.loads(marker.read_text())["temp_removed"])
        self.action("verify-complete", "--sample", "sample", "--genome", str(self.genome))
        self.action("cleanup-sample", "--sample", "sample", "--genome", str(self.genome))
        self.assertFalse((self.work / "sample").exists())
        self.assertTrue(json.loads(marker.read_text())["temp_removed"])
        self.assertTrue((self.result / "results/sample/mock_result.txt").is_file())
        self.action("cleanup-root")
        self.assertFalse(self.work.exists())

    def test_complete_refuses_input_changed_during_analysis(self):
        self.prepare_sample()
        self.publish_fixture()
        self.genome.write_text(">chr1\nAAAA\n")
        with self.assertRaisesRegex(ValueError, "Input changed"):
            self.action("complete", "--sample", "sample", "--genome", str(self.genome))
        self.assertFalse((self.result / "state/sample.complete").exists())

    def test_completed_result_tampering_prevents_verification_and_cleanup(self):
        directory = self.complete_fixture()
        (directory / "mock_result.txt").write_text("tampered")
        for action in ("verify-complete", "cleanup-sample"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "checksum"):
                self.action(action, "--sample", "sample", "--genome", str(self.genome))
        self.assertTrue((self.work / "sample").is_dir())

    def test_changed_input_prevents_completed_sample_skip(self):
        self.complete_fixture()
        self.genome.write_text(">chr1\nTTTT\n")
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.action("verify-complete", "--sample", "sample", "--genome", str(self.genome))

    def test_unlisted_result_file_is_not_accepted(self):
        self.prepare_sample()
        directory = self.publish_fixture()
        (directory / "unexpected.txt").write_text("not covered")
        with self.assertRaisesRegex(ValueError, "does not cover every"):
            guards.verify_export(directory)

    def test_checksum_traversal_and_result_symlink_are_refused(self):
        self.prepare_sample()
        directory = self.publish_fixture()
        manifest = directory / "qc/result_sha256.txt"
        manifest.write_text(guards.sha(self.genome) + "  ../../input.fa\n")
        with self.assertRaisesRegex(ValueError, "escapes"):
            guards.verify_export(directory)
        (directory / "link").symlink_to(self.genome)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            guards.verify_export(directory)

    def test_sample_owner_mismatch_blocks_cleanup_without_deleting(self):
        self.complete_fixture()
        sample = self.work / "sample"
        path = sample / guards.SAMPLE_MARKER
        record = json.loads(path.read_text())
        record["sample"] = "another"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "ownership mismatch"):
            self.action("cleanup-sample", "--sample", "sample", "--genome", str(self.genome))
        self.assertTrue(sample.is_dir())

    def test_cleanup_root_preserves_retained_diagnostic_files(self):
        self.action("prepare")
        sentinel = self.work / "failure.log"
        sentinel.write_text("diagnostic")
        self.action("cleanup-root")
        self.assertEqual(sentinel.read_text(), "diagnostic")

    def test_cpu_selection_respects_current_affinity_and_four_cpu_groups(self):
        with mock.patch.object(os, "sched_getaffinity", return_value={7, 9, 11, 13, 15, 17, 19, 21}):
            with mock.patch.object(sys, "argv", ["runtime.py", "cpus", "--threads", "4"]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    guards.main()
                self.assertEqual(output.getvalue().strip(), "7,9,11,13")
            for count in (0, 2, 6, 12):
                with self.subTest(threads=count), mock.patch.object(sys, "argv", ["runtime.py", "cpus", "--threads", str(count)]):
                    with self.assertRaises(ValueError):
                        guards.main()


if __name__ == "__main__":
    unittest.main()

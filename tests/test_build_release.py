"""Source archive integrity and deterministic packaging, without external tools."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile


class ReleaseBuildTests(unittest.TestCase):
    def test_archives_are_reproducible_and_manifest_complete(self):
        project = Path(__file__).resolve().parents[1]
        script = project / "scripts/build_release.py"
        version = (project / "VERSION").read_text().strip()
        stem = "repeat-annotation-v3-" + version
        with tempfile.TemporaryDirectory(prefix="te_v3_archive_") as temporary:
            roots = [Path(temporary) / "first", Path(temporary) / "second"]
            for output in roots:
                process = subprocess.run([sys.executable, str(script), "--output", str(output)],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
                self.assertEqual(process.returncode, 0, process.stderr)
            for suffix in (".zip", ".tar.gz", ".files.json"):
                self.assertEqual((roots[0] / (stem + suffix)).read_bytes(),
                                 (roots[1] / (stem + suffix)).read_bytes())
            with zipfile.ZipFile(roots[0] / (stem + ".zip")) as archive:
                self.assertIsNone(archive.testzip())
                entries = archive.namelist()
                self.assertTrue(all(n.startswith(stem + "/") and ".." not in Path(n).parts for n in entries))
                manifest = archive.read(stem + "/MANIFEST.sha256").decode()
                for line in manifest.splitlines():
                    expected, relative = line.split("  ", 1)
                    self.assertEqual(hashlib.sha256(archive.read(stem + "/" + relative)).hexdigest(), expected)
            with tarfile.open(roots[0] / (stem + ".tar.gz")) as archive:
                self.assertTrue(all(p.isfile() and not p.issym() and not p.islnk() for p in archive.getmembers()))
                self.assertTrue(all(p.mode in (0o644, 0o755) for p in archive.getmembers()))
            record = json.loads((roots[0] / (stem + ".files.json")).read_text())
            self.assertTrue(record["source_only"])
            self.assertFalse(any("__pycache__" in f["path"] or ".local." in f["path"] for f in record["files"]))


if __name__ == "__main__":
    unittest.main()

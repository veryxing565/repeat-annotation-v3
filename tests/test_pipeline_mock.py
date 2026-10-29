"""Linux plumbing integration using fake bio tools, NOT biological validation.

The real runner, runtime guards and Bio/PyYAML helpers process tiny fixtures.
All discovery/classification/masking executables are deliberately fake programs;
their synthetic FASTA/GFF/align files must never be treated as scientific results.
No downloads, production paths or active server jobs are used.
"""

import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

PROJECT = Path(__file__).resolve().parents[1]

FAKE_TOOL = r'''
import json
import os
from pathlib import Path
import shutil
import sys

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
def option(name):
    return args[args.index(name) + 1]
def fasta(path):
    result = []
    name = None
    sequence = []
    for line in Path(path).read_text().splitlines():
        if line.startswith('>'):
            if name is not None:
                result.append((name, ''.join(sequence)))
            name, sequence = line[1:].split()[0], []
        else:
            sequence.append(line.strip())
    if name is not None:
        result.append((name, ''.join(sequence)))
    return result
with open(os.environ['TE_V3_MOCK_CALLS'], 'a') as log:
    log.write(json.dumps(dict(tool=tool, args=args, cwd=str(Path.cwd()),
                             affinity=sorted(os.sched_getaffinity(0)))) + '\n')
if tool == 'perl':
    wrapper = Path(args[0]).name
    if wrapper not in ('LTR_FINDER_parallel', 'LTR_HARVEST_parallel'):
        raise SystemExit('The mock only accepts the two expected wrapper entry points')
    suffix = '.finder.combine.scn' if wrapper == 'LTR_FINDER_parallel' else '.harvest.combine.scn'
    Path(Path(option('-seq')).name + suffix).write_text('# MOCK candidate; not biological evidence\n1 80 80\n')
elif tool == 'LTR_retriever':
    genome = option('-genome')
    Path(genome + '.LTRlib.fa').write_text('>mock_ltr#LTR/Copia\n' + 'ACGT' * 20 + '\n')
    Path(genome + '.pass.list').write_text('# MOCK pass list\nmock_ltr\n')
elif tool == 'RepeatModeler':
    if '-version' in args:
        print('RepeatModeler version 2.0.1')
    elif '-help' in args:
        print('-genomeSampleSizeMax -srand -pa')
    else:
        sample = option('-database').removesuffix('.rmdb')
        if sample in os.environ.get('TE_V3_MOCK_FAIL', '').split(','):
            print('MOCK deliberate RepeatModeler failure: ' + sample, file=sys.stderr)
            raise SystemExit(23)
        directory = Path('RM_mock')
        directory.mkdir()
        (directory / 'consensi.fa.classified').write_text(
            '>mock_known#DNA/hAT\n' + 'ACGA' * 20 + '\n'
            '>mock_high#Unknown\n' + 'ACTG' * 20 + '\n'
            '>mock_low#Unknown\n' + 'AGCT' * 20 + '\n')
elif tool == 'BuildDatabase':
    if '-help' in args:
        print('MOCK BuildDatabase help')
    else:
        Path(option('-name') + '.mockdb').write_text('MOCK database\n')
elif tool == 'cd-hit-est':
    source, target = Path(option('-i')), Path(option('-o'))
    shutil.copyfile(source, target)
    with Path(str(target) + '.clstr').open('w') as handle:
        for index, (name, seq) in enumerate(fasta(source)):
            handle.write('>Cluster %d\n0 %dnt, >%s... *\n' % (index, len(seq), name))
elif tool == 'RepeatMasker':
    source = Path(args[-1])
    output = Path(option('-dir'))
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / source.name
    with Path(str(prefix) + '.masked').open('w') as handle:
        for name, seq in fasta(source):
            handle.write('>' + name + '\n' + seq[:4].lower() + seq[4:].upper() + '\n')
    for suffix in ('out', 'out.gff', 'tbl', 'align'):
        Path(str(prefix) + '.' + suffix).write_text('MOCK ' + suffix + '; not a biological result\n')
elif tool in ('gt', 'ltr_finder'):
    print('MOCK dependency placeholder')
else:
    raise SystemExit('Unexpected fake executable: ' + tool)
'''

FAKE_TECLASS = r'''
"""Synthetic classifier fixture; no neural model is loaded."""
import argparse
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--classify', action='store_true')
parser.add_argument('-c')
parser.add_argument('-f')
parser.add_argument('-o')
args = parser.parse_args()
names = [line[1:].split()[0] for line in Path(args.f).read_text().splitlines() if line.startswith('>')]
with Path(args.o).open('w') as output:
    output.write('name\tclass\tmax_probability\n')
    for index, name in enumerate(names):
        output.write(name + '\tGypsy\t' + ('0.95' if index == 0 else '0.50') + '\n')
'''


@unittest.skipUnless(sys.platform.startswith("linux"), "Requires Linux Bash/taskset/flock")
class MockPipelineTests(unittest.TestCase):
    def setUp(self):
        if len(os.sched_getaffinity(0)) < 4:
            self.skipTest("Mock integration requires four CPUs in the parent's affinity")
        for name in ("bash", "taskset", "flock", "setsid", "sha256sum", "file", "readlink", "sort", "xargs"):
            if not shutil.which(name):
                self.skipTest("Missing Linux test prerequisite: " + name)
        for name in ("Bio", "yaml"):
            if importlib.util.find_spec(name) is None:
                self.skipTest("Real workflow helpers require test dependency: " + name)
        temporary = tempfile.TemporaryDirectory(prefix="te_v3_mock_")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        shutil.copy2(PROJECT / "run_te_annotation_v3.sh", self.source)
        for name in ("scripts", "patched_tools"):
            shutil.copytree(PROJECT / name, self.source / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.bin = self.root / "fakebin"
        self.bin.mkdir()
        executable = self.bin / "fake_bio_tool.py"
        executable.write_text("#!" + sys.executable + "\n" + textwrap.dedent(FAKE_TOOL))
        executable.chmod(0o755)
        for name in ("perl", "gt", "ltr_finder", "LTR_retriever", "BuildDatabase", "RepeatModeler", "cd-hit-est", "RepeatMasker"):
            (self.bin / name).symlink_to(executable)
        self.teclass = self.root / "fake_teclass"
        (self.teclass / "models/clust_cats_16").mkdir(parents=True)
        (self.teclass / "models/clust_cats_16/pytorch_model.bin").write_text("MOCK weights placeholder; no real model\n")
        (self.teclass / "TEclass2.py").write_text(textwrap.dedent(FAKE_TECLASS))
        (self.teclass / "config.yml").write_text("model_name: unused\ndevice: cpu\n")
        # Preflight imports torch; this stub is limited to this subprocess env.
        modules = self.root / "mock_modules"
        modules.mkdir()
        (modules / "torch.py").write_text('"""Empty mock module; never used for inference."""\n')
        self.calls = self.root / "fake_calls.jsonl"
        self.result = self.root / "results"
        self.work = self.root / "work"
        self.config = self.root / "config.sh"
        self.config.write_text("\n".join([
            "# MOCK TEST ONLY: not a real annotation configuration.",
            "RESULT_ROOT=" + shlex.quote(str(self.result)),
            "TMP_ROOT=" + shlex.quote(str(self.work)),
            "TECLASS_HOME=" + shlex.quote(str(self.teclass)),
            "PYTHON=" + shlex.quote(sys.executable), "THREADS=4",
            "MAMBA=''", "ENV_PREFIX=''", "REPEATMODELER_BIN=''", "REPEATMODELER_SIF=''",
            "MAX_CONSECUTIVE_FAILURES=3", "",
        ]))
        self.env = os.environ.copy()
        self.env.update(PATH=str(self.bin) + os.pathsep + self.env.get("PATH", ""),
                        PYTHONPATH=str(modules) + os.pathsep + self.env.get("PYTHONPATH", ""),
                        TE_V3_MOCK_CALLS=str(self.calls), TE_V3_MOCK_FAIL="",
                        PYTHONDONTWRITEBYTECODE="1", BLAST_USAGE_REPORT="false")
        self.allowed = set(sorted(os.sched_getaffinity(0))[:4])
        self.inputs = {}

    def genome(self, sample):
        if sample not in self.inputs:
            path = self.root / (sample + ".fa")
            path.write_text(">chr1 description\n" + "acgt" * 30 + "\n", encoding="ascii")
            self.inputs[sample] = path
        return self.inputs[sample]

    def run_batch(self, samples, fail=()):
        manifest = self.root / "manifest.tsv"
        manifest.write_text("".join(sample + "\t" + str(self.genome(sample)) + "\n" for sample in samples))
        env = self.env.copy()
        env["TE_V3_MOCK_FAIL"] = ",".join(fail)
        process = subprocess.run(
            [shutil.which("bash"), str(self.source / "run_te_annotation_v3.sh"), str(self.config), str(manifest)],
            cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=180, preexec_fn=lambda: os.sched_setaffinity(0, self.allowed),
        )
        self.last_output = process.stdout
        return process

    def call_records(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def scientific_calls(self):
        return [r for r in self.call_records()
                if r["tool"] != "BuildDatabase" or "-help" not in r["args"]
                if r["tool"] != "RepeatModeler" or not any(x in r["args"] for x in ("-version", "-help"))]

    def test_success_copy_verified_cleanup_then_checksum_verified_skip(self):
        process = self.run_batch(["good"])
        self.assertEqual(process.returncode, 0, process.stdout)
        directory = self.result / "results/good"
        marker = self.result / "state/good.complete"
        record = json.loads(marker.read_text())
        self.assertTrue(record["temp_removed"])
        self.assertFalse(self.work.exists(), "Entire owned temporary root should be removed on all-success")
        for suffix in ("masked", "out", "out.gff", "tbl", "align"):
            self.assertTrue((directory / ("repeatmasker/good.normalized.fa." + suffix)).is_file())
        self.assertIn("acgtACGT", (directory / "repeatmasker/good.normalized.fa.masked").read_text())
        library = (directory / "library/good.v3.TElib.fa").read_text()
        self.assertIn("#Unknown", library, "Unresolved mock TE must survive in the only final library")
        self.assertIn("#LTR/Gypsy", library)
        verifier = subprocess.run([sys.executable, str(self.source / "scripts/runtime.py"),
                                  "verify-complete", "--result", str(self.result), "--sample", "good",
                                  "--genome", str(self.genome("good"))],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.assertEqual(verifier.returncode, 0, verifier.stdout)
        calls_before = self.scientific_calls()
        contents_before = (directory / "qc/result_sha256.txt").read_bytes()
        process = self.run_batch(["good"])
        self.assertEqual(process.returncode, 0, process.stdout)
        self.assertIn("SKIP checksum-verified completed sample=good", process.stdout)
        self.assertEqual(self.scientific_calls(), calls_before)
        self.assertEqual((directory / "qc/result_sha256.txt").read_bytes(), contents_before)
        self.assertTrue(all(set(r["affinity"]) <= self.allowed for r in self.call_records()))

    def test_one_scientific_failure_is_recorded_and_next_genome_runs(self):
        process = self.run_batch(["bad", "good"], fail=["bad"])
        self.assertEqual(process.returncode, 1, process.stdout)
        self.assertTrue((self.result / "state/bad.failed").is_file())
        self.assertFalse((self.result / "state/bad.complete").exists())
        self.assertTrue((self.work / "bad").is_dir(), "Failed workspace is retained for diagnosis")
        self.assertTrue((self.result / "state/good.complete").is_file())
        self.assertFalse((self.work / "good").exists())
        self.assertIn("CONTINUE to next genome", process.stdout)

    def test_three_consecutive_failures_stop_and_verified_skip_does_not_reset(self):
        prime = self.run_batch(["old"])
        self.assertEqual(prime.returncode, 0, prime.stdout)
        process = self.run_batch(["bad1", "old", "bad2", "bad3", "not_started"],
                                 fail=["bad1", "bad2", "bad3"])
        self.assertEqual(process.returncode, 3, process.stdout)
        self.assertIn("STOP: 3 consecutive genome failures", process.stdout)
        self.assertIn("skipped=1", process.stdout)
        for sample in ("bad1", "bad2", "bad3"):
            self.assertTrue((self.result / ("state/" + sample + ".failed")).is_file())
        self.assertFalse((self.work / "not_started").exists())
        self.assertFalse((self.result / "state/not_started.complete").exists())
        self.assertFalse((self.result / "state/not_started.failed").exists())

    def test_success_between_failures_resets_failure_streak(self):
        process = self.run_batch(["bad1", "good", "bad2", "bad3", "last"],
                                 fail=["bad1", "bad2", "bad3"])
        self.assertEqual(process.returncode, 1, process.stdout)
        self.assertTrue((self.result / "state/last.complete").is_file())
        self.assertNotIn("STOP: 3 consecutive", process.stdout)

    def test_tampered_input_is_not_skipped_or_silently_rerun(self):
        first = self.run_batch(["good"])
        self.assertEqual(first.returncode, 0, first.stdout)
        calls = self.scientific_calls()
        self.genome("good").write_text(">chr1\nTTTT\n")
        process = self.run_batch(["good"])
        self.assertNotEqual(process.returncode, 0, process.stdout)
        self.assertIn("provenance mismatch", process.stdout)
        self.assertNotIn("SKIP checksum-verified", process.stdout)
        self.assertEqual(self.scientific_calls(), calls)

    def test_tampered_retained_output_is_not_skipped_or_overwritten(self):
        first = self.run_batch(["good"])
        self.assertEqual(first.returncode, 0, first.stdout)
        output = self.result / "results/good/repeatmasker/good.normalized.fa.align"
        output.write_text("tampered mock alignment\n")
        calls = self.scientific_calls()
        process = self.run_batch(["good"])
        self.assertNotEqual(process.returncode, 0, process.stdout)
        self.assertIn("checksum", process.stdout)
        self.assertNotIn("SKIP checksum-verified", process.stdout)
        self.assertEqual(output.read_text(), "tampered mock alignment\n")
        self.assertEqual(self.scientific_calls(), calls)


if __name__ == "__main__":
    unittest.main()

# Validation status

## Portable code tests — 2026-10-29

On a Linux x86-64 reference server, using Python 3.10 from the existing
dependency environment and a four-CPU affinity:

- **55/55 unittest tests passed; no skipped tests**, approximately 30 seconds.
- Both Bash orchestration scripts passed `bash -n`.
- Both bundled LTR wrappers and all three included Perl helpers passed real
  `perl -c` syntax checks.
- Release-build tests verified ZIP integrity, every archived source hash,
  safe archive member paths/modes, and repeatable archive bytes in one environment.

The 55 tests comprise 9 FASTA-ID tests, 16 library-decision tests, 3 LTR patch
static tests, 20 runtime-guard tests, 6 mock pipeline tests, and 1 archive test.
The machine-readable record in `provenance/validation.json` identifies tested
code hashes. This documentation and the sanitized record were added after the
code test, without changing the tested executables/helpers/tests.

## What the integration tests actually establish

They run real Bash orchestration, file operations, CPU affinity, checksums,
Python/Biopython/YAML helpers, and strict worker failure propagation on tiny
synthetic fixtures. External discovery/classification/masking programs are
**deliberately fake**, including a subprocess-local stub for the torch import.
No real model, genome discovery, RepeatModeler database, or RepeatMasker search
is run by these six tests.

Covered behaviors include:

- Verified result copy/publication and owned scratch cleanup.
- Complete-sample skip only after input/output checksums match.
- Failure preserved, next genome processed, success resetting the streak.
- Stop after three new consecutive failures; skipped samples do not reset it.
- Changed input/output, traversal, symlinks and mismatched owners refused.
- Single final library containing unresolved Unknown source records.
- Four-CPU inheritance across mocked scientific subprocesses.

The tests emitted nonfatal Biopython `ResourceWarning` messages for path-based
iterator handles in the inherited library helper. Assertions, checksum checks,
and process exits all passed. These warnings are not presented as a successful
real-genome run or a biological validation result.

## Production-source provenance

The biological commands were derived from the latest running outgroup v3
source, collected 2026-10-29. Actual production job logs confirmed
RepeatModeler 2.0.1 and RepeatMasker 4.2.4. Bundled LTR sources are byte-identical
to that production snapshot. Helper format checks and execution/safety
portability changes are documented in the changelog.

## Not yet demonstrated

- A complete biological end-to-end run using the portable release on a second
  clean machine or every native/container dependency combination.
- A newly solved conda environment from `environment.yml` on every platform.
- GitHub Actions success (it runs only after upload).
- Universal TE sensitivity/specificity, memory/time guarantees, or bitwise
  identical biological results across hardware/dependency versions.

Accordingly this package is labeled **release candidate**. A real pilot with
the exact prepared external dependencies should precede a stable public release.

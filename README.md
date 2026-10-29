# Repeat annotation v3

A per-genome TE-library construction and soft-masking workflow for Linux.
It combines structural LTR evidence with RepeatModeler 2.0.1, classifies only
RepeatModeler `Unknown` sequences with TEclass2, retains unresolved candidates,
and runs RepeatMasker with a single final library.

**Status: 3.0.0rc1, portable release candidate.** The biological workflow was
used for arachnid assemblies; the portable packaging is tested separately.
This is not a claim of optimal annotation quality for every taxon. It is a
workflow integrating existing tools, not a replacement for their algorithms.

## Workflow

1. Read a FASTA or `.gz` assembly; uppercase all bases for discovery. Preserve
   short, shell-safe IDs and rename only overlong/unsafe IDs, retaining a map.
2. Run the **bundled patched** LTR_FINDER_parallel 1.4 and
   LTR_HARVEST_parallel 1.3, then LTR_retriever 3.0.5 (`-noanno`).
3. Run RepeatModeler **2.0.1**, maximum sample 81 Mb, seed 42, without
   `-LTRStruct`. The assembly is not split into separate model-building jobs.
4. Send only RepeatModeler `Unknown` consensuses to TEclass2. Accept mapped
   labels with probability >=0.80; retain lower-confidence/unmapped sequences
   as `Unknown`. A 0.70 threshold changes metadata only, not retention.
5. Merge LTR, RepeatModeler known, accepted TEclass2, and unresolved sequences.
6. Cluster near-duplicates with CD-HIT-EST at 95% local identity and 90%
   coverage of **both** sequences; select class/source-aware representatives.
7. Build **one** soft-masking library, then run RepeatMasker with `.align`.
8. Copy key results to the result filesystem, verify checksums, and only then
   remove that genome's owned temporary workspace.

"Class-aware" describes representative selection **after mixed clustering**,
not class-stratified clustering. Conflicting labels can occupy one cluster.
Unresolved sequences are never rejected merely for being Unknown, but a
near-duplicate Unknown can be represented by another cluster member. See
[methods and limitations](docs/METHODS.md).

## Requirements

- Linux x86-64 is the reference platform. Use a Linux environment on Windows;
  native Windows/macOS execution is not supported. Other architectures require
  compatible external binaries and independent validation.
- Bash >=4, Python >=3.10, Perl with threads/Thread::Queue/Pod::Usage, GNU
  coreutils (`timeout`, `readlink`, `sha256sum`, etc.), `file`, and util-linux
  (`flock`, `taskset`).
- LTR_FINDER, GenomeTools, LTR_retriever and its dependencies, CD-HIT-EST,
  RepeatMasker configured for RMBlast, compatible RepeatModeler **2.0.1**,
  and a complete TEclass2 installation with the `clust_cats_16` model assets.
- Biopython/PyYAML for helpers; TEclass2's own Python dependencies are additional.

No pretrained weights, databases, compiled third-party binaries, container
images, or research genomes are included. Dependencies are user supplied;
the runner does **not** download anything. See
[dependency setup and recorded versions](docs/DEPENDENCIES.md).

## Quick start

Download/clone the repository and keep it in a shell-safe Linux path, e.g.
`$HOME/software/repeat-annotation-v3`. No package installation of this workflow
is necessary. Prepare dependencies first, then:

```bash
cd "$HOME/software/repeat-annotation-v3"
cp config/config.example.sh config.local.sh
cp examples/samples.tsv samples.local.tsv
# Edit the configuration and manifest. Replace ALL /path/to/... placeholders.
# Use actual TAB separators and Unix LF line endings in the manifest.
bash run_te_annotation_v3.sh --check-only config.local.sh samples.local.tsv
bash run_te_annotation_v3.sh config.local.sh samples.local.tsv > batch.log 2>&1
```

Run inside a scheduler allocation, `tmux`, or `screen` for long jobs. The
foreground command above is intentional: this workflow does not manage your
scheduler or create hidden recurring tasks. Do not start another batch using
the same result/work roots while a batch is active.

The configuration is **trusted executable Bash**, not a safe format for
untrusted downloads. Use absolute result/work/tool paths. Result and work roots
must be dedicated, separate, and non-nested; do not use your home directory,
a mount root, an existing unrelated nonempty directory, or the repository
itself as a work root. The source installation, work root, and LTR tool paths
must not contain spaces or shell metacharacters because upstream wrappers use
shell commands internally. Input assemblies may be elsewhere; they are not
modified. Every sample ID must be unique, start with a letter/digit, contain
only letters/digits/`_`/`.`/`-`, be <=120 characters, and not contain `..`.

### CPU and scratch storage

`THREADS=56` is the original budget, not a minimum. Use a multiple of four
between 4 and the number of CPUs available in your scheduler allocation.
The workflow pins its subprocess tree to that many allowed logical CPUs.
RepeatModeler/RepeatMasker use `-pa THREADS/4`; other stages use `THREADS`.
Some post-processing steps are single-threaded. One genome runs at a time.
CPU affinity is a CPU-access cap, **not** a guarantee of full utilization or
a RAM/disk quota. Container/site restrictions may require administrator setup.

Use a large local scratch filesystem for `TMP_ROOT` and persistent storage for
`RESULT_ROOT`. Multi-gigabase assemblies can require hundreds of GB of scratch,
and uncompressed alignments can be very large. There is no universal runtime
or disk estimate: repeat content, fragmentation, and dependency versions matter.

## Outputs

```text
RESULT_ROOT/
├── results/SAMPLE/
│   ├── library/        # final SAMPLE.v3.TElib.fa, metadata, source libraries
│   ├── repeatmasker/   # normalized.fa.masked/.out/.out.gff/.tbl/.align
│   └── qc/            # ID map, parameters, input/output checksums
├── logs/              # per-sample logs
├── state/             # .complete or .failed markers
└── workflow_snapshot/ # reserved; per-sample source fingerprints are in qc/
```

Use `results/SAMPLE/repeatmasker/SAMPLE.normalized.fa.masked` for downstream
gene annotation. It is real soft masking: repeat bases are lowercase and
other bases remain uppercase. **Do not uppercase it again.** Use the matching
ID map if IDs were renamed. `.align` is retained uncompressed; no repeat-age
or burst analysis is performed. [Output details](docs/OUTPUTS.md).

## Failures, reruns, and cleanup

- Complete results are skipped only after input/result checksum validation.
- A failed genome keeps its work files and log; the next genome is attempted.
- Three consecutive new failures stop the batch (exit 3). A skipped result
  does not reset this counter. A batch with any other failures exits 1.
- Successful samples reset the failure counter. All-success exits 0.
- Failed/existing work is not silently overwritten or automatically resumed.
  Inspect it and move/remove only that exact failed sample workspace before
  a fresh retry. Preserve useful logs and inputs. No blanket cleanup command
  is provided.
- The site's one-off RepeatMasker-stage resume switch is deliberately not a
  public API. The portable release prefers explicit, checked complete results
  and safe fresh retries over accepting arbitrary partially cleaned work.

Read [troubleshooting](docs/TROUBLESHOOTING.md) before retrying.

## Testing and development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
bash -n run_te_annotation_v3.sh scripts/batch_runner.sh
perl -c patched_tools/LTR_FINDER_parallel/LTR_FINDER_parallel
perl -c patched_tools/LTR_HARVEST_parallel/LTR_HARVEST_parallel
```

Small integration tests use mock external programs, not biological validation.
The tiny synthetic fixtures cannot establish repeat discovery sensitivity or
runtime on real genomes. See [validation](docs/VALIDATION.md).

## Provenance, citation, and license

- [Recorded source/versions](provenance/source_snapshot.json)
- [LTR patch notes](docs/LTR_PATCHES.md)
- [Citations](docs/CITATIONS.md)
- [Release checklist](docs/RELEASING.md)

Cite the underlying tools in any methods section, not just this wrapper.
Original workflow code: MIT. Included LTR wrappers: their retained MIT
licenses. Other tools/models are separate dependencies; see
[third-party notices](THIRD_PARTY_NOTICES.md).

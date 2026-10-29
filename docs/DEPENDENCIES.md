# Dependency preparation

The workflow does not install or download dependencies. All installations
must be functional before `--check-only`. The bundled LTR wrappers are always
used; upstream conda wrappers in PATH do not override them.

## Reference installation, recorded 2026-10-29

| Component | Version / identity | Role |
| --- | --- | --- |
| Python | 3.10.20 | workflow helpers / reference TEclass2 environment |
| Biopython | 1.88 | FASTA parsing |
| PyYAML | 6.0.3 | TEclass2 configuration |
| LTR_FINDER | 1.07 (upstream 1.0.7) | structural candidates |
| LTR_FINDER_parallel | 1.4 + bundled v3 timeout fix | parallel wrapper |
| GenomeTools | 1.6.6 | suffixerator / ltrharvest |
| LTR_HARVEST_parallel | 1.3 + bundled v3 timeout fix | parallel wrapper |
| LTR_retriever | 3.0.5 | LTR library |
| RepeatModeler | **2.0.1**, confirmed in actual job logs | sampled de novo consensus discovery |
| RepeatMasker | 4.2.4 | final RMBlast masking |
| RMBlast | 2.17.0 in the host masking environment | RepeatMasker search engine |
| CD-HIT | 4.8.1 | near-duplicate clustering |
| Apptainer | 1.5.2, optional | local RepeatModeler SIF execution |
| TEclass2 | installed source entrypoint SHA256 below; Git revision unavailable | Unknown-only classification |
| TEclass2 model | `clust_cats_16` and its complete assets | classification |
| transformers | 4.17.0 in reference environment | TEclass2 dependency |
| PyTorch | 2.13.0 CPU build in reference environment | TEclass2 dependency |
| NumPy / pandas | 1.26.4 / 2.3.3 | reference environment |

The reference host also had RepeatModeler **2.0.9** installed, but the workflow
did **not** call it: it explicitly ran the local image's 2.0.1. Do not replace
the sampled legacy invocation with a new version and assume equivalence.
In particular, `-genomeSampleSizeMax` compatibility must be checked.

The original local SIF was derived from `kanghu/hite:3.3.3`. **Only
BuildDatabase and RepeatModeler were used**, not the HiTE workflow. The SIF is
not distributed here. Its filename is not a reproducible image digest, and
an arbitrary image with that name must not be trusted. A new native/container
installation needs its own version checks. A failed container mount is an
installation/runtime issue, not evidence that a running annotation completed
incorrectly.

TEclass2's recorded `TEclass2.py` SHA256:

```text
3519a010d8f1dc5f616354c283ce792dfe36d83c14125837831f3fa4d4619232
```

No Git metadata was present in that installation; we do not invent a commit
or semantic version. Matching the entrypoint alone does not establish that all
support modules/model assets match. The machine-readable provenance file
explicitly distinguishes recorded versions from unknown fingerprints.

## Option A: tools in an activated environment

An optional starting recipe is supplied:

```bash
conda env create -f environment.yml
conda activate te-v3
```

This recipe is **not a solved lockfile** and is not proof that every platform
can solve the exact historical environment. Channel packaging/solver changes
can require a separate legacy RepeatModeler environment. It intentionally does
not install TEclass2 weights or conflate the host's newer RepeatModeler with
the required 2.0.1.

Manual installations are equally valid. Ensure these commands resolve in the
selected PATH:

```text
python perl timeout gt ltr_finder LTR_retriever cd-hit-est RepeatMasker
```

Install LTR_retriever's full transitive dependencies according to its upstream
instructions, including its sequence search/alignment/TRF requirements. Configure
RepeatMasker for RMBlast and check `RepeatMasker -version` plus `rmblastn -version`.
The final masking run uses `-lib`; it does not require a Dfam species subset.
RepeatModeler's own classification dependencies/reference library are separate
from that custom final library and must be prepared according to its release.
Do not infer that all external databases are unnecessary.

The portable runner can also use an existing environment without activation:

```bash
MAMBA="/absolute/path/to/micromamba"
ENV_PREFIX="/absolute/path/to/envs/te-v3"
```

Set both or neither. No conda/micromamba package is required by the workflow
itself when tools are already available in PATH.

## RepeatModeler 2.0.1

Get the [official 2.0.1 release](https://github.com/Dfam-consortium/RepeatModeler/releases)
and configure its dependencies (RepeatMasker/RMBlast, RepeatScout, RECON,
TRF, etc.) following that release's instructions. Make sure these work:

```bash
RepeatModeler -version
RepeatModeler -help
BuildDatabase -help
```

The runner requires 2.0.1 and help text containing `genomeSampleSizeMax`,
`srand`, and `pa`; this catches incompatible modern invocations early. This
does not certify every dependency path or input-specific edge case.

Use a directory containing the native executables:

```bash
REPEATMODELER_BIN="/absolute/path/to/RepeatModeler-2.0.1"
REPEATMODELER_SIF=""
```

If its dependencies need additional environment variables, arrange them in the
trusted configuration/PATH or provide a fully configured local SIF instead.
For a user-supplied image:

```bash
REPEATMODELER_BIN=""
APPTAINER="/absolute/path/to/apptainer"
REPEATMODELER_SIF="/absolute/path/to/compatible-repeatmodeler-2.0.1.sif"
```

Only the current dedicated scratch root is explicitly bound for those calls;
site/container defaults may add standard binds. The image must allow the same
scratch path inside the container. Commas/colons in bind paths are unsupported.
Apptainer user namespaces/FUSE/setuid requirements depend on the host. The
workflow never changes host privileges or downloads/builds an image for you.

## TEclass2

Follow the [official TEclass2 installation/model instructions](https://github.com/IOB-Muenster/TEclass2).
Keep the entire source tree, base `config.yml`, model configuration, tokenizer,
and pretrained model assets; copying only `TEclass2.py` or only a weights file
is insufficient. Set:

```bash
TECLASS_HOME="/absolute/path/to/TEclass2"
# Optional independent Python with TEclass2's full dependencies:
TECLASS_PYTHON="/absolute/path/to/teclass-env/bin/python"
```

The expected layout includes
`models/clust_cats_16/pytorch_model.bin` and its `config.json`, as well as
`data/vocabs/5mer_vocab.json` **and** `data/vocabs/5mer_vocab.txt`. The reference
weights are 298,776,589 bytes, SHA256:

```text
e3ead17f7d5910544a71dce22c13517c06749051a6b90fa31f64b88e4df542f0
```

Supporting file fingerprints are in `provenance/source_snapshot.json`.
Optimizer/trainer state from model training is not needed for this prediction
step. The runner generates a per-sample
CPU/low-memory configuration and does not modify the installed base config.
It expects a prediction TSV with `name`, `class`, and `max_probability` columns.

No code/model/image redistribution rights are presumed. Obtain assets from
the authors and check their terms. For offline use, download assets in an
authorized environment and transfer them yourself; runtime requires no
network connection once every external dependency is prepared.

## System packages

On Debian/Ubuntu, GNU coreutils, Bash, Perl with ithreads, `file`, and
util-linux are required. Obtain them through your administrator/package
manager if absent. The supplied Python requirements install helpers only;
they are not a complete annotation environment.

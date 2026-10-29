# Methods and interpretation

The portable release retains the current production v3 scientific settings.
It makes machine-specific execution details configurable and strengthens
validation/cleanup; it does not introduce a new discovery algorithm.

| Stage | Default settings |
| --- | --- |
| Input | uppercase before discovery; safe IDs retained, overlong/unsafe IDs remapped |
| Main LTR windows | 5 Mb, 100 kb overlap, 300-second timeout, salvage enabled |
| LTR salvage | 50 kb, 5 kb overlap; Finder 10 seconds, Harvest 30 seconds per subwindow command |
| LTR_retriever | `-threads N -noanno`, Finder and Harvest candidate files |
| RepeatModeler | `-pa N/4 -genomeSampleSizeMax 81000000 -srand 42`, no `-LTRStruct` |
| TEclass2 | only RepeatModeler Unknown; CPU; `clust_cats_16`; acceptance >=0.80 |
| Candidate annotation | >=0.70 but <0.80 is metadata-only, still Unknown |
| CD-HIT-EST | `-c 0.95 -n 10 -G 0 -aS 0.90 -aL 0.90 -g 1 -d 0 -T N -M 0` |
| RepeatMasker | `-engine rmblast -pa N/4 -cutoff 225 -xsmall -gff -a -gccalc -excln -norna -no_is` |

`genomeSampleSizeMax` limits sampled sequence volume, not assembly size or
total memory. It trades discovery depth for bounded runtime; rare families
may be missed. Seed 42 controls sampling but does not make different CPU
counts/binaries/platforms bitwise identical. The genome remains a single
assembly for RepeatModeler and final masking; LTR programs internally window
sequences as part of their standard wrapper algorithm.

## Library identifiers and classification

Final headers use the RepeatMasker-compatible convention
`>SAMPLE|TE|0000001#Class/Subclass`. Source IDs, predicted classes/probabilities,
chosen representatives, cluster members, and final decisions are saved in TSV.

Only RepeatModeler records whose class starts with `Unknown` (case-insensitive)
are passed to TEclass2. Existing classifications and LTR structural records
are not reclassified by this step. Missing predictions, unknown model labels,
or low probabilities retain the sequence as Unknown. Malformed/duplicate
predictions stop with an error rather than silently changing a library.

The class mapping is explicitly encoded in `scripts/library_ops.py`.
In particular, the model's combined `L1_L2` category maps to `LINE/L1` for
historical compatibility. This is a coarse operational label, **not** evidence
that L1 and L2 have been phylogenetically distinguished. Do not use these
classification outputs as a substitute for domain/phylogenetic validation.

## Near-duplicate representative selection

All candidates enter one CD-HIT run. Each cluster gets one representative:

1. More specific labels precede partial `*/Unknown` labels, which precede
   wholly Unknown labels.
2. At equal specificity, source priority is structural LTR, RepeatModeler known,
   accepted TEclass2, then unresolved RepeatModeler Unknown.
3. Ties prefer longer sequences, then deterministic record-ID ordering.

Therefore a known label may outrank a structurally sourced partial Unknown.
Different known classes can collapse if their sequences cluster. CD-HIT's
greedy clusters do not guarantee all pairs in a cluster exceed both thresholds.
This is conservative near-duplicate reduction, not a complete TE-family
taxonomy or a promise that every distinct biological family is preserved.
The cluster-membership table is retained so decisions can be audited.

## What is deliberately not performed

- No panHiTE/standalone HiTE stage, EDTA whole-genome workflow, or Dfam
  chelicerate-library merge.
- No removal of unresolved Unknown consensuses, host-gene contamination
  screening, protein-domain validation, or splitting into separate sensitive
  and high-confidence libraries.
- No repeat divergence/age histogram or burst-event analysis. `.align` is
  provided so such analyses can be performed separately.
- No completeness/accuracy assessment of the predicted gene set.

These are workflow choices, not claims that those analyses are unnecessary.
Inspect TE libraries before interpreting family expansions, and validate
downstream biological conclusions independently.

## FASTA case and IDs

Uppercasing the input removes pre-existing softmask case so it cannot be
mistaken for new masking. RepeatMasker creates the final lowercase repeats
with `-xsmall`; preserve that case for subsequent gene annotation.

The ID limit follows the source workflow's LTR_retriever 3.0.5 rule:
`44 - 4 * digits(longest_sequence_length)`. For example, a longest scaffold
of 43,697,336 bp gives a 12-character limit. The portable edition additionally
renames IDs outside `[A-Za-z0-9_][A-Za-z0-9_.-]*` to keep upstream shell calls
safe. Replacement IDs are collision-checked against all original IDs.
Descriptions are removed from the normalized FASTA but retained in the map.
Sequence order, lengths, and bases (apart from case) are not intentionally
changed. Duplicate IDs or empty records are errors, not silently repaired.

## Zero-hit behavior

This release retains the production fail-fast policy when both LTR candidate
outputs, the LTR library, the RepeatModeler library, or required final masking
outputs are empty. It is intended for repeat-bearing eukaryotic assemblies,
not tiny repeat-free test sequences. An empty output can be biologically real;
a failed workflow is not itself proof of an algorithm error or a bad genome.

The retained upstream wrappers treat a nonzero regional command as a salvage
trigger, not exclusively as a proven timeout, and can suppress regional
stderr. A header-only `.scn` is not a positive candidate count. Neither wrapper
provides a complete audited coverage/error report for every timed-out or failed
subwindow. The portable packaging does not correct these upstream scientific
coverage limitations; inspect logs and validate structural results separately.

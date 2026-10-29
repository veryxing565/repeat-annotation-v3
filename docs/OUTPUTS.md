# Output contract

One result directory is published per successful sample. Files remain
uncompressed, including RepeatMasker's raw `.align`.

| File / location | Meaning |
| --- | --- |
| `library/SAMPLE.v3.TElib.fa` | the single library actually used for final masking |
| `library/SAMPLE.v3.TElib.metadata.tsv` | source/classification/cluster representative provenance |
| `library/SAMPLE.v3.TElib.clstr` | CD-HIT cluster membership |
| `library/ltr_retriever.*` | normalized LTR-derived source library and metadata |
| `library/repeatmodeler.known.fa` | known-class RepeatModeler source consensuses |
| `library/repeatmodeler.unknown.fa` | Unknown consensuses before TEclass2 |
| `library/teclass2.*` | predictions, accepted/retained source records, metadata/config |
| `library/SAMPLE.LTR_retriever.pass.list` | passing structural LTR candidates, when produced |
| `repeatmasker/SAMPLE.normalized.fa.masked` | final soft-masked assembly; preserve lowercase |
| `repeatmasker/SAMPLE.normalized.fa.out` | RepeatMasker hit annotation |
| `repeatmasker/SAMPLE.normalized.fa.out.gff` | RepeatMasker GFF (not necessarily a normalized GFF3) |
| `repeatmasker/SAMPLE.normalized.fa.tbl` | repeat summary; `-excln` affects the denominator |
| `repeatmasker/SAMPLE.normalized.fa.align` | uncompressed hit alignments for later analyses |
| `qc/SAMPLE.contig_id_map.tsv` | short/original IDs, original descriptions, sequence lengths |
| `qc/genome_summary.txt` | normalization counts, limits, sequence digest |
| `qc/v3_parameters.txt` | scientific settings for this sample |
| `qc/workflow_source_sha256.txt` | executed wrapper/helper source fingerprints |
| `qc/input_sha256.txt` | original/normalized input and ID-map hashes |
| `qc/result_sha256.txt` | relative-path hashes for all retained export files |

Empty optional source files may be absent: `copy_if_present` retains nonempty
source products only. Final required outputs must be nonempty. LTR/RepeatModeler
raw scratch databases are deliberately not retained after success; retain logs,
source libraries, final library, parameters and checksums instead.

The original assembly is not duplicated in results; the soft-masked assembly
is retained. Always use matching normalized IDs for annotation and visualization.
If you restore original IDs downstream, update every coordinate-bearing file
consistently; the workflow does not silently rewrite external annotations.

Completion markers are written only after published results pass checksum
validation. A completed marker records the source assembly SHA256 and result
location. Failure markers point to logs and preserved scratch work. Never
create a completion marker manually to bypass a failed stage.

To verify a published sample directly:

```bash
cd /absolute/path/to/RESULT_ROOT/results/SAMPLE
sha256sum -c qc/result_sha256.txt
```

Result checksums cover retained files, not biological quality. The input SHA256
is over the input file bytes, so recompressing an otherwise identical assembly
changes its input fingerprint and prevents silent reuse.

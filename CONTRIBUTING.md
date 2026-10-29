# Contributing

Discuss scientific changes separately from portability/safety changes. Keep
production v3 defaults reproducible; introduce changed methods under an explicit
new configuration/version with rationale and validation.

1. Add tests for FASTA/classification/cluster or execution behavior affected.
2. Run the documented unit, mock-integration and syntax tests on Linux.
3. Update methods, output contract, dependencies, and changelog if appropriate.
4. Preserve third-party attribution and original LICENSE files.
5. Do not commit genomes, reads, model weights, credentials, container images,
   machine-specific configurations, or analysis results.

Tests using mock programs establish orchestration behavior only. Claims about
sensitivity/specificity or runtime need real datasets, fixed tool versions,
reference truth/metrics, hardware details, and a reproducible benchmark.

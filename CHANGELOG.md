# Changelog

## 3.0.0rc1 — portable packaging of the production v3 workflow

- Based on the latest outgroup workflow source collected on 2026-10-29.
- Keeps LTR structural discovery, RepeatModeler 2.0.1/81 Mb/seed 42, Unknown-only
  TEclass2, conservative near-duplicate selection, and RepeatMasker settings.
- Bundles both MIT-licensed patched LTR wrappers and necessary text helpers.
- Replaces machine-specific paths with a configuration template; supports native
  dependencies or a user-supplied local RepeatModeler container.
- Adds configurable CPU budgets, dependency checks, ownership-based cleanup,
  checksum validation, tests, English documentation, and CI.
- Unsafe FASTA IDs as well as overlong IDs are renamed in the portable edition.
  Safe, short IDs, sequences, and sequence order are otherwise preserved.
- Rejects malformed TEclass2 probabilities and inconsistent CD-HIT membership
  instead of silently proceeding with corrupt outputs.

This is a release candidate, not a new benchmark or a claim of identical
results across different dependency versions/platforms. No biological analysis
is launched by unpacking the source distribution.

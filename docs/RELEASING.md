# Preparing a GitHub release

This directory is the repository root. Upload its contents, not its enclosing
private audit directory or another project's working tree. The source archive
contains no credentials, SSH settings, personal host addresses, genomic inputs,
TEclass2 model weights, container images, or runtime results.

Before a public release, the owner should:

1. Choose the final repository name and fill in real maintainer/contact details
   and author affiliations as appropriate; update `CITATION.cff` accordingly.
   No repository URL, contact email, or publication DOI has been invented.
2. Review MIT licensing for the original project code and the separate upstream
   licenses. Retain the included LTR copyright/license texts.
3. Review dependency preparation, especially a compatible RepeatModeler 2.0.1
   installation and TEclass2 model/source terms. These are user supplied.
4. Run unit/mock tests and a real small eukaryotic-genome pilot with the exact
   intended native/container dependencies. Mock tests are not a biological pilot.
5. Review `docs/VALIDATION.md`; do not claim universal performance or cross-platform
   bitwise reproducibility. Keep the release-candidate suffix until satisfied.
6. Run `python scripts/build_release.py --output /absolute/path/to/release_files`.
   Verify the generated archive hashes and inspect the source manifest.
7. Create the remote repository, add the source, and push/tag only after checking
   repository visibility and ownership. These publication steps are intentionally
   not performed merely by preparing this local package.

The supplied `.github/workflows/ci.yml` runs tests after upload; a local CI
configuration file is not evidence that GitHub Actions has already passed.
GitHub Releases/Zenodo archives can be added after the repository exists.

## Build artifacts

The build script emits ZIP and tar.gz sources, `SHA256SUMS`, and a JSON file
manifest into a separate output directory. Each archive has a single top-level
directory and includes its own `MANIFEST.sha256`. File permissions and tar
timestamps are normalized for release distribution; compiled caches/local
configurations/runtime data are excluded. This is a source distribution, not
a frozen dependency environment.

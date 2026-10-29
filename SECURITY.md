# Security

Do not put passwords, SSH private keys, access tokens, or unpublished biological
data into issues. Until a private reporting channel is configured by the
repository owner, report sensitive vulnerabilities privately to that owner;
do not publish credentials or an exploitable live server address.

Configuration files are trusted Bash and execute with your account privileges.
Do not source untrusted configurations. Third-party Perl wrappers invoke shell
commands internally; the portable runner restricts source/work/tool paths and
normalizes unsafe FASTA IDs, but is not a sandbox for hostile code or datasets.
Run under an unprivileged account and dedicated scratch storage.

Cleanup operates only on owned sample work after checksum validation. Do not
modify ownership markers, replace paths with symlinks, or place unrelated
files in active workspaces. File checksums detect changes, not malicious
replacement by a user with write access to both data and manifests.

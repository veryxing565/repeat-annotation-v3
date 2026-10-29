# Troubleshooting

## Preflight fails

- Replace all example paths; use real TAB characters, no header row, and Unix
  LF endings in the manifest. Comment lines begin with `#`.
- Activate the dependency environment or configure both MAMBA and ENV_PREFIX.
  The runtime's GNU tools (`taskset`, `flock`, etc.) must also be available.
- Check the scheduler CPU allowance. THREADS must be a multiple of four and
  cannot exceed the process's current allowed CPU set.
- Keep source/work/LTR tool paths free of spaces and shell syntax. Do not use
  symlinked or broad owned roots. Input genomes must be outside scratch.
- Prepare all model assets and TEclass2 imports. The light preflight cannot
  certify every transitive model dependency; follow upstream instructions.

## Wrong RepeatModeler or container errors

Check the actual invoked version, not the conda package list. Set
REPEATMODELER_BIN or REPEATMODELER_SIF, not both. This workflow depends on
2.0.1 legacy sampling/parallel options. Do not bypass checks to use 2.0.9.

For image mount/proc/FUSE/user-namespace errors, test your image independently
with your cluster administrator. A compatible native install is an alternative.
The workflow will not alter system mounts, permissions, or container services.

## An individual genome failed

Inspect `logs/SAMPLE.v3.log` and `state/SAMPLE.failed`. A scientific tool's
nonzero exit must remain a failure; do not manufacture required outputs.
Scratch is intentionally preserved. Missing/empty results may arise from tool
errors, absent dependencies, resource limits, or genuinely few structural LTRs.
Three consecutive failures are an operational stop rule, not a diagnosis.

Existing incomplete result/work directories are not overwritten. If you decide
to retry from scratch, first check the exact sample/path and preserve anything
you need; move/remove only that sample's failed work. Leave the owned root
marker and other samples alone. Reusing a new result root and new scratch root
is often safer than editing completion state.

## Slow or apparently quiet stages

RepeatModeler sampling and RepeatMasker searches vary with genome size and
repeat content. RepeatMasker's ProcessRepeats can be predominantly single-core
and print infrequently. Check CPU/I/O and log timestamps before concluding a
job is stalled. The LTR timeout limits windows, not the entire annotation job.
No maximum genome runtime, RAM limit, or automatic job-timeout rescue is set.

## Quality concerns

An unexpectedly small masked fraction can reflect incomplete discovery, wrong
libraries, sequence divergence, or true biology; a large fraction can include
false-positive/contaminating consensuses. Compare source libraries and genome
identity, not only percent masking. Unknown is not automatically bad sequence.
This workflow does not validate host-gene contamination or TE family phylogeny.

## Interrupted transfer/cleanup

A `.partial` result is not complete. Never delete scratch solely because a
copy command returned success; completion requires the checksum manifest.
If a crash occurs between publication and cleanup, keep both locations and
inspect provenance. Do not overwrite the final directory to force a retry.
The portable tool deliberately refuses ambiguous states for manual resolution.

## Opening an issue

Use the bug-report template. Include the workflow version, OS/architecture,
external tool versions, sanitized configuration, exact failed stage, exit code,
and relevant log tail. Exclude credentials, SSH keys, unpublished sequence data,
and personal server paths. Do not upload enormous alignments or model weights.

#!/usr/bin/env bash
# Trusted Bash configuration. Copy to config.local.sh and edit absolute paths.
# No downloads or dependency installation are performed by the workflow.

RESULT_ROOT="/path/to/project/te_results"
TMP_ROOT="/path/to/local_scratch/te_work"
TECLASS_HOME="/path/to/TEclass2"

# Default: use tools in the currently activated environment/PATH.
# Alternatively supply BOTH MAMBA (micromamba executable) and ENV_PREFIX.
MAMBA=""
ENV_PREFIX=""
PYTHON="python"
# Optional Python executable for a separate, fully prepared TEclass2 environment.
# Leave empty to use the same Python as the workflow helpers.
TECLASS_PYTHON=""

# RepeatModeler MUST be compatible 2.0.1 with -genomeSampleSizeMax/-srand/-pa.
# Option 1: native tools in PATH, or prepend this directory ONLY for RM tools.
REPEATMODELER_BIN="/path/to/RepeatModeler-2.0.1/bin"
# Option 2: use your own local SIF instead. Clear REPEATMODELER_BIN if selected.
APPTAINER="apptainer"
REPEATMODELER_SIF=""

# Optional read-only previous result ROOT. It must have the same results/state
# structure and checksums; do NOT point this at an arbitrary result folder.
PREVIOUS_COMPLETE_ROOT=""

# Total CPU budget; >=4, divisible by 4, <= CPUs allowed by your scheduler.
# One genome at a time. For a smaller machine, use e.g. 8, 16, 24, or 32.
THREADS=56
RM_SAMPLE_MAX=81000000
RM_SEED=42
LTR_CHUNK_SIZE=5000000
LTR_OVERLAP=100000
LTR_TIMEOUT=300
TECLASS_ACCEPT=0.80
TECLASS_CANDIDATE=0.70
CDHIT_IDENTITY=0.95
CDHIT_COVERAGE=0.90
RM_CUTOFF=225
MAX_CONSECUTIVE_FAILURES=3

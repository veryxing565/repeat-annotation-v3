#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s nullglob

usage() {
  cat <<'EOF'
Usage:
  bash run_te_annotation_v3.sh CONFIG MANIFEST
  bash run_te_annotation_v3.sh --check-only CONFIG MANIFEST

MANIFEST is a two-column tab-delimited file:
  sample_id<TAB>/absolute/path/to/genome.fa[.gz]
EOF
}

CHECK_ONLY=0
SAMPLE_WORKER=0
if [[ ${1:-} == --sample-worker ]]; then
  SAMPLE_WORKER=1
  shift
fi
if [[ ${1:-} == --check-only ]]; then
  CHECK_ONLY=1
  shift
fi
if (( SAMPLE_WORKER )); then
  [[ $# -eq 4 ]] || { usage >&2; exit 2; }
else
  [[ $# -eq 2 ]] || { usage >&2; exit 2; }
fi
CONFIG=$(readlink -f "$1")
MANIFEST=$(readlink -f "$2")
# shellcheck source=/dev/null
source "$CONFIG"

: "${TECLASS_HOME:?set TECLASS_HOME in config}"
: "${RESULT_ROOT:?set RESULT_ROOT in config}"
: "${TMP_ROOT:?set TMP_ROOT in config}"
: "${PREVIOUS_COMPLETE_ROOT:=}"
: "${MAMBA:=}"
: "${ENV_PREFIX:=}"
: "${PYTHON:=python}"
: "${TECLASS_PYTHON:=}"
: "${APPTAINER:=apptainer}"
: "${REPEATMODELER_SIF:=}"
: "${REPEATMODELER_BIN:=}"
: "${THREADS:=56}"
: "${RM_SAMPLE_MAX:=81000000}"
: "${RM_SEED:=42}"
: "${LTR_CHUNK_SIZE:=5000000}"
: "${LTR_OVERLAP:=100000}"
: "${LTR_TIMEOUT:=300}"
: "${TECLASS_ACCEPT:=0.80}"
: "${TECLASS_CANDIDATE:=0.70}"
: "${CDHIT_IDENTITY:=0.95}"
: "${CDHIT_COVERAGE:=0.90}"
: "${RM_CUTOFF:=225}"
: "${MAX_CONSECUTIVE_FAILURES:=3}"
[[ "$MAX_CONSECUTIVE_FAILURES" == 3 ]] || { echo "Failure limit must be 3" >&2; exit 2; }
[[ "$TECLASS_HOME" == /* ]] || { echo "TECLASS_HOME must be absolute" >&2; exit 2; }
[[ -z "$REPEATMODELER_SIF" || "$REPEATMODELER_SIF" == /* ]] || { echo "REPEATMODELER_SIF must be absolute" >&2; exit 2; }
[[ -z "$TECLASS_PYTHON" || "$TECLASS_PYTHON" == /* ]] || { echo "TECLASS_PYTHON must be an absolute executable path" >&2; exit 2; }
for executable in "$MAMBA" "$PYTHON" "$APPTAINER"; do
  [[ -z "$executable" || "$executable" != */* || "$executable" == /* ]] || {
    echo "Use a PATH command name or an absolute executable path: $executable" >&2; exit 2;
  }
done

[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] && (( THREADS >= 4 && THREADS % 4 == 0 )) || {
  echo "THREADS must be an integer >=4 divisible by 4: $THREADS" >&2
  exit 2
}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PY_IDS="$SCRIPT_DIR/scripts/fasta_ids.py"
PY_LIB="$SCRIPT_DIR/scripts/library_ops.py"
PY_CONFIG="$SCRIPT_DIR/scripts/make_teclass_config.py"
PY_RUNTIME="$SCRIPT_DIR/scripts/runtime.py"
LTR_FINDER_PATCHED="$SCRIPT_DIR/patched_tools/LTR_FINDER_parallel/LTR_FINDER_parallel"
LTR_HARVEST_PATCHED="$SCRIPT_DIR/patched_tools/LTR_HARVEST_parallel/LTR_HARVEST_parallel"

[[ "$RESULT_ROOT" == /* && "$TMP_ROOT" == /* ]] || { echo "Workspace roots must be absolute" >&2; exit 2; }
# Do not resolve symlinks here: runtime.py must be able to reject them.
MMRUN=()
if [[ -n "$MAMBA" || -n "$ENV_PREFIX" ]]; then
  [[ -n "$MAMBA" && -n "$ENV_PREFIX" ]] || { echo "Set both MAMBA and ENV_PREFIX, or neither" >&2; exit 2; }
  MMRUN=("$MAMBA" run -p "$ENV_PREFIX")
fi
PYRUN=("${MMRUN[@]}" "$PYTHON")
TEPYRUN=("${PYRUN[@]}")
[[ -z "$TECLASS_PYTHON" ]] || TEPYRUN=("$TECLASS_PYTHON")
runtime() { "${PYRUN[@]}" "$PY_RUNTIME" "$@"; }
root_lines=$(runtime roots --result "$RESULT_ROOT" --temporary "$TMP_ROOT")
RESULT_ROOT=$(printf '%s\n' "$root_lines" | head -n 1)
TMP_ROOT=$(printf '%s\n' "$root_lines" | tail -n 1)

[[ $(uname -s) == Linux ]] || { echo "This workflow requires Linux, GNU coreutils and taskset/flock" >&2; exit 2; }
CPU_LIST=$(runtime cpus --threads "$THREADS")
taskset -pc "$CPU_LIST" "$$" >/dev/null
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RM_PA=$(( THREADS / 4 ))
(( RM_PA > 0 && RM_PA * 4 == THREADS )) || { echo "Invalid RepeatModeler/RepeatMasker parallelism for THREADS=$THREADS" >&2; exit 2; }

require_env_command() {
  local tool_path
  if ! tool_path=$("${PYRUN[@]}" -c 'import shutil,sys;p=shutil.which(sys.argv[1]);sys.exit(1) if not p else print(p)' "$1"); then
    echo "Missing command in selected environment/PATH: $1" >&2
    exit 1
  fi
  runtime guard-tool-path --path "$tool_path"
}

if (( ! SAMPLE_WORKER )); then
  for command in perl timeout gt ltr_finder LTR_retriever cd-hit-est RepeatMasker; do
    require_env_command "$command"
  done
fi
for file in "$PY_IDS" "$PY_LIB" "$PY_CONFIG" "$PY_RUNTIME" "$LTR_FINDER_PATCHED" "$LTR_HARVEST_PATCHED"; do
  [[ -s "$file" ]] || { echo "Missing workflow file: $file" >&2; exit 1; }
done
RMRUN=("${MMRUN[@]}")
if [[ -n "$REPEATMODELER_BIN" && -n "$REPEATMODELER_SIF" ]]; then
  echo "Choose REPEATMODELER_BIN or REPEATMODELER_SIF, not both" >&2; exit 2
fi
if [[ -n "$REPEATMODELER_BIN" ]]; then
  [[ "$REPEATMODELER_BIN" == /* && -d "$REPEATMODELER_BIN" ]] || { echo "REPEATMODELER_BIN must be an absolute directory" >&2; exit 2; }
  runtime guard-tool-path --path "$REPEATMODELER_BIN"
  RMRUN=("${MMRUN[@]}" bash -c 'export PATH="$1:$PATH"; shift; exec "$@"' bash "$REPEATMODELER_BIN")
fi
if [[ -n "$REPEATMODELER_SIF" ]]; then
  command -v "$APPTAINER" >/dev/null || { echo "Missing Apptainer: $APPTAINER" >&2; exit 1; }
  [[ -s "$REPEATMODELER_SIF" ]] || { echo "Missing RepeatModeler image: $REPEATMODELER_SIF" >&2; exit 1; }
  RMRUN=("$APPTAINER" exec --cleanenv)
  [[ ! -d "$TMP_ROOT" ]] || RMRUN+=(--bind "$TMP_ROOT:$TMP_ROOT")
  RMRUN+=("$REPEATMODELER_SIF")
fi
if (( ! SAMPLE_WORKER )); then
  "${PYRUN[@]}" -c 'import sys,Bio,yaml;assert sys.version_info >= (3,10), "Python >=3.10 required"'
  "${TEPYRUN[@]}" -c 'import torch,yaml; print("TEClass2 Python dependencies available")'
  rm_version=$("${RMRUN[@]}" RepeatModeler -version 2>&1)
  [[ "$rm_version" =~ (^|[^0-9])2\.0\.1([^0-9.]|$) ]] || {
    echo "RepeatModeler 2.0.1 is required; got: $rm_version" >&2; exit 2;
  }
  rm_help=$("${RMRUN[@]}" RepeatModeler -help 2>&1 || true)
  for option in genomeSampleSizeMax srand pa; do
    [[ "$rm_help" == *"$option"* ]] || {
      echo "RepeatModeler lacks required -$option; use the compatible v3 2.0.1 build" >&2; exit 2;
    }
  done
  "${RMRUN[@]}" BuildDatabase -help >/dev/null 2>&1 || {
    echo "BuildDatabase unavailable or -help failed" >&2; exit 2;
  }
fi
[[ -s "$TECLASS_HOME/TEclass2.py" ]] || { echo "Missing TEClass2 source" >&2; exit 1; }
[[ -s "$TECLASS_HOME/models/clust_cats_16/pytorch_model.bin" ]] || {
  echo "Missing TEClass2 model" >&2; exit 1
}

metadata_header() {
  printf '%s\n' $'record_id\tspecies\tsource\toriginal_id\toriginal_class\tteclass2_class\tteclass2_score\tfinal_class\tdecision\tcluster_id\tmember_count\tmember_ids\tlength'
}

copy_if_present() {
  local source=$1 destination=$2
  if [[ -s "$source" ]]; then
    cp -p -- "$source" "$destination"
  fi
}

count_fasta() {
  awk '/^>/{n++} END{print n+0}' "$1"
}

preflight_manifest() {
  runtime manifest --result "$RESULT_ROOT" --temporary "$TMP_ROOT" \
    --manifest "$MANIFEST" --script-dir "$SCRIPT_DIR"
  echo "RESOURCES threads=$THREADS cpus=$CPU_LIST rm_pa=$RM_PA rm_sample_max=$RM_SAMPLE_MAX"
}

if (( CHECK_ONLY )); then
  preflight_manifest
  exit 0
fi
if (( ! SAMPLE_WORKER )); then
  for command in taskset flock setsid sha256sum file readlink sort xargs; do
    command -v "$command" >/dev/null || { echo "Missing Linux runtime command: $command" >&2; exit 2; }
  done
  preflight_manifest
  runtime prepare --result "$RESULT_ROOT" --temporary "$TMP_ROOT"
  [[ ! -L "$RESULT_ROOT/.batch.lock" && ! -L "$RESULT_ROOT/logs/manifest_preflight.log" ]] || {
    echo "Refusing symlink lock/preflight log" >&2; exit 2;
  }
  exec 9>>"$RESULT_ROOT/.batch.lock"
  flock -n 9 || { echo "A batch already owns this RESULT_ROOT" >&2; exit 2; }
  preflight_manifest > "$RESULT_ROOT/logs/manifest_preflight.log"
else
  [[ -e /proc/$$/fd/9 && $(readlink "/proc/$$/fd/9") == "$RESULT_ROOT/.batch.lock" ]] || {
    echo "Internal worker requires the inherited batch lock" >&2; exit 2;
  }
fi

process_one() {
  local sample=$1 genome=$2
  local work export_dir final_result partial_result genome_norm id_map
  local ltr_dir finder_scn harvest_scn ltr_library ltr_pass_list
  local rm_dir rm_library lib_dir mask_dir rm_base

  genome=$(readlink -f "$genome")

  if [[ -e "$RESULT_ROOT/state/$sample.complete" || -L "$RESULT_ROOT/state/$sample.complete" ]]; then
    runtime verify-complete --result "$RESULT_ROOT" --sample "$sample" --genome "$genome"
    echo "[$(date -Is)] SKIP v3-complete sample=$sample"
    return 0
  fi
  if [[ -n "$PREVIOUS_COMPLETE_ROOT" && ( -e "$PREVIOUS_COMPLETE_ROOT/state/$sample.complete" || -L "$PREVIOUS_COMPLETE_ROOT/state/$sample.complete" ) ]]; then
    runtime verify-complete --result "$PREVIOUS_COMPLETE_ROOT" --sample "$sample" --genome "$genome"
    {
      echo "sample=$sample"
      echo "reason=previous_complete"
      echo "previous_result=$PREVIOUS_COMPLETE_ROOT/results/$sample"
      echo "skipped=$(date -Is)"
    } > "$RESULT_ROOT/state/$sample.skipped_existing"
    echo "[$(date -Is)] SKIP previously completed sample=$sample"
    return 0
  fi

  final_result="$RESULT_ROOT/results/$sample"
  [[ ! -e "$final_result" && ! -L "$final_result" ]] || {
    echo "Result exists without v3 completion marker: $final_result" >&2
    return 1
  }

  work="$TMP_ROOT/$sample"
  if [[ ${RESUME_REPEATMASKER_SAMPLE:-} == "$sample" ]]; then
    runtime validate-sample --result "$RESULT_ROOT" --temporary "$TMP_ROOT" --sample "$sample" --genome "$genome"
    export_dir="$work/export"
    genome_norm="$work/$sample.normalized.fa"
    id_map="$work/$sample.contig_id_map.tsv"
    lib_dir="$work/library"
    [[ -s "$genome_norm" && -s "$export_dir/qc/input_sha256.txt" && -s "$export_dir/qc/v3_parameters.txt" ]]
    [[ -s "$lib_dir/$sample.v3.TElib.fa" ]]
    sha256sum -c "$export_dir/qc/input_sha256.txt"
    cmp "$lib_dir/$sample.v3.TElib.fa" "$export_dir/library/$sample.v3.TElib.fa"
    [[ -d "$work/repeatmasker" && -z $(find "$work/repeatmasker" -mindepth 1 -print -quit) ]]
    echo "[$(date -Is)] RESUME sample=$sample stage=repeatmasker verified_existing_library=true"
  else
  [[ ! -e "$work" ]] || {
    echo "Temporary sample directory already exists: $work" >&2
    echo "Inspect it before resuming; v3 will not overwrite it." >&2
    return 1
  }
  runtime init-sample --result "$RESULT_ROOT" --temporary "$TMP_ROOT" --sample "$sample" --genome "$genome"
  export_dir="$work/export"
  mkdir -p "$export_dir"/{library,repeatmasker,qc}
  sha256sum "$SCRIPT_DIR/run_te_annotation_v3.sh" "$SCRIPT_DIR/scripts/batch_runner.sh" \
    "$PY_RUNTIME" "$PY_IDS" "$PY_LIB" "$PY_CONFIG" \
    "$LTR_FINDER_PATCHED" "$LTR_HARVEST_PATCHED" \
    > "$export_dir/qc/workflow_source_sha256.txt"
  echo "[$(date -Is)] START v3 sample=$sample genome=$genome temp=$work"

  STAGE=normalize_ids_uppercase
  genome_norm="$work/$sample.normalized.fa"
  id_map="$work/$sample.contig_id_map.tsv"
  "${PYRUN[@]}" "$PY_IDS" \
    --input "$genome" --output "$genome_norm" --map "$id_map" --sample "$sample" \
    | tee "$export_dir/qc/genome_summary.txt"
  cp -p -- "$id_map" "$export_dir/qc/"
  sha256sum "$genome" "$genome_norm" "$id_map" > "$export_dir/qc/input_sha256.txt"

  STAGE=ltr_candidates
  ltr_dir="$work/ltr"
  mkdir -p "$ltr_dir"
  (
    cd "$ltr_dir"
    "${MMRUN[@]}" perl "$LTR_FINDER_PATCHED" \
      -seq "$genome_norm" -size "$LTR_CHUNK_SIZE" -overlap "$LTR_OVERLAP" \
      -time "$LTR_TIMEOUT" -try1 1 -harvest_out -threads "$THREADS"
    "${MMRUN[@]}" perl "$LTR_HARVEST_PATCHED" \
      -seq "$genome_norm" -size "$LTR_CHUNK_SIZE" -overlap "$LTR_OVERLAP" \
      -time "$LTR_TIMEOUT" -try1 1 -threads "$THREADS"
  )
  finder_scn="$ltr_dir/$(basename "$genome_norm").finder.combine.scn"
  harvest_scn="$ltr_dir/$(basename "$genome_norm").harvest.combine.scn"
  [[ -s "$finder_scn" || -s "$harvest_scn" ]] || {
    echo "Both patched LTR candidate finders returned empty output" >&2; return 1
  }

  STAGE=ltr_retriever
  ltr_args=(-genome "$genome_norm" -threads "$THREADS" -noanno)
  [[ -s "$finder_scn" ]] && ltr_args+=(-infinder "$finder_scn")
  [[ -s "$harvest_scn" ]] && ltr_args+=(-inharvest "$harvest_scn")
  (
    cd "$work"
    "${MMRUN[@]}" LTR_retriever "${ltr_args[@]}"
  )
  ltr_library=$(find "$work" -maxdepth 1 -type f \
    -name "$(basename "$genome_norm")*.LTRlib.fa" -size +0c | sort | head -n 1)
  [[ -n "$ltr_library" && -s "$ltr_library" ]] || {
    echo "LTR_retriever did not produce a non-empty library" >&2; return 1
  }

  STAGE=repeatmodeler
  rm_dir="$work/repeatmodeler"
  mkdir -p "$rm_dir"
  (
    cd "$rm_dir"
    "${RMRUN[@]}" \
      BuildDatabase -name "$sample.rmdb" -engine rmblast "$genome_norm"
    "${RMRUN[@]}" \
      RepeatModeler -database "$sample.rmdb" -pa "$RM_PA" \
        -genomeSampleSizeMax "$RM_SAMPLE_MAX" -srand "$RM_SEED"
  )
  rm_library=$(find "$rm_dir" -type f -path '*/RM_*/consensi.fa.classified' -size +0c | sort | tail -n 1)
  [[ -n "$rm_library" && -s "$rm_library" ]] || {
    echo "RepeatModeler did not produce consensi.fa.classified" >&2; return 1
  }

  STAGE=teclass_and_library
  lib_dir="$work/library"
  mkdir -p "$lib_dir"
  "${PYRUN[@]}" "$PY_LIB" normalize \
    --input "$ltr_library" --output "$lib_dir/ltr_retriever.fa" \
    --metadata "$lib_dir/ltr_retriever.metadata.tsv" \
    --species "$sample" --source LTRstruct --tag LTR --default-class LTR/Unknown

  "${PYRUN[@]}" "$PY_LIB" split-repeatmodeler \
    --input "$rm_library" \
    --known "$lib_dir/repeatmodeler.known.fa" \
    --unknown "$lib_dir/repeatmodeler.unknown.fa" \
    --metadata "$lib_dir/repeatmodeler.metadata.tsv" \
    --species "$sample"

  if grep -q '^>' "$lib_dir/repeatmodeler.unknown.fa"; then
    "${PYRUN[@]}" "$PY_CONFIG" \
      --base "$TECLASS_HOME/config.yml" --models "$TECLASS_HOME/models" \
      --output "$lib_dir/teclass2.cpu.yml"
    (
      cd "$TECLASS_HOME"
      OMP_NUM_THREADS="$THREADS" MKL_NUM_THREADS="$THREADS" \
        "${TEPYRUN[@]}" TEclass2.py --classify \
          -c "$lib_dir/teclass2.cpu.yml" \
          -f "$lib_dir/repeatmodeler.unknown.fa" \
          -o "$lib_dir/teclass2.predictions.tsv"
    )
    "${PYRUN[@]}" "$PY_LIB" apply-teclass \
      --input "$lib_dir/repeatmodeler.unknown.fa" \
      --predictions "$lib_dir/teclass2.predictions.tsv" \
      --accepted "$lib_dir/teclass2.accepted.fa" \
      --unknown "$lib_dir/teclass2.retained_unknown.fa" \
      --metadata "$lib_dir/teclass2.metadata.tsv" \
      --species "$sample" --threshold "$TECLASS_ACCEPT" \
      --candidate-threshold "$TECLASS_CANDIDATE"
  else
    printf '%s\n' $'name\tclass\tmax_probability' > "$lib_dir/teclass2.predictions.tsv"
    : > "$lib_dir/teclass2.accepted.fa"
    : > "$lib_dir/teclass2.retained_unknown.fa"
    metadata_header > "$lib_dir/teclass2.metadata.tsv"
  fi

  # v3 has exactly one softmasking library. All unresolved Unknown records
  # are deliberately retained as requested.
  cat "$lib_dir/ltr_retriever.fa" \
      "$lib_dir/repeatmodeler.known.fa" \
      "$lib_dir/teclass2.accepted.fa" \
      "$lib_dir/teclass2.retained_unknown.fa" \
      > "$lib_dir/all_candidates.fa"
  grep -q '^>' "$lib_dir/all_candidates.fa" || {
    echo "Combined v3 library is empty" >&2; return 1
  }

  "${MMRUN[@]}" cd-hit-est \
    -i "$lib_dir/all_candidates.fa" -o "$lib_dir/cdhit.raw_representatives.fa" \
    -c "$CDHIT_IDENTITY" -n 10 -G 0 \
    -aS "$CDHIT_COVERAGE" -aL "$CDHIT_COVERAGE" \
    -g 1 -d 0 -T "$THREADS" -M 0
  "${PYRUN[@]}" "$PY_LIB" dedup-select \
    --input "$lib_dir/all_candidates.fa" \
    --clusters "$lib_dir/cdhit.raw_representatives.fa.clstr" \
    --metadata "$lib_dir/ltr_retriever.metadata.tsv" \
               "$lib_dir/repeatmodeler.metadata.tsv" \
               "$lib_dir/teclass2.metadata.tsv" \
    --output "$lib_dir/$sample.v3.TElib.fa" \
    --output-metadata "$lib_dir/$sample.v3.TElib.metadata.tsv" \
    --scope "$sample"
  grep -q '^>' "$lib_dir/$sample.v3.TElib.fa" || {
    echo "Final v3 TE library is empty" >&2; return 1
  }

  cp -p -- "$lib_dir/$sample.v3.TElib.fa" "$export_dir/library/"
  cp -p -- "$lib_dir/$sample.v3.TElib.metadata.tsv" "$export_dir/library/"
  cp -p -- "$lib_dir/cdhit.raw_representatives.fa.clstr" \
    "$export_dir/library/$sample.v3.TElib.clstr"
  for file in ltr_retriever.fa ltr_retriever.metadata.tsv \
    repeatmodeler.known.fa repeatmodeler.unknown.fa repeatmodeler.metadata.tsv \
    teclass2.predictions.tsv teclass2.accepted.fa teclass2.retained_unknown.fa \
    teclass2.metadata.tsv teclass2.cpu.yml; do
    copy_if_present "$lib_dir/$file" "$export_dir/library/$file"
  done
  ltr_pass_list=$(find "$work" -maxdepth 1 -type f \
    -name "$(basename "$genome_norm")*.pass.list" -size +0c | sort | head -n 1)
  [[ -z "$ltr_pass_list" ]] || cp -p -- "$ltr_pass_list" \
    "$export_dir/library/$sample.LTR_retriever.pass.list"

  {
    echo "workflow_version=v3"
    echo "runner_revision=20260906_failure_policy"
    echo "input_case_policy=uppercase_before_discovery_and_masking"
    echo "repeatmodeler_seed=$RM_SEED"
    echo "sample=$sample"
    echo "threads=$THREADS"
    echo "cpu_affinity=$CPU_LIST"
    echo "repeatmodeler_pa=$RM_PA"
    echo "repeatmodeler_version=2.0.1"
    echo "repeatmodeler_sample_max=$RM_SAMPLE_MAX"
    echo "repeatmodeler_ltrstruct=disabled"
    echo "ltr_chunk_size=$LTR_CHUNK_SIZE"
    echo "ltr_overlap=$LTR_OVERLAP"
    echo "ltr_timeout=$LTR_TIMEOUT"
    echo "ltr_salvage_finder_piece=50000"
    echo "ltr_salvage_finder_timeout=10"
    echo "ltr_salvage_harvest_piece=50000"
    echo "ltr_salvage_harvest_timeout=30"
    echo "teclass_accept=$TECLASS_ACCEPT"
    echo "teclass_candidate=$TECLASS_CANDIDATE"
    echo "unknown_policy=retain_all"
    echo "cdhit_identity=$CDHIT_IDENTITY"
    echo "cdhit_coverage=$CDHIT_COVERAGE"
    echo "repeatmasker_cutoff=$RM_CUTOFF"
    echo "final_library_records=$(count_fasta "$lib_dir/$sample.v3.TElib.fa")"
  } > "$export_dir/qc/v3_parameters.txt"

  fi
  STAGE=repeatmasker
  mask_dir="$work/repeatmasker"
  mkdir -p "$mask_dir"
  "${MMRUN[@]}" RepeatMasker \
    -engine rmblast -pa "$RM_PA" \
    -lib "$lib_dir/$sample.v3.TElib.fa" \
    -cutoff "$RM_CUTOFF" -xsmall -gff -a -gccalc -excln -norna -no_is \
    -dir "$mask_dir" "$genome_norm"
  rm_base="$mask_dir/$(basename "$genome_norm")"
  for suffix in masked out out.gff tbl align; do
    [[ -s "$rm_base.$suffix" ]] || {
      echo "Missing RepeatMasker output: $rm_base.$suffix" >&2; return 1
    }
    cp -p -- "$rm_base.$suffix" "$export_dir/repeatmasker/"
  done
  file "$export_dir/repeatmasker/$(basename "$rm_base").align" \
    > "$export_dir/qc/repeatmasker_align_filetype.txt"
  (
    cd "$export_dir"
    find . -type f ! -path './qc/result_sha256.txt' -print0 \
      | sort -z | xargs -0 sha256sum > qc/result_sha256.txt
  )

  STAGE=transfer_and_validate
  partial_result="$RESULT_ROOT/results/.$sample.v3.partial.$$"
  [[ ! -e "$partial_result" && ! -L "$partial_result" ]] || { echo "Partial result exists: $partial_result" >&2; return 1; }
  mkdir -p "$partial_result"
  cp -a -- "$export_dir"/. "$partial_result"/
  for required in \
    "$partial_result/library/$sample.v3.TElib.fa" \
    "$partial_result/repeatmasker/$(basename "$rm_base").masked" \
    "$partial_result/repeatmasker/$(basename "$rm_base").out" \
    "$partial_result/repeatmasker/$(basename "$rm_base").out.gff" \
    "$partial_result/repeatmasker/$(basename "$rm_base").tbl" \
    "$partial_result/repeatmasker/$(basename "$rm_base").align"; do
    [[ -s "$required" ]] || { echo "Transfer validation failed: $required" >&2; return 1; }
  done
  (cd "$partial_result" && sha256sum -c qc/result_sha256.txt > /dev/null)
  mv -- "$partial_result" "$final_result"

  # Publish a checksum-verified completion before cleanup, closing the old
  # crash gap where a final result existed but had no completion marker.
  runtime complete --result "$RESULT_ROOT" --temporary "$TMP_ROOT" --sample "$sample" --genome "$genome"
  runtime cleanup-sample --result "$RESULT_ROOT" --temporary "$TMP_ROOT" --sample "$sample" --genome "$genome"
  echo "[$(date -Is)] COMPLETE v3 sample=$sample; result transferred; temporary files removed"
}

if (( SAMPLE_WORKER )); then
  STAGE=sample_preflight
  WORKER_SAMPLE=$3
  trap 'rc=$?; echo "[$(date -Is)] WORKER_ERROR sample=$WORKER_SAMPLE stage=$STAGE exit_code=$rc line=$LINENO" >&2' ERR
  # Invoke directly, never inside if/||: Bash would otherwise disable errexit
  # throughout process_one and could continue after a failed scientific tool.
  process_one "$3" "$4"
  exit 0
fi

source "$SCRIPT_DIR/scripts/batch_runner.sh"
run_v3_batch

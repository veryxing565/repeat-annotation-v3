#!/usr/bin/env bash
# Each genome runs in a separate strict Bash and inherits the batch lock/affinity.
run_v3_batch() {
  local sample genome extra rc child_pid="" marker_root
  local consecutive=0 failed=0 completed=0 skipped=0
  trap '[[ -z ${child_pid:-} ]] || kill -TERM -- "-$child_pid" 2>/dev/null; exit 143' TERM
  trap '[[ -z ${child_pid:-} ]] || kill -TERM -- "-$child_pid" 2>/dev/null; exit 130' INT
  while IFS=$'\t' read -r sample genome extra || [[ -n "${sample:-}" ]]; do
    [[ -z "${sample// }" || "$sample" == \#* ]] && continue
    marker_root=""
    if [[ -e "$RESULT_ROOT/state/$sample.complete" || -L "$RESULT_ROOT/state/$sample.complete" ]]; then
      marker_root=$RESULT_ROOT
    elif [[ -n "$PREVIOUS_COMPLETE_ROOT" && ( -e "$PREVIOUS_COMPLETE_ROOT/state/$sample.complete" || -L "$PREVIOUS_COMPLETE_ROOT/state/$sample.complete" ) ]]; then
      marker_root=$PREVIOUS_COMPLETE_ROOT
    fi
    if [[ -n "$marker_root" ]]; then
      if runtime verify-complete --result "$marker_root" --sample "$sample" --genome "$genome"; then
        echo "[$(date -Is)] SKIP checksum-verified completed sample=$sample"
        skipped=$((skipped + 1))
        # An old completed sample does not reset the new-failure streak.
        continue
      else
        rc=$?
      fi
    else
      [[ ! -L "$RESULT_ROOT/logs/$sample.v3.log" && ! -L "$RESULT_ROOT/state/$sample.failed" ]] || {
        echo "Refusing symlink log/failure marker for $sample" >&2; return 2;
      }
      setsid bash "$SCRIPT_DIR/run_te_annotation_v3.sh" --sample-worker "$CONFIG" "$MANIFEST" "$sample" "$genome" \
        > >(tee -a "$RESULT_ROOT/logs/$sample.v3.log") 2>&1 &
      child_pid=$!
      if wait "$child_pid"; then rc=0; else rc=$?; fi
      child_pid=""
      if (( rc == 0 )) && [[ ! -s "$RESULT_ROOT/state/$sample.complete" ]]; then
        echo "Worker exited without a completion marker: $sample" >&2
        rc=1
      fi
    fi
    if (( rc == 0 )); then
      completed=$((completed + 1))
      consecutive=0
      rm -f -- "$RESULT_ROOT/state/$sample.failed"
      continue
    fi
    failed=$((failed + 1))
    consecutive=$((consecutive + 1))
    [[ ! -L "$RESULT_ROOT/state/$sample.failed" ]] || return 2
    {
      echo "sample=$sample"
      echo "exit_code=$rc"
      echo "failed=$(date -Is)"
      echo "consecutive_failures=$consecutive"
      echo "log=$RESULT_ROOT/logs/$sample.v3.log"
      echo "temp_preserved=$TMP_ROOT/$sample"
    } > "$RESULT_ROOT/state/$sample.failed"
    echo "[$(date -Is)] FAILED sample=$sample exit_code=$rc consecutive=$consecutive/$MAX_CONSECUTIVE_FAILURES; temporary files retained"
    if (( consecutive >= MAX_CONSECUTIVE_FAILURES )); then
      echo "[$(date -Is)] STOP: 3 consecutive genome failures; investigate cause. completed=$completed failed=$failed skipped=$skipped"
      return 3
    fi
    echo "[$(date -Is)] CONTINUE to next genome"
  done < "$MANIFEST"
  trap - INT TERM
  echo "[$(date -Is)] BATCH_FINISHED completed=$completed failed=$failed skipped=$skipped"
  if (( failed > 0 )); then
    echo "Failed samples remain unfinished; inspect their .failed markers and logs."
    return 1
  fi
  runtime cleanup-root --result "$RESULT_ROOT" --temporary "$TMP_ROOT"
}

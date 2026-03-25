#!/bin/bash
# 定期実行ラッパー: コマンド実行 → 日別ログ追記 → エラー時にメール通知
#
# Usage:
#   ./run_with_notify.sh <コマンド名> <実行コマンド...>
#
# 例:
#   ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms youtube instagram x

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CMD_NAME="$1"
shift

if [ -z "$CMD_NAME" ]; then
  echo "Usage: run_with_notify.sh <コマンド名> <実行コマンド...>"
  exit 1
fi

cd "$SCRIPT_DIR"

# ── 共通ランナー: 日別ログに追記 ──
PROJECT_ROOT="$SCRIPT_DIR"
RUN_JOB_CORE="/Users/shindoryohei/ops-hub/locks/run-job-core.sh"
if [ -f "$RUN_JOB_CORE" ]; then
  source "$RUN_JOB_CORE"
  job_setup "youtube-auto" "$CMD_NAME" "${JOB_TRIGGER:-launchd}"
  job_run_start
fi

# コマンド実行（stdout/stderr を日別ログ + tmpfile にキャプチャ）
TMPLOG=$(mktemp /tmp/youtube-auto-XXXXXX)

if [ -n "$_JOB_LOG_FILE" ]; then
  "$@" 2>&1 | tee -a "$_JOB_LOG_FILE" > "$TMPLOG"
  EXIT_CODE=${PIPESTATUS[0]}
else
  "$@" > "$TMPLOG" 2>&1
  EXIT_CODE=$?
fi

# 実行終了を記録
if [ -n "$_JOB_LOG_FILE" ]; then
  job_run_end $EXIT_CODE
fi

if [ $EXIT_CODE -ne 0 ]; then
  venv/bin/python error_notify.py "$CMD_NAME" "$TMPLOG" 2>/dev/null || true
fi

rm -f "$TMPLOG"
exit $EXIT_CODE

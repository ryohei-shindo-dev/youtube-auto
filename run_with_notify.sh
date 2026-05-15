#!/bin/bash
# 定期実行ラッパー: コマンド実行 → 日別ログ追記（エラー通知は ops-hub/failure-triage に委譲）
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

# ── .env から環境変数を読み込む（launchd では未設定のため） ──
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

# ── 共通ランナー: 日別ログに追記 ──
PROJECT_ROOT="$SCRIPT_DIR"
RUN_JOB_CORE="/Users/shindoryohei/ops-hub/runtime/run-job-core.sh"
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

rm -f "$TMPLOG"
exit $EXIT_CODE

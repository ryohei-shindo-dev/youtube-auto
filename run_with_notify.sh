#!/bin/bash
# 定期実行ラッパー: コマンド実行 → エラー時にメール通知
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
mkdir -p logs

# コマンド実行（stdout/stderrを一時ファイルに集約）
TMPLOG=$(mktemp /tmp/youtube-auto-XXXXXX.log)
"$@" > "$TMPLOG" 2>&1
EXIT_CODE=$?

# ログファイルに追記
cat "$TMPLOG" >> "logs/${CMD_NAME}.log"

if [ $EXIT_CODE -ne 0 ]; then
  venv/bin/python error_notify.py "$CMD_NAME" "$TMPLOG" 2>/dev/null || true
fi

rm -f "$TMPLOG"
exit $EXIT_CODE

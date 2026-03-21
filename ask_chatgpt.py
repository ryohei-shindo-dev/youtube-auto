"""OpenAI API 経由で ChatGPT に相談するCLIツール.

使い方:
    python ask_chatgpt.py "相談文"
    python ask_chatgpt.py -f prompt.txt
    echo "相談文" | python ask_chatgpt.py

環境変数:
    OPENAI_API_KEY  — 必須。OpenAI の API キー
    OPENAI_MODEL    — 省略時 gpt-4o
"""
from __future__ import annotations

import os
import sys

from openai import OpenAI


def main() -> None:
    # --- 入力の取得 ---
    prompt: str | None = None

    # -f オプション: ファイルから読む
    if len(sys.argv) >= 3 and sys.argv[1] == "-f":
        path = sys.argv[2]
        if not os.path.isfile(path):
            print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            prompt = f.read().strip()

    # 引数から読む
    elif len(sys.argv) >= 2:
        prompt = sys.argv[1]

    # stdin から読む（パイプ用）
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("使い方: python ask_chatgpt.py '相談文'", file=sys.stderr)
        print("        python ask_chatgpt.py -f prompt.txt", file=sys.stderr)
        print("        echo '相談文' | python ask_chatgpt.py", file=sys.stderr)
        sys.exit(1)

    # --- API キー確認 ---
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("エラー: 環境変数 OPENAI_API_KEY が設定されていません。", file=sys.stderr)
        print("設定方法: export OPENAI_API_KEY='sk-...'", file=sys.stderr)
        sys.exit(1)

    # --- API 呼び出し ---
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    print(response.output_text)


if __name__ == "__main__":
    main()

"""note記事の内部リンクをマークダウン形式から埋め込みカード形式に変換する。

・[タイトル](https://note.com/gachiho_motive/n/xxx)
→
https://note.com/gachiho_motive/n/xxx

noteエディタではURLを単独行に置くと自動的にカード表示になる。
"""
from __future__ import annotations

import re
from pathlib import Path

NOTE_DIR = Path("note_articles")

# マッチパターン: ・[任意のテキスト](noteのURL)
LINK_PATTERN = re.compile(
    r"^[・\-\*]\s*\[.*?\]\((https://note\.com/gachiho_motive/n/[a-z0-9]+)\)\s*$",
    re.MULTILINE,
)

changed = 0
for md_file in sorted(NOTE_DIR.glob("*.md")):
    text = md_file.read_text(encoding="utf-8")
    new_text = LINK_PATTERN.sub(r"\1", text)
    if new_text != text:
        md_file.write_text(new_text, encoding="utf-8")
        count = len(LINK_PATTERN.findall(text))
        print(f"✔ {md_file.name}: {count}件変換")
        changed += 1

print(f"\n合計 {changed} ファイルを更新")

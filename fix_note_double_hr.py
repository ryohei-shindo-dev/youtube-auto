"""note記事末尾の連続 --- を1つに減らす。"""
from __future__ import annotations

import re
from pathlib import Path

NOTE_DIR = Path(__file__).parent / "note_articles"

# 連続する --- を1つにまとめる
DOUBLE_HR = re.compile(r"(^---\n)+---$", re.MULTILINE)

changed = 0
for md_file in sorted(NOTE_DIR.glob("*.md")):
    text = md_file.read_text(encoding="utf-8")
    new_text = DOUBLE_HR.sub("---", text)
    if new_text != text:
        md_file.write_text(new_text, encoding="utf-8")
        diff = len(text) - len(new_text)
        print(f"  {md_file.name}: {diff}文字削減")
        changed += 1

print(f"\n合計 {changed} ファイルを修正")


if __name__ == "__main__":
    pass

"""全note記事のmdファイル内の内部リンクが公開済みかチェックする。"""
from __future__ import annotations

import json
import re
from pathlib import Path

manifest = json.load(open("note_manifest.json", encoding="utf-8"))

# 未公開の note_key 一覧（check_note_status.py の結果）
UNPUBLISHED = {28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48}

# note_key → sheet_no のマッピング
key_to_sn = {}
for row in manifest:
    key_to_sn[row["note_key"]] = row["sheet_no"]

# 各mdファイルをチェック
URL_RE = re.compile(r"https://note\.com/gachiho_motive/n/([a-z0-9]+)")
broken_count = 0

for row in manifest:
    sn = row["sheet_no"]
    md_path = Path(row["md_path"])
    if not md_path.exists():
        continue
    text = md_path.read_text(encoding="utf-8")
    for m in URL_RE.finditer(text):
        linked_key = m.group(1)
        linked_sn = key_to_sn.get(linked_key)
        if linked_sn and linked_sn in UNPUBLISHED:
            print(f"  #{sn:2d} → #{linked_sn}({linked_key}) ← 未公開")
            broken_count += 1

print(f"\nリンク切れ合計: {broken_count}件")

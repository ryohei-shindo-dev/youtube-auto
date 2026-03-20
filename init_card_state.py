"""state.jsonに既存公開記事の追加済みカード情報を初期化する（1回だけ実行）。"""
from __future__ import annotations

import json
import re
import urllib.request
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"
STATE_FILE = SCRIPT_DIR / "note_body_update_state.json"
NOTE_KEY_RE = re.compile(r"https://note\.com/gachiho_motive/n/([a-z0-9]+)")

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
sn_map = {int(r["sheet_no"]): r for r in manifest}

# 公開済みチェック
print("公開状態チェック中...")
published_keys = set()
published_sns = set()
for row in manifest:
    sn = int(row["sheet_no"])
    try:
        req = urllib.request.Request(row["url"], method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.getcode() == 200:
            published_keys.add(row["note_key"])
            published_sns.add(sn)
    except Exception:
        pass
    time.sleep(0.2)
print(f"  公開済み: {len(published_sns)}本")

# 各公開済み記事のmdファイルから、公開済みリンク先を抽出
cards = {}
for sn in sorted(published_sns):
    art = sn_map[sn]
    md_path = SCRIPT_DIR / art.get("md_path", "")
    if not md_path.exists():
        continue
    text = md_path.read_text(encoding="utf-8")
    embedded = []
    for m in NOTE_KEY_RE.finditer(text):
        k = m.group(1)
        if k in published_keys:
            embedded.append(k)
    cards[str(sn)] = sorted(set(embedded))

# 保存
state = {
    "published": sorted(published_sns),
    "cards": cards,
}
STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"state.json 初期化完了: {len(cards)}記事分のカード情報を記録")


if __name__ == "__main__":
    pass

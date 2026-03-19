"""全note記事の公開状態をチェックする。"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
import time

manifest = json.load(open("note_manifest.json", encoding="utf-8"))

published = []
not_published = []

for row in manifest:
    sn = row["sheet_no"]
    url = row["url"]
    title = row["sheet_title"][:40]
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        code = resp.getcode()
        if code == 200:
            published.append(sn)
            print(f"  #{sn:2d} OK   {title}")
        else:
            not_published.append(sn)
            print(f"  #{sn:2d} NG({code}) {title}")
    except urllib.error.HTTPError as e:
        not_published.append(sn)
        print(f"  #{sn:2d} NG({e.code}) {title}")
    except Exception as e:
        not_published.append(sn)
        print(f"  #{sn:2d} ERR  {title} ({e})")
    time.sleep(0.3)

print(f"\n公開済み: {len(published)}本")
print(f"非公開/エラー: {len(not_published)}本")
if not_published:
    print(f"非公開 sheet_no: {not_published}")

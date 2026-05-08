"""既存シートに content_id 列を追加し、既存行にバックフィルする（1回だけ実行）。

使い方:
  python migrate_add_content_id.py --dry-run   # 確認のみ
  python migrate_add_content_id.py              # 実際に書き込み
"""
from __future__ import annotations

import argparse
import os
import sys

import sheets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（書き込みしない）")
    args = parser.parse_args()

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_ID が設定されていません。")
        sys.exit(1)

    service = sheets.get_service()

    # 全行読み取り（A〜AC）
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A:AC",
    ).execute()
    rows = result.get("values", [])

    if not rows:
        print("シートにデータがありません。")
        return

    # ── シートの列数を拡張（29列=AC列まで必要） ──
    sheet_meta = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets.properties",
    ).execute()
    for s in sheet_meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == sheets.SHEET_NAME:
            current_cols = props.get("gridProperties", {}).get("columnCount", 0)
            need_cols = 29  # A〜AC = 29列
            if current_cols < need_cols:
                print(f"シート列数を {current_cols} → {need_cols} に拡張します...")
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": [{
                        "appendDimension": {
                            "sheetId": props["sheetId"],
                            "dimension": "COLUMNS",
                            "length": need_cols - current_cols,
                        },
                    }]},
                ).execute()
                print(f"  列数拡張完了")
            break

    # ── ヘッダー更新 ──
    header = rows[0]
    new_headers = {
        23: "content_id",
        24: "Instagram media ID",
        25: "X post ID",
        26: "TikTok post ID",
        27: "created_at",
        28: "updated_at",
    }

    header_updates = []
    for idx, name in new_headers.items():
        current = header[idx] if len(header) > idx else ""
        if current != name:
            header_updates.append((idx, name))

    if header_updates:
        print("ヘッダー追加:")
        for idx, name in header_updates:
            col_letter = ["X", "Y", "Z", "AA", "AB", "AC"][idx - 23]
            print(f"  {col_letter}列(idx={idx}): '{name}'")
    else:
        print("ヘッダー: 変更不要（既に設定済み）")

    # ── content_id バックフィル ──
    backfill = []
    for i, row in enumerate(rows[1:], start=2):
        no_val = row[0] if row else ""
        folder = row[1] if len(row) > 1 else ""
        existing_cid = row[23] if len(row) > 23 else ""
        gen_date = row[8] if len(row) > 8 else ""

        if existing_cid:
            continue  # 既に設定済み

        # A列（No.）から content_id を生成
        try:
            num = int(no_val)
        except (ValueError, TypeError):
            num = i - 1  # No.が取れなければ行順で採番
        cid = f"gachiho_{num:06d}"

        backfill.append({
            "row": i,
            "content_id": cid,
            "folder": folder,
            "gen_date": gen_date,
        })

    print(f"\ncontent_id バックフィル対象: {len(backfill)}行")
    for b in backfill[:10]:
        print(f"  行{b['row']}: {b['content_id']} (folder={b['folder'][:30]})")
    if len(backfill) > 10:
        print(f"  ... 他 {len(backfill) - 10}行")

    if args.dry_run:
        print("\n[dry-run] 書き込みは行いません。")
        return

    # ── 書き込み ──
    data = []

    # ヘッダー
    for idx, name in header_updates:
        col_letter = ["X", "Y", "Z", "AA", "AB", "AC"][idx - 23]
        data.append({"range": f"{sheets.SHEET_NAME}!{col_letter}1", "values": [[name]]})

    # content_id + created_at
    for b in backfill:
        row = b["row"]
        data.append({
            "range": f"{sheets.SHEET_NAME}!{sheets.COL_LETTER['content_id']}{row}",
            "values": [[b["content_id"]]],
        })
        # created_at: 生成日があればその日付のT00:00:00、なければ空
        if b["gen_date"]:
            # "2026/03/15" → "2026-03-15T00:00:00"
            created = b["gen_date"].replace("/", "-") + "T00:00:00"
            data.append({
                "range": f"{sheets.SHEET_NAME}!{sheets.COL_LETTER['created_at']}{row}",
                "values": [[created]],
            })

    if not data:
        print("\n書き込み対象がありません。")
        return

    print(f"\n{len(data)}セルを書き込み中...")
    # batchUpdate は200件まで。それ以上なら分割
    BATCH_SIZE = 200
    for start in range(0, len(data), BATCH_SIZE):
        batch = data[start:start + BATCH_SIZE]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id,
            body={"valueInputOption": "RAW", "data": batch},
        ).execute()

    print(f"完了: ヘッダー{len(header_updates)}列 + content_id {len(backfill)}行をバックフィル")


if __name__ == "__main__":
    main()

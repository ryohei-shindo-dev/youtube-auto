"""
migrate_schedule.py
posting_schedule.json を新スキーマ（platforms対応版）に変換するワンタイムスクリプト。

使い方:
    python migrate_schedule.py           # マイグレーション実行
    python migrate_schedule.py --dry-run # 変換内容を確認するだけ
"""

import argparse
import json
import pathlib
from datetime import datetime

SCRIPT_DIR = pathlib.Path(__file__).parent
SCHEDULE_FILE = SCRIPT_DIR / "posting_schedule.json"
BACKUP_FILE = SCRIPT_DIR / "posting_schedule_backup.json"


def migrate():
    """既存スケジュールに platforms フィールドを追加する。"""
    with open(SCHEDULE_FILE, encoding="utf-8") as f:
        schedule = json.load(f)

    migrated = 0
    for entry in schedule:
        if "platforms" in entry:
            continue  # 既にマイグレーション済み

        entry["platforms"] = {
            "youtube": {
                "published": entry.get("published", False),
                "published_at": entry.get("published_at"),
                "url": None,
                "error": None,
            },
            "tiktok": {
                "published": False,
                "published_at": None,
                "url": None,
                "error": None,
            },
            "instagram": {
                "published": False,
                "published_at": None,
                "url": None,
                "error": None,
            },
        }
        migrated += 1

    return schedule, migrated


def main():
    parser = argparse.ArgumentParser(description="スケジュールのマイグレーション")
    parser.add_argument("--dry-run", action="store_true", help="変換内容を確認するだけ")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  posting_schedule.json マイグレーション")
    print(f"{'='*60}")

    schedule, migrated = migrate()

    print(f"\n  全エントリ: {len(schedule)}本")
    print(f"  マイグレーション対象: {migrated}本")

    if migrated == 0:
        print("  既にマイグレーション済みです。")
        return

    # サンプル表示
    sample = schedule[0]
    print(f"\n  サンプル（Day {sample['day']}）:")
    print(f"    YouTube:   published={sample['platforms']['youtube']['published']}")
    print(f"    TikTok:    published={sample['platforms']['tiktok']['published']}")
    print(f"    Instagram: published={sample['platforms']['instagram']['published']}")

    if args.dry_run:
        print("\n  [dry-run] 書き込みをスキップしました")
        return

    # バックアップ作成
    import shutil
    shutil.copy2(SCHEDULE_FILE, BACKUP_FILE)
    print(f"\n  バックアップ作成: {BACKUP_FILE.name}")

    # 保存
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)

    print(f"  マイグレーション完了！（{migrated}エントリ更新）")


if __name__ == "__main__":
    main()

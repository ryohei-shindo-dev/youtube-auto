"""note_schedule_mixer.py — 予約投稿キューにカテゴリ混合で記事を差し込む。

同じカテゴリが3連続しないよう、カテゴリ間の最小間隔を守りながら
新記事を既存キューに部分挿入する。

Usage:
    # 現在のキューのカテゴリバランスを表示
    python note_schedule_mixer.py --check

    # 新記事を差し込むシミュレーション（ドライラン）
    python note_schedule_mixer.py --insert seo --count 4 --dry-run

    # 実際に差し込み（manifestのスケジュール更新）
    python note_schedule_mixer.py --insert seo --count 4
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timedelta

MANIFEST_PATH = pathlib.Path(__file__).parent / "note_manifest.json"
SCHEDULED_PATH = pathlib.Path(__file__).parent / "scheduled_notes.json"

# --- カテゴリ別制約 ---
# max_consecutive: そのカテゴリの最大連続数
# min_gap: そのカテゴリの次の出現までの最小間隔（枠数）
CATEGORY_RULES = {
    "add":     {"max_consecutive": 2, "min_gap": 0},   # メイン、間隔制限なし
    "ugokite": {"max_consecutive": 2, "min_gap": 4},
    "seo":     {"max_consecutive": 2, "min_gap": 4},
    "ai":      {"max_consecutive": 1, "min_gap": 8},
    "age":     {"max_consecutive": 1, "min_gap": 6},
    "core":    {"max_consecutive": 2, "min_gap": 0},
}

# 全カテゴリ共通: 同カテゴリ最大2連続
MAX_CONSECUTIVE_ANY = 2


def _load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_manifest(manifest: list[dict]):
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _get_category(entry: dict) -> str:
    """manifestエントリからカテゴリを判定する。

    category フィールドがあればそれを使い、
    なければ md_path のプレフィックスから推論する（フォールバック）。
    """
    cat = entry.get("category")
    if cat:
        return cat

    # フォールバック: md_path から推論
    md = entry.get("md_path", "") or ""
    if "ugokite" in md:
        return "ugokite"
    if "add_" in md:
        return "add"
    if "seo_" in md:
        return "seo"
    if "ai_" in md:
        return "ai"
    if "age_" in md:
        return "age"
    return "core"


def _load_scheduled_queue() -> list[dict]:
    """予約投稿キューをmanifest + scheduled_notes.jsonから構築する。"""
    manifest = _load_manifest()
    key_to_entry = {m["note_key"]: m for m in manifest if m.get("note_key")}

    if not SCHEDULED_PATH.exists():
        return []

    data = json.loads(SCHEDULED_PATH.read_text(encoding="utf-8"))
    notes = data.get("notes", data) if isinstance(data, dict) else data
    reserved = [n for n in notes if n.get("status") == "reserved"]

    queue = []
    for n in reserved:
        entry = key_to_entry.get(n["id"])
        cat = _get_category(entry) if entry else "unknown"
        queue.append({
            "note_key": n["id"],
            "title": n.get("title", ""),
            "category": cat,
            "publish_at": n.get("publish_at", ""),
        })

    return queue


def check_balance(queue: list[dict]):
    """キューのカテゴリバランスと連続違反をチェックする。"""
    if not queue:
        print("キューが空です")
        return

    # カテゴリ集計
    cats = {}
    for item in queue:
        c = item["category"]
        cats[c] = cats.get(c, 0) + 1

    total = len(queue)
    print(f"予約投稿キュー: {total}本\n")
    print("カテゴリ比率:")
    for c, count in sorted(cats.items(), key=lambda x: -x[1]):
        pct = count * 100 // total
        print(f"  {c}: {count}本 ({pct}%)")

    # 連続チェック
    violations = []
    for i in range(2, len(queue)):
        if (queue[i]["category"] == queue[i-1]["category"] ==
                queue[i-2]["category"]):
            violations.append(i)

    print(f"\n3連続違反: {len(violations)}箇所")
    for v in violations:
        print(f"  位置{v-2}〜{v}: {queue[v]['category']} — "
              f"{queue[v-2]['title'][:20]} / {queue[v-1]['title'][:20]} / {queue[v]['title'][:20]}")

    # 間隔チェック
    print("\nカテゴリ間隔:")
    for cat, rule in CATEGORY_RULES.items():
        if rule["min_gap"] == 0:
            continue
        positions = [i for i, q in enumerate(queue) if q["category"] == cat]
        if len(positions) < 2:
            continue
        gaps = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
        min_actual = min(gaps)
        ok = "✅" if min_actual >= rule["min_gap"] else f"❌ (最小{min_actual}, 要{rule['min_gap']})"
        print(f"  {cat}: 最小間隔{min_actual} {ok}")


def find_insert_positions(
    queue: list[dict],
    category: str,
    count: int,
) -> list[int]:
    """新カテゴリをcount本挿入する最適位置を返す。

    既存キューを崩さず、制約を満たす位置を貪欲法で選択する。
    """
    rules = CATEGORY_RULES.get(category, {"max_consecutive": 2, "min_gap": 4})
    min_gap = rules["min_gap"]

    # 均等配置の目標位置を計算
    positions = []
    total_len = len(queue) + count  # 挿入後の全体長
    for n in range(count):
        target = int(total_len * (n + 1) / (count + 1))
        positions.append(target)

    # 各位置を制約に合うよう微調整
    final = []
    for target_pos in positions:
        best_pos = None
        best_score = -1

        # 目標位置の前後を探索
        for offset in range(total_len):
            for candidate in [target_pos + offset, target_pos - offset]:
                if candidate < 1 or candidate > len(queue) + len(final):
                    continue

                # 仮挿入して制約チェック
                test_queue = _simulate_insert(queue, final, category, candidate)
                if test_queue is None:
                    continue

                insert_idx = candidate + len(final)
                if not _check_constraints(test_queue, {insert_idx}):
                    continue

                score = 100 - abs(target_pos - candidate)
                if score > best_score:
                    best_score = score
                    best_pos = candidate
                    break  # 最も近い有効位置を採用
            if best_pos is not None:
                break

        if best_pos is not None:
            final.append(best_pos)
        else:
            print(f"  [警告] {len(final)+1}本目の挿入位置が見つかりません")

    return sorted(final)


def _simulate_insert(
    queue: list[dict],
    existing_inserts: list[int],
    category: str,
    new_pos: int,
) -> list[dict] | None:
    """既存キューに挿入をシミュレートして結果のキューを返す。"""
    result = list(queue)
    # 既存の挿入を適用
    for i, pos in enumerate(sorted(existing_inserts)):
        adjusted = pos + i  # 前の挿入でインデックスがずれる
        if adjusted > len(result):
            return None
        result.insert(adjusted, {"category": category, "title": f"[新規{category}]", "note_key": ""})

    # 新しい挿入
    adjusted_new = new_pos + len(existing_inserts)
    if adjusted_new > len(result):
        return None
    result.insert(adjusted_new, {"category": category, "title": f"[新規{category}]", "note_key": ""})

    return result


def _check_constraints(queue: list[dict], new_positions: set[int] | None = None) -> bool:
    """新規挿入位置の制約をチェックする。

    既存キューの制約違反は許容。新規挿入で制約が悪化しないことだけ確認。
    new_positions=None の場合は全体チェック。
    """
    n = len(queue)
    positions_to_check = new_positions or set(range(n))

    for i in positions_to_check:
        if i < 0 or i >= n:
            continue
        cat = queue[i]["category"]
        rules = CATEGORY_RULES.get(cat, {"max_consecutive": MAX_CONSECUTIVE_ANY, "min_gap": 0})

        # 連続チェック: この位置を含む連続数がmax_consecutiveを超えないか
        max_consec = min(rules["max_consecutive"], MAX_CONSECUTIVE_ANY)
        consec = 1
        # 前方
        j = i - 1
        while j >= 0 and queue[j]["category"] == cat:
            consec += 1
            j -= 1
        # 後方
        j = i + 1
        while j < n and queue[j]["category"] == cat:
            consec += 1
            j += 1
        if consec > max_consec:
            return False

        # 間隔チェック: 前後にmin_gap以内に同カテゴリがないか
        if rules["min_gap"] > 0:
            for j in range(1, rules["min_gap"] + 1):
                if i - j >= 0 and queue[i - j]["category"] == cat:
                    return False
                if i + j < n and queue[i + j]["category"] == cat:
                    return False

    return True


def show_queue_with_categories(queue: list[dict]):
    """キューをカテゴリ付きで表示する。"""
    for i, item in enumerate(queue):
        cat = item["category"]
        title = item["title"][:35]
        marker = "🆕" if not item.get("note_key") else "  "
        print(f"  {i+1:2d}. [{cat:8s}] {marker} {title}")


def main():
    parser = argparse.ArgumentParser(description="note予約投稿のカテゴリミキサー")
    parser.add_argument("--check", action="store_true", help="現在のバランスをチェック")
    parser.add_argument("--insert", type=str, help="差し込むカテゴリ名")
    parser.add_argument("--count", type=int, default=4, help="差し込む本数")
    parser.add_argument("--dry-run", action="store_true", help="シミュレーションのみ")
    args = parser.parse_args()

    queue = _load_scheduled_queue()

    if args.check:
        check_balance(queue)
        print("\nキュー一覧:")
        show_queue_with_categories(queue)
        return

    if args.insert:
        cat = args.insert
        count = args.count
        print(f"カテゴリ '{cat}' を {count} 本差し込みます\n")

        positions = find_insert_positions(queue, cat, count)
        if not positions:
            print("差し込み位置が見つかりませんでした")
            sys.exit(1)

        print(f"差し込み位置: {positions}")

        # シミュレート結果を表示
        result = list(queue)
        for i, pos in enumerate(positions):
            adjusted = pos + i
            result.insert(adjusted, {
                "category": cat,
                "title": f"[新規 {cat}]",
                "note_key": "",
            })

        print(f"\n混合後のキュー ({len(result)}本):")
        show_queue_with_categories(result)

        # バランスチェック
        print()
        check_balance(result)

        if args.dry_run:
            print("\n[ドライラン] 実際の変更はしません")
        else:
            print("\n差し込み位置が確定しました。")
            print("実際の予約投稿は note_publish_additional.py で行ってください。")

        return

    # デフォルト: チェック
    check_balance(queue)


if __name__ == "__main__":
    main()

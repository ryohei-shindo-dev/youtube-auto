"""note_schedule_mixer.py — note記事の投稿順をカテゴリバランスで自動計画する。

同じカテゴリが連続しないよう制約を守りながら、
未投稿記事の投稿順と予約日時を自動計算し、note_publish_queue.json に出力する。

Usage:
    # 現在の予約キューのカテゴリバランスを確認
    python note_schedule_mixer.py check

    # 未投稿記事の投稿計画をプレビュー
    python note_schedule_mixer.py plan --dry-run

    # 投稿計画を note_publish_queue.json に保存（件数指定可）
    python note_schedule_mixer.py plan --write --count 12

    # 開始日時を明示指定（予約キューの末尾日時が不明な場合）
    python note_schedule_mixer.py plan --write --start-after "2026-04-01 21:00"
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = pathlib.Path(__file__).parent
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"
SCHEDULED_PATH = SCRIPT_DIR / "scheduled_notes.json"
PUBLISH_QUEUE_PATH = SCRIPT_DIR / "note_publish_queue.json"

# デフォルトのマガジン・タグ（note_ops.py と同じ値）
DEFAULT_MAGAZINE = "こつこつ積み立てを続ける人の読みもの"
DEFAULT_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]

# --- theme別制約（ミキサー用） ---
CATEGORY_RULES = {
    "tsumitate":  {"max_consecutive": 2, "min_gap": 1},
    "comparison": {"max_consecutive": 2, "min_gap": 2},
    "loss_drop":  {"max_consecutive": 2, "min_gap": 2},
    "sell_exit":  {"max_consecutive": 1, "min_gap": 3},
    "sns_mind":   {"max_consecutive": 2, "min_gap": 2},
    "life_plan":  {"max_consecutive": 1, "min_gap": 4},
    "ai_support": {"max_consecutive": 1, "min_gap": 6},
}

MAX_CONSECUTIVE_ANY = 2

# 1日2本の投稿スロット
TIME_SLOTS = ["12:30", "21:00"]

# カテゴリ別の時間帯優先度（優先度であり固定ではない）
CATEGORY_TIME_PREF: dict[str, str] = {
    "tsumitate":  "21:00",   # 感情整理 → 夜
    "comparison": "21:00",
    "loss_drop":  "21:00",
    "sell_exit":  "21:00",
    "sns_mind":   "21:00",
    "life_plan":  "12:30",   # 制度・計画系 → ランチタイム
    "ai_support": "12:30",   # 検索流入 → ランチタイム
}

# カテゴリの日本語ラベル（表示用）
CATEGORY_LABELS = {
    "tsumitate": "積み立て継続・複利",
    "comparison": "商品比較・分散投資",
    "loss_drop": "含み損・暴落",
    "sell_exit": "売却・離脱・やめたい",
    "sns_mind": "SNS焦り・確認癖",
    "life_plan": "老後・年齢不安",
    "ai_support": "AI整理記事",
    "family": "家族・パートナー",
    "saving_balance": "投資と節約",
}


# ── データ読み込み ──

def _load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _get_category(entry: dict) -> str:
    """manifestエントリからカテゴリを判定する。

    category フィールドがあればそれを使い、
    なければ md_path のプレフィックスから推論する（フォールバック）。
    """
    # ミキサーは theme を使う
    theme = entry.get("theme")
    if theme:
        return theme

    # フォールバック: md_path から推論
    md = entry.get("md_path", "") or ""
    if "ai_" in md:
        return "ai_support"
    if "ugokite" in md:
        return "sell_exit"
    return "tsumitate"


def _get_unpublished_articles() -> list[dict]:
    """manifestから未投稿かつ未計画の記事を抽出する。

    未投稿 = md_path がある + sheet_title がある + url が空 + note_key が空
    未計画 = publish_queue に planned/processing として存在しない
    """
    manifest = _load_manifest()

    # 既存キューで計画済みの sheet_no を除外
    already_queued: set[int] = set()
    if PUBLISH_QUEUE_PATH.exists():
        queue = json.loads(PUBLISH_QUEUE_PATH.read_text(encoding="utf-8"))
        for q in queue:
            if q.get("status") in ("planned", "processing"):
                already_queued.add(q.get("sheet_no"))

    unpublished = []
    for entry in manifest:
        md = entry.get("md_path")
        title = entry.get("sheet_title")
        url = entry.get("url")
        key = entry.get("note_key")
        if md and title and not url and not key:
            if entry["sheet_no"] not in already_queued:
                unpublished.append(entry)
    return unpublished


def _get_last_scheduled_datetime() -> datetime | None:
    """scheduled_notes.json から最後の予約日時を取得する。

    publish_at が全て空の場合は None を返す。
    """
    if not SCHEDULED_PATH.exists():
        return None

    data = json.loads(SCHEDULED_PATH.read_text(encoding="utf-8"))
    notes = data.get("notes", data) if isinstance(data, dict) else data
    reserved = [n for n in notes if n.get("status") == "reserved"]

    dates = []
    for n in reserved:
        pa = n.get("publish_at", "")
        if pa:
            try:
                dates.append(datetime.strptime(pa[:16], "%Y-%m-%d %H:%M"))
            except ValueError:
                pass

    return max(dates) if dates else None


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


# ── 制約チェック ──

def _check_constraints_at(queue: list[dict], pos: int) -> bool:
    """キュー内の指定位置が制約を満たすか確認する。"""
    n = len(queue)
    if pos < 0 or pos >= n:
        return True

    cat = queue[pos]["category"]
    rules = CATEGORY_RULES.get(cat, {"max_consecutive": MAX_CONSECUTIVE_ANY, "min_gap": 0})

    # 連続チェック
    max_consec = min(rules["max_consecutive"], MAX_CONSECUTIVE_ANY)
    consec = 1
    j = pos - 1
    while j >= 0 and queue[j]["category"] == cat:
        consec += 1
        j -= 1
    j = pos + 1
    while j < n and queue[j]["category"] == cat:
        consec += 1
        j += 1
    if consec > max_consec:
        return False

    # 間隔チェック
    if rules["min_gap"] > 0:
        for j in range(1, rules["min_gap"] + 1):
            if pos - j >= 0 and queue[pos - j]["category"] == cat:
                return False
            if pos + j < n and queue[pos + j]["category"] == cat:
                return False

    return True


# ── 計画アルゴリズム ──

def _score_candidate(
    cat: str,
    queue_so_far: list[dict],
    slot_time: str,
    cat_remaining: dict[str, int],
    total_remaining: int,
    slots_left: int,
) -> float:
    """候補カテゴリのスコアを計算する。

    スコアが高いほど次のスロットに適している。
    -1000 は制約違反（配置不可）。
    """
    # 仮に末尾に追加して制約チェック
    test_queue = queue_so_far + [{"category": cat}]
    if not _check_constraints_at(test_queue, len(test_queue) - 1):
        return -1000

    score = 0.0
    remaining = cat_remaining.get(cat, 0)
    rules = CATEGORY_RULES.get(cat, {"max_consecutive": MAX_CONSECUTIVE_ANY, "min_gap": 0})
    min_gap = rules.get("min_gap", 0)

    # 在庫消化の緊急度: min_gap が大きいカテゴリほど早く消化すべき
    # （後回しにすると末尾で制約違反になる）
    if min_gap > 0 and remaining > 0 and slots_left > 0:
        # 残りスロットで消化可能か？ 各出現に min_gap 分の間隔が必要
        slots_needed = remaining + (remaining - 1) * min_gap
        if slots_needed >= slots_left:
            score += 50  # 緊急: 今置かないと間に合わない

    # 在庫が多いカテゴリを優先（均等消化）
    score += remaining * 2

    # 直前と違うカテゴリならボーナス
    if queue_so_far and queue_so_far[-1]["category"] != cat:
        score += 20

    # 時間帯マッチボーナス
    pref = CATEGORY_TIME_PREF.get(cat, "")
    if pref == slot_time:
        score += 10

    return score


def _next_slot(last_dt: datetime, slot_index: int) -> tuple[datetime, str, int]:
    """次の投稿スロット（日時 + 時刻文字列 + 次のインデックス）を返す。"""
    time_str = TIME_SLOTS[slot_index % len(TIME_SLOTS)]
    h, m = map(int, time_str.split(":"))

    if slot_index % len(TIME_SLOTS) == 0:
        # 新しい日の最初のスロット → 翌日
        dt = last_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if dt <= last_dt:
            dt += timedelta(days=1)
    else:
        # 同日の2つ目のスロット
        dt = last_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if dt <= last_dt:
            dt += timedelta(days=1)

    return dt, time_str, slot_index + 1


def plan_queue(
    unpublished: list[dict],
    start_after: datetime,
    count: int | None = None,
) -> list[dict]:
    """未投稿記事をカテゴリバランスで並べ、予約日時を付与する。

    Returns:
        publish_queue エントリのリスト
    """
    if not unpublished:
        return []

    # カテゴリ別にグルーピング
    by_cat: dict[str, list[dict]] = {}
    for entry in unpublished:
        cat = _get_category(entry)
        by_cat.setdefault(cat, []).append(entry)

    # 残り在庫数
    cat_remaining = {cat: len(articles) for cat, articles in by_cat.items()}
    total_available = sum(cat_remaining.values())

    if count is not None:
        total_to_plan = min(count, total_available)
    else:
        total_to_plan = total_available

    # 配置可能性チェック: min_gap があるカテゴリが全スロットに収まるか
    for cat, remaining in cat_remaining.items():
        if remaining <= 1:
            continue
        rules = CATEGORY_RULES.get(cat, {"min_gap": 0})
        gap = rules.get("min_gap", 0)
        if gap > 0:
            slots_needed = remaining + (remaining - 1) * gap
            if slots_needed > total_to_plan:
                print(f"  [注意] {cat} {remaining}本を間隔{gap}で配置するには"
                      f"{slots_needed}スロット必要（全体{total_to_plan}スロット）"
                      f" → 末尾で間隔が詰まる可能性があります")

    # 貪欲法で1本ずつ選択
    queue_so_far: list[dict] = []  # カテゴリだけ持つ軽量キュー（制約チェック用）
    planned: list[dict] = []       # 出力用の完全なエントリ
    current_dt = start_after

    # 最初のスロットインデックスを決定
    if start_after.hour < 12 or (start_after.hour == 12 and start_after.minute < 30):
        slot_idx = 0  # 12:30 から
    elif start_after.hour < 21:
        slot_idx = 1  # 21:00 から
    else:
        slot_idx = 0  # 翌日 12:30 から

    for _ in range(total_to_plan):
        # 次のスロットを計算
        current_dt, slot_time, slot_idx = _next_slot(current_dt, slot_idx)
        schedule_str = current_dt.strftime("%Y-%m-%d") + " " + slot_time

        # 各カテゴリのスコアを計算
        best_cat = None
        best_score = -2000
        remaining_total = sum(cat_remaining.values())
        slots_left = total_to_plan - len(planned)

        for cat in sorted(by_cat.keys()):
            if cat_remaining.get(cat, 0) <= 0:
                continue
            score = _score_candidate(
                cat, queue_so_far, slot_time, cat_remaining,
                remaining_total, slots_left,
            )
            if score > best_score:
                best_score = score
                best_cat = cat

        if best_cat is None or best_score <= -1000:
            # 制約を満たせるカテゴリがない → どれかを無理に置く
            for cat in sorted(by_cat.keys()):
                if cat_remaining.get(cat, 0) > 0:
                    best_cat = cat
                    break

        if best_cat is None:
            break

        # そのカテゴリから1本取り出す
        article = by_cat[best_cat].pop(0)
        cat_remaining[best_cat] -= 1

        queue_so_far.append({"category": best_cat})

        # タグの決定
        tags = list(DEFAULT_TAGS)
        if article.get("tags"):
            tag_mode = article.get("tag_mode", "merge")
            if tag_mode == "replace":
                tags = list(article["tags"])
            else:  # merge
                for t in article["tags"]:
                    if t not in tags:
                        tags.append(t)

        planned.append({
            "sheet_no": article["sheet_no"],
            "note_key": None,
            "title": article["sheet_title"],
            "category": best_cat,
            "magazine": article.get("magazine") or DEFAULT_MAGAZINE,
            "tags": tags,
            "md_path": article.get("md_path"),
            "image_path": article.get("image_path"),
            "schedule_at": schedule_str,
            "status": "planned",
            "last_step": None,
            "attempts": 0,
            "last_error": None,
        })

    return planned


# ── 表示 ──

def check_balance(queue: list[dict]):
    """キューのカテゴリバランスと連続違反をチェックする。"""
    if not queue:
        print("キューが空です")
        return

    cats: dict[str, int] = {}
    for item in queue:
        c = item["category"]
        cats[c] = cats.get(c, 0) + 1

    total = len(queue)
    print(f"予約投稿キュー: {total}本\n")
    print("カテゴリ比率:")
    for c, count in sorted(cats.items(), key=lambda x: -x[1]):
        pct = count * 100 // total
        label = CATEGORY_LABELS.get(c, c)
        print(f"  {c}: {count}本 ({pct}%) — {label}")

    # 連続チェック
    violations = []
    for i in range(2, len(queue)):
        if (queue[i]["category"] == queue[i-1]["category"] ==
                queue[i-2]["category"]):
            violations.append(i)

    print(f"\n3連続違反: {len(violations)}箇所")
    for v in violations:
        title_key = "title" if "title" in queue[v] else "sheet_title"
        print(f"  位置{v-2}〜{v}: {queue[v]['category']}")

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


def show_queue_with_categories(queue: list[dict]):
    """キューをカテゴリ付きで表示する。"""
    for i, item in enumerate(queue):
        cat = item["category"]
        title = (item.get("title") or item.get("sheet_title") or "")[:35]
        schedule = item.get("schedule_at") or item.get("publish_at") or ""
        print(f"  {i+1:2d}. [{cat:8s}] {schedule:16s} {title}")


def show_plan(planned: list[dict]):
    """計画をプレビュー表示する。"""
    if not planned:
        print("計画対象の未投稿記事がありません")
        return

    print(f"投稿計画: {len(planned)}本\n")

    # カテゴリ集計
    cats: dict[str, int] = {}
    for p in planned:
        c = p["category"]
        cats[c] = cats.get(c, 0) + 1

    print("カテゴリ内訳:")
    for c, count in sorted(cats.items(), key=lambda x: -x[1]):
        label = CATEGORY_LABELS.get(c, c)
        print(f"  {c}: {count}本 — {label}")

    print(f"\nスケジュール:")
    for i, p in enumerate(planned):
        cat = p["category"]
        title = p["title"][:40]
        schedule = p["schedule_at"]
        print(f"  {i+1:2d}. [{cat:8s}] {schedule} {title}")

    # 期間
    first = planned[0]["schedule_at"]
    last = planned[-1]["schedule_at"]
    print(f"\n期間: {first} 〜 {last}")


# ── CLI ──

def cmd_check(args):
    """予約キューのカテゴリバランスを確認する。"""
    queue = _load_scheduled_queue()
    check_balance(queue)
    print("\nキュー一覧:")
    show_queue_with_categories(queue)


def cmd_plan(args):
    """未投稿記事の投稿計画を作成する。"""
    # 未投稿記事を取得
    unpublished = _get_unpublished_articles()
    if not unpublished:
        print("未投稿の記事がありません")
        print("（manifest に md_path があり url/note_key が空のエントリが対象）")
        return

    print(f"未投稿記事: {len(unpublished)}本\n")

    # カテゴリ内訳を表示
    cats: dict[str, int] = {}
    for entry in unpublished:
        c = _get_category(entry)
        cats[c] = cats.get(c, 0) + 1
    print("カテゴリ内訳:")
    for c, count in sorted(cats.items(), key=lambda x: -x[1]):
        label = CATEGORY_LABELS.get(c, c)
        print(f"  {c}: {count}本 — {label}")
    print()

    # 開始日時の決定
    if args.start_after:
        start_after = datetime.strptime(args.start_after, "%Y-%m-%d %H:%M")
    else:
        start_after = _get_last_scheduled_datetime()
        if start_after is None:
            print("[警告] scheduled_notes.json に予約日時がありません")
            print("       --start-after で開始日時を指定してください")
            print('  例: python note_schedule_mixer.py plan --start-after "2026-04-01 21:00"')
            return

    print(f"開始基準: {start_after.strftime('%Y-%m-%d %H:%M')} の次のスロットから")

    # 計画作成
    planned = plan_queue(unpublished, start_after, args.count)

    if not planned:
        print("計画を作成できませんでした")
        return

    print()
    show_plan(planned)

    # バランスチェック
    print()
    check_balance(planned)

    if args.write:
        PUBLISH_QUEUE_PATH.write_text(
            json.dumps(planned, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n✅ {PUBLISH_QUEUE_PATH.name} に保存しました（{len(planned)}本）")
    else:
        print("\n[プレビュー] --write を付けると note_publish_queue.json に保存します")


def main():
    parser = argparse.ArgumentParser(
        description="note予約投稿のカテゴリミキサー",
    )
    sub = parser.add_subparsers(dest="command")

    # check
    sub.add_parser("check", help="予約キューのカテゴリバランスを確認")

    # plan
    p_plan = sub.add_parser("plan", help="未投稿記事の投稿計画を作成")
    p_plan.add_argument("--count", type=int, help="計画する本数（省略時は全件）")
    p_plan.add_argument("--write", action="store_true",
                        help="note_publish_queue.json に保存")
    p_plan.add_argument("--dry-run", action="store_true",
                        help="プレビューのみ（--write なしと同じ）")
    p_plan.add_argument("--start-after", type=str,
                        help='開始基準日時 (例: "2026-04-01 21:00")')

    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "plan":
        cmd_plan(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

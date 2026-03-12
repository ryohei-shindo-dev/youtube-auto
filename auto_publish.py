"""
auto_publish.py
投稿管理シートを正本として、YouTube Shorts / TikTok / Instagram Reels / X を自動投稿する。

データソース:
    Google Sheets「投稿管理」シート（唯一の管理元）
    B列のフォルダ名をキーに done/{フォルダ名}/ から動画を取得

使い方:
    python auto_publish.py                                    # 次の未投稿動画を自動投稿
    python auto_publish.py --dry-run                          # 投稿せずに確認だけ
    python auto_publish.py --force 5                          # No.5 を強制投稿
    python auto_publish.py --private                          # 非公開で投稿（テスト用）
    python auto_publish.py --platforms youtube tiktok         # 指定プラットフォームのみ
    python auto_publish.py --retry-failed                     # 失敗したプラットフォームだけ再投稿

cron設定例（プラットフォーム別に時間をずらして投稿）:
    0 7 * * *  cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms youtube
    30 7 * * * cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms x
    0 12 * * * cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms instagram
    0 19 * * * cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms youtube
    30 19 * * * cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms x
    0 21 * * * cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms instagram
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

SCRIPT_DIR = pathlib.Path(__file__).parent
DONE_DIR = SCRIPT_DIR / "done"
LOG_DIR = SCRIPT_DIR / "logs"

# ── hook 近接チェック用定義 ──
# stock_scorer.py からもインポートされる（hook定義の正本）

# hook カテゴリ定義（部分一致キーワード → カテゴリ名）
HOOK_CATEGORIES: dict[str, list[str]] = {
    "含み損系": ["含み損", "損", "元本割れ", "目減り", "負け"],
    "暴落系": ["暴落", "退場"],
    "売りたい系": ["売りたい", "利確", "動き"],
    "比較焦り系": ["焦", "比べ", "爆益", "差がない", "毎日見"],
    "増えてない系": ["増え", "待て", "続かない", "続け"],
    "積立疲れ系": ["積立", "つらい", "やめ", "疲れ", "向いてな"],
    "不安系": ["不安", "怖い", "円高", "不確実"],
    "後悔系": ["使った", "売った", "やめた", "待った", "比べた", "できなかった"],
    "出口不安系": ["いつ売る", "取り崩し", "老後", "65歳"],
    "制度金額系": ["1800万", "新NISA", "100万", "iDeCo"],
    "機会損失系": ["買っておけば", "待ちすぎ", "現金のまま", "乗り遅れ"],
    "継続肯定系": ["続けて", "十分", "褒め", "正解", "そのまま", "変えなかった", "進んで"],
}

# hookステム一覧（カテゴリキーワードをフラット化）
HOOK_STEMS = sorted(
    {kw for keywords in HOOK_CATEGORIES.values() for kw in keywords},
    key=len, reverse=True,  # 長いキーワードを先にマッチ
)

# stem → category のマッピング
STEM_TO_CATEGORY: dict[str, str] = {}
for _cat_name, _kws in HOOK_CATEGORIES.items():
    for _kw in _kws:
        STEM_TO_CATEGORY[_kw] = _cat_name

# 近接制約: 同じステムは直近N本以内に出さない（売りたい系は特に多いため広めに）
_STEM_PROXIMITY = 8
# 近接制約: 同じカテゴリは直近N本以内に出さない
_CATEGORY_PROXIMITY = 5


def _read_hook_text(folder_name: str) -> str:
    """done/{folder}/transcript.json から hook テキストを取得する。"""
    path = DONE_DIR / folder_name / "transcript.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for s in data.get("scenes", []):
            if s.get("role") == "hook":
                return s.get("text", "")
    except (json.JSONDecodeError, OSError):
        pass
    return ""


def extract_hook_stem(hook_text: str) -> str:
    """hook テキストから句読点を除去し、既知ステムに一致するものを返す。"""
    cleaned = hook_text.rstrip("。？！?! ")
    for stem in HOOK_STEMS:
        if stem in cleaned:
            return stem
    return cleaned[:3] if cleaned else "不明"


def extract_hook_category(hook_text: str) -> str:
    """hook テキストからカテゴリを判定する。"""
    cleaned = hook_text.rstrip("。？！?! ")
    for stem, cat in STEM_TO_CATEGORY.items():
        if stem in cleaned:
            return cat
    return "その他"


def _get_recent_published_hooks(rows: list, limit: int = 7) -> list[dict]:
    """公開済みエントリから直近N件のhook情報を取得する（pub_date降順）。"""
    import sheets
    C = sheets.COL
    published = []
    for row in rows[1:]:
        status = sheets.get_cell(row, C["status"])
        if status != sheets.STATUS_PUBLISHED:
            continue
        folder = sheets.get_cell(row, C["folder"])
        pub_date = sheets.get_cell(row, C["pub_date"])
        if not folder:
            continue
        published.append({"folder": folder, "pub_date": pub_date})

    # pub_date 降順でソートし、直近 limit 件を取得
    published.sort(key=lambda e: e["pub_date"], reverse=True)
    recent = published[:limit]

    # 各エントリに hook 情報を付加
    result = []
    for entry in recent:
        hook_text = _read_hook_text(entry["folder"])
        if hook_text:
            entry["hook_text"] = hook_text
            entry["hook_stem"] = extract_hook_stem(hook_text)
            entry["hook_category"] = extract_hook_category(hook_text)
            result.append(entry)
    return result

ALL_PLATFORMS = ["youtube", "tiktok", "instagram", "x"]
DEFAULT_PLATFORMS = ["youtube", "instagram", "x"]
X_HANDLE = "gachiho_motive"

# プラットフォーム名 → _row_to_entry() のURLキー
_PLATFORM_URL_KEYS = {
    "youtube": "youtube_url",
    "instagram": "instagram_url",
    "x": "x_url",
    "tiktok": "tiktok_url",
}

# Shorts タイトル用サフィックス（ランダムで選択）
_TITLE_SUFFIXES = [
    "長期投資",
    "積立投資",
    "ガチホの真実",
    "インデックス投資",
    "NISA",
    "資産形成",
]

# プラットフォーム別ハッシュタグ
_YT_HASHTAGS = "#長期投資 #積立投資 #NISA #資産形成 #ガチホ"
_TT_HASHTAGS = "#長期投資 #積立投資 #NISA #資産形成 #ガチホ #投資初心者 #お金の勉強 #fyp"
_IG_HASHTAGS = "#長期投資 #積立投資 #NISA #資産形成 #ガチホ #投資 #お金 #reels #リール"


YOUTUBE_TITLE_MAX_LENGTH = 100


def _pick_suffix(raw_title: str) -> tuple[str, str]:
    """元タイトルの句読点を除去し、重複しないサフィックスを選ぶ。"""
    front = raw_title.rstrip("。、！？ ")
    available = [s for s in _TITLE_SUFFIXES if s not in front]
    suffix = random.choice(available or _TITLE_SUFFIXES)
    return front, suffix


def _optimize_title(raw_title: str, meta: dict) -> str:
    """Shorts最適タイトルに変換する。

    元のタイトルをそのまま活かし、サフィックスを付ける。
    形式: 元タイトル｜投資キーワード #Shorts
    例: 暴落で売った人が後悔している理由｜長期投資 #Shorts
    """
    front, suffix = _pick_suffix(raw_title)
    suffix_part = f"｜{suffix} #Shorts"
    if len(front) + len(suffix_part) > YOUTUBE_TITLE_MAX_LENGTH:
        front = front[:YOUTUBE_TITLE_MAX_LENGTH - len(suffix_part)]
    return f"{front}{suffix_part}"


_YT_FOOTER = (
    "▼ 他のプラットフォーム\n"
    "note（深掘り記事）: https://note.com/gachiho_motive\n"
    "X: https://x.com/gachiho_motive\n"
    "Instagram: https://www.instagram.com/gachiho_motive/"
)


def _optimize_description(raw_description: str, raw_title: str) -> str:
    """YouTube用の説明文を生成する。"""
    lines = [raw_title, ""]
    if raw_description:
        lines.append(raw_description)
        lines.append("")
    lines.append(_YT_HASHTAGS)
    lines.append("")
    lines.append(_YT_FOOTER)
    return "\n".join(lines)


def _optimize_tiktok_title(raw_title: str, meta: dict) -> str:
    """TikTok用のタイトル（投稿テキスト）を生成する。"""
    front, suffix = _pick_suffix(raw_title)
    return f"{front}｜{suffix}"


def _optimize_instagram_caption(raw_title: str, meta: dict) -> str:
    """Instagram用のキャプションを生成する。"""
    front, suffix = _pick_suffix(raw_title)
    return f"{front}｜{suffix}\n\n{_IG_HASHTAGS}"


def _build_x_text_from_transcript(meta: dict) -> str:
    """transcript.json からXポスト用テキストを生成する（social_captions.json がない場合の代替）。"""
    from social_gen import _strip_connector, X_HASHTAGS

    scenes = {s.get("role", ""): s.get("text", "") for s in meta.get("scenes", [])}
    hook = scenes.get("hook", "").rstrip("。")
    data = _strip_connector(scenes.get("data", ""))
    resolve = _strip_connector(scenes.get("resolve", ""))

    hashtag_str = " ".join(f"#{t}" for t in X_HASHTAGS)
    lines = [hook, "", "でも", data, "", resolve, "", hashtag_str]
    return "\n".join(lines)


# ── シートからエントリを取得する関数群 ──

def _read_sheet_rows() -> list[list[str]]:
    """投稿管理シートの全行を取得する（A列〜N列）。"""
    import sheets
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        return []
    svc = sheets.get_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="投稿管理!A:N",
    ).execute()
    return result.get("values", [])


def _row_to_entry(row: list, sheet_row: int) -> dict:
    """シートの行データをエントリdictに変換する。"""
    import sheets
    C = sheets.COL
    return {
        "row": sheet_row,
        "no": sheets.get_cell(row, C["no"]),
        "folder": sheets.get_cell(row, C["folder"]),
        "type": sheets.get_cell(row, C["type"]),
        "title": sheets.get_cell(row, C["title"]),
        "status": sheets.get_cell(row, C["status"]),
        "gen_date": sheets.get_cell(row, C["gen_date"]),
        "youtube_url": sheets.get_cell(row, C["youtube_url"]),
        "instagram_url": sheets.get_cell(row, C["instagram_url"]),
        "x_url": sheets.get_cell(row, C["x_url"]),
        "tiktok_url": sheets.get_cell(row, C["tiktok_url"]),
    }


def _sort_by_score(entries: list) -> list:
    """台本スコア降順（高スコア優先）でソートする。スコア不明は末尾に回す。"""
    import candidate_ranker

    scored = []
    for entry in entries:
        transcript_path = DONE_DIR / entry["folder"] / "transcript.json"
        try:
            script_data = json.loads(transcript_path.read_text(encoding="utf-8"))
            result = candidate_ranker.score_script(script_data)
            score = result.get("total_score", 0)
        except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError):
            score = -1  # スコア不明は最後尾
        entry["_score"] = score
        scored.append(entry)

    scored.sort(key=lambda c: (-c["_score"], c["gen_date"]))
    if scored and scored[0]["_score"] >= 0:
        print(f"  [公開順] スコア順を使用（最高: {scored[0]['_score']}点）")
    else:
        print(f"  [公開順] 生成日順を使用（スコア情報なし）")
    return scored


def get_next_publishable(rows: list | None = None, platforms: list | None = None) -> dict | None:
    """シートから次に投稿すべき動画を取得する。

    1. 部分投稿済み（G=公開済みだが指定プラットフォームのURLが空）を優先
       → 同じ動画が全プラットフォームに揃ってから次の動画に進む
    2. 該当がなければ、G=生成済み（まだどこにも投稿していない）を選択
    """
    import sheets
    if rows is None:
        rows = _read_sheet_rows()
    if platforms is None:
        platforms = list(DEFAULT_PLATFORMS)

    generated = []
    partial = []
    for i, row in enumerate(rows[1:], start=2):
        entry = _row_to_entry(row, i)
        if not entry["folder"]:
            continue
        if entry["status"] == sheets.STATUS_GENERATED:
            generated.append(entry)
        elif entry["status"] == sheets.STATUS_PUBLISHED:
            # 指定プラットフォームのURLが空なら投稿が必要
            missing = [p for p in platforms if not entry.get(_PLATFORM_URL_KEYS.get(p, ""))]
            if missing:
                partial.append(entry)

    # 部分投稿済み（他プラットフォームは済みだが指定プラットフォームが未投稿）を優先。
    # これにより YouTube→X→Instagram の時間差投稿で同じ動画が順番に全プラットフォームに投稿される。
    if partial:
        partial.sort(key=lambda c: c["gen_date"])
        return partial[0]
    if not generated:
        return None

    # publish_queue.json があればその順序を優先、なければスコア順
    queue_path = SCRIPT_DIR / "publish_queue.json"
    try:
        queue_order = json.loads(queue_path.read_text(encoding="utf-8"))
        queue_index = {folder: idx for idx, folder in enumerate(queue_order)}
        generated.sort(key=lambda c: queue_index.get(c["folder"], 999999))
        print(f"  [公開順] publish_queue.json の最適順を使用（{len(queue_order)}本）")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        generated = _sort_by_score(generated)

    # hook 近接チェック: 直近の公開済み動画とhookが被らない候補を優先選択
    recent_hooks = _get_recent_published_hooks(rows)

    if not recent_hooks:
        # 公開済みがなければ近接チェック不要 → 最古の候補を返す
        return generated[0]

    recent_stems = [h["hook_stem"] for h in recent_hooks[:_STEM_PROXIMITY]]
    recent_categories = [h["hook_category"] for h in recent_hooks[:_CATEGORY_PROXIMITY]
                         if h["hook_category"]]

    best_fallback = None
    best_fallback_recency = -1  # ステムの最終出現位置（大きいほど古い＝良い）

    for candidate in generated:
        hook_text = _read_hook_text(candidate["folder"])
        if not hook_text:
            # hook が取得できない場合はチェックをスキップして候補として返す
            return candidate

        c_stem = extract_hook_stem(hook_text)
        c_category = extract_hook_category(hook_text)

        # ステム近接チェック
        stem_conflict = c_stem in recent_stems
        # カテゴリ近接チェック
        category_conflict = c_category and c_category in recent_categories

        if not stem_conflict and not category_conflict:
            print(f"  [hook近接] ✓ hook「{hook_text.rstrip('。？！')}」は直近と被りなし")
            return candidate

        # フォールバック用: ステムの最終出現位置が最も古い候補を記録
        if c_stem in recent_stems:
            # recent_stems のインデックス（0が最新、大きいほど古い）
            recency = recent_stems.index(c_stem)
        else:
            recency = len(recent_stems)  # ステムは被ってない（カテゴリだけ被り）

        if recency > best_fallback_recency:
            best_fallback_recency = recency
            best_fallback = candidate

    # 全候補が近接制約に引っかかった場合 → 最も古いステムの候補を選択
    chosen = best_fallback or generated[0]
    print(f"  [hook近接] △ 全候補が近接制約に該当。フォールバック候補を選択")
    return chosen


def get_entry_by_no(no: int) -> dict | None:
    """A列のNo.でエントリを検索する。"""
    rows = _read_sheet_rows()
    import sheets
    for i, row in enumerate(rows[1:], start=2):
        no_str = sheets.get_cell(row, 0)
        if no_str.isdigit() and int(no_str) == no:
            return _row_to_entry(row, i)
    return None


def _get_retry_platforms(entry: dict, allowed_platforms: list) -> list:
    """URLが空のプラットフォームを返す（再投稿対象）。"""
    failed = []
    for p in allowed_platforms:
        key = _PLATFORM_URL_KEYS.get(p)
        if key and not entry.get(key):
            failed.append(p)
    return failed


def get_remaining_count(rows: list | None = None) -> int:
    """生成済みで未投稿の動画数を返す。"""
    import sheets
    if rows is None:
        rows = _read_sheet_rows()
    count = 0
    for row in rows[1:]:
        status = sheets.get_cell(row, sheets.COL["status"])
        if status == sheets.STATUS_GENERATED:
            count += 1
    return count


def publish_entry(
    entry: dict,
    privacy: str = "public",
    dry_run: bool = False,
    platforms: list = None,
) -> dict:
    """
    1本の動画を各プラットフォームに投稿する。

    Returns:
        {"youtube": True/False, "tiktok": True/False, "instagram": True/False, "x": True/False}
    """
    if platforms is None:
        platforms = list(ALL_PLATFORMS)

    folder = DONE_DIR / entry["folder"]
    video_path = folder / "output.mp4"
    thumbnail_path = folder / "thumbnail.png"
    transcript_path = folder / "transcript.json"

    if not video_path.exists():
        print(f"  [エラー] 動画ファイルが見つかりません: {video_path}")
        return {p: False for p in platforms}

    if not transcript_path.exists():
        print(f"  [エラー] transcript.jsonが見つかりません: {transcript_path}")
        return {p: False for p in platforms}

    # メタデータ読み込み
    with open(transcript_path, encoding="utf-8") as f:
        meta = json.load(f)

    raw_title = meta.get("title", "")
    raw_description = meta.get("description", "")
    tags = meta.get("tags", [])

    # プラットフォーム別に最適化されたテキスト
    yt_title = _optimize_title(raw_title, meta)
    yt_description = _optimize_description(raw_description, raw_title)
    tt_title = _optimize_tiktok_title(raw_title, meta)
    ig_caption = _optimize_instagram_caption(raw_title, meta)

    print(f"\n{'='*60}")
    print(f"  No.{entry['no']}: {raw_title[:40]}")
    print(f"  フォルダ: {entry['folder']}")
    print(f"  動画: {video_path}")
    print(f"  公開設定: {privacy}")
    print(f"  プラットフォーム: {', '.join(platforms)}")
    print(f"{'='*60}")

    if dry_run:
        print("  [dry-run] 投稿をスキップしました")
        if "youtube" in platforms:
            print(f"    YouTube: {yt_title}")
        if "tiktok" in platforms:
            print(f"    TikTok:  {tt_title}")
        if "instagram" in platforms:
            print(f"    Instagram: {ig_caption[:50]}...")
        if "x" in platforms:
            social_path = folder / "social_captions.json"
            try:
                with open(social_path, encoding="utf-8") as f:
                    social_data = json.load(f)
                x_preview = social_data.get("x", {}).get("shorts_post", "")[:50]
            except FileNotFoundError:
                x_preview = _build_x_text_from_transcript(meta)[:50]
            print(f"    X: {x_preview}...")
        return {p: True for p in platforms}

    results = {}
    urls = {}

    # --- YouTube ---
    if "youtube" in platforms:
        try:
            print("\n  [YouTube] 投稿中...")
            import youtube_upload
            video_id = youtube_upload.upload_video(
                video_path=str(video_path),
                title=yt_title,
                description=yt_description,
                tags=tags,
                privacy=privacy,
                thumbnail_path=str(thumbnail_path) if thumbnail_path.exists() else None,
            )
            if video_id:
                youtube_url = f"https://youtube.com/shorts/{video_id}"
                urls["youtube"] = youtube_url
                results["youtube"] = True
                print(f"  [YouTube] 投稿完了: {youtube_url}")

                # 固定コメント + いいね + 再生リスト追加
                try:
                    import sheets
                    youtube = sheets.get_youtube_service()
                    _post_pinned_comment(youtube, video_id)
                    _like_video(youtube, video_id)
                except Exception as e:
                    print(f"  [警告] 初期ブースト処理に失敗: {e}")

                try:
                    youtube_upload.add_to_playlists(
                        video_id,
                        topic=meta.get("topic", ""),
                        tags=tags,
                        title=raw_title,
                    )
                except Exception as e:
                    print(f"  [警告] 再生リスト追加に失敗: {e}")
            else:
                results["youtube"] = False
                print("  [YouTube] アップロード失敗")
        except Exception as e:
            results["youtube"] = False
            print(f"  [YouTube] エラー: {e}")

    # --- TikTok ---
    if "tiktok" in platforms:
        try:
            print("\n  [TikTok] 投稿中...")
            import tiktok_upload
            tt_tags = ["長期投資", "積立投資", "NISA", "資産形成", "ガチホ", "投資初心者", "お金の勉強"]
            publish_id = tiktok_upload.upload_video(
                video_path=str(video_path),
                title=tt_title,
                tags=tt_tags,
                privacy=privacy,
            )
            if publish_id:
                results["tiktok"] = True
                urls["tiktok"] = f"tiktok:publish_id={publish_id}"
                print(f"  [TikTok] 投稿完了")
            else:
                results["tiktok"] = False
                print("  [TikTok] 投稿失敗")
        except Exception as e:
            results["tiktok"] = False
            print(f"  [TikTok] エラー: {e}")

    # --- Instagram ---
    if "instagram" in platforms:
        try:
            print("\n  [Instagram] 投稿中...")
            import instagram_upload
            ig_url = instagram_upload.upload_video(
                video_path=str(video_path),
                caption=ig_caption,
            )
            if ig_url:
                results["instagram"] = True
                urls["instagram"] = ig_url
                print(f"  [Instagram] 投稿完了: {ig_url}")
            else:
                results["instagram"] = False
                print("  [Instagram] 投稿失敗")
        except Exception as e:
            results["instagram"] = False
            print(f"  [Instagram] エラー: {e}")

    # --- X（旧Twitter） ---
    if "x" in platforms:
        try:
            print("\n  [X] 投稿中...")
            import x_upload

            # social_captions.json からXポストテキストを読み込み
            social_path = folder / "social_captions.json"
            x_text = ""
            try:
                with open(social_path, encoding="utf-8") as f:
                    social_data = json.load(f)
                x_text = social_data.get("x", {}).get("shorts_post", "")
            except FileNotFoundError:
                pass

            # social_captions.json がない or 空の場合、transcript.json から生成
            if not x_text:
                x_text = _build_x_text_from_transcript(meta)

            # YouTube URLがあればShorts誘導リンクを追加
            # 同一プロセス内のurlsと、シート上の既存URLの両方を確認
            yt_url = urls.get("youtube", "") or entry.get("youtube_url", "")
            if yt_url and "今日のShorts👇" in x_text:
                x_text = x_text.replace("今日のShorts👇", f"今日のShorts👇\n{yt_url}")
            elif yt_url:
                x_text += f"\n\n今日のShorts👇\n{yt_url}"

            tweet_id = x_upload.post_tweet(x_text)
            if tweet_id:
                tweet_url = f"https://x.com/{X_HANDLE}/status/{tweet_id}"
                results["x"] = True
                urls["x"] = tweet_url
                print(f"  [X] 投稿完了: {tweet_url}")
            else:
                results["x"] = False
                print("  [X] 投稿失敗")
        except Exception as e:
            results["x"] = False
            print(f"  [X] エラー: {e}")

    # --- 結果サマリー ---
    print(f"\n  {'='*40}")
    for p in platforms:
        status = "✓ 成功" if results.get(p) else "✗ 失敗"
        print(f"  {p:12s}: {status}")
    print(f"  {'='*40}")

    # スプレッドシート更新
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if sheet_id:
        try:
            import sheets
            failed = [p for p, ok in results.items() if not ok]
            any_success = any(results.values())
            sheets.update_published(
                sheet_id,
                entry["row"],
                urls=urls or None,
                failed_platforms=failed if not any_success else None,
                target_platforms=DEFAULT_PLATFORMS,
            )
        except Exception as e:
            print(f"  [警告] シート更新に失敗: {e}")

    return results


# 固定コメントテンプレ
_PINNED_COMMENT = (
    "長期投資で一番つらい時期。\n"
    "それは今かもしれません。\n"
    "\n"
    "でも、退場しない人だけが勝つ。\n"
    "\n"
    "このチャンネルでは\n"
    "「静かな長期投資モチベーション」を毎日配信しています。"
)


def _post_pinned_comment(youtube, video_id: str):
    """動画に固定コメントを投稿する。"""
    result = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": _PINNED_COMMENT,
                    }
                },
            }
        },
    ).execute()
    comment_id = result["snippet"]["topLevelComment"]["id"]
    print(f"  固定コメント投稿完了: {comment_id}")


def _like_video(youtube, video_id: str):
    """動画にいいねする。"""
    youtube.videos().rate(id=video_id, rating="like").execute()
    print("  自動いいね完了")


def main():
    parser = argparse.ArgumentParser(description="マルチプラットフォーム自動投稿")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずに確認だけ")
    parser.add_argument("--force", type=int, default=None, help="指定したNo.を強制投稿")
    parser.add_argument("--private", action="store_true", help="非公開で投稿（テスト用）")
    parser.add_argument("--platforms", nargs="+", default=None,
                        choices=ALL_PLATFORMS,
                        help="投稿先プラットフォーム（デフォルト: youtube instagram x）")
    parser.add_argument("--retry-failed", action="store_true",
                        help="失敗したプラットフォームだけ再投稿")
    args = parser.parse_args()

    privacy = "private" if args.private else "public"

    LOG_DIR.mkdir(exist_ok=True)

    # シートを1回だけ読み込み（複数箇所で使い回す）
    sheet_rows = _read_sheet_rows()

    # 投稿対象を決定
    if args.force is not None:
        entry = get_entry_by_no(args.force)
        if not entry:
            print(f"[エラー] No.{args.force} がシートにありません")
            sys.exit(1)
        import sheets
        if entry["status"] == sheets.STATUS_PUBLISHED and not args.dry_run and not args.retry_failed:
            print(f"[警告] No.{args.force} は既に公開済みです。再投稿します。")
    else:
        entry = get_next_publishable(sheet_rows, platforms=args.platforms)
        if not entry:
            print(f"[情報] 投稿可能な動画（生成済み）がありません。")
            sys.exit(0)

    # プラットフォームを決定
    if args.retry_failed:
        retry_candidates = args.platforms or list(DEFAULT_PLATFORMS)
        platforms = _get_retry_platforms(entry, retry_candidates)
        if not platforms:
            print(f"  [情報] No.{entry['no']} は全プラットフォーム投稿済みです。")
            sys.exit(0)
        print(f"  再投稿対象: {', '.join(platforms)}")
    elif args.platforms:
        platforms = args.platforms
    else:
        platforms = list(DEFAULT_PLATFORMS)

    # 投稿実行
    results = publish_entry(entry, privacy=privacy, dry_run=args.dry_run, platforms=platforms)

    if not args.dry_run:
        success_count = sum(1 for r in results.values() if r)
        print(f"\n  投稿完了（No.{entry['no']}: {success_count}/{len(results)} 成功）")

    # 次回予告（シートは投稿前の状態だが、概算として十分）
    remaining = get_remaining_count(sheet_rows)
    if remaining > 0:
        # 今投稿した分を除外
        remaining_after = remaining - 1 if any(results.values()) else remaining
        if remaining_after > 0:
            print(f"\n  残り投稿待ち: {remaining_after}本")
    else:
        print("\n  全動画が投稿済みです！")

    failed_platforms = [p for p, ok in results.items() if not ok]
    if failed_platforms and not args.dry_run:
        print(f"\n  [エラー] 失敗プラットフォーム: {', '.join(failed_platforms)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

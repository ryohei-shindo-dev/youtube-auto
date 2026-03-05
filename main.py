"""
YouTube 自動生成パイプライン

使い方:
    youtube-shorts                              # 今日の曜日に応じたShortsを自動生成
    youtube-shorts --dry-run                    # 動画生成まで（アップロードなし）
    youtube-shorts --topic "S&P500の年利10%"    # トピックを手動指定
    youtube-shorts --long                       # 通常動画を生成（日曜用）
    youtube-shorts --theme メリット             # テーマを手動指定

投稿スケジュール:
    Shorts: 月〜金 7:00（週5本、テーマローテーション）
    通常動画: 日曜 21:00（週1本）

テーマローテーション（月〜金）:
    月: メリット / 火: 格言 / 水: あるある / 木: 歴史データ / 金: ガチホモチベ
"""

import argparse
import os
import pathlib
import shutil
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import script_gen
import voice_gen
import slide_gen
import video_gen
import thumbnail_gen
import subtitle_gen

SCRIPT_DIR = pathlib.Path(__file__).parent
PENDING_DIR = SCRIPT_DIR / "pending"
DONE_DIR = SCRIPT_DIR / "done"


def main():
    parser = argparse.ArgumentParser(description="YouTube 自動生成パイプライン")
    parser.add_argument("--dry-run", action="store_true", help="動画生成まで（アップロードなし）")
    parser.add_argument("--topic", type=str, default=None, help="トピックを手動指定")
    parser.add_argument("--theme", type=str, default=None, help="テーマを手動指定（メリット/格言/あるある/歴史データ/ガチホモチベ）")
    parser.add_argument("--long", action="store_true", help="通常動画を生成（日曜用）")
    args = parser.parse_args()

    if not _check_env():
        sys.exit(1)

    PENDING_DIR.mkdir(exist_ok=True)
    DONE_DIR.mkdir(exist_ok=True)

    # 動画タイプ判定
    is_long = args.long
    today = datetime.now()
    weekday = today.weekday()  # 0=月, 6=日

    if is_long:
        video_type = "通常動画"
        theme = "通常"
    else:
        video_type = "Shorts"
        # テーマ: 手動指定 or 曜日ローテーション
        if args.theme:
            theme = args.theme
        elif weekday in script_gen.WEEKDAY_THEME:
            theme = script_gen.WEEKDAY_THEME[weekday]
        else:
            theme = "ガチホモチベ"

    print("=" * 50)
    print(f"YouTube {video_type} 自動生成パイプライン")
    print(f"  日付: {today.strftime('%Y/%m/%d (%a)')}")
    if not is_long:
        print(f"  テーマ: {theme}")
    print("=" * 50)

    # ── Step 0: トピック取得 ──
    sheet_row = None
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")

    if args.topic:
        topic = args.topic
        print(f"\n  トピック（手動指定）: {topic}")
    elif sheet_id:
        import sheets
        print("\n  シートから次のトピックを取得中...")
        next_item = sheets.get_next_topic(sheet_id, theme=theme if not is_long else None, video_type="通常" if is_long else "Shorts")
        if not next_item:
            print(f"\n[完了] {theme} の未生成トピックがありません。")
            sys.exit(0)
        topic = next_item["topic"]
        sheet_row = next_item["row"]
        print(f"  トピック（シート行{sheet_row}）: {topic}")
    else:
        print("\n  [注意] YOUTUBE_SHEET_ID が未設定。デフォルトトピックを使用します。")
        topic = "S&P500の過去100年の平均リターンは年利約10%"

    # ── Step 1: 台本生成 ──
    print("\n[Step 1/7] 台本生成")
    if is_long:
        script_data = script_gen.generate_long_script(topic)
    else:
        script_data = script_gen.generate_shorts_script(topic, theme=theme)

    if not script_data:
        print("\n[失敗] 台本生成に失敗しました。終了します。")
        sys.exit(1)

    scenes = script_data["scenes"]
    print(f"  タイトル: {script_data['title']}")

    # ── Step 2: 音声生成 ──
    print("\n[Step 2/7] 音声生成")
    scenes = voice_gen.generate_voice_for_scenes(scenes, PENDING_DIR)
    success_audio = sum(1 for s in scenes if s.get("audio_path"))
    if success_audio == 0:
        print("\n[失敗] 音声が1つも生成できませんでした。終了します。")
        sys.exit(1)

    # ── Step 3: スライド画像生成 ──
    print("\n[Step 3/7] スライド画像生成")
    slide_paths = slide_gen.generate_all_slides(scenes, PENDING_DIR, theme=theme)
    for i, scene in enumerate(scenes):
        if i < len(slide_paths):
            scene["slide_path"] = str(slide_paths[i])

    # ── Step 4: 動画合成 ──
    print("\n[Step 4/7] 動画合成")
    video_path = video_gen.compose_shorts_video(scenes, PENDING_DIR / "output.mp4")
    if not video_path:
        print("\n[失敗] 動画合成に失敗しました。終了します。")
        sys.exit(1)

    # ── Step 5: サムネイル生成 ──
    print("\n[Step 5/7] サムネイル生成")
    thumb_path = thumbnail_gen.generate_thumbnail(
        script_data["title"], PENDING_DIR / "thumbnail.png", theme=theme,
    )

    # ── Step 6: 字幕・文字起こし生成 ──
    print("\n[Step 6/7] 字幕・文字起こし生成")
    sub_files = subtitle_gen.generate_subtitle_files(script_data, scenes, PENDING_DIR)

    # ── Step 7: シート更新 ──
    if sheet_row and sheet_id:
        print("\n[Step 7/7] シート更新")
        import sheets
        sheets.update_generated(sheet_id, sheet_row, script_data["title"], script_data.get("tags", []))
    else:
        print("\n[Step 7/7] シート更新（スキップ）")

    # ── 結果サマリー ──
    print("\n" + "=" * 50)
    print("生成完了！")
    print("=" * 50)
    print(f"  タイプ:       {video_type}" + (f"（{theme}）" if not is_long else ""))
    print(f"  タイトル:     {script_data['title']}")
    print(f"  動画:         {video_path}")
    if thumb_path:
        print(f"  サムネイル:   {thumb_path}")
    print(f"  字幕(SRT):    {sub_files.get('srt_path', 'なし')}")
    print(f"  タグ:         {', '.join(script_data.get('tags', []))}")

    if args.dry_run:
        print("\n  (--dry-run モード: アップロードはスキップ)")
    else:
        print("\n  (アップロード機能は Phase 2 で実装予定)")

    _archive_files(script_data["title"])
    print("\n完了！")


def _check_env():
    """必要な環境変数の存在をチェックする。"""
    required = {
        "ANTHROPIC_API_KEY": "Claude API（台本生成）",
        "ELEVENLABS_API_KEY": "ElevenLabs（音声生成）",
        "ELEVENLABS_VOICE_ID": "ElevenLabs ボイスID",
    }
    missing = []
    for key, desc in required.items():
        if not os.getenv(key):
            missing.append(f"  {key} — {desc}")

    if missing:
        print("[エラー] 以下の環境変数が設定されていません:")
        for m in missing:
            print(m)
        return False

    if not shutil.which("ffmpeg"):
        print("[エラー] FFmpeg がインストールされていません。")
        return False

    return True


def _archive_files(title: str):
    """生成したファイルを done/ にアーカイブする。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = DONE_DIR / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)

    for f in PENDING_DIR.iterdir():
        if f.is_file():
            shutil.move(str(f), str(archive_dir / f.name))

    print(f"  ファイルをアーカイブ: {archive_dir}")


if __name__ == "__main__":
    main()

"""
バッチ生成スクリプト — 指定本数のShortsを連続生成する。

使い方:
    python batch_gen.py              # 50本生成（デフォルト）
    python batch_gen.py --count 10   # 10本生成
    python batch_gen.py --count 5 --theme メリット  # テーマ指定で5本
"""

import argparse
import os
import pathlib
import shutil
import sys
import time
import traceback
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import script_gen
import voice_gen
import slide_gen
import video_gen
import thumbnail_gen
import subtitle_gen
import note_gen
import social_gen
import candidate_ranker
import dedupe_check

SCRIPT_DIR = pathlib.Path(__file__).parent
PENDING_DIR = SCRIPT_DIR / "pending"
DONE_DIR = SCRIPT_DIR / "done"

# スコアリングで不合格の場合のリトライ上限
MAX_SCRIPT_RETRIES = 2


def generate_one(topic: str, theme: str, index: int, total: int) -> dict:
    """1本のShortsを生成する。成功時はファイル情報を返す。"""
    print(f"\n{'='*60}")
    print(f"  [{index}/{total}] テーマ: {theme}")
    print(f"  トピック: {topic}")
    print(f"{'='*60}")

    # pendingをクリア
    PENDING_DIR.mkdir(exist_ok=True)
    for f in PENDING_DIR.iterdir():
        if f.is_file():
            f.unlink()

    # Step 1: 台本生成 + スコアリング（閾値未満は再生成）
    print("\n  [1/5] 台本生成...")
    script_data = None
    for attempt in range(1, MAX_SCRIPT_RETRIES + 2):
        candidate = script_gen.generate_shorts_script(topic, theme=theme)
        if not candidate:
            raise RuntimeError("台本生成に失敗")

        result = candidate_ranker.score_script(candidate)
        print(candidate_ranker.format_report(result))

        if candidate_ranker.is_acceptable(result):
            # 重複チェック
            dup = dedupe_check.check_duplicate(candidate)
            print(dedupe_check.format_report(dup))
            if not dup["is_duplicate"]:
                # トピック−タイトル一致チェック
                topic_result = candidate_ranker.check_topic_match(candidate)
                if topic_result["score"] <= -2:
                    print(f"  [トピック不一致] スコア={topic_result['score']}、"
                          f"トピックKW: {topic_result['topic_keywords']}")
                    if attempt <= MAX_SCRIPT_RETRIES:
                        print(f"  [再生成] トピック不一致 → リトライ {attempt}/{MAX_SCRIPT_RETRIES}")
                        time.sleep(1)
                        continue
                    else:
                        raise RuntimeError(
                            f"リトライ上限到達。タイトルがトピックと無関係: "
                            f"「{candidate.get('title', '')}」"
                        )
                script_data = candidate
                dedupe_check.register_accepted(candidate)
                break
            # 重複あり → リトライ扱い
            if attempt <= MAX_SCRIPT_RETRIES:
                print(f"  [再生成] 類似動画あり → リトライ {attempt}/{MAX_SCRIPT_RETRIES}")
                time.sleep(1)
                continue
            else:
                # 重複のまま採用しない → スキップ
                raise RuntimeError(
                    f"リトライ上限到達。類似動画あり: {dup['reason']}"
                )

        if attempt <= MAX_SCRIPT_RETRIES:
            print(f"  [再生成] スコア不足（{result['total_score']}/{result['max_score']}）→ リトライ {attempt}/{MAX_SCRIPT_RETRIES}")
            time.sleep(1)
        else:
            # リトライ上限 → 最後の候補をそのまま採用（スコア不足は許容、重複は不可）
            dup = dedupe_check.check_duplicate(candidate)
            if dup["is_duplicate"]:
                raise RuntimeError(
                    f"リトライ上限到達。スコア不足かつ類似動画あり: {dup['reason']}"
                )
            topic_result = candidate_ranker.check_topic_match(candidate)
            if topic_result["score"] <= -2:
                raise RuntimeError(
                    f"リトライ上限到達。タイトルがトピックと無関係: "
                    f"「{candidate.get('title', '')}」"
                )
            print(f"  [採用] リトライ上限到達。最終候補を採用（{result['total_score']}/{result['max_score']}）")
            script_data = candidate
            dedupe_check.register_accepted(candidate)
            break

    scenes = script_data["scenes"]
    print(f"    タイトル: {script_data['title']}")

    # Step 2: 音声生成
    print("  [2/5] 音声生成...")
    scenes = voice_gen.generate_voice_for_scenes(scenes, PENDING_DIR)
    if not any(s.get("audio_path") for s in scenes):
        raise RuntimeError("音声が1つも生成できなかった")

    # Step 3: スライド画像生成
    print("  [3/5] スライド画像生成...")
    slide_paths = slide_gen.generate_all_slides(scenes, PENDING_DIR, theme=theme)
    for i, scene in enumerate(scenes):
        if i < len(slide_paths):
            scene["slide_path"] = str(slide_paths[i])

    # Step 4: 動画合成
    print("  [4/5] 動画合成...")
    video_path = video_gen.compose_shorts_video(scenes, PENDING_DIR / "output.mp4")
    if not video_path:
        raise RuntimeError("動画合成に失敗")

    # Step 5: サムネイル + 字幕
    print("  [5/7] サムネイル・字幕生成...")
    scene_texts = script_gen.extract_scene_texts(script_data, "hook", "resolve")
    thumbnail_gen.generate_thumbnail(
        script_data["title"], PENDING_DIR / "thumbnail.png", theme=theme,
        hook_text=scene_texts["hook"], resolve_text=scene_texts["resolve"],
    )
    subtitle_gen.generate_subtitle_files(script_data, scenes, PENDING_DIR)

    # Step 6: note記事生成
    print("  [6/7] note記事生成...")
    note_gen.generate_note_article(script_data, PENDING_DIR)

    # Step 7: SNSキャプション生成
    print("  [7/7] SNSキャプション生成...")
    social_gen.generate_social_captions(script_data, PENDING_DIR)

    return script_data


def archive_files(title: str) -> str:
    """生成したファイルを done/ にアーカイブする。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = DONE_DIR / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)

    for f in PENDING_DIR.iterdir():
        if f.is_file():
            shutil.move(str(f), str(archive_dir / f.name))

    return str(archive_dir)


def main():
    parser = argparse.ArgumentParser(description="Shorts バッチ生成")
    parser.add_argument("--count", type=int, default=50, help="生成本数（デフォルト: 50）")
    parser.add_argument("--theme", type=str, default=None, help="テーマを固定（省略時はシートから順番に取得）")
    args = parser.parse_args()

    # 環境チェック
    for key in ["ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"]:
        if not os.getenv(key):
            print(f"[エラー] {key} が未設定です。")
            sys.exit(1)
    if not shutil.which("ffmpeg"):
        print("[エラー] ffmpeg がインストールされていません。")
        sys.exit(1)

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("[エラー] YOUTUBE_SHEET_ID が未設定です。シートからトピックを取得できません。")
        sys.exit(1)

    import sheets

    PENDING_DIR.mkdir(exist_ok=True)
    DONE_DIR.mkdir(exist_ok=True)

    target = args.count
    success = 0
    fail = 0
    results = []

    print(f"\n{'#'*60}")
    print(f"  量産開始: {target}本")
    print(f"  テーマ: {args.theme or '自動（シートから順番取得）'}")
    print(f"  開始時刻: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print(f"{'#'*60}")

    for i in range(1, target + 1):
        try:
            # シートから次のトピックを取得
            next_item = sheets.get_next_topic(
                sheet_id,
                theme=args.theme,
                video_type="Shorts",
            )
            if not next_item:
                print(f"\n[完了] 未生成トピックがなくなりました（{success}本生成済み）。")
                break

            topic = next_item["topic"]
            sheet_row = next_item["row"]
            row_type = next_item["type"]
            # 種別からテーマ名を抽出（例: "Shorts/メリット" → "メリット"）
            theme = row_type.split("/")[1] if "/" in row_type else "ガチホモチベ"

            # 生成
            script_data = generate_one(topic, theme, i, target)

            # アーカイブ（フォルダ名確定）
            archive_path = archive_files(script_data["title"])
            folder_name = pathlib.Path(archive_path).name

            # シート更新（フォルダ名付き）
            sheets.update_generated(
                sheet_id, sheet_row,
                script_data["title"],
                script_data.get("tags", []),
                folder=folder_name,
            )

            success += 1
            results.append({
                "no": i,
                "status": "OK",
                "title": script_data["title"],
                "theme": theme,
                "archive": archive_path,
            })
            print(f"\n  ✓ [{i}/{target}] 成功 — {script_data['title']}")

        except Exception as e:
            fail += 1
            results.append({
                "no": i,
                "status": "FAIL",
                "error": str(e),
            })
            print(f"\n  ✗ [{i}/{target}] 失敗 — {e}")
            traceback.print_exc()

        # API レート制限対策（1秒待つ）
        if i < target:
            time.sleep(1)

    # ── 結果サマリー ──
    print(f"\n\n{'#'*60}")
    print(f"  量産完了")
    print(f"{'#'*60}")
    print(f"  成功: {success}本")
    print(f"  失敗: {fail}本")
    print(f"  終了時刻: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print()

    for r in results:
        if r["status"] == "OK":
            print(f"  {r['no']:3d}. ✓ [{r['theme']}] {r['title']}")
        else:
            print(f"  {r['no']:3d}. ✗ {r['error']}")

    print()


if __name__ == "__main__":
    main()

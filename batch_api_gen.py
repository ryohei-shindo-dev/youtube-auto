"""
batch_api_gen.py — Anthropic Batch API で台本を一括生成する。

通常のAPIの50%割引で処理される（非同期、最大24時間）。
大量生成時のコスト削減用。結果取得後は従来のパイプライン（音声→動画）に流す。

使い方:
    # Step 1: バッチ送信（トピックをシートから取得してBatch APIに投げる）
    python batch_api_gen.py submit --count 30

    # Step 2: 結果取得（完了したバッチの結果をダウンロード→動画生成）
    python batch_api_gen.py fetch --batch-id msgbatch_xxx

    # ワンショット: 送信→完了待ち→動画生成まで一括
    python batch_api_gen.py run --count 30

    # ステータス確認
    python batch_api_gen.py status --batch-id msgbatch_xxx
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import time
import traceback
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import anthropic
import candidate_ranker
import dedupe_check
import note_gen
import script_gen
import sheets
import slide_gen
import social_gen
import subtitle_gen
import thumbnail_gen
import video_gen
import voice_gen

SCRIPT_DIR = pathlib.Path(__file__).parent
PENDING_DIR = SCRIPT_DIR / "pending"
DONE_DIR = SCRIPT_DIR / "done"

# ポーリング間隔（秒）
POLL_INTERVAL_INITIAL = 30
POLL_INTERVAL_MAX = 300
# バッチ完了までの最大待ち時間（秒）
MAX_WAIT_SECONDS = 86400  # 24時間


def _get_all_pending_topics(
    sheet_id: str, count: int, theme: str = None,
) -> list:
    """シートから未生成トピックをcount件まとめて取得する。"""
    service = sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A:G",
    ).execute()

    rows = result.get("values", [])
    topics = []
    for i, row in enumerate(rows[1:], start=2):
        if len(topics) >= count:
            break
        if len(row) < 7 or row[6] != sheets.STATUS_PENDING:
            continue
        row_type = row[2] if len(row) > 2 else ""
        if not row_type.startswith("Shorts"):
            continue
        if theme:
            if row_type != f"Shorts/{theme}":
                continue
        topic_text = row[3] if len(row) > 3 else ""
        row_theme = row_type.split("/")[1] if "/" in row_type else "ガチホモチベ"
        topics.append({
            "row": i,
            "type": row_type,
            "topic": topic_text,
            "theme": row_theme,
        })

    return topics


def _build_batch_requests(topics: list) -> list:
    """トピックリストからBatch APIリクエストを構築する。

    各トピックに対して、script_gen の SHORTS_TEMPLATE と同じプロンプトを構築し、
    Batch API の Request 形式にまとめる。
    """
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    # insights は全リクエスト共通
    insights = script_gen.load_insights()
    insights_block = script_gen._build_insights_block(insights)

    requests = []
    # 各トピックの固定変数をメタデータとして保存（結果処理で使う）
    metadata = {}

    for item in topics:
        topic = item["topic"]
        theme = item["theme"]
        row = item["row"]

        # Shorts用の固定変数をセットアップ
        shorts_vars = script_gen._build_shorts_vars(theme)

        # プロンプト構築（_generate_script の前処理を再現）
        fmt_vars = {
            "concept": script_gen.CHANNEL_CONCEPT,
            "topic": topic,
            "opening": script_gen.OPENING_PHRASE,
            "conclusion": script_gen.CONCLUSION_PHRASES[0],
            "closing": script_gen.CLOSING_PHRASE,
        }
        fmt_vars.update(shorts_vars)

        prompt = script_gen.SHORTS_TEMPLATE.format(**fmt_vars)
        if insights_block:
            prompt = insights_block + "\n\n" + prompt

        # custom_id にシート行番号を埋め込む（結果処理で使う）
        custom_id = f"row_{row}"

        request = Request(
            custom_id=custom_id,
            params=MessageCreateParamsNonStreaming(
                model=script_gen.get_model_for_theme(theme),
                max_tokens=2000,
                system=[{
                    "type": "text",
                    "text": prompt,
                }],
                messages=[{
                    "role": "user",
                    "content": f"トピック「{topic}」の台本をJSON形式で生成してください。",
                }],
            ),
        )
        requests.append(request)
        metadata[custom_id] = {
            "row": row,
            "topic": topic,
            "theme": theme,
            "fmt_vars": fmt_vars,
        }

    return requests, metadata


def submit_batch(topics: list) -> tuple:
    """バッチを送信して batch_id とメタデータを返す。"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[エラー] ANTHROPIC_API_KEY が未設定です。")
        sys.exit(1)

    requests, metadata = _build_batch_requests(topics)
    if not requests:
        print("[エラー] リクエストが0件です。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"\n  Batch API に {len(requests)} 件のリクエストを送信中...")
    batch = client.messages.batches.create(requests=requests)

    print(f"  バッチID: {batch.id}")
    print(f"  ステータス: {batch.processing_status}")

    # メタデータをファイルに保存（fetch時に使う）
    meta_path = SCRIPT_DIR / f"batch_meta_{batch.id}.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  メタデータ保存: {meta_path.name}")

    return batch.id, metadata


def check_status(batch_id: str) -> str:
    """バッチのステータスを確認する。"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)
    batch = client.messages.batches.retrieve(batch_id)

    print(f"\n  バッチID: {batch_id}")
    print(f"  ステータス: {batch.processing_status}")
    counts = batch.request_counts
    print(f"  処理中: {counts.processing}")
    print(f"  成功: {counts.succeeded}")
    print(f"  エラー: {counts.errored}")
    print(f"  期限切れ: {counts.expired}")

    return batch.processing_status


def poll_until_done(batch_id: str) -> None:
    """バッチの完了をポーリングで待つ。"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    start = time.time()
    interval = POLL_INTERVAL_INITIAL

    while time.time() - start < MAX_WAIT_SECONDS:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        elapsed = int(time.time() - start)
        print(f"\n  [{elapsed}秒経過] ステータス: {batch.processing_status}"
              f"  成功: {counts.succeeded}  処理中: {counts.processing}"
              f"  エラー: {counts.errored}")

        if batch.processing_status == "ended":
            print(f"\n  バッチ完了!")
            return

        print(f"  次の確認: {interval}秒後...")
        time.sleep(interval)
        # 指数バックオフ（最大5分）
        interval = min(interval * 2, POLL_INTERVAL_MAX)

    raise TimeoutError(f"バッチ {batch_id} が24時間以内に完了しませんでした")


def fetch_and_process(batch_id: str, sheet_id: str) -> dict:
    """バッチ結果を取得し、台本ポスト処理→動画生成→アーカイブする。"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    # メタデータを読み込む
    meta_path = SCRIPT_DIR / f"batch_meta_{batch_id}.json"
    if not meta_path.exists():
        print(f"[エラー] メタデータファイルが見つかりません: {meta_path.name}")
        sys.exit(1)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    print(f"\n  バッチ結果を取得中... (ID: {batch_id})")

    success = 0
    fail = 0
    results_summary = []

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        meta = metadata.get(custom_id)
        if not meta:
            print(f"  [警告] メタデータなし: {custom_id}")
            continue

        row = meta["row"]
        topic = meta["topic"]
        theme = meta["theme"]
        fmt_vars = meta["fmt_vars"]

        print(f"\n{'='*60}")
        print(f"  トピック: {topic} (行{row})")
        print(f"{'='*60}")

        if result.result.type == "errored":
            fail += 1
            error_msg = getattr(result.result.error, "message", "不明なエラー")
            print(f"  [エラー] Batch APIエラー: {error_msg}")
            results_summary.append({"row": row, "status": "FAIL", "error": error_msg})
            _mark_sheet_failed(sheet_id, row)
            continue

        if result.result.type == "expired":
            fail += 1
            print(f"  [エラー] リクエスト期限切れ")
            results_summary.append({"row": row, "status": "FAIL", "error": "期限切れ"})
            _mark_sheet_failed(sheet_id, row)
            continue

        # 成功: レスポンスからJSONを抽出してポスト処理
        try:
            raw = result.result.message.content[0].text.strip()
            script_data = _process_raw_response(raw, topic, fmt_vars)
            if not script_data:
                raise RuntimeError("台本のポスト処理に失敗")

            # スコアリング・重複チェック
            score = candidate_ranker.score_script(script_data)
            print(candidate_ranker.format_report(score))
            dup = dedupe_check.check_duplicate(script_data)
            print(dedupe_check.format_report(dup))
            if dup["is_duplicate"]:
                raise RuntimeError(f"重複検知: {dup['reason']}")

            # 動画パイプライン
            _run_video_pipeline(script_data, theme)

            # アーカイブ
            archive_path = _archive_files(script_data["title"])
            folder_name = pathlib.Path(archive_path).name

            # シート更新
            sheets.update_generated(
                sheet_id, row,
                script_data["title"],
                script_data.get("tags", []),
                folder=folder_name,
            )

            dedupe_check.register_accepted(script_data)
            success += 1
            results_summary.append({
                "row": row, "status": "OK",
                "title": script_data["title"],
                "archive": archive_path,
            })
            print(f"\n  ✓ 成功 — {script_data['title']}")

        except Exception as e:
            fail += 1
            results_summary.append({"row": row, "status": "FAIL", "error": str(e)})
            print(f"\n  ✗ 失敗 — {e}")
            traceback.print_exc()
            _mark_sheet_failed(sheet_id, row)

    # サマリー
    print(f"\n\n{'#'*60}")
    print(f"  Batch API 処理完了")
    print(f"{'#'*60}")
    print(f"  成功: {success}本")
    print(f"  失敗: {fail}本")
    print()
    for r in results_summary:
        if r["status"] == "OK":
            print(f"  ✓ 行{r['row']}: {r['title']}")
        else:
            print(f"  ✗ 行{r['row']}: {r['error']}")

    return {"success": success, "fail": fail, "results": results_summary}


def _process_raw_response(raw: str, topic: str, fmt_vars: dict) -> dict:
    """Batch APIのレスポンスからJSON抽出 → ポスト処理。"""
    import re
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        print("  [エラー] JSON形式のレスポンスが見つかりませんでした。")
        return {}

    data = json.loads(m.group())
    return script_gen._postprocess_script(data, topic, fmt_vars, expected_scenes=5)


def _run_video_pipeline(script_data: dict, theme: str) -> None:
    """台本から音声・スライド・動画・サムネイル・字幕・note・SNSを生成する。"""
    PENDING_DIR.mkdir(exist_ok=True)
    for f in PENDING_DIR.iterdir():
        if f.is_file():
            f.unlink()

    scenes = script_data["scenes"]

    # 音声生成
    print("  [2/7] 音声生成...")
    scenes = voice_gen.generate_voice_for_scenes(scenes, PENDING_DIR)
    if not any(s.get("audio_path") for s in scenes):
        raise RuntimeError("音声が1つも生成できなかった")

    # スライド画像生成
    print("  [3/7] スライド画像生成...")
    slide_paths = slide_gen.generate_all_slides(scenes, PENDING_DIR, theme=theme, use_photo=True)
    for i, scene in enumerate(scenes):
        if i < len(slide_paths):
            scene["slide_path"] = str(slide_paths[i])

    # 動画合成
    print("  [4/7] 動画合成...")
    video_path = video_gen.compose_shorts_video(scenes, PENDING_DIR / "output.mp4", use_photo=True)
    if not video_path:
        raise RuntimeError("動画合成に失敗")

    # サムネイル + 字幕
    print("  [5/7] サムネイル・字幕生成...")
    scene_texts = script_gen.extract_scene_texts(script_data, "hook", "resolve")
    thumbnail_gen.generate_thumbnail(
        script_data["title"], PENDING_DIR / "thumbnail.png", theme=theme,
        hook_text=scene_texts["hook"], resolve_text=scene_texts["resolve"],
    )
    subtitle_gen.generate_subtitle_files(script_data, scenes, PENDING_DIR)

    # note記事生成
    print("  [6/7] note記事生成...")
    note_gen.generate_note_article(script_data, PENDING_DIR)

    # SNSキャプション生成
    print("  [7/7] SNSキャプション生成...")
    social_gen.generate_social_captions(script_data, PENDING_DIR)


def _archive_files(title: str) -> str:
    """生成したファイルを done/ にアーカイブする。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = DONE_DIR / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)

    for f in PENDING_DIR.iterdir():
        if f.is_file():
            shutil.move(str(f), str(archive_dir / f.name))

    return str(archive_dir)


def _mark_sheet_failed(sheet_id: str, row: int) -> None:
    """シートの行を「生成失敗」に更新する。"""
    try:
        svc = sheets.get_service()
        svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheets.SHEET_NAME}!G{row}",
            valueInputOption="RAW",
            body={"values": [[sheets.STATUS_GEN_FAILED]]},
        ).execute()
        print(f"  シート行{row}を「生成失敗」に更新")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Batch API で台本一括生成（50%割引）")
    sub = parser.add_subparsers(dest="command")

    # submit: バッチ送信のみ
    p_submit = sub.add_parser("submit", help="バッチ送信（結果は後で取得）")
    p_submit.add_argument("--count", type=int, default=30, help="トピック数（デフォルト: 30）")
    p_submit.add_argument("--theme", type=str, default=None, help="テーマ固定")

    # fetch: 結果取得＋動画生成
    p_fetch = sub.add_parser("fetch", help="バッチ結果を取得して動画生成")
    p_fetch.add_argument("--batch-id", required=True, help="バッチID")

    # status: ステータス確認
    p_status = sub.add_parser("status", help="バッチステータス確認")
    p_status.add_argument("--batch-id", required=True, help="バッチID")

    # run: 送信→完了待ち→動画生成の一括実行
    p_run = sub.add_parser("run", help="送信→完了待ち→動画生成を一括実行")
    p_run.add_argument("--count", type=int, default=30, help="トピック数（デフォルト: 30）")
    p_run.add_argument("--theme", type=str, default=None, help="テーマ固定")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

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
        print("[エラー] YOUTUBE_SHEET_ID が未設定です。")
        sys.exit(1)

    PENDING_DIR.mkdir(exist_ok=True)
    DONE_DIR.mkdir(exist_ok=True)

    if args.command == "submit":
        topics = _get_all_pending_topics(sheet_id, args.count, args.theme)
        if not topics:
            print("[完了] 未生成トピックがありません。")
            return
        print(f"\n  {len(topics)}件のトピックを取得")
        batch_id, _ = submit_batch(topics)
        print(f"\n  バッチ送信完了。結果取得コマンド:")
        print(f"    python batch_api_gen.py fetch --batch-id {batch_id}")

    elif args.command == "fetch":
        status = check_status(args.batch_id)
        if status != "ended":
            print(f"\n  [注意] バッチはまだ完了していません（{status}）。")
            print(f"  完了後に再実行してください。")
            return
        fetch_and_process(args.batch_id, sheet_id)

    elif args.command == "status":
        check_status(args.batch_id)

    elif args.command == "run":
        topics = _get_all_pending_topics(sheet_id, args.count, args.theme)
        if not topics:
            print("[完了] 未生成トピックがありません。")
            return
        print(f"\n  {len(topics)}件のトピックを取得")

        # 送信
        batch_id, _ = submit_batch(topics)

        # 完了待ち
        print(f"\n  バッチ完了を待機中...")
        poll_until_done(batch_id)

        # 結果取得＋動画生成
        fetch_and_process(batch_id, sheet_id)


if __name__ == "__main__":
    main()

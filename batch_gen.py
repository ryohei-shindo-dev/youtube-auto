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


def _get_scene_text(script_data: dict, role: str) -> str:
    """台本から指定ロールのテキストを取り出す。"""
    for s in script_data.get("scenes", []):
        if s.get("role") == role:
            return s.get("text", "")
    return ""


def _get_data_text(script_data: dict) -> str:
    """台本からdataシーンのテキストを取り出す。"""
    return _get_scene_text(script_data, "data")


def _normalize(text: str) -> str:
    """比較用にテキストを正規化（句読点・スペース除去）。"""
    import re
    return re.sub(r"[。、！？\s]", "", text)


def _is_batch_duplicate(text: str, existing_list: list) -> bool:
    """テキストが既存リストと重複していないかチェック。"""
    if not existing_list or not text:
        return False
    norm = _normalize(text)
    return any(_normalize(e) == norm for e in existing_list)


def _is_batch_data_duplicate(script_data: dict, batch_data_texts: list) -> bool:
    """同一バッチ内でdataテキストが重複していないかチェック。"""
    return _is_batch_duplicate(_get_data_text(script_data), batch_data_texts)


def _check_candidate(
    candidate: dict, topic: str,
    batch_data_texts: list, batch_hook_texts: list, batch_resolve_texts: list,
) -> dict:
    """1つの候補をスコアリング・重複・トピック一致チェックする。

    戻り値: {"ok": bool, "reason_type": str, "reason": str,
             "score_result": dict, "candidate": dict}
    reason_type: "score_low" / "duplicate" / "topic_mismatch" /
                 "batch_duplicate" / "" (合格時)
    """
    result = candidate_ranker.score_script(candidate)
    print(candidate_ranker.format_report(result))

    if not candidate_ranker.is_acceptable(result):
        return {"ok": False, "reason_type": "score_low",
                "reason": f"スコア不足（{result['total_score']}/{result['max_score']}）",
                "score_result": result, "candidate": candidate}

    dup = dedupe_check.check_duplicate(candidate)
    print(dedupe_check.format_report(dup))
    if dup["is_duplicate"]:
        return {"ok": False, "reason_type": "duplicate",
                "reason": f"重複: {dup['reason']}",
                "score_result": result, "candidate": candidate}

    topic_result = candidate_ranker.check_topic_match(candidate)
    if topic_result["score"] <= -2:
        return {"ok": False, "reason_type": "topic_mismatch",
                "reason": f"トピック不一致（スコア={topic_result['score']}）",
                "score_result": result, "candidate": candidate}

    # バッチ内重複チェック
    if _is_batch_data_duplicate(candidate, batch_data_texts):
        return {"ok": False, "reason_type": "batch_duplicate",
                "reason": f"バッチ内data重複:「{_get_data_text(candidate)}」",
                "score_result": result, "candidate": candidate}
    if _is_batch_duplicate(_get_scene_text(candidate, "hook"), batch_hook_texts):
        return {"ok": False, "reason_type": "batch_duplicate",
                "reason": f"バッチ内hook重複:「{_get_scene_text(candidate, 'hook')}」",
                "score_result": result, "candidate": candidate}
    if _is_batch_duplicate(_get_scene_text(candidate, "resolve"), batch_resolve_texts):
        return {"ok": False, "reason_type": "batch_duplicate",
                "reason": f"バッチ内resolve重複:「{_get_scene_text(candidate, 'resolve')}」",
                "score_result": result, "candidate": candidate}

    return {"ok": True, "reason_type": "", "reason": "",
            "score_result": result, "candidate": candidate}


def _select_best_candidate(
    topic: str, theme: str, effective_retries: int,
    batch_data_texts: list, batch_hook_texts: list, batch_resolve_texts: list,
) -> dict:
    """3候補一括生成 → ローカル選別 → フォールバックリトライ。

    1回のAPI呼び出しで3候補を取得し、合格する最良のものを返す。
    全候補が不合格の場合のみ、従来の1候補リトライを行う。
    """
    # Phase 1: 3候補を1回のAPIで生成（使用済みhookを禁止リストとして注入）
    print("  [Phase1] 3候補を一括生成...")
    candidates = script_gen.generate_shorts_candidates(
        topic, theme=theme, count=3,
        prohibited_hooks=batch_hook_texts,
    )
    if not candidates:
        raise RuntimeError("台本生成に失敗（候補が0件）")

    # 各候補をチェックし、スコア順にソート
    checked = []
    for ci, cand in enumerate(candidates):
        if not cand:
            continue
        print(f"\n  --- 候補 {ci+1}/{len(candidates)} チェック ---")
        check = _check_candidate(
            cand, topic, batch_data_texts, batch_hook_texts, batch_resolve_texts,
        )
        checked.append(check)

    # 合格候補をスコア順で選択
    passed = [c for c in checked if c["ok"]]
    if passed:
        # スコアが最も高い候補を採用
        best = max(passed, key=lambda c: c["score_result"]["total_score"])
        print(f"\n  [Phase1] {len(passed)}/{len(checked)}候補が合格 → 最高スコアを採用"
              f"（{best['score_result']['total_score']}/{best['score_result']['max_score']}）")
        dedupe_check.register_accepted(best["candidate"])
        return best["candidate"]

    # 全候補不合格の理由を表示
    print(f"\n  [Phase1] 全{len(checked)}候補が不合格:")
    for ci, c in enumerate(checked):
        print(f"    候補{ci+1}: {c['reason']}")

    # Phase 2: 従来の1候補リトライ（effective_retries回まで）
    if effective_retries <= 0:
        raise RuntimeError(
            f"全候補不合格かつリトライ不可: {checked[0]['reason'] if checked else '候補なし'}"
        )

    print(f"\n  [Phase2] 1候補ずつリトライ（最大{effective_retries}回）...")
    last_fail_reason = ""
    for attempt in range(1, effective_retries + 1):
        candidate = script_gen.generate_shorts_script(topic, theme=theme)
        if not candidate:
            raise RuntimeError("台本生成に失敗")

        check = _check_candidate(
            candidate, topic, batch_data_texts, batch_hook_texts, batch_resolve_texts,
        )
        if check["ok"]:
            print(f"  [Phase2] リトライ{attempt}回目で合格")
            dedupe_check.register_accepted(candidate)
            return candidate

        # 同じ理由で連続失敗 → API節約のため即スキップ
        current_reason = check["reason"]
        if last_fail_reason and current_reason == last_fail_reason:
            raise RuntimeError(
                f"同一理由で連続失敗（API節約のためスキップ）: {current_reason}"
            )
        last_fail_reason = current_reason
        print(f"  [Phase2] リトライ {attempt}/{effective_retries} 不合格: {current_reason}")
        time.sleep(1)

    # リトライ上限 → スコア不足は許容だが重複・トピック不一致は不可
    # Phase1の候補からスコア不足だけのものを探す
    score_only_fails = [
        c for c in checked
        if not c["ok"] and c["reason_type"] == "score_low"
    ]
    if score_only_fails:
        best_fallback = max(score_only_fails, key=lambda c: c["score_result"]["total_score"])
        print(f"  [採用] リトライ上限。Phase1のスコア不足候補を採用"
              f"（{best_fallback['score_result']['total_score']}/{best_fallback['score_result']['max_score']}）")
        dedupe_check.register_accepted(best_fallback["candidate"])
        return best_fallback["candidate"]

    raise RuntimeError(
        f"リトライ上限到達。全候補不合格: {checked[-1]['reason'] if checked else '候補なし'}"
    )


def generate_one(
    topic: str, theme: str, index: int, total: int,
    batch_data_texts: list = None,
    batch_hook_texts: list = None,
    batch_resolve_texts: list = None,
) -> dict:
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

    # Step 0: 事前枯渇度チェック（APIを叩く前にローカルで判定）
    exhaustion = dedupe_check.check_exhaustion(
        topic, script_gen.DATA_POOL, script_gen._TOPIC_TO_CATEGORY,
    )
    effective_retries = MAX_SCRIPT_RETRIES
    if exhaustion["is_exhausted"]:
        raise RuntimeError(
            f"事前判定: APIスキップ（{exhaustion['reason']}）"
        )
    if exhaustion["max_retries"] >= 0:
        effective_retries = exhaustion["max_retries"]
        if exhaustion["reason"]:
            print(f"  [事前判定] {exhaustion['reason']} → リトライ{effective_retries}回に制限")

    # Step 1: 台本生成 + スコアリング
    # まず3候補を1回のAPI呼び出しで生成し、ローカルで選別する（コスト削減）
    # 全候補が不合格なら従来の1候補リトライにフォールバック
    print("\n  [1/5] 台本生成...")
    script_data = _select_best_candidate(
        topic, theme, effective_retries,
        batch_data_texts, batch_hook_texts, batch_resolve_texts,
    )

    scenes = script_data["scenes"]
    print(f"    タイトル: {script_data['title']}")

    # Step 2: 音声生成
    print("  [2/5] 音声生成...")
    scenes = voice_gen.generate_voice_for_scenes(scenes, PENDING_DIR)
    if not any(s.get("audio_path") for s in scenes):
        raise RuntimeError("音声が1つも生成できなかった")

    # Step 3: スライド画像生成
    print("  [3/5] スライド画像生成...")
    slide_paths = slide_gen.generate_all_slides(scenes, PENDING_DIR, theme=theme, use_photo=True)
    for i, scene in enumerate(scenes):
        if i < len(slide_paths):
            scene["slide_path"] = str(slide_paths[i])

    # Step 4: 動画合成
    print("  [4/5] 動画合成...")
    video_path = video_gen.compose_shorts_video(scenes, PENDING_DIR / "output.mp4", use_photo=True)
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
    batch_data_texts = []     # 同一バッチ内のdataテキスト（重複防止用）
    batch_hook_texts = []     # 同一バッチ内のhookテキスト
    batch_resolve_texts = []  # 同一バッチ内のresolveテキスト

    print(f"\n{'#'*60}")
    print(f"  量産開始: {target}本")
    print(f"  テーマ: {args.theme or '自動（シートから順番取得）'}")
    print(f"  開始時刻: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print(f"{'#'*60}")

    for i in range(1, target + 1):
        sheet_row = None
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
            script_data = generate_one(
                topic, theme, i, target,
                batch_data_texts, batch_hook_texts, batch_resolve_texts,
            )

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
            # バッチ内重複防止用にテキストを記録
            for role, lst in [("data", batch_data_texts), ("hook", batch_hook_texts), ("resolve", batch_resolve_texts)]:
                t = _get_scene_text(script_data, role)
                if t:
                    lst.append(t)
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

            # 生成失敗をシートに記録（同じトピックの無限ループを防止）
            if sheet_row:
                try:
                    svc = sheets.get_service()
                    svc.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"{sheets.SHEET_NAME}!G{sheet_row}",
                        valueInputOption="RAW",
                        body={"values": [[sheets.STATUS_GEN_FAILED]]},
                    ).execute()
                    print(f"  シート行{sheet_row}を「生成失敗」に更新")
                except Exception:
                    pass

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

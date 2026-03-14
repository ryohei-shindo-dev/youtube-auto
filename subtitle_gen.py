"""
subtitle_gen.py
台本データから字幕ファイル（SRT）と文字起こしテキスト（JSON）を生成するモジュール。

【出力形式】
  - SRT: YouTube にアップロードできる標準字幕形式
  - JSON: シーン構造を保持した文字起こしデータ（再利用・検索用）

【SRTの仕様】
  - 各シーンの text をそのまま字幕テキストにする
  - タイミングは actual_duration_sec（音声の実際の長さ）に基づく
  - 長いテキストは40文字で改行（YouTube表示に適した幅）
"""

import json
import pathlib
import textwrap


def generate_subtitle_files(
    script_data: dict,
    scenes: list,
    output_dir: pathlib.Path,
) -> dict:
    """
    SRT字幕ファイルと文字起こしJSONを生成する。

    Args:
        script_data: script_gen が返した台本データ全体
        scenes: actual_duration_sec が追加済みの scenes リスト
        output_dir: 出力先ディレクトリ

    Returns:
        {"srt_path": Path, "transcript_path": Path}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}

    # SRT生成
    srt_path = output_dir / "subtitles.srt"
    _generate_srt(scenes, srt_path)
    result["srt_path"] = srt_path
    print(f"  字幕ファイル生成完了: {srt_path.name}")

    # 文字起こしJSON生成
    transcript_path = output_dir / "transcript.json"
    _generate_transcript_json(script_data, scenes, transcript_path)
    result["transcript_path"] = transcript_path
    print(f"  文字起こしJSON生成完了: {transcript_path.name}")

    return result


def _generate_srt(scenes: list, output_path: pathlib.Path):
    """SRT形式の字幕ファイルを生成する。"""
    lines = []
    current_time = 0.0

    for i, scene in enumerate(scenes):
        idx = i + 1
        text = scene.get("text", "")
        duration = scene.get("actual_duration_sec", scene.get("duration_sec", 3))

        if not text:
            current_time += duration
            continue

        start = current_time
        end = current_time + duration

        # SRT タイムスタンプ形式: HH:MM:SS,mmm
        start_ts = _format_srt_time(start)
        end_ts = _format_srt_time(end)

        # 長いテキストを40文字で改行
        wrapped = "\n".join(textwrap.wrap(text, width=40))

        lines.append(f"{idx}")
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(wrapped)
        lines.append("")  # 空行

        current_time = end

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _generate_transcript_json(
    script_data: dict,
    scenes: list,
    output_path: pathlib.Path,
):
    """文字起こしJSON を生成する。"""
    transcript = {
        "title": script_data.get("title", ""),
        "topic": script_data.get("topic", ""),
        "description": script_data.get("description", ""),
        "tags": script_data.get("tags", []),
        "total_duration_sec": sum(s.get("actual_duration_sec", 0) for s in scenes),
        "scenes": [],
    }

    current_time = 0.0
    for scene in scenes:
        duration = scene.get("actual_duration_sec", scene.get("duration_sec", 0))
        transcript["scenes"].append({
            "role": scene.get("role", ""),
            "text": scene.get("text", ""),
            "slide_text": scene.get("slide_text", ""),
            "photo_asset": scene.get("photo_asset", ""),
            "start_sec": round(current_time, 2),
            "end_sec": round(current_time + duration, 2),
            "duration_sec": round(duration, 2),
        })
        current_time += duration

    output_path.write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _format_srt_time(seconds: float) -> str:
    """秒数を SRT タイムスタンプ形式 (HH:MM:SS,mmm) に変換する。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

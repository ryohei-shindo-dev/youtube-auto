"""音声APIを使わずにShorts台本を確認するためのプレビューCLI."""
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime

from dotenv import load_dotenv

import scene_linter
import script_gen
import style_rules

SCRIPT_DIR = pathlib.Path(__file__).parent
PREVIEW_DIR = SCRIPT_DIR / "outputs" / "previews"

load_dotenv(SCRIPT_DIR / ".env")


def _build_preview_payload(topic: str, theme: str, script_data: dict) -> dict:
    style_issues = style_rules.lint_script(script_data)
    scene_issues = scene_linter.lint_all_scenes(script_data)
    return {
        "generated_at": datetime.now().isoformat(),
        "topic": topic,
        "theme": theme,
        "title": script_data.get("title", ""),
        "description": script_data.get("description", ""),
        "tags": script_data.get("tags", []),
        "scenes": script_data.get("scenes", []),
        "style_issues": style_issues,
        "scene_issues": scene_issues,
    }


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"\s+", "-", value.strip().lower())
    slug = re.sub(r"[^a-z0-9_\-\u3040-\u30ff\u3400-\u9fff]+", "-", slug).strip("-")
    return slug or "preview"


def _save_preview(payload: dict) -> pathlib.Path:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = PREVIEW_DIR / f"{timestamp}_{_slugify(payload['topic'])}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _render_preview(payload: dict) -> str:
    lines = [
        f"タイトル: {payload['title']}",
        f"トピック: {payload['topic']}",
        f"テーマ: {payload['theme']}",
        "",
    ]
    for index, scene in enumerate(payload.get("scenes", []), 1):
        lines.append(
            f"{index}. {scene.get('role', '')}: "
            f"text=\"{scene.get('text', '')}\" / "
            f"slide=\"{scene.get('slide_text', '')}\""
        )

    lines.append("")
    lines.append(f"scene_issues: {len(payload.get('scene_issues', []))}")
    for issue in payload.get("scene_issues", []):
        lines.append(
            f"- {issue.get('level')} {issue.get('role')} {issue.get('code')}: {issue.get('message')}"
        )

    lines.append(f"style_issues: {len(payload.get('style_issues', []))}")
    for issue in payload.get("style_issues", []):
        lines.append(
            f"- {issue.get('level')} {issue.get('field')} {issue.get('rule')}: {issue.get('found')}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="音声APIを使わないShorts台本プレビュー")
    parser.add_argument("--topic", required=True, help="確認したいトピック")
    parser.add_argument("--theme", default="ガチホモチベ", help="テーマ名")
    parser.add_argument("--save-only", action="store_true", help="標準出力を抑制してJSON保存のみ行う")
    args = parser.parse_args()

    script_data = script_gen.generate_shorts_script(args.topic, theme=args.theme)
    if not script_data:
        raise SystemExit(1)

    payload = _build_preview_payload(args.topic, args.theme, script_data)
    path = _save_preview(payload)

    if not args.save_only:
        print(_render_preview(payload))
        print("")
    print(f"preview_json: {path}")


if __name__ == "__main__":
    main()

"""
build_manifest.py
note管理シートから note_manifest.json を生成する。

使い方:
    python build_manifest.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re

from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"
MANIFEST_PATH = SCRIPT_DIR / "data" / "manifests" / "note_manifest.json"


def build():
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        raise RuntimeError("YOUTUBE_SHEET_ID が未設定です。")

    # --- シートデータ取得 ---
    service = sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.NOTE_SHEET_NAME}!A:I",
    ).execute()
    rows = result.get("values", [])

    articles = []
    for row in rows[1:]:
        if len(row) < 1 or not row[0]:
            continue
        try:
            no = int(row[0])
        except ValueError:
            continue
        title = row[5] if len(row) > 5 else ""
        url = row[8] if len(row) > 8 else ""
        note_key = ""
        if url:
            m = re.search(r"/n/(n[a-zA-Z0-9]+)", url)
            if m:
                note_key = m.group(1)
        articles.append({
            "sheet_no": no, "sheet_title": title,
            "url": url, "note_key": note_key,
        })
    print(f"シート: {len(articles)}件取得")

    # --- 全 md ファイルの H1 を収集 ---
    md_files = sorted(ARTICLES_DIR.glob("*.md"))
    md_data = []
    for md in md_files:
        with md.open(encoding="utf-8") as f:
            first_line = f.readline()
        h1 = first_line.lstrip("# ").strip()
        rel = str(md.relative_to(SCRIPT_DIR))
        md_data.append({"path": rel, "h1": h1, "used": False})

    # --- note_publish_additional.py から画像マッピング ---
    from note_publish_additional import ARTICLE_SPECS
    spec_title_to_img: dict[str, str] = {}
    for spec in ARTICLE_SPECS:
        img = spec.get("image_path")
        t = spec.get("title", "")
        if img and pathlib.Path(img).exists() and t:
            spec_title_to_img[t] = str(
                pathlib.Path(img).relative_to(SCRIPT_DIR)
            )

    # --- マッチング ---
    manifest = []
    for art in articles:
        sheet_no = art["sheet_no"]
        title = art["sheet_title"]

        # md_path: 段階的に緩い照合
        md_path = _match_md(title, md_data)

        # image_path
        image_path = _match_image(title, md_path, spec_title_to_img)

        manifest.append({
            "sheet_no": sheet_no,
            "note_key": art["note_key"],
            "sheet_title": title,
            "md_path": md_path,
            "image_path": image_path,
            "url": art["url"],
        })

    # --- 保存 ---
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    matched_md = sum(1 for e in manifest if e["md_path"])
    matched_img = sum(1 for e in manifest if e["image_path"])
    print(f"manifest 生成完了: {MANIFEST_PATH.name}")
    print(f"  md対応: {matched_md}/{len(manifest)}")
    print(f"  画像対応: {matched_img}/{len(manifest)}")

    unmatched = [e for e in manifest if not e["md_path"]]
    if unmatched:
        print(f"\n  md未対応（{len(unmatched)}件）:")
        for e in unmatched:
            print(f"    #{e['sheet_no']}: {e['sheet_title'][:50]}")


def _match_md(title: str, md_data: list[dict]) -> str | None:
    """シートタイトルに対応する md ファイルを探す。"""
    if not title:
        return None

    # 1. 完全一致
    for md in md_data:
        if not md["used"] and md["h1"] == title:
            md["used"] = True
            return md["path"]

    # 2. 前方10文字一致
    for md in md_data:
        if not md["used"] and md["h1"][:10] == title[:10]:
            md["used"] = True
            return md["path"]

    # 3. 文字の重なりスコア（大幅にリライトされた場合）
    title_chars = set(title)
    best_score = 0.0
    best_md = None
    for md in md_data:
        if md["used"]:
            continue
        h1_chars = set(md["h1"])
        union = len(title_chars | h1_chars)
        if union == 0:
            continue
        score = len(title_chars & h1_chars) / union
        if score > best_score and score > 0.3:
            best_score = score
            best_md = md

    if best_md:
        best_md["used"] = True
        return best_md["path"]

    return None


def _match_image(
    title: str, md_path: str | None,
    spec_title_to_img: dict[str, str],
) -> str | None:
    """画像パスを探す。"""
    # 1. note_publish_additional のタイトルで照合
    if title:
        for spec_title, img_path in spec_title_to_img.items():
            if spec_title[:12] == title[:12]:
                return img_path

    # 2. md_path から add_XX を推測
    if md_path:
        fname = pathlib.Path(md_path).stem
        if "note_add_" in fname:
            parts = fname.split("_")
            # note_add_XX_title → XX
            if len(parts) >= 3:
                add_num = parts[2]
                candidate = IMAGES_DIR / f"note_add_{add_num}.png"
                if candidate.exists():
                    return str(candidate.relative_to(SCRIPT_DIR))

    return None


if __name__ == "__main__":
    build()

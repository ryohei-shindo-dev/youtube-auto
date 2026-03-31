"""サムネイル生成モジュール.

Shorts サムネイル（1080x1920）とサムネフレーム（動画内埋め込み用）を生成する。
slide_gen.py から分離。
"""
from __future__ import annotations

import json
import pathlib
import random
import re
import textwrap
from functools import lru_cache

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from slide_gen import (
    SHORTS_WIDTH, SHORTS_HEIGHT, PHOTOS_DIR,
    ROLE_PHOTO_CATEGORY, FONT_PATH_HEAVY,
    _fit_photo_to_area, _blend_gradient, _load_font,
)
from thumbnail_gen import _auto_font_size

SCRIPT_DIR = pathlib.Path(__file__).parent

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


def generate_shorts_thumbnail(
    scenes: list,
    output_path: pathlib.Path,
    title: str = "",
) -> pathlib.Path | None:
    """Shortsサムネイル専用画像（縦型1080x1920）を新規生成する。

    動画スライドの流用はしない。
    顔が大きい人物写真 + titleから生成した短いテキスト で構成。
    """
    from PIL import ImageEnhance

    # ── テキスト: titleから短いサムネ専用文を作る ──
    thumb_text = _make_thumbnail_text_v2(title, scenes)
    if not thumb_text:
        return None

    # ── 写真: 縦型で顔が大きい人物写真を優先 ──
    photo = None
    # まず各シーンの写真から縦型を探す
    for photo_role in ("hook", "empathy", "hook", "empathy"):
        for s in scenes:
            if s.get("role") == photo_role and s.get("photo_asset"):
                category = ROLE_PHOTO_CATEGORY.get(photo_role, "anxiety")
                photo_path = PHOTOS_DIR / category / s["photo_asset"]
                if photo_path.exists():
                    try:
                        candidate = Image.open(photo_path)
                        # 縦型写真を優先（横型だと顔が切れる）
                        if candidate.height >= candidate.width:
                            photo = candidate
                            break
                        elif photo is None:
                            photo = candidate  # 横型でもフォールバックとして保持
                    except Exception:
                        continue
        if photo and photo.height >= photo.width:
            break

    # フォールバック: anxietyから縦型写真をランダム取得
    if photo is None or photo.height < photo.width:
        portrait_photos = []
        for cat in ("anxiety", "comparison", "recovery"):
            cat_dir = PHOTOS_DIR / cat
            if cat_dir.exists():
                for p in cat_dir.glob("*.jpg"):
                    try:
                        img = Image.open(p)
                        if img.height >= img.width:
                            portrait_photos.append(p)
                    except Exception:
                        continue
        if portrait_photos:
            selected = random.choice(portrait_photos)
            photo = Image.open(selected)

    if photo is None:
        return None

    # ── サムネ画像を組み立て ──
    photo = photo.convert("RGB")
    photo = _fit_photo_to_area(photo, SHORTS_WIDTH, SHORTS_HEIGHT)

    # 明るさ調整（暗くしすぎない）
    photo = ImageEnhance.Brightness(photo).enhance(0.88)

    # 下部にグラデーション（テキスト読みやすく、でも暗すぎない）
    _blend_gradient(photo, start_y=int(SHORTS_HEIGHT * 0.55),
                    bg_color=(20, 20, 30), exponent=1.2)

    draw = ImageDraw.Draw(photo)

    # テキスト描画（下寄せ中央、2行、太字）
    lines = thumb_text.split("\n")
    font_size = 100 if max(len(l) for l in lines) <= 8 else 80
    font = _load_font(FONT_PATH_HEAVY, font_size)

    # 各行の描画位置を計算
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    gap = 20
    total_h = sum(line_heights) + gap * (len(lines) - 1)
    # 下から30%の位置に配置
    start_y = int(SHORTS_HEIGHT * 0.65) - total_h // 2

    for i, line in enumerate(lines):
        x = (SHORTS_WIDTH - line_widths[i]) // 2
        y = start_y + i * (line_heights[0] + gap)
        # 1行目は黄色（強調）、2行目は白
        color = (240, 200, 60) if i == 0 else (255, 255, 255)
        draw.text((x, y), line, font=font, fill=color,
                  stroke_width=5, stroke_fill=(0, 0, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(str(output_path), "PNG", optimize=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  サムネイル生成完了: {output_path.name}（{size_kb}KB）")
    return output_path


def _make_thumbnail_text(title: str, scenes: list) -> str:
    """タイトルからサムネ用見出しを再構成する（2行、各行14文字以内）。

    タイトルを機械的に切るのではなく、主題語を抽出して見出しを作り直す。
    """
    if not title:
        return ""

    # タイトルから「|」「｜」「#Shorts」以降を除去
    clean = title.split("|")[0].split("｜")[0].split("#")[0].strip()
    clean = clean.rstrip("。、！？!? ")

    # 短いならそのまま
    if len(clean) <= 10:
        return clean

    # 1. 句読点で自然に2行に分割できるか
    for sep in ["。", "、", "…", "―"]:
        if sep in clean:
            parts = clean.split(sep, 1)
            line1 = parts[0].strip().rstrip("。、 ")
            line2 = parts[1].strip().rstrip("。、 ") if len(parts) > 1 else ""
            if line1 and line2 and len(line1) <= 14 and len(line2) <= 14:
                return f"{line1}\n{line2}"
            if line1 and len(line1) <= 14:
                return line1

    # 2. dataのslide_text（各動画固有の数字データ、意味が通りやすい）
    for s in scenes:
        if s.get("role") == "data" and s.get("slide_text"):
            data_text = s["slide_text"].rstrip("。")
            if len(data_text) <= 14:
                return data_text

    # 3. タイトルの助詞で自然に区切る
    for m in re.finditer(r"[をにでとは]", clean):
        pos = m.end()
        if 6 <= pos <= 14:
            return clean[:pos]

    # 4. resolveのslide_text（結論、ただしempathyは使わない）
    for s in scenes:
        if s.get("role") == "resolve" and s.get("slide_text"):
            resolve_text = s["slide_text"].rstrip("。")
            if len(resolve_text) <= 14:
                return resolve_text

    # 5. hookのslide_text
    for s in scenes:
        if s.get("role") == "hook" and s.get("slide_text"):
            hook_text = s["slide_text"].rstrip("。")
            if len(hook_text) <= 14:
                return hook_text

    return clean[:14]


# ── サムネフレーム（動画内埋め込み用） ──────────────────────

THUMBNAIL_DIR = PHOTOS_DIR / "thumbnail"
THUMBNAIL_REGISTRY_PATH = SCRIPT_DIR / "data" / "manifests" / "thumbnail_registry.json"
_THUMBNAIL_NO_REUSE_WINDOW = 30  # 直近30本で同じ写真を使わない


def _normalize_thumb_text(text: str) -> str:
    """サムネテキストを正規化して類似判定に使う。

    改行除去 + 文末の「です」「だ」「ですね」等を除去して比較する。
    例: 「時間が最大の武器です」→「時間が最大の武器」
    """
    t = text.replace("\n", "")
    # 文末の丁寧表現・断定表現を除去（長い順にマッチ）
    for suffix in ("ですね", "です", "だね", "だよ", "だ", "ね", "よ"):
        if t.endswith(suffix) and len(t) > len(suffix) + 2:
            t = t[: -len(suffix)]
            break
    return t


def _load_thumbnail_registry() -> list[dict]:
    """thumbnail_registry.json を読み込む。"""
    if THUMBNAIL_REGISTRY_PATH.exists():
        try:
            return json.loads(THUMBNAIL_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_thumbnail_registry(registry: list[dict]) -> None:
    """thumbnail_registry.json を保存する（直近100件に切り詰め）。"""
    registry = registry[-100:]
    THUMBNAIL_REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _pick_thumbnail_photo(registry: list[dict]) -> pathlib.Path | None:
    """thumbnail/ フォルダからサムネ用写真を1枚選ぶ（直近で使った写真を避ける）。"""
    if not THUMBNAIL_DIR.exists():
        return None

    all_photos = sorted(THUMBNAIL_DIR.glob("*.jpg"))
    if not all_photos:
        return None

    # 縦型写真のみ使用（横型はクロップで被写体が切れるため）
    portrait_photos = []
    for p in all_photos:
        try:
            with Image.open(p) as img:
                if img.height >= img.width:
                    portrait_photos.append(p)
        except Exception:
            continue
    if not portrait_photos:
        return None
    all_photos = portrait_photos

    # 直近N本で使った写真パスを集める
    recent_photos = set()
    for entry in registry[-_THUMBNAIL_NO_REUSE_WINDOW:]:
        p = entry.get("thumbnail_photo", "")
        if p:
            recent_photos.add(pathlib.Path(p).name)

    # 未使用の写真を優先
    available = [p for p in all_photos if p.name not in recent_photos]
    if not available:
        # 全部使い切った場合は最も古い使用のものから再利用
        available = all_photos

    return random.choice(available)


def _make_thumbnail_text_v2(title: str, scenes: list) -> str:
    """タイトルからサムネ用見出しを再構成する（2行、合計10〜18文字）。

    タイトルの「短縮」ではなく、主題語を使った見出しの「再構成」を行う。
    empathyのslide_textへのフォールバックは禁止。
    """
    if not title:
        return ""

    # タイトルから「|」「｜」「#Shorts」以降を除去
    clean = title.split("|")[0].split("｜")[0].split("#")[0].strip()
    clean = clean.rstrip("。、！？!? ")

    # ── 1. 句読点で自然に2行分割 ──
    for sep in ["。", "、", "…", "―"]:
        if sep in clean:
            parts = clean.split(sep, 1)
            line1 = parts[0].strip().rstrip("。、 ")
            line2 = parts[1].strip().rstrip("。、 ") if len(parts) > 1 else ""
            if line1 and line2 and len(line1) <= 12 and len(line2) <= 12:
                total = len(line1) + len(line2)
                if 8 <= total <= 20:
                    return f"{line1}\n{line2}"

    # ── 2. タイトル全体が短ければそのまま ──
    if 10 <= len(clean) <= 18:
        # 助詞で2行に分割を試みる
        for m in re.finditer(r"[をにでとはがも]", clean):
            pos = m.end()
            if 4 <= pos <= 12 and 4 <= len(clean) - pos <= 12:
                return f"{clean[:pos]}\n{clean[pos:]}"
        # 分割できなければ1行で
        if len(clean) <= 12:
            return clean

    # ── 3. タイトルから主題語を抽出して2行に再構成 ──
    # dataのslide_text（各動画固有の数字データ）
    data_text = ""
    for s in scenes:
        if s.get("role") == "data" and s.get("slide_text"):
            data_text = s["slide_text"].rstrip("。")
            break

    # hookのslide_text
    hook_text = ""
    for s in scenes:
        if s.get("role") == "hook" and s.get("slide_text"):
            hook_text = s["slide_text"].rstrip("。")
            break

    # resolveのslide_text
    resolve_text = ""
    for s in scenes:
        if s.get("role") == "resolve" and s.get("slide_text"):
            resolve_text = s["slide_text"].rstrip("。")
            break

    # ── 3a. dataテキストが使えるなら、hook+dataの組み合わせ ──
    # ただし hookがdataに含まれる場合は文言重複になるのでスキップ
    if data_text and hook_text and len(hook_text) <= 12 and len(data_text) <= 12:
        if hook_text not in data_text and data_text not in hook_text:
            total = len(hook_text) + len(data_text)
            if 8 <= total <= 20:
                return f"{hook_text}\n{data_text}"

    # ── 3b. dataテキスト単体（14文字以内で意味が通る） ──
    if data_text and 6 <= len(data_text) <= 14:
        return data_text

    # ── 3c. 助詞でタイトルを区切る ──
    for m in re.finditer(r"[をにでとはがも]", clean):
        pos = m.end()
        line1 = clean[:pos]
        line2 = clean[pos:]
        if 4 <= len(line1) <= 12 and 4 <= len(line2) <= 12:
            total = len(line1) + len(line2)
            if 8 <= total <= 20:
                return f"{line1}\n{line2}"

    # ── 3d. resolveテキスト（結論）── ただしempathyは使わない
    if resolve_text and 6 <= len(resolve_text) <= 14:
        return resolve_text

    # ── 4. フォールバック: タイトル先頭14文字 ──
    if len(clean) > 14:
        # 助詞の位置で切る
        for m in re.finditer(r"[をにでとはがも]", clean[:15]):
            pos = m.end()
            if 6 <= pos:
                return clean[:pos]
        return clean[:14]

    return clean


# ========== サムネフレーム用 禁則処理 ==========
# ChatGPT組版レビュー（2026-03-19）に基づく

# 行頭禁止文字（句読点・閉じ括弧・助詞・機能語の一部）
_NO_HEAD_CHARS = set("、。，．・：；！？）」』】〉》!?,.)]}%‰+をにへとがはもでの")

# 行末禁止文字（開き括弧・「第」「約」など）
_NO_TAIL_CHARS = set("（「『【〈《([{第約っッ")

# 2行目先頭に来てはいけない2文字機能語
_NO_HEAD_BIGRAMS = {
    "より", "では", "とは", "にも", "でも", "への",
    "から", "まで", "だけ", "ほど", "など", "のは",
}

# 分割してはいけないパターン（数字+単位・分数・英数字語）
_NO_SPLIT_PATTERNS = re.compile(
    r"\d+/\d+"                                       # 分数 1/3
    r"|\d+\.\d+"                                     # 小数 2.5
    r"|\d+(?:年目|ヶ月目|か月目|年|ヶ月|か月|月|日|時間"
    r"|分|秒|回|人|倍|割|％|%|万|億|円|ドル|点|歳|代|本|枚|件)"  # 数字+単位
    r"|[+\-]\d+[%％]?"                               # +40%, -3%
    r"|S&P500|NASDAQ100|NISA|iDeCo"                  # 英数字混在語
)

# 3文字以上のカタカナ語（途中で切らない）
_KATAKANA_WORD = re.compile(r"[ァ-ヶー]{3,}")

# 保護語辞書（複合語の途中で切らない）
_PROTECTED_WORDS = [
    "非課税効果", "元本割れ", "長期投資家", "長期投資", "積み立て",
    "積立投資", "配当再投資", "信託報酬", "平均取得単価",
    "ドルコスト平均法", "インデックス投資", "インフレ",
    "レバレッジ", "リターン", "バフェット", "資産", "複利",
]

# 各行の最小文字数
_MIN_LINE_CHARS = 5


def _find_split_pos(text: str) -> int | None:
    """テキストの適切な分割位置を返す。禁則処理付き。

    ChatGPT組版レビューに基づく3段方式:
    1. 絶対に切らない塊を守る
    2. 切るなら助詞・読点の直後だけに寄せる
    3. 不自然に短い行を禁止する
    """
    n = len(text)
    if n <= 6:
        return None

    # --- 分割禁止区間を収集 ---
    no_split: set[int] = set()

    # 数字+単位、英数字語（内部での分割のみ禁止、直前での分割は許可）
    for m in _NO_SPLIT_PATTERNS.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)

    # カタカナ語
    for m in _KATAKANA_WORD.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)

    # 保護語辞書（内部での分割のみ禁止、直前での分割は許可）
    for word in _PROTECTED_WORDS:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx == -1:
                break
            for i in range(idx + 1, idx + len(word)):
                no_split.add(i)
            start = idx + 1

    # 2文字機能語の途中分割を禁止
    for bigram in _NO_HEAD_BIGRAMS:
        start = 0
        while True:
            idx = text.find(bigram, start)
            if idx == -1:
                break
            # bigram の途中（idx + 1）での分割を禁止
            no_split.add(idx + 1)
            start = idx + 1

    def _is_valid_split(pos: int) -> bool:
        """pos の位置で分割したとき、禁則違反がないか。"""
        if pos <= 0 or pos >= n:
            return False
        # 各行の最小文字数チェック
        if pos < _MIN_LINE_CHARS or (n - pos) < _MIN_LINE_CHARS:
            return False
        # 分割禁止区間の途中でないか
        if pos in no_split:
            return False
        # 2行目の先頭が行頭禁止文字でないか
        if text[pos] in _NO_HEAD_CHARS:
            return False
        # 2行目の先頭が2文字機能語でないか
        if text[pos:pos + 2] in _NO_HEAD_BIGRAMS:
            return False
        # 1行目の末尾が行末禁止文字でないか
        if text[pos - 1] in _NO_TAIL_CHARS:
            return False
        return True

    # --- 候補を集めてスコア付け（中央に近いほど良い） ---
    center = n // 2
    best_pos = None
    best_score = float("inf")

    # 1. 助詞・読点の後で分割（最も自然）
    for m in re.finditer(r"[をにとがの、]|(?<=[ぁ-んァ-ヶ\u4e00-\u9fff0-9])[でもは]", text):
        pos = m.end()
        if _is_valid_split(pos):
            score = abs(center - pos)
            if score < best_score:
                best_score = score
                best_pos = pos

    if best_pos is not None:
        return best_pos

    # 2. 助詞がない場合: 中央付近の有効位置で分割（サムネ用フォールバック）
    for dist in range(n):
        for pos in [center + dist, center - dist]:
            if 0 < pos < n and _is_valid_split(pos):
                return pos

    return None


def _split_long_lines_for_thumb(
    lines: list[str], draw, max_width: int,
) -> list[str]:
    """はみ出す行を自動改行で分割する。禁則処理付き。

    9文字以上の1行テキストは強制分割（インスタグリッドで縮小表示されるため）。
    """
    result = []
    for line in lines:
        # 12文字以上の行は幅に収まっていても分割を試みる（フォント縮小防止）
        # 9→12に引き上げ: 行数が増えるとフォントが小さくなりIG grid で読めなくなるため
        needs_split = len(line) >= 12

        if not needs_split:
            # 12文字未満は分割せず、generate_thumbnail_frame のフォント縮小ループに任せる
            result.append(line)
            continue

        if needs_split:
            # サムネ用: 最小文字数を緩和して分割（通常の禁則処理は厳しすぎる）
            split_pos = _find_split_pos_for_thumb(line)
            if split_pos is not None:
                result.append(line[:split_pos].strip())
                result.append(line[split_pos:].strip())
            else:
                result.append(line)

    return result


def _find_split_pos_for_thumb(text: str) -> int | None:
    """サムネ用の緩い分割位置検索。最小3文字、中央寄りで分割。"""
    n = len(text)
    if n <= 6:
        return None

    min_chars = 3  # サムネ用は3文字から許可
    center = n // 2

    # 分割禁止区間を収集（内部のみ）
    no_split: set[int] = set()
    for m in _NO_SPLIT_PATTERNS.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)
    for m in _KATAKANA_WORD.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)
    for word in _PROTECTED_WORDS:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx == -1:
                break
            for i in range(idx + 1, idx + len(word)):
                no_split.add(i)
            start = idx + 1

    def _ok(pos: int) -> bool:
        if pos < min_chars or (n - pos) < min_chars:
            return False
        if pos in no_split:
            return False
        if text[pos] in _NO_HEAD_CHARS:
            return False
        return True

    # 1. 助詞・読点の後（最も自然）
    best_pos = None
    best_score = float("inf")
    for m in re.finditer(r"[をにとがの、]|(?<=[ぁ-んァ-ヶ\u4e00-\u9fff0-9])[でもは]", text):
        pos = m.end()
        if _ok(pos):
            score = abs(center - pos)
            if score < best_score:
                best_score = score
                best_pos = pos

    if best_pos is not None:
        return best_pos

    # 2. 中央付近の任意位置
    for dist in range(n):
        for pos in [center + dist, center - dist]:
            if 0 < pos < n and _ok(pos):
                return pos

    return None


def generate_thumbnail_frame(
    scenes: list,
    output_path: pathlib.Path,
    title: str = "",
    used_texts: list[str] | None = None,
) -> dict | None:
    """サムネフレーム画像を生成する（動画先頭に埋め込み用）。

    Returns:
        {"path": output_path, "text": thumb_text, "photo": photo_name}
        失敗時は None。
    """
    registry = _load_thumbnail_registry()

    # ── テキスト生成 ──
    thumb_text = _make_thumbnail_text_v2(title, scenes)
    if not thumb_text:
        print("  [サムネフレーム] テキスト生成失敗")
        return None

    # サムネテキスト重複チェック（バッチ内 + レジストリの過去100本）
    all_existing: set[str] = set()
    # レジストリ（公開済み・キュー内）のテキストを正規化して追加
    for entry in registry:
        if entry.get("thumbnail_text"):
            all_existing.add(_normalize_thumb_text(entry["thumbnail_text"]))
    # バッチ内のテキストも追加
    if used_texts is not None:
        for t in used_texts:
            all_existing.add(_normalize_thumb_text(t))

    if _normalize_thumb_text(thumb_text) in all_existing:
        print(f"  [サムネフレーム] テキスト重複: {thumb_text.replace(chr(10), ' ')}")
        # data → resolve → hookの順でフォールバック
        for role in ("data", "resolve", "hook"):
            for s in scenes:
                if s.get("role") == role and s.get("slide_text"):
                    alt = s["slide_text"].rstrip("。")
                    if 6 <= len(alt) <= 14 and _normalize_thumb_text(alt) not in all_existing:
                        thumb_text = alt
                        break
            else:
                continue
            break

    # ── 写真選択 ──
    photo_path = _pick_thumbnail_photo(registry)
    if not photo_path:
        print("  [サムネフレーム] サムネ用写真がありません（assets/photos/thumbnail/）")
        return None

    # ── 画像生成 ──
    photo = Image.open(photo_path).convert("RGB")
    photo = _fit_photo_to_area(photo, SHORTS_WIDTH, SHORTS_HEIGHT)
    photo = ImageEnhance.Brightness(photo).enhance(0.88)
    _blend_gradient(photo, start_y=int(SHORTS_HEIGHT * 0.55),
                    bg_color=(20, 20, 30), exponent=1.2)

    draw = ImageDraw.Draw(photo)

    # テキスト描画（1行目は大きく、2行目はやや小さく — thumbnail_gen と同方式）
    # 左右マージン確保（テキストが画面幅をはみ出さないように）
    text_max_width = SHORTS_WIDTH - 80  # 左右40pxずつ余白

    # はみ出す行を自動改行で分割
    lines = _split_long_lines_for_thumb(thumb_text.split("\n"), draw, text_max_width)

    fonts = []
    for i, line in enumerate(lines):
        if i == 0:
            sz = _auto_font_size(line, max_size=160, min_size=110)
        else:
            sz = _auto_font_size(line, max_size=130, min_size=90)
        # 改行で収まらなかった場合のフォールバック: フォントサイズ縮小
        while sz > 80:
            font = _load_font(FONT_PATH_HEAVY, sz)
            bbox = draw.textbbox((0, 0), line, font=font)
            if (bbox[2] - bbox[0]) <= text_max_width:
                break
            sz -= 4
        fonts.append(_load_font(FONT_PATH_HEAVY, sz))

    line_heights = []
    line_widths = []
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=fonts[i])
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    gap = 24
    total_h = sum(line_heights) + gap * (len(lines) - 1)
    start_y = int(SHORTS_HEIGHT * 0.65) - total_h // 2

    cur_y = start_y
    for i, line in enumerate(lines):
        x = (SHORTS_WIDTH - line_widths[i]) // 2
        color = (240, 200, 60) if i == 0 else (255, 255, 255)
        draw.text((x, cur_y), line, font=fonts[i], fill=color,
                  stroke_width=5, stroke_fill=(0, 0, 0))
        cur_y += line_heights[i] + gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(str(output_path), "PNG", optimize=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  サムネフレーム生成: {thumb_text.replace(chr(10), ' / ')}（{size_kb}KB）")

    # ── レジストリ更新 ──
    from datetime import datetime
    registry.append({
        "thumbnail_photo": photo_path.name,
        "thumbnail_text": thumb_text,
        "generated_at": datetime.now().isoformat(),
    })
    _save_thumbnail_registry(registry)

    return {
        "path": str(output_path),
        "text": thumb_text,
        "photo": photo_path.name,
    }

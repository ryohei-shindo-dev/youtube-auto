"""
queue_guard.py — キュー投入前の重複・偏りチェック

公開済み+キュー内の data シーンと比較し、
exact重複・数字構造重複・意味カテゴリ偏りを検出する。

使い方:
    from queue_guard import DataRegistry, check_candidate
    registry = DataRegistry()           # done/ + publish_queue.json を読み込み
    result = check_candidate(script_data, registry)
    if not result["ok"]:
        print(result["reason"])
    else:
        registry.register(script_data, folder_name)  # 採用時にレジストリ追加
"""
from __future__ import annotations

import json
import pathlib
import re

from style_rules import normalize_text

SCRIPT_DIR = pathlib.Path(__file__).parent
DONE_DIR = SCRIPT_DIR / "done"
QUEUE_PATH = SCRIPT_DIR / "data" / "queues" / "publish_queue.json"

# 数字+単位の抽出パターン
_RE_NUMERIC = re.compile(r"\d+[万億千百円%％年ヶ月倍本歳日回件人割分]*")

# semantic bucket 判定用キーワード
_BUCKET_KEYWORDS: dict[str, list[str]] = {
    "複利差分": ["年7%", "年5%", "倍", "複利", "元本", "加速", "後半"],
    "非課税差分": ["NISA", "非課税", "iDeCo", "税"],
    "機会損失": ["逃す", "やめた", "売った", "手放した", "離れ", "解約"],
    "元本割れ": ["元本割れ", "勝率", "全員プラス"],
    "継続優位": ["続けた", "持ち続け", "長く", "忘れ", "見ない"],
    "暴落回復": ["暴落", "回復", "恐慌", "リーマン", "コロナ", "恐怖指数"],
    "心理統計": ["口座", "見る", "感情", "焦", "8割", "冷静"],
    "比較事実": ["プロ", "個別株", "インデックス", "レバレッジ", "仮想通貨",
                "年収", "隣", "比べ", "生存者"],
    "金額試算": ["万円", "500万", "250万", "130万", "6000万", "1000万",
               "月1万", "月3万", "月5000", "100円"],
}

# 同一 semantic bucket の近接許容距離
BUCKET_PROXIMITY_LIMIT = 5

# hook stem の近接許容距離
HOOK_PROXIMITY_LIMIT = 10


def _extract_exact_key(text: str) -> str:
    """data textから正規化された完全一致キーを作る。"""
    normalized = normalize_text(text)
    # 句読点・スペースを除去
    return re.sub(r"[。、？！!?\s　]", "", normalized)


def _extract_numeric_pattern(text: str) -> str:
    """data textから数字+単位パターンを抽出する。"""
    matches = _RE_NUMERIC.findall(text)
    # 1桁だけの数字は除外
    return "_".join(m for m in matches if len(m) >= 2)


def _classify_bucket(text: str) -> str:
    """data textを意味カテゴリに分類する。"""
    for bucket, keywords in _BUCKET_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return bucket
    return "other"


def _extract_hook_stem(script_data: dict) -> str:
    """hookのテキストから句読点を除いた語幹を取る。"""
    for s in script_data.get("scenes", []):
        if s.get("role") == "hook":
            return re.sub(r"[。、？！!?\s　]", "", s.get("text", ""))
    return ""


def _extract_data_text(script_data: dict) -> str:
    """script_dataからdataシーンのtextを取得。"""
    for s in script_data.get("scenes", []):
        if s.get("role") in ("data", "fact"):
            return s.get("text", "")
    return ""


class DataRegistry:
    """公開済み+キュー内のdata情報を保持するレジストリ。"""

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self._load_queue_scripts()

    def _load_queue_scripts(self) -> None:
        """publish_queue.json のフォルダを読み込む。"""
        if not QUEUE_PATH.exists():
            return
        queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        for i, folder in enumerate(queue):
            t_path = DONE_DIR / folder / "transcript.json"
            if not t_path.exists():
                continue
            try:
                data = json.loads(t_path.read_text(encoding="utf-8"))
                self._add_entry(data, folder, position=i)
            except (json.JSONDecodeError, KeyError):
                continue

    def _add_entry(self, script_data: dict, folder: str, position: int) -> None:
        data_text = _extract_data_text(script_data)
        if not data_text:
            return
        self.entries.append({
            "folder": folder,
            "position": position,
            "exact_key": _extract_exact_key(data_text),
            "numeric_pattern": _extract_numeric_pattern(data_text),
            "bucket": _classify_bucket(data_text),
            "hook_stem": _extract_hook_stem(script_data),
            "data_text": data_text,
        })

    def register(self, script_data: dict, folder: str) -> None:
        """採用した台本をレジストリに追加する。"""
        position = len(self.entries)
        self._add_entry(script_data, folder, position)


def check_candidate(script_data: dict, registry: DataRegistry) -> dict:
    """新規台本をレジストリと照合し、重複・偏りを判定する。

    Returns:
        {"ok": bool, "level": str, "reason": str, "details": dict}
    """
    data_text = _extract_data_text(script_data)
    if not data_text:
        return {"ok": True, "level": "pass", "reason": "", "details": {}}

    candidate_exact = _extract_exact_key(data_text)
    candidate_numeric = _extract_numeric_pattern(data_text)
    candidate_bucket = _classify_bucket(data_text)
    candidate_hook = _extract_hook_stem(script_data)

    details: dict = {}

    # 1. exact_key 完全一致 → 即却下
    for entry in registry.entries:
        if entry["exact_key"] == candidate_exact:
            details["exact_match"] = entry["folder"]
            return {
                "ok": False,
                "level": "reject",
                "reason": f"dataが完全一致: 「{data_text[:30]}」（{entry['folder']}）",
                "details": details,
            }

    # 2. numeric_pattern 一致 → 強い警告
    if candidate_numeric:
        for entry in registry.entries:
            if entry["numeric_pattern"] == candidate_numeric and entry["numeric_pattern"]:
                details["numeric_match"] = entry["folder"]
                return {
                    "ok": False,
                    "level": "strong_warning",
                    "reason": (f"dataの数字構造が一致: {candidate_numeric}"
                               f"（{entry['folder']}: {entry['data_text'][:30]}）"),
                    "details": details,
                }

    # 3. semantic bucket 近接チェック
    tail_entries = registry.entries[-BUCKET_PROXIMITY_LIMIT:]
    for entry in tail_entries:
        if entry["bucket"] == candidate_bucket and candidate_bucket != "other":
            details["bucket_conflict"] = entry["folder"]
            return {
                "ok": True,
                "level": "warning",
                "reason": (f"同じカテゴリ「{candidate_bucket}」が近接"
                           f"（{entry['folder']}）"),
                "details": details,
            }

    # 4. hook stem 近接チェック
    if candidate_hook:
        tail_hooks = registry.entries[-HOOK_PROXIMITY_LIMIT:]
        for entry in tail_hooks:
            if entry["hook_stem"] == candidate_hook:
                details["hook_stem_match"] = entry["folder"]
                return {
                    "ok": True,
                    "level": "warning",
                    "reason": f"hookが近接で重複: 「{candidate_hook}」（{entry['folder']}）",
                    "details": details,
                }

    return {"ok": True, "level": "pass", "reason": "", "details": {}}


def format_report(result: dict) -> str:
    """判定結果を人間が読める文字列に変換する。"""
    if result["level"] == "pass":
        return "キューチェック: OK"
    mark = {"reject": "❌", "strong_warning": "🟠", "warning": "⚠"}.get(
        result["level"], "?"
    )
    return f"キューチェック: {mark} {result['reason']}"

"""Shorts → 長尺動画のマッピングロジック.

Shortsのトピック/タイトルから、関連動画として設定すべき長尺動画を選定する。
playlists.json の既存マッピングを基盤にしつつ、長尺動画のキーワードで照合する。
"""
from __future__ import annotations

import json
import pathlib

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent

# 長尺動画のマッピング: video_id → キーワードリスト
# キーワードの一致数が多い長尺を選定する
LONG_VIDEO_MAP: dict[str, dict] = {
    "othACgQKmt8": {
        "title": "含み損がつらい夜に聞く、静かな整理",
        "keywords": ["含み損", "不安", "眠れない"],
    },
    "tVxLD4myubY": {
        "title": "積み立て3年目が一番つらい理由",
        "keywords": ["積み立て", "増えない", "3年", "つらい", "報われ", "待て", "やめ"],
    },
    "MLQx3Ne_AmM": {
        "title": "オルカンとS&P500で揺れる人へ",
        "keywords": ["オルカン", "S&P", "比較", "比べ", "SNS", "焦", "迷"],
    },
    "pDIRnONqzMg": {
        "title": "高配当株とインデックスで揺れる人へ",
        "keywords": ["配当", "含み益", "利確", "乗り換え"],
    },
    "4fOghz-cNgU": {
        "title": "一括投資か積立投資かで揺れる人へ",
        "keywords": ["一括", "積立", "NISA", "非課税", "1800万"],
    },
    "mEgLWQdCec4": {
        "title": "暴落で売ると何を失うのか",
        "keywords": ["暴落", "売りたい", "退場", "元本割れ", "売っ"],
    },
    "GkOGhfTHLeY": {
        "title": "取り崩しが怖い人へ",
        "keywords": ["取り崩し", "出口", "老後", "65歳", "退職"],
    },
}

# フォールバック: どのキーワードにもマッチしない場合
DEFAULT_LONG_VIDEO_ID = "MLQx3Ne_AmM"  # 最も再生数が多いオルカンvsS&P500


def select_related_video(title: str, topic: str = "") -> str:
    """Shortsのタイトル+トピックから最適な長尺動画IDを返す。"""
    text = f"{topic} {title}"

    best_id = DEFAULT_LONG_VIDEO_ID
    best_score = 0

    for vid, info in LONG_VIDEO_MAP.items():
        score = sum(1 for kw in info["keywords"] if kw in text)
        if score > best_score:
            best_score = score
            best_id = vid

    return best_id


def get_long_video_title(video_id: str) -> str:
    """長尺動画IDからタイトルを返す。"""
    info = LONG_VIDEO_MAP.get(video_id)
    return info["title"] if info else video_id

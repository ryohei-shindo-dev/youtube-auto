"""
theme_selector.py — テーマ自動選定

analytics_insights.json の分析結果から、次に作るべきトピック候補を
自動生成し、Google Sheets に追加する。

仕組み:
  1. insights から「強いパターン」を抽出（数字、痛みワード、テーマ傾向）
  2. 上位動画の共通点からテーマの優先度を決定
  3. 痛みワード × 数字パターン × テーマの組み合わせで候補を生成
  4. dedupe_check で既存動画との重複を排除
  5. シートに「未生成」として追加

使い方:
    python theme_selector.py                  # 候補10件を生成・表示
    python theme_selector.py --count 5        # 候補5件
    python theme_selector.py --add            # シートに追加
    python theme_selector.py --count 5 --add  # 5件をシートに追加
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

from script_gen import STRONG_HOOKS as PAIN_WORDS, load_insights as _load_insights

SCRIPT_DIR = pathlib.Path(__file__).parent
TOPICS_FILE = SCRIPT_DIR / "topics.json"

# --- 強い数字パターン ---
NUMBER_PATTERNS = [
    "1800万円", "500万円", "3000万円", "100万円", "2000万円",
    "3年", "5年", "10年", "20年", "30年",
    "月3万円", "月1万円", "月5000円", "100円",
    "年利7%", "年利5%", "平均10%",
    "55%暴落", "25%リターン", "95%の確率",
]

# --- テーマ別トピックテンプレート ---
# 痛みワード + 数字 + テーマを組み合わせて新しいトピックを生成
# テンプレートは (テンプレート文字列, 使う変数の種類) のタプル
# kind: "pain_money" = 痛み×金額, "pain_time" = 痛み×期間, "money" = 金額のみ, "pain" = 痛みのみ
TOPIC_TEMPLATES = [
    # 痛みワード × 金額
    ("{pain_de}{money}失った人へ｜それでもガチホする理由", "pain_money"),
    ("{money}投資して{pain}を乗り越えた人の共通点", "pain_money"),
    ("{money}投資して{pain_adj}人へ｜歴史が教える真実", "pain_money"),
    # 痛みワード × 期間
    ("{pain_de}も{time}持ち続けた結果", "pain_time"),
    ("{time}の{pain}に耐えた人だけが知っていること", "pain_time"),
    # 金額 × 期間
    ("{money}を{time}続けたら資産はいくらになる？", "money_time"),
    ("{money}からの積立で人生が変わる理由", "money"),
    # 痛みのみ
    ("{pain_adj}夜に思い出してほしいデータ", "pain"),
    ("{pain_adj}人ほど長期投資に向いている理由", "pain"),
]

# 痛みワードの「で」助詞形（名詞系は「で」、形容詞系は「くて」）
_PAIN_DE_MAP = {
    "含み損": "含み損で", "暴落": "暴落で", "退場": "退場で",
    "損した": "損して", "溶けた": "溶けて",
    "つらい": "つらくて", "怖い": "怖くて", "不安": "不安で",
    "眠れない": "眠れなくて", "後悔": "後悔して", "焦る": "焦って",
    "売りたい": "売りたくて",
}

# 痛みワードの形容詞形（「〜な人」に繋がる形）
_PAIN_ADJ_MAP = {
    "含み損": "含み損を抱えている", "暴落": "暴落が怖い",
    "退場": "退場を考えている", "損した": "損した",
    "溶けた": "資産が溶けた", "つらい": "つらい",
    "怖い": "怖い", "不安": "不安な",
    "眠れない": "眠れない", "後悔": "後悔している",
    "焦る": "焦っている", "売りたい": "売りたい",
}

# テーマ（種別）ごとの狙い
THEME_INTENTS = {
    "メリット": "長期投資のメリットを具体的な数字で伝える",
    "格言": "投資家の名言をストーリーで伝える",
    "あるある": "共感で視聴者の心を掴む",
    "歴史データ": "歴史的データで長期投資の正しさを証明",
    "ガチホモチベ": "長期投資を続けるモチベーションを提供",
}


def _load_topics() -> dict:
    """topics.json を読み込む。"""
    try:
        with open(TOPICS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _get_strong_patterns(insights: dict) -> dict:
    """insights から強いパターンを抽出する。"""
    top_videos = insights.get("top_videos", [])
    title_rules = insights.get("title_rules", {})
    strong_hooks = insights.get("strong_hooks", [])

    # 上位動画のタイトルから頻出キーワードを抽出
    top_keywords = []
    for v in top_videos:
        title = v.get("title", "")
        for pain in PAIN_WORDS:
            if pain in title:
                top_keywords.append(pain)
        for num in NUMBER_PATTERNS:
            if num in title:
                top_keywords.append(num)

    return {
        "prefer_numeric": title_rules.get("prefer_numeric_titles", True),
        "prefer_money": title_rules.get("prefer_money_amounts", True),
        "prefer_timeframes": title_rules.get("prefer_specific_timeframes", True),
        "strong_hooks": strong_hooks,
        "top_keywords": top_keywords,
    }


def generate_candidates(count: int = 10) -> list[dict]:
    """テーマ候補を自動生成する。

    戻り値:
        [
            {
                "topic": str,          # トピック文字列
                "theme": str,          # テーマ名（メリット, 格言, etc）
                "intent": str,         # 狙い
                "source": str,         # 生成元（"auto_selector"）
                "priority_reason": str, # 優先度の理由
            },
            ...
        ]
    """
    insights = _load_insights()
    patterns = _get_strong_patterns(insights)

    candidates = []
    used_topics = set()  # 重複排除用

    # --- 戦略1: 痛みワード × 数字のテンプレート組み合わせ ---
    pain_pool = list(PAIN_WORDS)
    # insights の strong_hooks があればそれを優先
    if patterns["strong_hooks"]:
        pain_pool = patterns["strong_hooks"] + pain_pool

    # 数字プール（テンプレートの kind に応じて money / time を使い分ける）
    money_numbers = [n for n in NUMBER_PATTERNS if "万" in n or "円" in n]
    time_numbers = [n for n in NUMBER_PATTERNS if "年" in n or "月" in n]

    # テーマは5つをバランスよく
    themes = list(THEME_INTENTS.keys())
    random.shuffle(themes)

    attempts = 0
    max_attempts = count * 5

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1

        template_str, kind = random.choice(TOPIC_TEMPLATES)
        theme = themes[len(candidates) % len(themes)]

        pain = random.choice(pain_pool)
        pain_de = _PAIN_DE_MAP.get(pain, f"{pain}で")
        pain_adj = _PAIN_ADJ_MAP.get(pain, f"{pain}な")
        money = random.choice(money_numbers)
        time = random.choice(time_numbers)

        fmt = {
            "pain": pain, "pain_de": pain_de, "pain_adj": pain_adj,
            "money": money, "time": time,
        }
        try:
            topic = template_str.format(**fmt)
        except (KeyError, IndexError):
            continue

        # 重複チェック（生成内での重複）
        if topic in used_topics:
            continue
        used_topics.add(topic)

        # 検索キーワードをkindに応じて設定
        if "pain" in kind:
            search_kw = f"{pain}, {money if 'money' in kind else time}"
        else:
            search_kw = f"{money}, {time}" if "time" in kind else money

        reason_parts = []
        if patterns["prefer_numeric"]:
            reason_parts.append("数字入りタイトル推奨")
        if pain in (patterns.get("strong_hooks") or []):
            reason_parts.append(f"強hook「{pain}」使用")
        if any(kw in topic for kw in patterns.get("top_keywords", [])):
            reason_parts.append("上位動画のキーワード含む")

        candidates.append({
            "topic": topic,
            "theme": theme,
            "intent": THEME_INTENTS[theme],
            "source": "auto_selector",
            "search_keywords": search_kw,
            "priority_reason": " / ".join(reason_parts) if reason_parts else "テンプレート生成",
        })

    return candidates


def add_to_sheet(candidates: list[dict]) -> int:
    """候補をシートに「未生成」として追加する。

    戻り値: 追加した件数
    """
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("[エラー] YOUTUBE_SHEET_ID が未設定です。")
        return 0

    service = sheets.get_service()

    # 既存の行数を取得して通番を決定
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A:A",
    ).execute()
    existing_rows = result.get("values", [])
    next_no = len(existing_rows)  # ヘッダー含むのでそのままで次の番号

    # 追加行を作成
    new_rows = []
    for c in candidates:
        new_rows.append([
            next_no,                    # A: No.
            "",                         # B: フォルダ名
            f"Shorts/{c['theme']}",     # C: 種別
            c["topic"],                 # D: トピック
            c["search_keywords"],       # E: 検索KW
            c["intent"],                # F: 狙い
            sheets.STATUS_PENDING,      # G: ステータス
        ])
        next_no += 1

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows},
    ).execute()

    return len(new_rows)


def main():
    parser = argparse.ArgumentParser(description="テーマ自動選定")
    parser.add_argument("--count", type=int, default=10, help="生成する候補数（デフォルト: 10）")
    parser.add_argument("--add", action="store_true", help="シートに追加する")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  テーマ自動選定")
    print(f"  生成候補数: {args.count}")
    print(f"  シート追加: {'する' if args.add else 'しない（表示のみ）'}")
    print(f"{'='*60}\n")

    # insights の読み込み状況
    insights = _load_insights()
    if insights:
        meta = insights.get("meta", {})
        print(f"  [insights] {meta.get('sample_size', 0)}本分析済み（信頼度: {meta.get('confidence', '不明')}）")
    else:
        print("  [insights] 分析データなし → デフォルトルールで生成")

    # 候補生成
    candidates = generate_candidates(args.count)
    print(f"\n  生成された候補: {len(candidates)}件\n")

    for i, c in enumerate(candidates, 1):
        print(f"  {i:3d}. [{c['theme']}] {c['topic']}")
        print(f"       狙い: {c['intent']}")
        print(f"       理由: {c['priority_reason']}")
        print()

    # シート追加
    if args.add:
        added = add_to_sheet(candidates)
        print(f"\n  ✓ {added}件をシートに追加しました。")
    else:
        print("  ※ シートに追加するには --add オプションを付けてください。")

    print()


if __name__ == "__main__":
    main()

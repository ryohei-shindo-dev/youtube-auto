"""
script_gen.py
Claude API で YouTube 用の台本を生成するモジュール。

チャンネル: ガチホのモチベ
コンセプト: 長期投資の継続モチベーション提供

【固定フレーズ】
  挨拶: 「今日もガチホしてますか？」
  結論: 5パターンからランダム選択
  CTA: 「明日もガチホしたい人はチャンネル登録お願いします。」

【Shorts台本構成（5シーン、16〜18秒目標17秒）】
  感情曲線: 不安で掴む → 共感 → データで安心 → 断言・希望 → CTA
  1. hook（3秒）     — 不安ワードで掴む（最初の1.5秒が勝負）
  2. empathy（4秒）  — 共感 + 挨拶「今日もガチホしてますか？」
  3. data（5秒）     — 具体的な数字1つだけ
  4. resolve（4秒）  — 断言フレーズ + 結論
  5. closing（2秒）  — CTA固定

【通常動画台本構成（6シーン、約5分）】
  1. opening（30秒）  — 導入「今日もガチホしてますか？」
  2. theme（30秒）    — 今日のテーマ
  3. data（90秒）     — データ・歴史・格言
  4. explain（90秒）  — 解説
  5. summary（30秒）  — まとめ
  6. closing（30秒）  — 締め

【Shortsテーマローテーション（月〜金）】
  月: メリット / 火: 格言 / 水: あるある / 木: 歴史データ / 金: ガチホモチベ
"""

import json
import os
import pathlib
import random
import re

import anthropic

# --- 分析結果の読み込み ---
INSIGHTS_FILE = pathlib.Path(__file__).parent / "analytics_insights.json"


def load_insights() -> dict:
    """analytics_insights.json を読み込む。ファイルがなければ空辞書。"""
    try:
        with open(INSIGHTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _build_insights_block(insights: dict) -> str:
    """insights辞書からプロンプトに差し込む文字列を生成する。"""
    guidance = insights.get("prompt_guidance", [])
    if not guidance:
        return ""

    meta = insights.get("meta", {})
    confidence = meta.get("confidence", "unknown")
    sample = meta.get("sample_size", 0)

    lines = [
        f"\n━━━ チャンネル分析からの学習結果（{sample}本分析、信頼度: {confidence}） ━━━",
        "以下は過去の動画データから自動抽出されたルール。従え。",
    ]
    for g in guidance:
        lines.append(f"- {g}")
    lines.append("━━━")
    return "\n".join(lines)

# チャンネル設定
CHANNEL_CONCEPT = (
    "チャンネル名「ガチホのモチベ」。"
    "長期投資（インデックス投資など）を続けるモチベーションを提供するチャンネル。"
    "視聴者は長期投資をしている or 始めたばかりの20〜50代。"
    "投資手法の解説ではなく、長期投資を「続けよう」と思える心理的モチベーションを提供する。"
    "個別株の推奨・具体的な投資助言・短期トレード解説は絶対にしない。"
    "視聴後に「長期投資を続けてよかった」「短期売買に手を出さなくてよかった」と思える内容を目指す。"
)

# 語りかけフレーズ（「〜か？」で視聴者に継続を確認する形式）
OPENING_PHRASES = [
    "ガチホしてますか？",
    "まだ残ってますか？",
    "続けてますか？",
    "持ち続けてますか？",
    "今日もガチホしてますか？",
    "まだ持ってますか？",
    "今日も残ってますか？",
]
OPENING_PHRASE = OPENING_PHRASES[0]  # デフォルト（通常動画用）
# Shortsで語りかけフレーズを入れる確率（約3本に1本）
_SHORTS_OPENING_RATIO = 1 / 3
CLOSING_PHRASES_LIST = [
    "明日もガチホしたい人はフォローお願いします。",
    "同じ気持ちの人、コメントで教えてください。",
    "あなたもガチホ仲間ですか？フォローお願いします。",
    "同じ人いますか？コメントで教えてください。",
]
CLOSING_PHRASE = CLOSING_PHRASES_LIST[0]  # デフォルト（通常動画用）

# closingスライドテキスト（CTAに対応）
CLOSING_SLIDE_TEXTS = [
    "明日もガチホしたい人はフォロー",
    "同じ気持ちの人はコメントへ",
    "ガチホ仲間はフォロー",
    "同じ人いますか？コメントへ",
]

# ── ループ再生用closingテンプレート ──
# {hook} にhookワードが埋め込まれる。closing→hookが自然に繋がりループ再生を誘発。
# 名詞系hook用（暴落、含み損、退場…）: 「{hook}でも」が自然
_LOOP_CLOSING_NOUN = [
    ("{hook}でも、ガチホ。フォローお願いします。", "{hook}でも、ガチホ。フォロー"),
    ("{hook}でも、続けよう。フォローお願いします。", "{hook}でも、続けよう。フォロー"),
    ("{hook}でも、売るな。コメントで教えてください。", "{hook}でも、売るな。コメントへ"),
]
# 形容詞系hook用（眠れない、つらい、怖い、虚しい…）: 「{hook}。それでも」が自然
_LOOP_CLOSING_ADJ = [
    ("{hook}。それでもガチホ。フォローお願いします。", "{hook}。それでもガチホ。フォロー"),
    ("{hook}。それでも続けよう。フォローお願いします。", "{hook}。それでも続けよう。フォロー"),
    ("{hook}。それでも売るな。コメントで教えてください。", "{hook}。それでも売るな。コメントへ"),
]
# 共通（どちらでも使える）
_LOOP_CLOSING_COMMON = [
    ("{hook}…それでも持つ。フォローお願いします。", "{hook}…それでも持つ。フォロー"),
]
# 継続モチベ系（hook非再掲・穏やかな締め専用文）
_LOOP_CLOSING_CONTINUATION = [
    ("それでも、今日もそのままでいい。フォローお願いします。", "今日もそのままでいい。フォロー"),
    ("でも、それで十分です。フォローお願いします。", "それで十分です。フォロー"),
    ("焦らなくて大丈夫。コメントで教えてください。", "焦らなくて大丈夫。コメントへ"),
    ("今日も続いています。フォローお願いします。", "今日も続いています。フォロー"),
    ("今夜は変えなくていい。コメントで教えてください。", "今夜は変えなくていい。コメントへ"),
]
# 形容詞・動詞系hookの判定語尾（「暴落」「含み損」等の名詞は非マッチ→NOUN用）
_ADJ_HOOK_ENDINGS = ["ない", "たい", "しい", "つい", "にくい", "づらい"]


def _pick_loop_closing(hook: str, theme_name: str = "") -> tuple:
    """hookの品詞・テーマに応じてループ再生用closingテンプレートを選択する。"""
    # 継続モチベ系: hook非再掲の穏やか専用文
    if theme_name == "継続モチベ系":
        return random.choice(_LOOP_CLOSING_CONTINUATION)
    is_adj = any(hook.endswith(e) for e in _ADJ_HOOK_ENDINGS)
    pool = (_LOOP_CLOSING_ADJ if is_adj else _LOOP_CLOSING_NOUN) + _LOOP_CLOSING_COMMON
    return random.choice(pool)


def _apply_loop_closing(scenes: list, hook_word: str, theme_name: str = "") -> tuple:
    """hookワードからループ再生用closingを生成してscenesに反映する。"""
    tpl_text, tpl_slide = _pick_loop_closing(hook_word, theme_name)
    closing = tpl_text.format(hook=hook_word)
    closing_slide = tpl_slide.format(hook=hook_word)
    for s in scenes:
        if s.get("role") == "closing":
            s["text"] = closing
            s["slide_text"] = _strip_terminal_punctuation(closing_slide)
            break
    return closing, closing_slide

# 結論フレーズ（10パターンからランダム選択）
CONCLUSION_PHRASES = [
    "やっぱり、長期投資しかないですね。",
    "市場に残る人だけが勝ちます。",
    "暴落は、長期投資家の味方です。",
    "時間が、最大の武器です。",
    "退場しない人だけが勝つ。",
    "今日もそのままでいい。",
    "何もしない日にも、意味があります。",
    "変えなかったことも、積み上がっています。",
    "焦らない日が、長期では効いてきます。",
    "続いているなら、それで十分です。",
]

# Shortsテーマ定義（曜日ローテーション）
SHORTS_THEMES = {
    "メリット": "長期投資のメリット（複利、ドルコスト平均法、長期リターン、非課税制度の効果など）",
    "格言": "投資家の名言をストーリーで伝える（バフェット、ボーグル、マンガー等の人生や行動から学ぶ）",
    "あるある": "長期投資あるある（暴落で不安、短期トレードに目移り、含み損で眠れない、SNSに焦るなど共感系）",
    "歴史データ": "歴史データ（過去の暴落と回復、市場の長期成長、具体的な数字やデータ）",
    "ガチホモチベ": "ガチホモチベーション（長期投資を続ける理由、市場にい続ける大切さ、感情に負けない投資）",
}

# 曜日→テーマのマッピング（0=月曜, 4=金曜）
WEEKDAY_THEME = {
    0: "メリット",
    1: "格言",
    2: "あるある",
    3: "歴史データ",
    4: "ガチホモチベ",
}

# ── Shorts テンプレート ──
SHORTS_TEMPLATE = """
あなたは共感動画の台本ライターです。
教育動画は禁止。説明は禁止。ストーリーで感情を動かせ。

これは投資ノウハウチャンネルではない。
投資モチベーションチャンネルだ。
視聴者は不安を抱えている。教えるな。寄り添え。

チャンネル: {concept}
テーマ: {theme_name}（{theme_desc}）
トピック: {topic}

━━━ 最重要: これは「ストーリー」だ ━━━
Shortsは説明動画ではない。15秒の感情ストーリーだ。

理想の流れ:
  痛み → 共感 → 希望の光 → 一撃の断言

悪い例（教育型）:
  「長期投資のリターンは10年以降に加速します」
  「やめた人の9割が上昇を逃しています」
  → これは授業。Shortsでは離脱される。

良い例（ストーリー型）:
  「含み損。つらいですよね」
  「でも、ここを超えた人だけが勝つ」
  → これは共感。保存される。

━━━ 台本の構成（5シーン） ━━━
1. hook（1〜2秒）: 痛みワード1つ。最大6文字。
   hookは必ず「視聴者の痛み・不安」で始めろ。数字やデータで始めるな。
   以下の3型から選べ:
   ■ 単語型（最強）: 「含み損。」「暴落。」「不安。」「退場。」「売りたい。」
   ■ 痛み型: 「また下がった。」「増えない。」「眠れない。」
   ■ 逆説型: 「暴落は正常。」「含み損は味方。」
   良い: 「含み損。」「不安。」「売りたい。」← 痛みで止まる。
   悪い: 「2倍。」「200年。」「1800万円。」← 数字は痛みにならない。スクロールされる。
   悪い: 「積立3年目、しんどい。」← 2語。長い。
   悪い: 「含み損、つらいですよね。」← 説明的。
   悪い: 「増えない。」「差がない。」← 痛みが弱い。感情が動かない。
   hookは必ず「恐怖・後悔・焦り」のどれかを刺せ。
   ★画面表示用のslide_textは文末の句点不要。「含み損」「不安」のように止める。

2. empathy（2〜3秒）: 「あなた」+共感1文。{opening}
   {opening}がある場合 → 共感文の後に「{opening}」を付ける。例: 「あなただけじゃない。{opening}」
   {opening}が空の場合 → 共感文だけでOK。例: 「あなただけじゃない。」「つらい夜です。」
   共感部分は6文字以内。短いほど強い。間延びは離脱される。
   悪い: 「あなたもそう感じたことありますよね。」← 長すぎ。離脱。

3. data（4秒）: 数字1つで希望を見せる。教えるな。
   トピックに最も合うデータを1つ選べ。
   ★重要: トピックの内容に直接関係するデータを選べ。無関係なデータは禁止。
   ★重要: dataはresolveの結論フレーズと因果関係が成立するものを選べ。

   データプール（25個。トピックに最も合うものを1つ選べ）:
   【暴落・下落】
   - 「暴落後1年のリターン、平均+25%。」
   - 「売った人の9割が回復を逃した。」
   - 「暴落は平均18ヶ月ごとに来る。」
   - 「リーマンから5年で完全回復。」
   - 「コロナ後、1年半で最高値更新。」
   【長期投資・継続】
   - 「20年続けた人、元本割れゼロ。」
   - 「10年持てば勝率95%以上。」
   - 「ベスト10日を逃すとリターン半減。」
   - 「最悪のタイミングで買っても利益。」
   - 「保有3年でやめた人、翌年逃す。」
   【複利・積立】
   - 「月3万の積立、30年後に6000万。」
   - 「月1万でも20年で500万。」
   - 「毎日100円で30年後130万超。」
   - 「年7%なら10年で2倍になる。」
   - 「配当再投資でリターン約2倍。」
   【心理・行動】
   - 「SNSは勝った人しか叫ばない。」
   - 「口座を見る回数が多い人ほど損。」
   - 「途中でやめた人、リターン1/3。」
   - 「忘れてた人が一番儲かる。」
   - 「プロの7割がインデックスに負ける。」
   【制度・歴史】
   - 「NISA非課税効果、20年で約200万。」
   - 「長期では株式が債券を上回る傾向。」
   - 「世界のGDP、50年で10倍。」
   - 「バフェットの資産99%は50歳以降。」
   - 「恐怖指数が高い時に買った人が勝つ。」

   悪い: 「長期投資のリターンは10年以降に加速します。」← 教科書。
   悪い: トピックが配当なのに「売った人の9割」← 無関係。
   ★重要: 誇張・断定は避けろ。「200年間負けなし」のような表現は誤解を招く。
   正確で控えめな表現を使え（例: 「長期では株式が成長し続けた」）。
   最大20文字。

4. resolve（4秒）: dataの文脈に合った接続詞 + 結論フレーズで締める。
   ★最重要: dataとresolveは「読んだ人がうなずける因果関係」が必要。

   結論フレーズ（以下の5つから、dataに最も合うものを1つ選べ）:
   A: 「やっぱり、長期投資しかないですね。」← メリット・成長系データに合う
   B: 「市場に残る人だけが勝ちます。」← 退場・売却・離脱系データに合う
   C: 「暴落は、長期投資家の味方です。」← 暴落・下落・回復系データに合う
   D: 「時間が、最大の武器です。」← 複利・積立・長期保有系データに合う
   E: 「退場しない人だけが勝つ。」← 損失・失敗・心理系データに合う

   接続詞の選択:
   ■ dataが失敗・損失の話 →「でも、」（逆接: 失敗→でも希望がある）
     例: 「売った人の9割が回復を逃した。でも、市場に残る人だけが勝ちます。」✓
   ■ dataが成功・実績の話 →「だから、」（順接: 実績→だから続けよう）
     例: 「20年続けた人、元本割れゼロ。だから、時間が最大の武器です。」✓
   ■ dataが意外な事実 →「そう、」（肯定: 事実→そうなんです）
     例: 「バフェットの資産99%は50歳以降。そう、時間が最大の武器です。」✓

   ★チェック: dataを読んだ直後にresolveを読み、「だから何？」と思ったらNG。書き直せ。
   悪い組み合わせ（絶対禁止）:
   ✗ 「年7%で2倍。だから、暴落は味方。」← 複利と暴落は無関係。
   ✗ 「配当再投資で2倍。だから、暴落は味方。」← 配当と暴落は無関係。
   ✗ 「月3万で6000万。でも、退場しない人だけが勝つ。」← ポジティブに逆接は不自然。

5. closing（2秒）: 固定。textは「{closing}」のみ。

━━━ 絶対禁止 ━━━
- 説明文（「〜は〜です」型の文）
- 列挙（複数の理由、複数のデータ）
- 教科書トーン
- 1シーンに2つ以上の主張

━━━ 書き方のルール ━━━
- 短文のみ。句読点は最小限。
- 1シーン＝1メッセージ。
- 話し言葉で断言。丁寧語より断言。
- slide_textは最大14文字。それだけで意味が伝わること。
- slide_textは見出しとして扱い、文末の句点・感嘆符・疑問符は付けない。
- resolveのslide_textは7文字以内の断言。
- empathyのslide_textは「{opening}」固定。
- closingのslide_textは「{closing_slide}」固定。
- タイトルは「痛み or 共感ワード」必須（40文字以内）。
- descriptionは100〜200文字。末尾「※投資助言ではありません」。
- tagsは5〜8個。

━━━ 出力 ━━━
JSON形式のみ（説明不要）:
{{"title": "タイトル", "description": "概要欄", "tags": ["タグ1", ...], "theme": "{theme_name}", "scenes": [{{"text": "含み損。", "slide_text": "含み損", "duration_sec": 1, "role": "hook"}}, {{"text": "あなたも共感。{opening}", "slide_text": "{opening}", "duration_sec": 3, "role": "empathy"}}, {{"text": "数字で希望", "slide_text": "数字要点", "duration_sec": 4, "role": "data"}}, {{"text": "だから、{conclusion}", "slide_text": "断言7文字", "duration_sec": 4, "role": "resolve"}}, {{"text": "{closing}", "slide_text": "{closing_slide}", "duration_sec": 2, "role": "closing"}}]}}
"""

# ── 通常動画テンプレート ──
LONG_TEMPLATE = """
あなたはYouTube動画の台本ライターです。

チャンネルコンセプト:
{concept}

以下のトピックで YouTube 通常動画（約5分）の台本を作成してください。

トピック: {topic}

台本の構成（6シーン固定、この順番を厳守）:
1. opening（30秒）: 導入。「{opening}」で始め、視聴者への語りかけ。今日の動画で何がわかるかを予告。
2. theme（30秒）: 今日のテーマを紹介。視聴者が感じている不安や疑問を言語化する。
3. data（90秒）: 根拠となるデータ・格言・歴史的事実を紹介。具体的な数字を使う。
4. explain（90秒）: dataの内容をかみ砕いて解説。日常の例えを使って分かりやすく。短期売買に走らない理由も含める。
5. summary（30秒）: まとめ。「{conclusion}」に自然に繋がるポジティブな総括。最後に「{conclusion}」を入れること。
6. closing（30秒）: 締め。summaryの内容を受けて「{closing}」で終わる。

重要ルール:
- 各シーンには2種類のテキストを用意する:
  - "text": ナレーション用（話し言葉、全文）。openingの冒頭は必ず「{opening}」で始めること。closingの末尾は必ず「{closing}」で終わること。
  - "slide_text": スライド表示用（最大10文字）。各シーンの要点キーワード。
- slide_textは見出しとして扱い、文末の句点・感嘆符・疑問符は付けない。
- 投資助言は絶対にしない。
- 穏やかで落ち着いたトーン。煽らない。
- すべての結論は「{conclusion}」に収束させる。
- 視聴後に「長期投資を続けてよかった」と思える内容にすること。
- タイトルは50文字以内
- descriptionは200〜400文字。免責事項「※投資助言ではありません」を末尾に含める。
- tagsは8〜12個

出力は以下のJSON形式のみ（説明・コメント不要）:
{{"title": "動画タイトル", "description": "概要欄テキスト", "tags": ["タグ1", ...], "scenes": [{{"text": "ナレーション", "slide_text": "表示テキスト", "duration_sec": 30, "role": "opening"}}, {{"text": "...", "slide_text": "...", "duration_sec": 30, "role": "theme"}}, {{"text": "...", "slide_text": "...", "duration_sec": 90, "role": "data"}}, {{"text": "...", "slide_text": "...", "duration_sec": 90, "role": "explain"}}, {{"text": "...", "slide_text": "...", "duration_sec": 30, "role": "summary"}}, {{"text": "...", "slide_text": "...", "duration_sec": 30, "role": "closing"}}]}}
"""


# データプール（テーマキーワード → 定型文リスト）
# Claudeが22文字超のdataを生成した場合、ここからフォールバック選択する
DATA_POOL = {
    "暴落": ["暴落後1年のリターン、平均+25%。", "売った人の9割が回復を逃した。", "暴落は平均18ヶ月ごとに来る。",
             "リーマンから5年で完全回復。", "コロナ後、1年半で最高値更新。"],
    "長期": ["20年続けた人、元本割れゼロ。", "10年持てば勝率95%以上。", "ベスト10日を逃すとリターン半減。",
             "最悪のタイミングで買っても利益。", "保有3年でやめた人、翌年逃す。"],
    "複利": ["月3万の積立、30年後に6000万。", "月1万でも20年で500万。", "毎日100円で30年後130万超。",
             "年7%なら10年で2倍になる。", "配当再投資でリターン約2倍。"],
    "心理": ["SNSは勝った人しか叫ばない。", "口座を見る回数が多い人ほど損。", "途中でやめた人、リターン1/3。",
             "忘れてた人が一番儲かる。", "プロの7割がインデックスに負ける。"],
    "歴史": ["NISA非課税効果、20年で約200万。", "長期では株式が債券を上回る傾向。", "世界のGDP、50年で10倍。",
             "バフェットの資産99%は50歳以降。", "恐怖指数が高い時に買った人が勝つ。"],
}

# トピックキーワード → データプールカテゴリのマッピング
_TOPIC_TO_CATEGORY = {
    "暴落": "暴落", "下落": "暴落", "リーマン": "暴落", "コロナ": "暴落", "恐慌": "暴落", "回復": "暴落",
    "複利": "複利", "積立": "複利", "配当": "複利", "年利": "複利", "100円": "複利", "月": "複利",
    "SNS": "心理", "焦": "心理", "口座": "心理", "感情": "心理", "パニック": "心理",
    "NISA": "歴史", "GDP": "歴史", "バフェット": "歴史", "200年": "歴史", "歴史": "歴史",
}


# データ分類用キーワード（結論選択・接続詞判定で共用）
_CRASH_WORDS = ["暴落", "下落", "回復", "リーマン", "コロナ", "恐慌", "恐怖指数", "ショック"]
_EXIT_WORDS = ["売った", "やめた", "逃した", "離れ", "退場", "解約", "損", "負ける", "崩壊", "減"]
_TIME_WORDS = ["倍", "複利", "積立", "50歳", "30年", "20年", "10年", "月", "年7%", "100円"]
_PSYCH_WORDS = ["SNS", "口座", "忘れ", "見る", "プロ", "感情", "パニック"]
_POSITIVE_WORDS = ["ゼロ", "勝率", "2倍", "成長", "利益", "6000万", "500万", "完全回復", "最高値"]
_SURPRISE_WORDS = ["バフェット", "99%", "50歳", "プロ", "忘れ"]
_CONTINUATION_WORDS = ["続け", "変えなかった", "そのまま", "十分", "何もしない", "退屈", "変わらない", "褒め", "正解"]

# hookチェック用キーワード
STRONG_HOOKS = ["含み損", "暴落", "売りたい", "退場", "不安", "怖い",
                 "つらい", "眠れない", "後悔", "焦る", "損した", "溶けた"]
WEAK_HOOKS = ["増えない", "差がない", "もったいない", "知らない", "違う"]
_TOPIC_PAIN_MAP = {"配当": "損してる。", "複利": "焦る。", "年利": "不安。",
                   "積立": "つらい。", "100円": "不安。", "差": "後悔。",
                   "200年": "不安。", "非課税": "焦る。", "再投資": "損してる。"}

# 誇張表現の修正マップ
_EXAGGERATION_FIXES = {
    "200年間、株式が債券に勝ち続けた": "長期では株式が債券を上回る傾向",
    "株式200年、負けなし": "長期では株式が債券を上回る傾向",
    "200年間負けなし": "長期では株式が成長し続けた",
    "株式が債券に勝ち続けた": "株式が債券を上回る傾向",
}


def _strip_terminal_punctuation(text: str) -> str:
    """画面テキスト末尾の句点類を落として見出しとして整える。"""
    return text.rstrip("。.!！?？ ").strip()


# 絵文字除去用の正規表現（サロゲートペア・記号・修飾子を除去）
_RE_EMOJI = re.compile(r'[\U00010000-\U0010FFFF\u2600-\u27BF\uFE00-\uFE0F\u200D]')


def _clean_slide_text(text: str) -> str:
    """slide_text から絵文字を除去し、末尾句読点を落とす。"""
    return _strip_terminal_punctuation(_RE_EMOJI.sub('', text).strip())


def _trim_to_first_sentence(text: str, max_len: int) -> str:
    """テキストを最初の文（句点区切り）で切り詰める。句点がなければmax_lenで切る。"""
    if len(text) <= max_len:
        return text
    parts = re.split(r"(?<=[。？！])", text)
    first = parts[0].rstrip("。、 ") if parts[0] else ""
    # 最初の文が収まるならそれを使う
    if first and len(first) <= max_len:
        return first
    # 最初の文が長すぎる場合、読点で区切って収まる部分を返す
    if first:
        comma_parts = re.split(r"(?<=[、])", first)
        built = ""
        for cp in comma_parts:
            if len(built + cp) <= max_len:
                built += cp
            else:
                break
        if built:
            return built.rstrip("、 ")
    return text[:max_len]


def _select_conclusion_and_connector(data_text: str, theme_name: str = "") -> tuple:
    """dataの内容に最も合う結論フレーズと接続詞を選択する。"""
    # テーマ主導: 継続モチベ系なら継続肯定resolveを最優先固定
    is_continue_theme = theme_name == "継続モチベ系"
    if is_continue_theme:
        conclusion = random.choice([
            "今日もそのままでいい。",
            "何もしない日にも、意味があります。",
            "変えなかったことも、積み上がっています。",
            "焦らない日が、長期では効いてきます。",
            "続いているなら、それで十分です。",
        ])
        connector = "そう、"
        return conclusion, connector

    is_crash = any(w in data_text for w in _CRASH_WORDS)
    is_exit = any(w in data_text for w in _EXIT_WORDS)
    is_negative = is_crash or is_exit
    is_surprise = any(w in data_text for w in _SURPRISE_WORDS) and not is_negative

    # 結論フレーズ選択
    if is_crash:
        conclusion = random.choice([
            "暴落は、長期投資家の味方です。",
            "市場に残る人だけが勝ちます。",
        ])
    elif is_exit:
        conclusion = random.choice([
            "市場に残る人だけが勝ちます。",
            "退場しない人だけが勝つ。",
        ])
    elif any(w in data_text for w in _TIME_WORDS):
        conclusion = random.choice([
            "時間が、最大の武器です。",
            "やっぱり、長期投資しかないですね。",
            "退場しない人だけが勝つ。",
        ])
    elif any(w in data_text for w in _PSYCH_WORDS):
        conclusion = random.choice([
            "退場しない人だけが勝つ。",
            "市場に残る人だけが勝ちます。",
        ])
    else:
        conclusion = random.choice([
            "やっぱり、長期投資しかないですね。",
            "時間が、最大の武器です。",
        ])

    # 接続詞選択
    if is_negative:
        connector = "でも、"
    elif is_surprise:
        connector = "そう、"
    else:
        connector = "だから、"

    return conclusion, connector


def extract_scene_texts(script_data: dict, *roles: str) -> dict:
    """台本データから指定ロールのslide_textを辞書で返すヘルパー。

    使用例:
        texts = extract_scene_texts(script_data, "hook", "resolve")
        hook_text = texts.get("hook", "")
    """
    result = {r: "" for r in roles}
    for scene in script_data.get("scenes", []):
        role = scene.get("role", "")
        if role in result:
            result[role] = scene.get("slide_text", "")
    return result


def generate_shorts_script(topic: str, theme: str = "ガチホモチベ") -> dict:
    """Shorts用台本（5シーン、16〜18秒）を生成する。"""
    theme_desc = SHORTS_THEMES.get(theme, SHORTS_THEMES["ガチホモチベ"])
    # 語りかけフレーズ: 約3本に1本だけ入れる（尺圧迫を避ける）
    if random.random() < _SHORTS_OPENING_RATIO:
        opening = random.choice(OPENING_PHRASES)
        print(f"  [語りかけ] この動画にフレーズを入れます:「{opening}」")
    else:
        opening = ""
    conclusion = random.choice(CONCLUSION_PHRASES)  # 初期値（ポスプロで上書き）
    closing_idx = random.randrange(len(CLOSING_PHRASES_LIST))
    closing = CLOSING_PHRASES_LIST[closing_idx]
    closing_slide = CLOSING_SLIDE_TEXTS[closing_idx]
    return _generate_script(
        topic,
        SHORTS_TEMPLATE,
        expected_scenes=5,
        extra_vars={
            "theme_name": theme,
            "theme_desc": theme_desc,
            "opening": opening,
            "conclusion": conclusion,
            "closing": closing,
            "closing_slide": closing_slide,
        },
    )


def generate_long_script(topic: str) -> dict:
    """通常動画用台本（6シーン、約5分）を生成する。"""
    opening = random.choice(OPENING_PHRASES)
    conclusion = random.choice(CONCLUSION_PHRASES)
    return _generate_script(
        topic,
        LONG_TEMPLATE,
        expected_scenes=6,
        extra_vars={"opening": opening, "conclusion": conclusion},
    )


def _generate_script(
    topic: str,
    template: str,
    expected_scenes: int,
    extra_vars: dict = None,
) -> dict:
    """Claude API で台本を生成する共通関数。"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  [エラー] ANTHROPIC_API_KEY が設定されていません。")
        return {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        fmt_vars = {
            "concept": CHANNEL_CONCEPT,
            "topic": topic,
            "opening": OPENING_PHRASE,
            "conclusion": CONCLUSION_PHRASES[0],
            "closing": CLOSING_PHRASE,
        }
        if extra_vars:
            fmt_vars.update(extra_vars)

        conclusion = fmt_vars["conclusion"]
        opening = fmt_vars["opening"]
        closing = fmt_vars["closing"]
        closing_slide = fmt_vars.get("closing_slide", "明日もガチホしたい人はフォロー")
        prompt = template.format(**fmt_vars)

        # 分析 insights をプロンプト先頭に差し込む
        insights = load_insights()
        insights_block = _build_insights_block(insights)
        if insights_block:
            prompt = insights_block + "\n\n" + prompt
            print(f"  [insights] 分析結果を差し込み（{insights.get('meta', {}).get('sample_size', 0)}本）")

        # プロンプトキャッシュ: 固定テンプレート部分を system に分離
        # system 部分はバッチ内で使い回され、2回目以降はキャッシュヒットでトークン節約
        # user 部分はトピック固有の可変テキストのみ
        system_text = prompt  # テンプレート全体を system に入れる
        user_text = f"トピック「{topic}」の台本をJSON形式で生成してください。"

        print(f"  Claude API で台本を生成中（トピック: {topic}）...")
        print(f"  挨拶: {opening} / 結論: {conclusion}")
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=[{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_text}],
        )
        raw = message.content[0].text.strip()

        # JSON を抽出
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            print("  [エラー] JSON形式のレスポンスが見つかりませんでした。")
            _save_debug("script_raw_response.txt", raw)
            return {}

        data = json.loads(m.group())

        # 固定テキストを強制適用（Claudeが指示に従わなくても上書き）
        scenes = data.get("scenes", [])

        # ── ループ再生: hookワードを取得してclosingに埋め込む ──
        hook_word = ""
        for s in scenes:
            if s.get("role") == "hook":
                hook_word = s.get("text", "").rstrip("。？！ ")
                break
        if hook_word:
            closing, closing_slide = _apply_loop_closing(scenes, hook_word, fmt_vars.get("theme_name", ""))
            print(f"  [ループ再生] closing にhookワード埋め込み:「{closing_slide}」")

        for s in scenes:
            role = s.get("role", "")
            if role == "empathy":
                if opening:
                    # 語りかけフレーズあり → slide_textに表示、ナレーションにも含める
                    s["slide_text"] = opening
                    if opening not in s.get("text", ""):
                        s["text"] = s.get("text", "").rstrip("。") + "。" + opening
                else:
                    # 語りかけなし → ナレーションからslide_textを生成（絵文字防止）
                    s["slide_text"] = s.get("text", "").rstrip("。？！ ")[:10]
            elif role == "opening":
                # 通常動画用: openingのslide_textを固定
                s["slide_text"] = OPENING_PHRASE
            elif role == "resolve":
                # resolveの整形は文字数制限ループ内で実施（data内容を見て結論を選択）
                pass
            elif role == "closing":
                s["slide_text"] = closing_slide
                s["text"] = closing

            if "slide_text" in s:
                s["slide_text"] = _clean_slide_text(s.get("slide_text", ""))

        # 文字数制限チェック
        # 固定フレーズを保護しながら AI生成部分を切り詰める
        strict_limits = {"hook": 8, "data": 22}
        # data_text をループ前に1回だけ取得（resolve等で使用）
        data_text = next((s.get("text", "") for s in scenes if s.get("role") == "data"), "")
        for s in scenes:
            role = s.get("role", "")
            text = s.get("text", "")

            if role == "hook":
                # hookの痛みワードチェック: 弱いhookを検出して警告
                hook_text = text.rstrip("。？！ ")
                if any(w in hook_text for w in WEAK_HOOKS) and not any(w in hook_text for w in STRONG_HOOKS):
                    replaced = False
                    for kw, replacement in _TOPIC_PAIN_MAP.items():
                        if kw in topic:
                            print(f"  [修正] hookが弱い「{hook_text}」→「{replacement}」に変更")
                            s["text"] = replacement
                            s["slide_text"] = _strip_terminal_punctuation(replacement)
                            text = replacement
                            replaced = True
                            break
                    if not replaced:
                        print(f"  [警告] hookが弱い可能性:「{hook_text}」")
                # ループ再生: hook修正後のワードでclosingを再更新
                new_hook = text.rstrip("。？！ ")
                if new_hook and new_hook != hook_word:
                    hook_word = new_hook
                    closing, closing_slide = _apply_loop_closing(scenes, hook_word)
                    print(f"  [ループ再生] hook修正に合わせてclosing更新:「{closing_slide}」")

            if role == "data":
                # 誇張表現を正確な表現に自動置換
                for bad, good in _EXAGGERATION_FIXES.items():
                    if bad in text:
                        old_text = text
                        text = text.replace(bad, good)
                        s["text"] = text
                        s["slide_text"] = _strip_terminal_punctuation(good[:14])
                        print(f"  [修正] data誇張表現を修正:「{old_text.rstrip('。')}」→「{text.rstrip('。')}」")
                        data_text = text  # resolve用に更新
                        break

            if role == "data" and len(text) > 22:
                # dataが22文字超 → データプールからフォールバック選択
                # まずトピックからカテゴリを特定
                category = "長期"  # デフォルト
                for kw, cat in _TOPIC_TO_CATEGORY.items():
                    if kw in topic:
                        category = cat
                        break
                pool = DATA_POOL.get(category, DATA_POOL["長期"])
                # Claudeの生成文とキーワードが重なるものを優先選択
                best = pool[0]
                best_score = 0
                for candidate in pool:
                    score = sum(1 for w in candidate if w in text)
                    if score > best_score:
                        best_score = score
                        best = candidate
                print(f"  [修正] dataが{len(text)}文字で長すぎ → プールから選択:「{best}」")
                s["text"] = best
                s["slide_text"] = _strip_terminal_punctuation(best[:14])
                text = best
                data_text = best  # resolve用に更新

            elif role in strict_limits:
                limit = strict_limits[role]
                if len(text) > limit:
                    print(f"  [警告] {role}が{len(text)}文字（制限{limit}文字）→ 切り詰めます")
                    parts = re.split(r"(?<=[。？！])", text)
                    trimmed = ""
                    for part in parts:
                        if len(trimmed + part) <= limit:
                            trimmed += part
                        else:
                            break
                    s["text"] = trimmed if trimmed else text[:limit]

            elif role == "empathy":
                # AI生成部分の間延び防止
                if opening and opening in text:
                    raw_ai_part = text.replace(opening, "").strip().rstrip("。、 ")
                    ai_part = _trim_to_first_sentence(raw_ai_part, 12)
                    if ai_part != raw_ai_part:
                        print(f"  [調整] empathyのAI部分を切り詰めました")
                    s["text"] = (ai_part + "。" + opening) if ai_part else opening
                elif not opening:
                    # 語りかけなし → AI生成の共感テキストを10文字以内に制限
                    # ただし最低4文字は確保（「あなたも。」等の短すぎ防止）
                    if len(text) > 10:
                        trimmed = _trim_to_first_sentence(text, 10)
                        if len(trimmed) >= 4:
                            s["text"] = trimmed + "。"
                            print(f"  [調整] empathy（語りかけなし）を切り詰めました")
                        else:
                            print(f"  [維持] empathy切り詰め結果が短すぎるため元テキストを維持")

            elif role == "resolve":
                # dataの内容に最も合う結論フレーズと接続詞を一括選択
                theme_name = fmt_vars.get("theme_name", "")
                best_conclusion, connector = _select_conclusion_and_connector(data_text, theme_name)
                if best_conclusion != conclusion:
                    print(f"  [修正] 結論フレーズを変更: 「{conclusion}」→「{best_conclusion}」")
                    conclusion = best_conclusion

                s["text"] = connector + conclusion
                short_conclusion = conclusion.rstrip("。").replace("やっぱり、", "").replace("、", "")
                s["slide_text"] = _strip_terminal_punctuation(short_conclusion)

            if "slide_text" in s:
                s["slide_text"] = _clean_slide_text(s.get("slide_text", ""))

        # バリデーション
        title = data.get("title", "").strip()
        if not title or len(scenes) != expected_scenes:
            print(f"  [エラー] 台本の形式が不正です（タイトル: {bool(title)}, シーン数: {len(scenes)}/{expected_scenes}）")
            _save_debug("script_invalid.json", json.dumps(data, ensure_ascii=False, indent=2))
            return {}

        total_sec = sum(s.get("duration_sec", 0) for s in scenes)
        total_chars = sum(len(s.get("text", "")) for s in scenes)
        print(f"  台本生成完了（タイトル: {title}）")
        print(f"  シーン数: {len(scenes)} / 想定尺: {total_sec}秒 / 文字数: {total_chars}文字")

        # トピックを返り値に含める（transcript.json への保存・dedupe等で使用）
        data["topic"] = topic

        return data

    except json.JSONDecodeError as e:
        print(f"  [エラー] JSONパースに失敗しました: {e}")
        _save_debug("script_json_error.txt", raw)
        return {}
    except Exception as e:
        print(f"  [エラー] 台本生成中にエラーが発生しました: {e}")
        return {}


def _save_debug(filename: str, content: str):
    """デバッグ情報を debug/ に保存する。"""
    import pathlib
    debug_dir = pathlib.Path(__file__).parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    try:
        (debug_dir / filename).write_text(content, encoding="utf-8")
        print(f"  デバッグ情報を保存: debug/{filename}")
    except Exception:
        pass

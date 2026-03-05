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
import random
import re

import anthropic

# チャンネル設定
CHANNEL_CONCEPT = (
    "チャンネル名「ガチホのモチベ」。"
    "長期投資（インデックス投資など）を続けるモチベーションを提供するチャンネル。"
    "視聴者は長期投資をしている or 始めたばかりの20〜50代。"
    "投資手法の解説ではなく、長期投資を「続けよう」と思える心理的モチベーションを提供する。"
    "個別株の推奨・具体的な投資助言・短期トレード解説は絶対にしない。"
    "視聴後に「長期投資を続けてよかった」「短期売買に手を出さなくてよかった」と思える内容を目指す。"
)

# 固定フレーズ
OPENING_PHRASES = [
    "今日もガチホしてますか？",
    "まだ市場に残ってますか？",
    "今日も積み立て続けてますか？",
]
OPENING_PHRASE = OPENING_PHRASES[0]  # デフォルト（通常動画用）
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

# 結論フレーズ（5パターンからランダム選択）
CONCLUSION_PHRASES = [
    "やっぱり、長期投資しかないですね。",
    "市場に残る人だけが勝ちます。",
    "暴落は、長期投資家の味方です。",
    "時間が、最大の武器です。",
    "退場しない人だけが勝つ。",
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

2. empathy（2〜3秒）: 「あなた」+共感1文 + 「{opening}」
   良い: 「あなただけじゃない。{opening}」
   共感部分は6文字以内。短いほど強い。間延びは離脱される。
   悪い: 「あなたもそう感じたことありますよね。{opening}」← 長すぎ。離脱。

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
   - 「200年間、株式が債券に勝ち続けた。」
   - 「世界のGDP、50年で10倍。」
   - 「バフェットの資産99%は50歳以降。」
   - 「恐怖指数が高い時に買った人が勝つ。」

   悪い: 「長期投資のリターンは10年以降に加速します。」← 教科書。
   悪い: トピックが配当なのに「売った人の9割」← 無関係。
   最大20文字。

4. resolve（4秒）: dataの文脈に合った接続詞 + 「{conclusion}」で締める。
   ★最重要: 接続詞の選択はdata→resolveの因果関係で決まる。必ずチェックしろ。

   判定方法: dataを読んだ後、resolveを読んで「文章として自然か？」を確認せよ。
   ■ dataが失敗・損失の話 →「でも、」（逆接: 失敗→でも希望がある）
     例: 「売った人の9割が回復を逃した。でも、市場に残る人だけが勝ちます。」✓
   ■ dataが成功・実績の話 →「だから、」（順接: 実績→だから続けよう）
     例: 「20年続けた人、元本割れゼロ。だから、退場しない人だけが勝つ。」✓
   ■ dataが意外な事実 →「そう、」（肯定: 事実→そうなんです）
     例: 「バフェットの資産99%は50歳以降。そう、時間が最大の武器です。」✓

   悪い組み合わせ（絶対禁止）:
   ✗ 「元本割れゼロ。でも、〜」← ポジティブなのに逆接。意味不明。
   ✗ 「配当再投資で2倍。だから、暴落は味方。」← 配当と暴落は無関係。
   ✗ 「月3万で6000万。でも、退場しない人だけが勝つ。」← 因果なし。

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
- resolveのslide_textは7文字以内の断言。
- empathyのslide_textは「{opening}」固定。
- closingのslide_textは「{closing_slide}」固定。
- タイトルは「痛み or 共感ワード」必須（40文字以内）。
- descriptionは100〜200文字。末尾「※投資助言ではありません」。
- tagsは5〜8個。

━━━ 出力 ━━━
JSON形式のみ（説明不要）:
{{"title": "タイトル", "description": "概要欄", "tags": ["タグ1", ...], "theme": "{theme_name}", "scenes": [{{"text": "含み損。", "slide_text": "含み損。", "duration_sec": 1, "role": "hook"}}, {{"text": "あなたも共感。{opening}", "slide_text": "{opening}", "duration_sec": 3, "role": "empathy"}}, {{"text": "数字で希望", "slide_text": "数字要点", "duration_sec": 4, "role": "data"}}, {{"text": "だから、{conclusion}", "slide_text": "断言7文字", "duration_sec": 4, "role": "resolve"}}, {{"text": "{closing}", "slide_text": "{closing_slide}", "duration_sec": 2, "role": "closing"}}]}}
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


def generate_shorts_script(topic: str, theme: str = "ガチホモチベ") -> dict:
    """Shorts用台本（5シーン、16〜18秒）を生成する。"""
    theme_desc = SHORTS_THEMES.get(theme, SHORTS_THEMES["ガチホモチベ"])
    # フレーズをランダム選択
    opening = random.choice(OPENING_PHRASES)
    conclusion = random.choice(CONCLUSION_PHRASES)
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
    conclusion = random.choice(CONCLUSION_PHRASES)
    return _generate_script(
        topic,
        LONG_TEMPLATE,
        expected_scenes=6,
        extra_vars={"conclusion": conclusion},
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

        print(f"  Claude API で台本を生成中（トピック: {topic}）...")
        print(f"  挨拶: {opening} / 結論: {conclusion}")
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
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
        for s in scenes:
            role = s.get("role", "")
            if role == "empathy":
                s["slide_text"] = opening
                # ナレーションにも挨拶フレーズを必ず含める
                if opening not in s.get("text", ""):
                    s["text"] = s.get("text", "").rstrip("。") + "。" + opening
            elif role == "opening":
                # 通常動画用: openingのslide_textを固定
                s["slide_text"] = OPENING_PHRASE
            elif role == "resolve":
                if conclusion not in s.get("text", ""):
                    s["text"] = s.get("text", "").rstrip("。") + "。" + conclusion
                # slide_textを結論フレーズの要約に統一（ナレーションとの不一致を防ぐ）
                # 結論フレーズから「。」を除去して短縮版をslide_textに
                short_conclusion = conclusion.rstrip("。").replace("やっぱり、", "").replace("、", "")
                s["slide_text"] = short_conclusion
            elif role == "closing":
                s["slide_text"] = closing_slide
                s["text"] = closing

        # 文字数制限チェック
        # 固定フレーズを保護しながら AI生成部分を切り詰める
        strict_limits = {"hook": 8, "data": 22}
        for s in scenes:
            role = s.get("role", "")
            text = s.get("text", "")

            if role in strict_limits:
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
                # AI生成部分を最大6文字に制限（+ 挨拶フレーズ）— 間延び防止
                if opening in text:
                    ai_part = text.replace(opening, "").strip().rstrip("。、 ")
                    if len(ai_part) > 6:
                        # 句点で区切って自然に切る
                        parts = re.split(r"(?<=[。？！])", ai_part)
                        ai_part = parts[0].rstrip("。、 ") if parts[0] else ai_part[:6]
                        print(f"  [調整] empathyのAI部分を切り詰めました")
                    s["text"] = (ai_part + "。" + opening) if ai_part else opening

            elif role == "resolve":
                # 接続詞（でも/だから/そう）+ 結論フレーズに整形
                if conclusion in text:
                    ai_part = text.replace(conclusion, "").strip().rstrip("。、 ")
                    # 接続詞を抽出（でも、だから、そう のいずれか）
                    connector = "だから、"
                    for c in ["でも、", "だから、", "そう、"]:
                        if c in ai_part:
                            connector = c
                            break

                    # dataの内容と接続詞の整合性チェック
                    data_text = ""
                    for ds in scenes:
                        if ds.get("role") == "data":
                            data_text = ds.get("text", "")
                            break
                    # ネガティブ判定を優先（「回復を逃した」等の複合表現対策）
                    negative_words = ["売った", "やめた", "逃した", "負ける", "損", "崩壊", "下落", "暴落", "離れ", "減"]
                    positive_words = ["ゼロ", "勝率", "2倍", "成長", "利益", "6000万", "500万", "完全回復", "最高値"]
                    data_is_negative = any(w in data_text for w in negative_words)
                    data_is_positive = any(w in data_text for w in positive_words) and not data_is_negative

                    if data_is_positive and connector == "でも、":
                        connector = "だから、"
                        print(f"  [修正] dataがポジティブなので接続詞を「でも」→「だから」に変更")
                    elif data_is_negative and connector != "でも、":
                        connector = "でも、"
                        print(f"  [修正] dataがネガティブなので接続詞を「でも」に変更")

                    s["text"] = connector + conclusion

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

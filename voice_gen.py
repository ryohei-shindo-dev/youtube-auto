"""
voice_gen.py
ElevenLabs REST API で各シーンのナレーション音声を生成するモジュール。

SDK は使わず requests で直接呼び出し（依存最小化）。

【ElevenLabs テキスト整形ルール】
  - 句読点「。」の後に半角スペースを入れてポーズを作る
  - 「！」「？」の後にも半角スペース（感情の間を確保）
  - 数字は漢数字に変換しない（アラビア数字のまま読ませる）
  - 「%」→「パーセント」、「&」→「アンド」に変換
  - 英単語（S&P500等）はそのまま（ElevenLabsが英語として読む）
  - 改行は除去（1つの連続テキストとして読ませる）
  - speed=1.15 で落ち着いたテンポ（思想系チャンネル向け）
"""

import json
import os
import pathlib
import re
import subprocess

import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# ElevenLabsが読み間違える漢字の読み替え辞書
# (元の表記, 正しい読み) のリスト。上から順に適用される。
_READING_FIXES = [
    # ── 長い語句を先に（部分一致の誤置換を防ぐ） ──
    # 複合語・制度名
    ("ドルコスト平均法", "どるこすとへいきんほう"),
    ("平均取得単価", "へいきんしゅとくたんか"),
    ("資産形成", "しさんけいせい"),
    ("株価指数", "かぶかしすう"),
    ("信託報酬", "しんたくほうしゅう"),
    ("投資信託", "とうししんたく"),
    ("分散投資", "ぶんさんとうし"),
    ("長期投資", "ちょうきとうし"),
    ("短期投資", "たんきとうし"),
    ("積立投資", "つみたてとうし"),
    ("世界恐慌", "せかいきょうこう"),
    ("ITバブル", "あいてぃーばぶる"),
    ("生活防衛資金", "せいかつぼうえいしきん"),
    ("配当再投資", "はいとうさいとうし"),
    ("感情的な売却", "かんじょうてきなばいきゃく"),
    ("含み損の時期", "ふくみぞんのじき"),
    ("増えない期間", "ふえないきかん"),
    ("見逃している", "みのがしている"),
    ("売買タイミング", "ばいばいたいみんぐ"),
    ("全世界株式", "ぜんせかいかぶしき"),
    ("全米株式", "ぜんべいかぶしき"),
    ("先進国株式", "せんしんこくかぶしき"),
    ("新興国株式", "しんこうこくかぶしき"),
    ("株式市場", "かぶしきしじょう"),
    ("金融市場", "きんゆうしじょう"),
    ("市場平均", "しじょうへいきん"),
    ("指数投資", "しすうとうし"),
    ("継続投資", "けいぞくとうし"),
    ("一括投資", "いっかつとうし"),
    ("再投資", "さいとうし"),
    ("資産運用", "しさんうんよう"),
    ("老後資金", "ろうごしきん"),
    ("余剰資金", "よじょうしきん"),
    ("期待利回り", "きたいりまわり"),
    ("期待リターン", "きたいりたーん"),
    ("実質リターン", "じっしつりたーん"),
    ("含み損益", "ふくみそんえき"),
    ("元本割れ", "がんぽんわれ"),
    ("定額積立", "ていがくつみたて"),
    ("自動積立", "じどうつみたて"),
    ("積立設定", "つみたてせってい"),
    ("長期保有", "ちょうきほゆう"),
    ("保有期間", "ほゆうきかん"),
    ("投資期間", "とうしきかん"),
    ("運用期間", "うんようきかん"),
    ("取り崩し", "とりくずし"),
    ("口座残高", "こうざざんだか"),
    ("資本主義", "しほんしゅぎ"),
    ("機会損失", "きかいそんしつ"),
    ("物価上昇", "ぶっかじょうしょう"),
    ("回復局面", "かいふくきょくめん"),
    ("下落局面", "げらくきょくめん"),
    ("上昇局面", "じょうしょうきょくめん"),
    ("景気後退", "けいきこうたい"),
    ("景気循環", "けいきじゅんかん"),
    # 指数・英語（長い方を先に）
    ("S&P500", "えすあんどぴーごひゃく"),
    ("S&P", "えすあんどぴー"),
    ("NASDAQ", "なすだっく"),
    ("NYダウ", "にゅーよーくだう"),
    ("ダウ平均", "だうへいきん"),
    # ETF・ファンド（長い方を先に）
    ("eMAXIS Slim", "いーまくしすすりむ"),
    ("emaxis slim", "いーまくしすすりむ"),
    ("楽天VTI", "らくてんぶいてぃーあい"),
    ("インデックスファンド", "いんでっくすふぁんど"),
    ("ETF", "いーてぃーえふ"),
    ("VTI", "ぶいてぃーあい"),
    ("VOO", "ぶいおーおー"),
    ("VYM", "ぶいわいえむ"),
    ("HDV", "えいちでぃーぶい"),
    ("SPYD", "えすぴーわいでぃー"),
    ("SCHD", "えすしーえいちでぃー"),
    ("VT", "ぶいてぃー"),
    # 証券・制度
    ("楽天証券", "らくてんしょうけん"),
    ("SBI", "えすびーあい"),
    ("iDeCo", "いでこ"),
    ("FRB", "えふあーるびー"),
    ("FOMC", "えふおーえむしー"),
    ("GDP", "じーでぃーぴー"),
    ("FIRE", "ふぁいあ"),
    # 人名・イベント
    ("リーマンショック", "りーまんしょっく"),
    ("コロナショック", "ころなしょっく"),
    ("ブラックマンデー", "ぶらっくまんでー"),
    ("バフェット", "ばふぇっと"),
    ("ボーグル", "ぼーぐる"),
    ("バンガード", "ばんがーど"),
    ("グレアム", "ぐれあむ"),
    ("オルカン", "おるかん"),
    # NISA系（長い方を先に）
    ("つみたてNISA", "つみたてにーさ"),
    ("新NISA", "しんにーさ"),
    ("NISA", "にーさ"),
    # ── 単語（既存 + 追加） ──
    # 投資用語
    ("元本", "がんぽん"),
    ("一択", "いったく"),
    ("含み損", "ふくみぞん"),
    ("含み益", "ふくみえき"),
    ("爆益", "ばくえき"),
    ("利回り", "りまわり"),
    ("年利", "ねんり"),
    ("複利", "ふくり"),
    ("暴落", "ぼうらく"),
    ("下落", "げらく"),
    ("約定", "やくじょう"),
    ("出来高", "できだか"),
    ("相場", "そうば"),
    ("正念場", "しょうねんば"),
    ("損切り", "そんぎり"),
    ("塩漬け", "しおづけ"),
    ("利確", "りかく"),
    ("損益", "そんえき"),
    ("配当金", "はいとうきん"),
    ("配当", "はいとう"),
    ("増配", "ぞうはい"),
    ("減配", "げんぱい"),
    ("分散", "ぶんさん"),
    ("指数", "しすう"),
    ("積立", "つみたて"),
    ("保有", "ほゆう"),
    ("回復", "かいふく"),
    ("継続", "けいぞく"),
    ("非課税", "ひかぜい"),
    ("課税", "かぜい"),
    ("税制", "ぜいせい"),
    ("評価損", "ひょうかぞん"),
    ("評価益", "ひょうかえき"),
    ("期待値", "きたいち"),
    ("米国株", "べいこくかぶ"),
    ("複利効果", "ふくりこうか"),
    ("運用益", "うんようえき"),
    ("狼狽売り", "ろうばいうり"),
    ("利上げ", "りあげ"),
    ("利下げ", "りさげ"),
    ("急落", "きゅうらく"),
    ("急騰", "きゅうとう"),
    ("暴騰", "ぼうとう"),
    ("反発", "はんぱつ"),
    ("反落", "はんらく"),
    ("続落", "ぞくらく"),
    ("底値", "そこね"),
    ("下値", "したね"),
    ("天井", "てんじょう"),
    ("横ばい", "よこばい"),
    ("上振れ", "うわぶれ"),
    ("下振れ", "したぶれ"),
    ("割安", "わりやす"),
    ("割高", "わりだか"),
    ("円高", "えんだか"),
    ("円安", "えんやす"),
    ("物価", "ぶっか"),
    ("為替", "かわせ"),
    ("インフレ率", "いんふれりつ"),
    ("手数料", "てすうりょう"),
    # 一般
    ("退場", "たいじょう"),
    ("見逃す", "みのがす"),
    ("二文字", "ふたもじ"),
    ("今夜", "こんや"),
    ("明日", "あした"),
    ("市場", "しじょう"),
    ("上昇", "じょうしょう"),
    ("翌年", "よくねん"),
    ("売りたい", "うりたい"),
    ("売った", "うった"),
    ("買った", "かった"),
    ("焦り", "あせり"),
    ("勝った", "かった"),
    ("勝つ", "かつ"),
    ("勝ち", "かち"),
    ("勝率", "しょうりつ"),
    # 一般（活用形・長い順）
    ("減らさなくていい", "へらさなくていい"),
    ("動かなかった", "うごかなかった"),
    ("落ち着ける", "おちつける"),
    ("間違えた", "まちがえた"),
    ("珍しい", "めずらしい"),
    ("出やすい", "でやすい"),
    ("減らした", "へらした"),
    ("置きます", "おきます"),
    ("勝手に", "かってに"),
    ("使って", "つかって"),
    ("減って", "へって"),
    ("引っ張られます", "ひっぱられます"),
    ("失う痛み", "うしなういたみ"),
    ("その先を", "そのさきを"),
    ("朝見て", "あさみて"),
    ("昼見て", "ひるみて"),
    ("夜見て", "よるみて"),
    ("短く", "みじかく"),
    ("高値", "たかね"),
    ("損失", "そんしつ"),
    ("痛み", "いたみ"),
    ("反応", "はんのう"),
    ("疑い", "うたがい"),
    ("口座", "こうざ"),
    ("浅い", "あさい"),
    ("最中", "さいちゅう"),
    ("傷", "きず"),
    ("底", "そこ"),
]


def generate_voice_for_scenes(
    scenes: list,
    output_dir: pathlib.Path,
) -> list:
    """
    ElevenLabs API で各シーンのナレーション音声を生成する。

    Args:
        scenes: script_gen が返した scenes リスト
        output_dir: 音声ファイルの保存先ディレクトリ

    Returns:
        scenes に "audio_path" と "actual_duration_sec" を追加したリスト。
        失敗したシーンの audio_path は None になる（処理は継続）。
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
    if not api_key or not voice_id:
        print("  [エラー] ELEVENLABS_API_KEY または ELEVENLABS_VOICE_ID が設定されていません。")
        for scene in scenes:
            scene["audio_path"] = None
            scene["actual_duration_sec"] = 0
        return scenes

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(scenes):
        idx = i + 1
        output_path = output_dir / f"audio_{idx:02d}.mp3"
        raw_text = scene.get("text", "")
        role = scene.get("role", "unknown")

        # TTS用にテキストを整形
        text = _format_for_tts(raw_text)

        print(f"  シーン{idx}（{role}）の音声を生成中...")
        success = _text_to_speech(api_key, voice_id, text, output_path)

        if success:
            duration = _get_audio_duration(output_path)
            scene["audio_path"] = str(output_path)
            scene["actual_duration_sec"] = duration
            size_kb = output_path.stat().st_size // 1024
            print(f"    保存完了: {output_path.name}（{duration:.1f}秒 / {size_kb}KB）")
        else:
            scene["audio_path"] = None
            scene["actual_duration_sec"] = 0
            print(f"    [エラー] シーン{idx}の音声生成に失敗しました。")

    total_sec = sum(s.get("actual_duration_sec", 0) for s in scenes)
    success_count = sum(1 for s in scenes if s.get("audio_path"))
    print(f"  音声生成完了（{success_count}/{len(scenes)}シーン成功 / 合計{total_sec:.1f}秒）")

    return scenes


def _format_for_tts(text: str) -> str:
    """
    ElevenLabs 用にテキストを整形する。

    ルール:
      0. 読み間違えやすい漢字をひらがなに変換
      1. 改行を除去（1つの連続テキストにする）
      2. 「%」→「パーセント」に変換（記号を正しく読ませる）
      3. 「&」で囲まれていない単独の「&」→「アンド」（S&P500等は除く）
      4. 句読点「。」の後に半角スペースを挿入（自然なポーズ）
      5. 「！」「？」の後に半角スペースを挿入（感情の間）
      6. 連続する空白を1つに正規化
    """
    # 読み間違えやすい漢字の読み替え辞書
    # ElevenLabsが間違える漢字→正しい読みのひらがなに変換
    for wrong, correct in _READING_FIXES:
        text = text.replace(wrong, correct)

    # 改行を除去
    text = text.replace("\n", "")

    # 「%」→「パーセント」
    text = text.replace("%", "パーセント")

    # 単独の「&」→「アンド」（ただし S&P のような英字に挟まれた & は除く）
    text = re.sub(r"(?<![A-Za-z])&(?![A-Za-z])", "アンド", text)

    # 「でも」「だから」「だけど」の後に間を入れる（断言前のポーズ）
    text = re.sub(r"(でも、|だから、|だけど、)", r"\1 ", text)

    # 句読点・感嘆符の後にスペースを挿入（ポーズ用）
    text = re.sub(r"([。！？])", r"\1 ", text)

    # 連続空白を1つに
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _text_to_speech(
    api_key: str,
    voice_id: str,
    text: str,
    output_path: pathlib.Path,
) -> bool:
    """ElevenLabs API で1シーン分の音声を生成する。失敗時は False。"""
    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.75,
            "style": 0.2,
            "use_speaker_boost": True,
            "speed": 1.15,
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            _save_debug(
                f"elevenlabs_error_{output_path.stem}.json",
                json.dumps({"status": resp.status_code, "body": resp.text}, ensure_ascii=False, indent=2),
            )
            print(f"    ElevenLabs API エラー: {resp.status_code}")
            return False

        output_path.write_bytes(resp.content)
        return True

    except Exception as e:
        print(f"    リクエストエラー: {e}")
        return False


def _get_audio_duration(audio_path: pathlib.Path) -> float:
    """FFprobe で音声の実際の長さ（秒）を取得する。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _save_debug(filename: str, content: str):
    """デバッグ情報を debug/ に保存する。"""
    debug_dir = pathlib.Path(__file__).parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    try:
        (debug_dir / filename).write_text(content, encoding="utf-8")
    except Exception:
        pass

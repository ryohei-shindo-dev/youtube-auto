"""
long_voice_gen.py
5分動画用の音声生成スクリプト。

voice_gen.py の _format_for_tts / _READING_FIXES / _get_audio_duration を流用し、
セクション単位で個別の音声ファイルを生成する。
speed を Shorts(1.15) より遅い 1.05 に設定。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import requests

# voice_gen.py の読み辞書と整形関数を再利用
from voice_gen import _READING_FIXES, _format_for_tts, _get_audio_duration

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# 5分動画用: Shorts(1.15)より少しゆっくり
LONG_VIDEO_SPEED = 1.05

# ── 台本定義 ──────────────────────────────────────────
# セクションごとに分割。role はセクション名、text は読み上げ本文のみ。
SCRIPT_01_SCENES = [
    {
        "role": "hook",
        "text": (
            "含み損。\n"
            "この三文字が、夜を長くします。\n"
            "\n"
            "つらいのは、\n"
            "お金が減って見えるからだけではありません。\n"
            "自分の判断が、間違っていた気がするからです。\n"
            "\n"
            "今日は、\n"
            "含み損で眠れない夜に、\n"
            "どう考えれば少し落ち着けるのか。\n"
            "数字を使って、静かに整理します。"
        ),
    },
    {
        "role": "overview",
        "text": (
            "今日は、二つだけ整理します。\n"
            "なぜ、含み損の夜は必要以上につらいのか。\n"
            "そして、今夜は何をしないのが一番いいのか。\n"
            "\n"
            "途中で一つだけ、\n"
            "金融危機の数字も置きます。\n"
            "\n"
            "ショート動画で言っている、\n"
            "時間が武器、という話を、\n"
            "今日は少しだけ長く整理します。"
        ),
    },
    {
        "role": "why_painful",
        "text": (
            "含み損の夜が苦しいのは、\n"
            "数字そのものより、\n"
            "その先を勝手に想像してしまうからです。\n"
            "\n"
            "このまま戻らなかったらどうしよう。\n"
            "自分だけ判断を間違えたのではないか。\n"
            "ここで止めた方が、傷が浅いのではないか。\n"
            "\n"
            "こういう考えが、一気に出てきます。\n"
            "\n"
            "しかも、\n"
            "口座を何度も見てしまう。\n"
            "朝見て、昼見て、夜見て、寝る前にまた見る。\n"
            "\n"
            "数字は少ししか変わっていなくても、\n"
            "苦しさだけは増えていく。\n"
            "これは珍しいことではありません。\n"
            "\n"
            "カーネマンとトヴェルスキーのプロスペクト理論でも、\n"
            "人は利益より損失を強く感じやすい、\n"
            "つまり、失う痛みの方が大きく出やすいと整理されています。\n"
            "\n"
            "だから、含み損の夜がきついのは、\n"
            "反応としてかなり普通です。"
        ),
    },
    {
        "role": "data",
        "text": (
            "ここで、具体的な数字を置きます。\n"
            "\n"
            "2008年前後の金融危機では、\n"
            "S&P500は\n"
            "2007年10月のピークから\n"
            "2009年3月の底まで、\n"
            "57%下落しました。\n"
            "\n"
            "半分以上です。\n"
            "かなりきつい下落です。\n"
            "\n"
            "でも、その後は止まりませんでした。\n"
            "S&P500は\n"
            "2013年3月に、\n"
            "2007年の高値を回復しています。\n"
            "\n"
            "つまり、\n"
            "下落の最中に切り取ると、\n"
            "もう終わったように見える。\n"
            "でも、時間を伸ばして見ると、\n"
            "景色はかなり変わる、ということです。\n"
            "\n"
            "ここで大事なのは、\n"
            "暴落は痛い、ということと、\n"
            "長く持てば見え方が変わる、ということを、\n"
            "分けて考えることです。"
        ),
    },
    {
        "role": "interpret",
        "text": (
            "今日の下落と、\n"
            "長期の結果は、同じではありません。\n"
            "\n"
            "この数字が意味しているのは、\n"
            "20年持てば絶対大丈夫、\n"
            "という雑な話ではありません。\n"
            "\n"
            "そうではなくて、\n"
            "今見えている下落と、\n"
            "長期での結果は、同じではない、ということです。\n"
            "\n"
            "含み損の夜は、\n"
            "投資全体を、\n"
            "今日の価格だけで採点してしまいます。\n"
            "\n"
            "でも長期投資では、\n"
            "今日の価格は途中です。\n"
            "途中の数字だけで、\n"
            "全部を決めてしまうと、\n"
            "本来受け取れるはずの、かいふくまで、\n"
            "自分で切ってしまうことがあります。\n"
            "\n"
            "過去の大きな下落は、\n"
            "痛かった。\n"
            "でも、その痛みの中でも市場に残った人は、\n"
            "回復を受け取る側に残れた。\n"
            "そこは大きいです。"
        ),
    },
    {
        "role": "action",
        "text": (
            "今夜やることは、多くありません。\n"
            "むしろ、減らした方がいいです。\n"
            "\n"
            "まず、\n"
            "このあと口座アプリをもう開かない。\n"
            "それだけでいいです。\n"
            "\n"
            "次に、\n"
            "積立設定を変えない。\n"
            "増やさなくていい。\n"
            "減らさなくていい。\n"
            "止めなくていい。\n"
            "\n"
            "今夜は、\n"
            "変更しない。\n"
            "それで十分です。\n"
            "\n"
            "不安が大きい夜に判断すると、\n"
            "判断は数字より感情に引っ張られます。\n"
            "だから今夜は、\n"
            "何かを足すより、\n"
            "何もしない方がいいことがあります。\n"
            "\n"
            "長期投資の夜は、\n"
            "動かなかったことが正解になる日があります。"
        ),
    },
    {
        "role": "closing",
        "text": (
            "途中の数字だけで、\n"
            "全部を決めなくていい。\n"
            "\n"
            "今夜やることは、二つです。\n"
            "口座を閉じる。\n"
            "設定を変えない。\n"
            "\n"
            "今日は、それで十分です。\n"
            "\n"
            "ショート動画で話している、\n"
            "時間が武器、という話を、\n"
            "今日は少し長く整理しました。"
        ),
    },
]


# ── 台本定義 02: 積立3年目 ──────────────────────────────
SCRIPT_02_SCENES = [
    {
        "role": "hook",
        "text": (
            "積立3年目。\n"
            "いちばん、しんどい時期です。\n"
            "\n"
            "最初の頃の新鮮さは消えて、\n"
            "でも、結果が出るには早すぎる。\n"
            "\n"
            "口座を見ても、\n"
            "増えているのか減っているのか、\n"
            "よく分からない。\n"
            "\n"
            "今日は、\n"
            "なぜ3年目がいちばんきついのか、\n"
            "その正体を整理します。"
        ),
    },
    {
        "role": "overview",
        "text": (
            "今日整理するのは、二つです。\n"
            "\n"
            "一つ目は、\n"
            "なぜ3年目に気持ちが折れやすいのか。\n"
            "二つ目は、\n"
            "増えない時期に、何が起きているのか。\n"
            "\n"
            "途中で数字も置きます。\n"
            "3年という時間のみえかたが、\n"
            "少しだけ変わるかもしれません。\n"
            "\n"
            "ショート動画でも話している、\n"
            "退場しない、という話を、\n"
            "今日はもう少し丁寧に整理します。"
        ),
    },
    {
        "role": "why_painful",
        "text": (
            "1年目は、まだ新鮮です。\n"
            "積立を始めたばかりで、\n"
            "毎月の引き落としにも意味を感じる。\n"
            "少し増えただけで、嬉しい。\n"
            "\n"
            "2年目は、慣れてくる。\n"
            "良くも悪くも、自動操縦です。\n"
            "特別なことは何もない。\n"
            "\n"
            "問題は、3年目です。\n"
            "\n"
            "3年目になると、\n"
            "積み上がった金額が大きくなっています。\n"
            "だから、相場が下がると、\n"
            "金額の振れ幅も大きく見えるようになる。\n"
            "\n"
            "一方で、\n"
            "複利の効果はまだ小さい。\n"
            "3年では、\n"
            "自分が入れたお金と、\n"
            "増えた分の差が、ほとんど見えません。\n"
            "\n"
            "つまり、\n"
            "減る実感は大きくなるのに、\n"
            "増える実感はまだ来ない。\n"
            "このズレが、3年目をきつくしています。\n"
            "\n"
            "しかも、\n"
            "周りの人はもっと増えているように見える。\n"
            "さんねんも続けたのに、この程度か、\n"
            "と思ってしまう。\n"
            "\n"
            "この、期待と現実の差が、\n"
            "いちばん開くのが3年目です。"
        ),
    },
    {
        "role": "data",
        "text": (
            "ここで、数字を一つ置きます。\n"
            "\n"
            "S&P500に毎月一定額を積み立てた場合、\n"
            "過去のデータでは、\n"
            "3年間の累積リターンが\n"
            "マイナスだった期間もあります。\n"
            "\n"
            "たとえば、\n"
            "2000年から積み立てを始めた人は、\n"
            "3年経った2003年時点で、\n"
            "元本割れの状態でした。\n"
            "\n"
            "ITバブル崩壊の直後です。\n"
            "3年続けて、まだマイナス。\n"
            "かなりきつい状況です。\n"
            "\n"
            "でも、同じ人が止めずに続けた場合、\n"
            "10年後の2010年には、\n"
            "元本を上回っています。\n"
            "20年後の2020年には、\n"
            "大きく増えています。\n"
            "\n"
            "3年で切り取ると、失敗に見える。\n"
            "でも、10年、20年で切り取ると、\n"
            "景色はまったく違います。\n"
            "\n"
            "ここで大事なのは、\n"
            "3年の結果で、20年の意味を判断しない、\n"
            "ということです。"
        ),
    },
    {
        "role": "interpret",
        "text": (
            "増えていない、というのは、\n"
            "意味がない、とは違います。\n"
            "\n"
            "積立の最初の数年は、\n"
            "たねをまいている時期です。\n"
            "芽が出るのは、もっと先です。\n"
            "\n"
            "複利というのは、\n"
            "後半に効いてくる仕組みです。\n"
            "最初の3年で見えなくて当然です。\n"
            "\n"
            "それなのに、\n"
            "3年という時間は、\n"
            "人間の感覚では十分長い。\n"
            "3年も続けたのに、と思うのは自然です。\n"
            "\n"
            "でも、複利の時間軸と、\n"
            "人間の体感する時間軸は、\n"
            "ずれています。\n"
            "\n"
            "このずれを知っているだけで、\n"
            "3年目の景色が少しだけ変わります。\n"
            "\n"
            "やめたくなったとき、\n"
            "増えていないから意味がない、\n"
            "ではなく、\n"
            "まだ結果が出る時期ではない、\n"
            "と整理できるかどうか。\n"
            "ここが分かれ目です。"
        ),
    },
    {
        "role": "action",
        "text": (
            "3年目にやることは、少ないです。\n"
            "\n"
            "まず、\n"
            "3年間の結果で、全体を評価しない。\n"
            "3年は途中です。\n"
            "\n"
            "次に、\n"
            "口座を見る回数を減らす。\n"
            "月に一度で十分です。\n"
            "\n"
            "そして、\n"
            "積立設定を確認する。\n"
            "金額が変わっていなければ、それでいい。\n"
            "閉じて、忘れる。\n"
            "\n"
            "いちばん大事なのは、\n"
            "今の数字で、続けるか止めるかを決めないことです。\n"
            "\n"
            "3年目に退場する人と、\n"
            "3年目を通過する人の違いは、\n"
            "才能でも知識でもなく、\n"
            "ただ、設定を変えなかったかどうかです。"
        ),
    },
    {
        "role": "closing",
        "text": (
            "3年目は、結果ではありません。\n"
            "途中です。\n"
            "\n"
            "増えない時期は、\n"
            "たねをまいている時期です。\n"
            "\n"
            "今日確認したことは二つ。\n"
            "3年の結果で全体を判断しない。\n"
            "設定を変えない。\n"
            "\n"
            "退屈に感じるなら、\n"
            "それは順調な証拠かもしれません。\n"
            "\n"
            "ショート動画でも話している、\n"
            "退場しない人が受け取る、という話を、\n"
            "今日は少し長く整理しました。"
        ),
    },
]


def _text_to_speech_long(
    api_key: str,
    voice_id: str,
    text: str,
    output_path: pathlib.Path,
) -> bool:
    """ElevenLabs API で音声生成（5分動画用speed設定）。"""
    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.6,
            "similarity_boost": 0.75,
            "style": 0.15,
            "use_speaker_boost": True,
            "speed": LONG_VIDEO_SPEED,
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            print(f"    ElevenLabs API エラー: {resp.status_code} {resp.text[:200]}")
            return False
        output_path.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    リクエストエラー: {e}")
        return False


def generate_long_video_voice(
    scenes: list[dict],
    output_dir: pathlib.Path,
) -> list[dict]:
    """
    セクション単位で音声ファイルを生成する。

    Returns:
        scenes に audio_path, actual_duration_sec を追加したリスト
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
    if not api_key or not voice_id:
        print("[エラー] ELEVENLABS_API_KEY または ELEVENLABS_VOICE_ID が未設定です。")
        print("  .env ファイルを確認してください。")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(scenes):
        idx = i + 1
        role = scene["role"]
        output_path = output_dir / f"{idx:02d}_{role}.mp3"

        # TTS用テキスト整形（voice_gen.py の関数を流用）
        text = _format_for_tts(scene["text"])

        print(f"[{idx}/{len(scenes)}] {role} の音声を生成中...")
        success = _text_to_speech_long(api_key, voice_id, text, output_path)

        if success:
            duration = _get_audio_duration(output_path)
            scene["audio_path"] = str(output_path)
            scene["actual_duration_sec"] = duration
            size_kb = output_path.stat().st_size // 1024
            print(f"  -> {output_path.name}（{duration:.1f}秒 / {size_kb}KB）")
        else:
            scene["audio_path"] = None
            scene["actual_duration_sec"] = 0
            print(f"  -> [失敗] {role}")

    # サマリー表示
    total = sum(s.get("actual_duration_sec", 0) for s in scenes)
    ok = sum(1 for s in scenes if s.get("audio_path"))
    print()
    print(f"=== 完了: {ok}/{len(scenes)} セクション成功 ===")
    print(f"=== 合計尺: {total:.1f}秒（{total/60:.1f}分） ===")
    print()

    # セクション別の尺を表示
    for s in scenes:
        dur = s.get("actual_duration_sec", 0)
        print(f"  {s['role']:15s}  {dur:5.1f}秒")

    return scenes


def main():
    """1本目「含み損で眠れない夜」の仮音声を生成する。"""
    # .env を読み込む
    env_path = pathlib.Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    output_dir = pathlib.Path(__file__).parent / "long_video" / "01_fukumison" / "audio"
    print(f"出力先: {output_dir}")
    print(f"speed: {LONG_VIDEO_SPEED}（Shorts: 1.15 → 5分動画: {LONG_VIDEO_SPEED}）")
    print()

    scenes = generate_long_video_voice(SCRIPT_01_SCENES, output_dir)

    # 結果をJSONで保存
    result_path = output_dir.parent / "voice_result.json"
    result_data = [
        {
            "role": s["role"],
            "audio_path": s.get("audio_path"),
            "duration_sec": s.get("actual_duration_sec", 0),
        }
        for s in scenes
    ]
    result_path.write_text(
        json.dumps(result_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n結果を保存: {result_path}")


def main_02():
    """2本目「積立3年目が一番つらい理由」の音声を生成する。"""
    env_path = pathlib.Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    output_dir = pathlib.Path(__file__).parent / "long_video" / "02_tsumitate3" / "audio"
    print(f"出力先: {output_dir}")
    print(f"speed: {LONG_VIDEO_SPEED}（Shorts: 1.15 → 5分動画: {LONG_VIDEO_SPEED}）")
    print()

    scenes = generate_long_video_voice(SCRIPT_02_SCENES, output_dir)

    result_path = output_dir.parent / "voice_result.json"
    result_data = [
        {
            "role": s["role"],
            "audio_path": s.get("audio_path"),
            "duration_sec": s.get("actual_duration_sec", 0),
        }
        for s in scenes
    ]
    result_path.write_text(
        json.dumps(result_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n結果を保存: {result_path}")


if __name__ == "__main__":
    import sys as _sys
    if "--02" in _sys.argv:
        main_02()
    else:
        main()

# long_video/ — 長尺動画モジュール

## 概要
5 分前後の長尺動画を生成するためのディレクトリ。Shorts パイプラインとは別系統。

## 関連スクリプト（リポジトリルートにある）
- `long_voice_gen.py` — 音声合成（速度 1.05x、Shorts の 1.15x より遅い）
- `long_video_builder.py` — スライド + 音声 + BGM を合成
- `publish_long_video.py` — YouTube に予約投稿

## ビジュアルルール（AGENTS.md より）
- **音声主役 / 文字は補助** を徹底
- 1 画面 1 メッセージ、文字量は「見出し + 1 行」まで
- 文字ボックスは常用しない、背景の空気感を主役にする
- ズーム: Ken Burns 方式（`scale→crop`）、100% → 103.5% 固定
  - zoom in: 内面系シーン（hook / empathy / why_painful / data）
  - zoom out: 余韻系シーン（interpret / action / closing）
- `zoompan` フィルターは使わない（揺れるため）

## 背景画像の選び方
チャンネルに合う象徴: 扉 / 灯り / 鍛える / 待つ / 耐える / 夜明け前 / 一人で考える人物 / 静かに進む
避ける象徴: 権威 / 支配感 / 高級車 / 札束 / 威圧的モチーフ

## ディレクトリ構成
```
long_video/
├── 01_fukumison/           # エピソードごとのサブフォルダ
│   ├── audio/              # シーンごとの音声ファイル
│   ├── slides/             # スライド画像
│   ├── overlays/           # テキストオーバーレイ PNG
│   ├── video_meta.json     # タイトル・説明・公開日時
│   ├── voice_result.json   # 音声生成の結果メタデータ
│   ├── *_thumbnail.png     # サムネイル
│   └── *.mp4               # 最終出力動画
└── motion_test/            # ズーム方式の比較テスト用
```

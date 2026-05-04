# Piper Plus

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

高速・高品質なニューラルテキスト音声合成 (TTS) システム。[VITS](https://github.com/jaywalnut310/vits/) アーキテクチャを採用し、8言語マルチスピーカー音声合成に対応。[Piper](https://github.com/rhasspy/piper) のフォークで、日本語対応・音質向上・学習機能を大幅に強化しています。

**[Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly デモ](https://ayutaz.github.io/piper-plus/)** | **[GitHub](https://github.com/ayutaz/piper-plus)**

## 主要機能

- **8言語対応** — 日本語・英語・中国語・韓国語・スペイン語・フランス語・ポルトガル語・スウェーデン語
- **日本語 TTS** — OpenJTalk統合、韻律情報 (A1/A2/A3)、文脈依存音素バリアント
- **英語 TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0)、espeak-ng 不要
- **マルチスピーカー** — ベースモデル571話者、言語グループ均等サンプリング
- **カスタム辞書** — 200+技術用語の発音辞書内蔵
- **音素入力** — `[[ phonemes ]]` 記法による直接指定
- **クロスプラットフォーム** — Linux (x86_64/ARM64)、macOS (Apple Silicon)、Windows (x64)

## インストール

```bash
pip install piper-plus

# GPU サポート
pip install "piper-plus[gpu]"
```

Python 3.11+ が必要です。

## クイックスタート

### コマンドライン

```bash
# モデル一覧を表示
piper --list-models
piper --list-models ja

# モデルをダウンロード
piper --download-model tsukuyomi

# 音声を生成
piper --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

### Python API

```python
import wave
from piper import PiperVoice

voice = PiperVoice.load("path/to/model.onnx", config_path="path/to/config.json")
with wave.open("output.wav", "wb") as wav_file:
    voice.synthesize("こんにちは、今日は良い天気ですね。", wav_file)
```

## Phoneme Timing (リップシンク・字幕同期)

piper-plus は VITS Duration Predictor から音素レベルのタイミング情報を抽出できます。リップシンク、字幕同期、カラオケアプリケーションで使用できます。Rust/Go/C++/C# 実装と byte-for-byte 互換です。

### Python API

```python
from piper import PiperVoice
from piper.timing import (
    PhonemeTimingInfo,
    TimingResult,
    durations_to_timing,
    timing_to_json,
    timing_to_tsv,
    timing_to_srt,
)

voice = PiperVoice.load("model.onnx", config_path="config.json")

# モデルが durations 出力をサポートしているか確認
if voice.has_duration_output:
    wav_bytes, timing = voice.synthesize_with_timing("こんにちは")

    if timing:
        # JSON 出力 (pretty-printed)
        print(timing_to_json(timing))

        # TSV 出力 (タブ区切り、ヘッダ付き)
        with open("timing.tsv", "w") as f:
            f.write(timing_to_tsv(timing))

        # SRT 字幕形式
        with open("subtitles.srt", "w") as f:
            f.write(timing_to_srt(timing))

        # 各音素を直接アクセス
        for p in timing.phonemes:
            print(f"{p.phoneme}: {p.start_ms:.1f} - {p.end_ms:.1f} ms ({p.duration_ms:.1f} ms)")
```

### 出力例

```json
{
  "phonemes": [
    {"phoneme": "^", "start_ms": 0.0, "end_ms": 58.0, "duration_ms": 58.0},
    {"phoneme": "k", "start_ms": 58.0, "end_ms": 150.8, "duration_ms": 92.8},
    {"phoneme": "o", "start_ms": 150.8, "end_ms": 290.0, "duration_ms": 139.2}
  ],
  "total_duration_ms": 290.0,
  "sample_rate": 22050
}
```

### HTTP エンドポイント

`piper.http_server` を起動すると `/api/phoneme-timing` エンドポイントが利用可能になります:

```bash
# JSON で取得
curl "http://localhost:5000/api/phoneme-timing?text=Hello&format=json"

# TSV で取得
curl "http://localhost:5000/api/phoneme-timing?text=Hello&format=tsv"

# 言語指定
curl "http://localhost:5000/api/phoneme-timing?text=Hello&language=en&format=json"
```

### API リファレンス

| 関数 / メソッド | 説明 |
|----------------|------|
| `PiperVoice.synthesize_with_timing(text, ...)` | 音声 + TimingResult を返す |
| `PiperVoice.has_duration_output` | モデルが timing をサポートするか判定 |
| `durations_to_timing(durations, tokens, sample_rate, hop_length)` | duration フレーム → TimingResult |
| `timing_to_json(result)` | pretty-printed JSON |
| `timing_to_json_compact(result)` | 単一行 JSON |
| `timing_to_tsv(result)` | TSV (start_ms, end_ms, duration_ms, phoneme) |
| `timing_to_srt(result)` | SRT 字幕形式 |
| `build_phoneme_id_reverse_map(phoneme_id_map, pua_to_multi_char?)` | ID → 音素文字列の逆引きマップ |

### 設定

`config.json` の `audio.hop_size` で STFT hop length を指定できます (デフォルト: 256)。値は `PiperConfig.hop_size` 経由で利用され、timing 計算に使用されます。

## 事前学習済みモデル

| モデル | 言語 | 話者数 | ダウンロード |
|--------|------|--------|-------------|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | 6言語 (ja/en/zh/es/fr/pt) | 571 | `piper --download-model base` |
| [tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | 6言語 (ja/en/zh/es/fr/pt) | 1 | `piper --download-model tsukuyomi` |

## 対応言語

| 言語 | コード | Phonemizer | 依存 |
|------|--------|------------|------|
| 日本語 | ja | OpenJTalk | pyopenjtalk-plus |
| 英語 | en | g2p-en | g2p-en (Apache-2.0) |
| 中国語 | zh | pypinyin | pypinyin |
| 韓国語 | ko | g2pk2 | g2pk2 (Apache-2.0, optional) |
| スペイン語 | es | 規則ベース | なし |
| フランス語 | fr | 規則ベース | なし |
| ポルトガル語 | pt | 規則ベース | なし |
| スウェーデン語 | sv | 規則ベース | なし |

## その他のインターフェース

- **[C++ CLI](https://github.com/ayutaz/piper-plus/releases)** — ストリーミング、CUDA推論、カスタム辞書
- **[Rust CLI](https://github.com/ayutaz/piper-plus/tree/dev/src/rust)** — ストリーミング、CUDA/CoreML/DirectML対応
- **[C# CLI (.NET)](https://github.com/ayutaz/piper-plus/tree/dev/src/csharp)** — クロスプラットフォーム .NET 10
- **[WebAssembly](https://ayutaz.github.io/piper-plus/)** — ブラウザ内で完全動作
- **[Docker](https://github.com/ayutaz/piper-plus/tree/dev/docker)** — 推論・学習・WebUI イメージ

## リンク

- [GitHub リポジトリ](https://github.com/ayutaz/piper-plus)
- [Hugging Face デモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
- [Hugging Face モデル](https://huggingface.co/ayousanz/piper-plus-base)
- [ドキュメント](https://github.com/ayutaz/piper-plus/tree/dev/docs)

## ライセンス

MIT License — 詳細は [LICENSE](https://github.com/ayutaz/piper-plus/blob/dev/LICENSE.md) を参照。

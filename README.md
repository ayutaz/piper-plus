![Piper logo](etc/logo.png)

[English](README_EN.md) | 日本語

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

A fast, local neural text to speech system that sounds great and is optimized for the Raspberry Pi 4.
Piper is used in a [variety of projects](#people-using-piper).

🎙️ **[Try Piper TTS Demo on Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** - Experience Japanese and English text-to-speech in your browser!

## 目次
- [追加機能](#追加機能)
- [関連記事](#関連記事)
- [プラットフォームサポート](#プラットフォームサポート)
  - [対応プラットフォーム](#対応プラットフォーム)
  - [⚠️ 重要: macOSユーザーへのお知らせ](#️-重要-macosユーザーへのお知らせ)
- [Voices](#voices)
- [Installation](#installation)
- [Usage](#usage)
  - [Streaming Audio](#streaming-audio)
  - [JSON Input](#json-input)
- [People using Piper](#people-using-piper)
- [事前学習済みモデル](#事前学習済みモデル)
- [Training](#training)
- [Running in Python](#running-in-python)

## 追加機能
* **🌐 WebUI (Gradio)** - ブラウザベースの使いやすいインターフェース
  * 🚀 **[オンラインデモ](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** - Hugging Face Spacesで今すぐ試せます！
  * 🌏 **[WebAssemblyデモ](https://ayutaz.github.io/piper-plus/)** - ブラウザで動作する日本語TTSデモ（サーバー不要）
  * 詳細は[WebUI使用ガイド](docs/features/webui-usage.md)を参照
  * 推論と学習の両方に対応
  * 多言語テンプレートシステム（日本語、英語、ドイツ語、フランス語）
  * Docker対応で簡単デプロイ
  * 使用例: `python -m piper.webui --data-dir ./models`
* **🎤 音素入力機能** - `[[ phonemes ]]` 記法による直接音素指定
  * 詳細は[音素入力ガイド](docs/features/phoneme-input.md)を参照
  * 使用例: `echo "Hello [[ h ə l oʊ ]] world" | piper --model en.onnx -f out.wav`
  * 日本語例: `echo "今日は [[ ky o o w a ]] です" | piper --model ja.onnx -f out.wav`
* **📚 カスタム辞書機能** - 技術用語や固有名詞の読みを正確に制御
  * 詳細は[カスタム辞書ガイド](docs/features/custom_dictionary.md)を参照
  * 200以上の技術用語を含むデフォルト辞書（Docker→ドッカー、GitHub→ギットハブ等）
  * 使用例: `echo "DockerとGitHubを使います" | piper --model ja.onnx --custom-dict my_dict.json -f out.wav`
  * Python/C++両対応、複数辞書の同時使用可能
* 日本語の事前学習及び追加学習/推論対応（OpenJTalk統合）
  * 詳細な使用方法は[日本語音声合成ガイド](docs/guides/japanese/japanese-usage.md)を参照
  * **Windows対応**: [Windowsセットアップガイド](docs/getting-started/windows-setup.md)を参照
  * **API ドキュメント**: [OpenJTalk API リファレンス](docs/guides/japanese/openjtalk-api.md)を参照
  * PUA音素マッピングによる日本語TTS精度向上 - [技術詳細](docs/api-reference/phoneme-mapping.md)を参照
  * **自動ダウンロード機能**: 初回実行時に必要な辞書とHTSボイスファイルを自動ダウンロード
  * 環境変数（オプション）：
    - `OPENJTALK_DICTIONARY_DIR`: OpenJTalk辞書へのパス（未設定時は自動ダウンロード）
    - `OPENJTALK_VOICE`: HTSボイスモデル（.htsvoice）へのパス（未設定時は自動ダウンロード）
    - `PIPER_AUTO_DOWNLOAD_DICT`: `0`に設定すると自動ダウンロードを無効化
    - `PIPER_OFFLINE_MODE`: `1`に設定するとオフラインモード（ネットワーク接続不要）
  * 既存の日本語モデルは**再学習不要** - 設定ファイルの更新のみで対応可能
* GitHub Actionsによる自動ビルドとバイナリー配布（詳細は[プラットフォームサポート](#プラットフォームサポート)を参照）
* 前処理済み .pt ファイルが破損していても学習時に自動スキップして継続できるように改善
* DataLoader に `pin_memory=True` を設定し GPU 転送を最適化
* `preprocess.py` に `--timeout-seconds` を追加し、ハングする発話を自動タイムアウト/スキップ
* `piper_train` に `--num-workers` を追加し、DataLoader のワーカー数をコマンドラインから指定可能に
* `piper_train` に `--save-top-k` を追加し、チェックポイント保存個数をコマンドラインから指定可能に
* PyPI パッケージ `piper-tts-plus` として公開し、`pip install` で簡単インストール可能に
* 多言語TTSテストインフラストラクチャーを追加し、CI/CDで自動テスト実行 - [詳細](docs/guides/testing/multilingual-testing.md)
* OpenJTalk辞書とHTSボイスモデルの自動ダウンロード機能を追加し、日本語TTSのセットアップを簡略化
* **🌏 WebAssembly対応** - ブラウザで直接動作する日本語TTS実装
  * OpenJTalk WebAssembly版による日本語音素化
  * ONNX Runtime WebAssemblyによるニューラル音声合成
  * サーバー不要で完全にブラウザ内で動作
  * コンパクトサイズ: WASM < 400KB、JS < 40KB
  * 詳細: [OpenJTalk WebAssembly README](src/wasm/openjtalk-web/README.md)
* **🎯 音声品質向上機能**
  * **EMA (Exponential Moving Average)**: 学習安定性とファインチューニング品質向上（デフォルトで有効）
  * **カスタム辞書機能**: 日本語発音の精度向上（478エントリの発音辞書を標準搭載）
  * **効果**: 学習の安定性向上、日本語複合語の正確な発音
  * 詳細: [EMA実装ドキュメント](src/python/docs/integrated-components-ja.md)
* マルチGPU学習対応（PyTorch Lightning 2.4.0）
  * DDP (Distributed Data Parallel) 戦略による複数GPU並列学習
  * 学習率の自動スケーリング機能（`--auto_lr_scaling`）
  * コード品質向上（セキュリティ強化、分散ログ最適化）
  * 使用例：
    ```bash
    python -m piper_train \
      --dataset-dir /path/to/dataset \
      --batch-size 64 \
      --devices 4 \
      --strategy ddp_find_unused_parameters_true \
      --ema-decay 0.9995 \
      --num-workers 80
    # 注: --auto_lr_scaling はデフォルトで有効
    # EMAもデフォルトで有効、--no-emaで無効化可能
    ```
* **📊 Wandb統合** - 学習メトリクスのリアルタイム監視
  * wandbがインストールされていれば自動的にログを送信
  * TensorBoardと並行して使用可能
  * プロジェクト名: `piper-tts`、run名: データセットディレクトリ名
  * インストール: `pip install wandb`
  * 設定: `wandb login`でAPIキーを設定
* チェックポイント管理機能の強化
  * `--resume_from_checkpoint` でチェックポイントからの学習再開
  * `--resume_from_single_speaker_checkpoint` でシングルスピーカーモデルからマルチスピーカーへの変換
* GPU推論サポート（C++バイナリ）
  * `--use-cuda` オプションでONNX Runtime CUDAプロバイダーを有効化
* 学習時の高度なオプション
  * `--gradient_clip_val` - 勾配クリッピング
  * `--accumulate_grad_batches` - 勾配累積によるバッチサイズ仮想拡張
  * `--precision` - Mixed Precision Training対応（16-mixed等）
  * `--detect_anomaly` - 学習時の異常検出機能
* 音声評価ツール（`scripts/evaluation/`）
  * MCD (Mel-Cepstral Distortion) 評価
  * PESQ (Perceptual Evaluation of Speech Quality) 評価
  * UTMOS評価
* **🎵 CLI機能強化** - [詳細ドキュメント](docs/features/cli-enhancements.md)
  * **音量調整**: `--volume` オプション (0.1-2.0)
  * **自動再生**: `--auto-play` で生成後自動再生
  * **直接テキスト入力**: `piper "テキスト" --model model.onnx`
  * **ファイル入力**: `--input-file` で複数ファイル対応
  * **使用例**:
    ```bash
    # 音量調整付き自動再生
    piper "こんにちは" --model ja_JP-test.onnx --volume 1.2 --auto-play
    
    # ファイルから読み込み
    piper --model en_US-lessac.onnx --input-file story.txt -f output.wav
    ```
* **🎯 音素タイミング情報出力** - [詳細ドキュメント](docs/features/phoneme-timing.md)
  * リップシンク、カラオケ、字幕同期用のタイミング情報
  * JSON/TSV形式での出力
  * 使用例:
    ```bash
    echo "Hello world" | piper --model en_US-lessac.onnx \
      --output-file speech.wav --output-timing timing.json
    ```

## 関連記事
* [LJSpeechを使って英語のpiperの事前学習モデルを作成する](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
* [jvs音声データセットを使ったpiper日本語モデルの作成](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
* [piperモデルからつくよみちゃんデータセットを使って追加学習を行う](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

``` sh
echo 'Welcome to the world of speech synthesis!' | \
  ./piper --model en_US-lessac-medium.onnx --output_file welcome.wav

# Streaming mode for reduced latency (outputs audio chunks progressively)
echo 'This is a long text that will be processed in chunks for lower latency.' | \
  ./piper --model en_US-lessac-medium.onnx --output_file output.wav --streaming
```

### Streaming Mode

The `--streaming` flag enables chunk-based processing for reduced latency:
- **Dynamic chunk sizing**: Automatically adjusts chunk size based on punctuation density
- **Audio crossfading**: Smooth transitions between chunks to prevent clicks/artifacts
- **~15% latency reduction** for long texts

[Listen to voice samples](https://rhasspy.github.io/piper-samples) and check out a [video tutorial by Thorsten Müller](https://youtu.be/rjq5eZoWWSo)

Voices are trained with [VITS](https://github.com/jaywalnut310/vits/) and exported to the [onnxruntime](https://onnxruntime.ai/).

[![A library from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-library.png)](https://www.openhomefoundation.org/)

## プラットフォームサポート

### 対応プラットフォーム

| プラットフォーム | アーキテクチャ | OpenJTalk対応 | 備考 |
|-----------------|---------------|--------------|------|
| Linux | x86_64 (amd64) | ✅ | フルサポート |
| Linux | ARM64 | ✅ | フルサポート (CMakeビルド使用) |
| macOS | **ARM64 (Apple Silicon)のみ** | ✅ | M1/M2/M3以降のMac専用 |
| Windows | x64 | ✅ | フルサポート |
| **Web (ブラウザ)** | WebAssembly | ✅ | Chrome/Edge/Firefox/Safari対応 |

### ⚠️ 重要: macOSユーザーへのお知らせ

**2024年より、macOSではApple Silicon (M1/M2/M3以降) のみをサポートしています。**

#### Intel Macをお使いの方へ
Intel Mac (x86_64) のサポートは終了しました。以下の代替方法をご利用ください：

1. **Dockerを使用（推奨）**
   ```bash
   # Dockerイメージをプル
   docker pull ghcr.io/ayutaz/piper-plus:latest
   
   # 実行例
   docker run --rm -v $(pwd):/data ghcr.io/ayutaz/piper-plus:latest \
     echo "Hello from Docker" | piper --model /data/model.onnx --output_file /data/output.wav
   ```

2. **ソースからビルド**
   ```bash
   # 依存関係をインストール
   brew install cmake onnxruntime
   
   # ビルド
   git clone https://github.com/ayutaz/piper-plus.git
   cd piper-plus
   mkdir build && cd build
   cmake .. -DCMAKE_BUILD_TYPE=Release
   make -j$(sysctl -n hw.ncpu)
   ```

3. **仮想マシンでLinux版を使用**
   - UTM、Parallels Desktop、VMware Fusionなどを使用

#### Apple Siliconユーザーの方へ
通常通りダウンロードしてご利用いただけます。初回実行時のセキュリティ警告については、以下をご参照ください。

##### macOSセキュリティ警告の対処
ダウンロードしたバイナリを初めて実行する際、macOSのセキュリティ機能により警告が表示される場合があります。以下のコマンドで検疫属性を削除してください：

```bash
# ダウンロードしたファイルを展開後
xattr -cr piper/

# または特定のバイナリのみ
xattr -cr piper/bin/piper
xattr -cr piper/bin/open_jtalk  # 日本語TTSを使用する場合
```

これにより、Gatekeeperの警告なしに実行できるようになります。

### 🌐 WebAssembly版（ブラウザ対応）

Piper-plusはWebAssemblyを使用してブラウザで直接動作します：

#### 特徴
- **完全ブラウザ動作**: サーバー不要、オフライン対応
- **日本語対応**: OpenJTalk WebAssembly版による高精度な音素化
- **軽量**: WASM < 400KB、JS < 40KB
- **対応ブラウザ**: Chrome、Edge、Firefox、Safari（最新版）

#### デモ・使用方法
- 🌏 **[オンラインデモ](https://ayutaz.github.io/piper-plus/)** - 今すぐブラウザで試せます
- 📖 **[技術詳細](docs/webassembly/openjtalk-approach/README.md)** - 実装の詳細情報
- 🔧 **[統合ガイド](src/wasm/openjtalk-web/README.md)** - Webアプリへの組み込み方法

## Voices

Our goal is to support Home Assistant and the [Year of Voice](https://www.home-assistant.io/blog/2022/12/20/year-of-voice/).

[Download voices](docs/api-reference/available-voices.md) for the supported languages:

* العربية, Jordan (Arabic, ar_JO)
* Català, Spain (Catalan, ca_ES)
* Čeština, Czech Republic (Czech, cs_CZ)
* Cymraeg, Great Britain (Welsh, cy_GB)
* Dansk, Denmark (Danish, da_DK)
* Deutsch, Germany (German, de_DE)
* Ελληνικά, Greece (Greek, el_GR)
* English, Great Britain (English, en_GB)
* English, United States (English, en_US)
* Español, Argentina (Spanish, es_AR)
* Español, Spain (Spanish, es_ES)
* Español, Mexico (Spanish, es_MX)
* فارسی, Iran (Farsi, fa_IR)
* Suomi, Finland (Finnish, fi_FI)
* Français, France (French, fr_FR)
* Magyar, Hungary (Hungarian, hu_HU)
* íslenska, Iceland (Icelandic, is_IS)
* Italiano, Italy (Italian, it_IT)
* ქართული ენა, Georgia (Georgian, ka_GE)
* қазақша, Kazakhstan (Kazakh, kk_KZ)
* Lëtzebuergesch, Luxembourg (Luxembourgish, lb_LU)
* Latviešu, Latvia (Latvian, lv_LV)
* മലയാളം, India (Malayalam, ml_IN)
* हिंदी, India (Hindi, hi_IN)
* नेपाली, Nepal (Nepali, ne_NP)
* Nederlands, Belgium (Dutch, nl_BE)
* Nederlands, Netherlands (Dutch, nl_NL)
* Norsk, Norway (Norwegian, no_NO)
* Polski, Poland (Polish, pl_PL)
* Português, Brazil (Portuguese, pt_BR)
* Português, Portugal (Portuguese, pt_PT)
* Română, Romania (Romanian, ro_RO)
* Русский, Russia (Russian, ru_RU)
* Slovenčina, Slovakia (Slovak, sk_SK)
* Slovenščina, Slovenia (Slovenian, sl_SI)
* srpski, Serbia (Serbian, sr_RS)
* Svenska, Sweden (Swedish, sv_SE)
* Kiswahili, Democratic Republic of the Congo (Swahili, sw_CD)
* Türkçe, Turkey (Turkish, tr_TR)
* украї́нська мо́ва, Ukraine (Ukrainian, uk_UA)
* Tiếng Việt, Vietnam (Vietnamese, vi_VN)
* 简体中文, China (Chinese, zh_CN)

You will need two files per voice:

1. A `.onnx` model file, such as [`en_US-lessac-medium.onnx`](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx)
2. A `.onnx.json` config file, such as [`en_US-lessac-medium.onnx.json`](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json)

The `MODEL_CARD` file for each voice contains important licensing information. Piper is intended for text to speech research, and does not impose any additional restrictions on voice models. Some voices may have restrictive licenses, however, so please review them carefully!


## Installation

### Dependencies

Piper has different requirements depending on your use case:

```bash
# For inference only (using pre-trained models)
pip install -r requirements.txt

# For training custom models
pip install -r requirements-train.txt

# For development (includes testing and linting tools)
pip install -r requirements-dev.txt
```

## Quick Start - WebUI

The easiest way to get started with Piper is using the WebUI:

```bash
# Install inference dependencies first
pip install -r requirements.txt

# Install WebUI dependencies
pip install gradio>=4.0.0

# Run WebUI
cd src/python_run
python -m piper.webui --data-dir /path/to/models
```

Or using Docker:

```bash
# Run with Docker
docker run -p 7860:7860 -v ./models:/models ghcr.io/rhasspy/piper-webui
```

Access the WebUI at http://localhost:7860

## Installation

You can [run Piper with Python](#running-in-python) or download a binary release:

* [amd64](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz) (64-bit desktop Linux)
* [arm64](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz) (64-bit Raspberry Pi 4)
* [armv7](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_armv7.tar.gz) (32-bit Raspberry Pi 3/4)

### Building from Source

If you want to build from source, see the [CMakeLists.txt](CMakeLists.txt) and [C++ source](src/cpp).

#### Prerequisites

* C++ compiler with C++17 support
* CMake 3.13 or later
* Git

#### Build Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/rhasspy/piper.git
   cd piper
   ```

2. Create build directory:
   ```bash
   mkdir build
   cd build
   ```

3. Configure and build:
   ```bash
   cmake ..
   cmake --build . --config Release
   ```

#### Platform-specific Notes

**Linux**: You must download and extract [piper-phonemize](https://github.com/rhasspy/piper-phonemize) to `lib/Linux-$(uname -m)/piper_phonemize` before building.
For example, `lib/Linux-x86_64/piper_phonemize/lib/libpiper_phonemize.so` should exist for AMD/Intel machines.

**Windows**: See the [Windows Setup Guide](docs/getting-started/windows-setup.md) for detailed instructions.

**macOS**: The build process will automatically download required dependencies.


## Usage

1. [Download a voice](#voices) and extract the `.onnx` and `.onnx.json` files
2. Run the `piper` binary with text on standard input, `--model /path/to/your-voice.onnx`, and `--output_file output.wav`

For example:

``` sh
echo 'Welcome to the world of speech synthesis!' | \
  ./piper --model en_US-lessac-medium.onnx --output_file welcome.wav
```

For multi-speaker models, use `--speaker <number>` to change speakers (default: 0).

### Additional Options

* `--use-cuda` - Enable GPU acceleration with CUDA
* `--gpu-device-id <number>` - GPU device ID for CUDA (default: 0)
* `--quiet` / `-q` - Disable logging output
* `--phoneme-silence <phoneme> <seconds>` - Set silence duration for specific phonemes
* `--length-scale <value>` - Adjust speech speed (default: 1.0, smaller = faster)
* `--noise-scale <value>` - Control audio variation (default: 0.667)
* `--noise-w <value>` - Control phoneme duration variation (default: 0.8)
* `--sentence-silence <seconds>` - Silence between sentences (default: 0.2)
* `--raw-phonemes` - Interpret input as raw phonemes (space-separated)

See `piper --help` for more options.

### Phoneme Input

Piper supports two methods for direct phoneme input:

1. **Inline phoneme notation** - Mix text with phonemes using `[[ ]]`:
   ```sh
   echo 'Hello [[ h ə l oʊ ]] world' | ./piper --model en_US-lessac-medium.onnx -f output.wav
   ```

2. **Raw phoneme mode** - Input only phonemes with `--raw-phonemes`:
   ```sh
   echo 'h ə l oʊ _ w ɜː l d' | ./piper --model en_US-lessac-medium.onnx --raw-phonemes -f output.wav
   ```

See [raw-phoneme-input.md](docs/features/raw-phoneme-input.md) for detailed documentation.

### Windows Troubleshooting

If you encounter the error "Could not find espeak-ng-data directory" on Windows:

1. **Check Directory Structure**: Ensure your Piper installation has the following structure:
   ```
   piper/
   ├── piper.exe
   ├── espeak-ng.dll
   ├── piper_phonemize.dll
   └── espeak-ng-data/       # This directory must be present
       └── phontab            # This file must exist
   ```

2. **Alternative Locations**: The program also searches for `espeak-ng-data` in:
   - `../share/espeak-ng-data` (relative to piper.exe)
   - Standard eSpeak NG installation paths

3. **Manual Configuration**: If the automatic detection fails, you can:
   - Set the `ESPEAK_DATA_PATH` environment variable:
     ```cmd
     set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
     piper.exe --model en_US-lessac-medium.onnx -f output.wav
     ```
   - Or use the `--espeak_data` command-line option:
     ```cmd
     piper.exe --espeak_data C:\path\to\espeak-ng-data --model en_US-lessac-medium.onnx -f output.wav
     ```

4. **Download Missing Data**: If `espeak-ng-data` is missing from your distribution:
   - Download it from the [official releases](https://github.com/ayutaz/piper-plus/releases)
   - Extract it to the same directory as `piper.exe`

For more Windows-specific information, see the [Windows Setup Guide](docs/getting-started/windows-setup.md).

### Streaming Audio

Piper can stream raw audio to stdout as its produced:

``` sh
echo 'This sentence is spoken first. This sentence is synthesized while the first sentence is spoken.' | \
  ./piper --model en_US-lessac-medium.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

This is **raw** audio and not a WAV file, so make sure your audio player is set to play 16-bit mono PCM samples at the correct sample rate for the voice.

### JSON Input

The `piper` executable can accept JSON input when using the `--json-input` flag. Each line of input must be a JSON object with `text` field. For example:

``` json
{ "text": "First sentence to speak." }
{ "text": "Second sentence to speak." }
```

Optional fields include:

* `speaker` - string
    * Name of the speaker to use from `speaker_id_map` in config (multi-speaker voices only)
* `speaker_id` - number
    * Id of speaker to use from 0 to number of speakers - 1 (multi-speaker voices only, overrides "speaker")
* `output_file` - string
    * Path to output WAV file
    
The following example writes two sentences with different speakers to different files:

``` json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```


## People using Piper

Piper has been used in the following projects/papers:

* [Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md)
* [Rhasspy 3](https://github.com/rhasspy/rhasspy3/)
* [NVDA - NonVisual Desktop Access](https://www.nvaccess.org/post/in-process-8th-may-2023/#voices)
* [Image Captioning for the Visually Impaired and Blind: A Recipe for Low-Resource Languages](https://www.techrxiv.org/articles/preprint/Image_Captioning_for_the_Visually_Impaired_and_Blind_A_Recipe_for_Low-Resource_Languages/22133894)
* [Open Voice Operating System](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper)
* [JetsonGPT](https://github.com/shahizat/jetsonGPT)
* [LocalAI](https://github.com/go-skynet/LocalAI)
* [Lernstick EDU / EXAM: reading clipboard content aloud with language detection](https://lernstick.ch/)
* [Natural Speech - A plugin for Runelite, an OSRS Client](https://github.com/phyce/rl-natural-speech)
* [mintPiper](https://github.com/evuraan/mintPiper)
* [Vim-Piper](https://github.com/wolandark/vim-piper)

## Unity Integration - uPiper

PiperをUnityで使用するためのプラグイン「uPiper」が開発されています：

* **GitHub**: https://github.com/ayutaz/uPiper
* **Unity 6000.0.35f1以降対応**
* **Unity.InferenceEngine**を使用したONNXモデル実行
* 非同期APIとストリーミングサポート
* 現在は日本語と英語に対応（他言語は今後対応予定）
* **対応プラットフォーム**:
  - Windows (x64)
  - macOS (Apple Silicon対応、IntelはDocker環境でのみ)
  - Linux (x64)
  - Android (ARM64)
  - iOS（未対応）
  - WebGL（計画中）

uPiperは、ゲーム開発やインタラクティブアプリケーションでPiper TTSを活用するための包括的なソリューションを提供します。

## 事前学習済みモデル

日本語TTSのファインチューニング用ベースモデルをHugging Faceで公開しています。

| モデル | 説明 | ライセンス |
|--------|------|-----------|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | 日本語TTS ベースモデル（VITS + WavLM Discriminator + Prosody） | CC-BY-SA-4.0 |
| [piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | つくよみちゃんファインチューニング済みモデル | モデルカード参照 |

### piper-plus-base の特徴

- **アーキテクチャ**: VITS + WavLM Discriminator
- **学習データ**: 60,164発話（20話者）
- **サンプリングレート**: 22,050 Hz
- **Prosody Features**: A1/A2/A3 韻律情報対応（`--prosody-dim 16`）
- **拡張音素**: 疑問詞マーカー、文脈依存「ん」バリアント
- **音素数**: 65

詳細は [Hugging Face モデルカード](https://huggingface.co/ayousanz/piper-plus-base) および [学習ガイド](docs/guides/training/training-guide.md) を参照してください。

## Training

See the [training guide](docs/guides/training/training-guide.md) and the [source code](src/python).

Pretrained checkpoints are available on [Hugging Face](https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main)


## Running in Python

See [src/python_run](src/python_run)

Install with `pip`:

``` sh
# 基本機能のみ
pip install piper-tts-plus

# GPU 版 (CUDA 環境がある場合)
pip install "piper-tts-plus[gpu]"

# HTTP サーバー機能を含む場合
pip install "piper-tts-plus[http]"

# GPU + HTTP
pip install "piper-tts-plus[gpu,http]"
```

This will automatically download [voice files](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0) the first time they're used. Use `--data-dir` and `--download-dir` to adjust where voices are found/downloaded.

If you'd like to use a GPU, install the `onnxruntime-gpu` package:


``` sh
.venv/bin/pip3 install onnxruntime-gpu
```

and then run `piper` with the `--cuda` argument. You will need to have a functioning CUDA environment, such as what's available in [NVIDIA's PyTorch containers](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/pytorch).


## Documentation

For detailed documentation, see the [docs/](docs/) directory.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

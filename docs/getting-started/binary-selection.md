# CLI バイナリの選び方

GitHub Releases には 3 種類の CLI バイナリが並んでおり、初めて使うときはどれを選べばよいか迷いがちです。このドキュメントは、用途・OS・アーキテクチャから最適なバイナリを選ぶための判断材料をまとめたものです。

**迷ったら C++ CLI (`piper-*`) を選んでください。** 最も多くのプラットフォームで動作し、Quick Start のサンプルとも整合しています。

## 目次

- [3 つのバリアントの比較](#3-つのバリアントの比較)
- [OS x アーキテクチャ対応マトリクス](#os-x-アーキテクチャ対応マトリクス)
- [判断フロー](#判断フロー)
- [ダウンロード方法](#ダウンロード方法)
- [トラブルシューティング](#トラブルシューティング)

## 3 つのバリアントの比較

| バリアント | 実装 | プレフィクス | 特徴 | 推奨用途 |
|---|---|---|---|---|
| **C++ CLI** | C++ | `piper-*` | 最も成熟・安定。バイナリサイズ最小、起動が軽量。armv7 (32bit ARM) を唯一サポート。OpenJTalk 辞書の自動 DL に対応 | 初めて使う / 組み込み機器 / Raspberry Pi / 本番運用で安定性重視 |
| **C# .NET CLI** | C# / .NET 10 | `piper-plus-cli-*` | 8 言語マルチリンガル (JA/EN/ZH/KO/ES/FR/PT/SV)、`lid` テンソル対応、ストリーミング文分割、カスタム辞書 (JSON/TSV)、インライン音素 `[[ph]]` 記法、モデル名自動解決。Intel Mac (osx-x64) を唯一サポート | Windows ユーザー / Intel Mac ユーザー / 多言語合成 / .NET 環境との統合 |
| **Rust CLI** | Rust | `piper-plus-rs-cli-*` | ストリーミング、CUDA / CoreML / DirectML での GPU 推論対応。8 言語対応。`--sentence-silence`, `--phoneme-silence` 等の細かい無音制御。jpreprocess (lindera) と naist-jdic (OpenJTalk) を選択可能 | GPU 推論を使いたい / 最新機能や細かいチューニングを試したい / 開発者 |

各バリアントの実装は `src/cpp/`、`src/csharp/PiperPlus.Cli/`、`src/rust/piper-cli/` にあります。

## OS x アーキテクチャ対応マトリクス

`o` = 配布あり、`-` = 配布なし

| OS / アーキテクチャ | C++ (`piper-*`) | C# (`piper-plus-cli-*`) | Rust (`piper-plus-rs-cli-*`) |
|---|:---:|:---:|:---:|
| Linux x64 | o | o | o |
| Linux arm64 (Raspberry Pi 5 等) | o | o | - |
| Linux armv7 (Raspberry Pi 4 32bit 等) | o | - | - |
| macOS arm64 (Apple Silicon) | o | o | o |
| macOS x64 (Intel Mac) | - | o | - |
| Windows x64 | o | o | o |
| Windows arm64 | - | o | - |

Intel Mac、Linux armv7、Windows arm64 のいずれかを使う場合は、選択肢が一意に決まる点に注意してください。

## 判断フロー

1. **Raspberry Pi 4 (32bit) などの armv7 環境** -> **C++ CLI 一択** (`piper-linux-armv7.tar.gz`)
2. **Intel Mac (macOS x64)** -> **C# .NET CLI 一択** (`piper-plus-cli-osx-x64.tar.gz`)
3. **Windows on ARM** -> **C# .NET CLI 一択** (`piper-plus-cli-win-arm64.zip`)
4. **GPU 推論 (CUDA / CoreML / DirectML) を使いたい** -> **Rust CLI**
5. **Windows / 多言語 (中国語・スペイン語など) を使う / .NET と統合したい** -> **C# .NET CLI**
6. **上記に当てはまらない / とにかく動かしたい / 何を選んでよいか分からない** -> **C++ CLI**

Apple Silicon Mac で `piper-macos-arm64.tar.gz` (C++) と `piper-plus-cli-osx-arm64.tar.gz` (C#) で迷った場合、まずは C++ を試し、多言語合成や `lid` テンソル対応モデルを使う場面で C# を検討するのがおすすめです。

## ダウンロード方法

最新リリースは <https://github.com/ayutaz/piper-plus/releases/latest> にあります。以下は代表的なコマンド例です (ファイル名のバージョン部分は実際のリリースに合わせてください)。

### C++ CLI (macOS arm64)

```bash
curl -LO https://github.com/ayutaz/piper-plus/releases/latest/download/piper-macos-arm64.tar.gz
tar -xzf piper-macos-arm64.tar.gz
cd piper
./bin/piper --help
```

### C# .NET CLI (Linux x64)

```bash
curl -LO https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cli-linux-x64.tar.gz
tar -xzf piper-plus-cli-linux-x64.tar.gz
./PiperPlus.Cli --help
```

### Rust CLI (Windows x64)

PowerShell:

```powershell
Invoke-WebRequest -Uri https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-rs-cli-win-x64.zip -OutFile piper-plus-rs-cli.zip
Expand-Archive piper-plus-rs-cli.zip -DestinationPath piper-plus-rs-cli
.\piper-plus-rs-cli\piper-plus-cli.exe --help
```

実行例の詳細は README の Quick Start セクションを参照してください。

## トラブルシューティング

### macOS: 「開発元を確認できないため開けません」

Gatekeeper によりブロックされる場合があります。展開後、隔離属性を外してください。

```bash
xattr -dr com.apple.quarantine ./bin/piper
```

または「システム設定 > プライバシーとセキュリティ」から個別に許可することもできます。

### Linux: `error while loading shared libraries: libonnxruntime.so`

C++ CLI のアーカイブには ONNX Runtime の共有ライブラリが `lib/` ディレクトリに同梱されています。展開した `piper` ディレクトリ直下で `LD_LIBRARY_PATH` に `lib` を追加してから実行してください。

```bash
export LD_LIBRARY_PATH=$(pwd)/lib:$LD_LIBRARY_PATH
./bin/piper --help
```

### Windows: Defender / SmartScreen によるブロック

署名されていないバイナリは初回起動時にブロックされることがあります。「詳細情報」 -> 「実行」で許可するか、ファイルのプロパティから「ブロックの解除」にチェックを入れてください。

### C# .NET CLI: ランタイム不要

`piper-plus-cli-*` はセルフコンテインド (self-contained) でビルドされており、別途 .NET ランタイムをインストールする必要はありません。

### より詳しい問題

その他の問題は [troubleshooting.md](./troubleshooting.md) を参照してください。

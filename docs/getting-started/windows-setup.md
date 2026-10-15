# Windows セットアップガイド

Windows で C++ CLI を使う手順です。通常は配布バイナリを利用し、ソースを変更するときにビルドしてください。ほかの CLI との違いは [バイナリの選び方](binary-selection.md) を参照してください。

## 配布バイナリを使う

[GitHub Releases](https://github.com/ayutaz/piper-plus/releases) から `piper-plus-cpp-windows-x64.zip` を取得し、アーカイブ全体を展開します。`bin/piper-plus.exe` と同梱 DLL、`share/` の配置を保持してください。

PowerShell で展開先の `piper-plus` ディレクトリに移動します。

```powershell
.\bin\piper-plus.exe --help
```

モデルの取得方法は [事前学習済みモデル](../guides/development/pretrained-models.md) を参照してください。以下の `models\model.onnx` は取得したモデルのパスに置き換えます。

```powershell
# Windows PowerShell 5.1 でもネイティブプロセスへ UTF-8 で渡す
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
"こんにちは、今日はいい天気ですね。" |
    .\bin\piper-plus.exe --model .\models\model.onnx --language ja --output_file .\hello.wav
```

設定ファイルは `model.onnx.json`、次いで同じディレクトリの `config.json` が検索されます。別の場所に置く場合は `--config` で指定します。Zero-Shot モデルには対応する話者埋め込みも必要です。モデルごとの入力とサンプルコマンドを確認してください。

## ソースからビルドする

### 必要なツール

- Visual Studio 2022 の「C++ によるデスクトップ開発」ワークロード、MSVC v143、Windows SDK
- CMake 3.15 以降
- Git for Windows
- 依存ソースと ONNX Runtime を取得するためのインターネット接続

通常のビルドに管理者権限は不要です。Visual Studio の Developer PowerShell、または CMake と Git が利用できる PowerShell で実行します。

以下は未リリースの変更を含む `dev` のビルド手順です。公開版の再現が目的なら `--branch dev` を `--branch v2.0.1` に置き換えてください。

```powershell
git clone --branch dev https://github.com/ayutaz/piper-plus.git
Set-Location piper-plus
git submodule update --init --recursive

cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release --parallel
cmake --install build --config Release --prefix dist/piper-plus

.\dist\piper-plus\bin\piper-plus.exe --help
```

Visual Studio は複数構成のジェネレーターなので、構成は `--config Release` で指定します。ONNX Runtime と OpenJTalk は CMake の依存設定から用意され、インストール先に必要な DLL やデータが配置されます。詳細は [ソースビルド](../guides/development/building-from-source.md) を参照してください。

## 日本語辞書

C++ CLI の日本語 G2P は OpenJTalk 辞書を使用します。OpenJTalk の実行ファイルや HTS 音声ファイルは別途不要です。辞書が見つからず自動取得が有効な場合、**日本語を音素化するとき**に辞書を取得します。`--help` はヘルプ表示のみで、辞書のダウンロード確認にはなりません。

標準の保存先は `%APPDATA%\piper-plus\open_jtalk_dic_utf_8-1.11` です。手動で用意した辞書には、`sys.dic`、`unk.dic`、`matrix.bin` などの辞書ファイルを含めてください。

```powershell
# 展開済みの辞書を、この PowerShell セッションで指定する
$env:OPENJTALK_DICTIONARY_PATH = 'C:\models\open_jtalk_dic_utf_8-1.11'
$env:PIPER_PLUS_OFFLINE_MODE = '1'

$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
"辞書の動作確認です。" |
    .\dist\piper-plus\bin\piper-plus.exe --model .\models\model.onnx --language ja --output_file .\dictionary-test.wav
```

`PIPER_PLUS_OFFLINE_MODE` は辞書取得の制御です。モデル本体もあらかじめローカルに用意してください。設定は [環境変数](environment-variables.md)、取得失敗の対処は [トラブルシューティング](troubleshooting.md#failed-to-download-dictionary-error) を参照してください。

## C# CLI

C# の配布バイナリはセルフコンテインドで、実行時の .NET インストールは不要です。ソースからビルドする場合は .NET 10 SDK を用意し、リポジトリのルートで実行します。

```powershell
dotnet build src\csharp\PiperPlus.sln -c Release
dotnet run --project src\csharp\PiperPlus.Cli -- --model .\models\model.onnx --text "動作確認です。" --output_file .\csharp-test.wav
```

オプションと API は [C# CLI README](../../src/csharp/PiperPlus.Cli/README.md) を参照してください。

## Python

推論パッケージは [Python README](../../src/python_run/README.md)、学習環境は [学習ガイド](../guides/training/training-guide.md) を参照してください。開発用 workspace はリポジトリのルートで同期します。学習用の PyTorch なども含むため、CLI の実行だけであれば同期は不要です。

```powershell
uv sync
uv run python -m piper_plus --help
uv run python -m piper_train.infer_onnx --help
```

## よくある問題

### 日本語が文字化けする

PowerShell の `$OutputEncoding` を UTF-8 に設定してください。UTF-8 ファイルを `Get-Content` で読み込むだけでは、ネイティブプロセスへのパイプ出力の文字コードは変わりません。

cmd では、UTF-8 で保存した入力ファイルを次のように渡せます。

```cmd
chcp 65001
type input.txt | .\bin\piper-plus.exe --model .\models\model.onnx --language ja --output_file output.wav
```

### DLL が見つからない

アーカイブ全体を再展開するか、`cmake --install` を実行し、インストール先の `bin/` から起動してください。異なる ONNX Runtime の DLL を個別にコピーして混在させないでください。

### GPU を使いたい

対応プロバイダーはビルドに依存します。C++ CLI の `--use-cuda` は CUDA 対応 ONNX Runtime が必要で、CPU 用配布物に環境変数を設定するだけでは有効になりません。C#、Rust、Python は各ランタイムの README を参照してください。

### C/C++ アプリケーションへ組み込みたい

公開 C API の例は [examples/c-api](../../examples/c-api/README.md) にあります。公開ヘッダー `piper_plus.h` と同梱ライブラリの組み合わせを使用してください。

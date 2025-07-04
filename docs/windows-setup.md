# Windows環境でのOpenJTalkセットアップガイド

## 概要
このガイドでは、Windows環境でPiperとOpenJTalkを使用して日本語音声合成を行うための手順を説明します。

## 前提条件

- Windows 10以降
- Visual Studio 2019以降（C++開発ワークロード）
- CMake 3.13以降
- Git

## ビルド手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/rhasspy/piper.git
cd piper
```

### 2. ビルド

```bash
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

### 3. OpenJTalkのセットアップ

OpenJTalkは自動的にビルドされ、必要な辞書とHTS音声ファイルは初回実行時に自動ダウンロードされます。

手動でダウンロードする場合：
```bash
# PowerShellで実行
$env:OPENJTALK_DICTIONARY_PATH = "C:\path\to\dictionary"
$env:OPENJTALK_VOICE = "C:\path\to\voice.htsvoice"
```

## 使用例

### 基本的な使用方法

```bash
# 日本語テキストを音声ファイルに変換
echo "こんにちは世界" | .\piper.exe --model ja_JP-voice.onnx --output_file hello.wav
```

### C++から使用する例

```cpp
#include "piper.hpp"
#include <iostream>

int main() {
    piper::PiperConfig config;
    piper::Voice voice;
    
    // モデルをロード
    loadVoice(config, "ja_JP-voice.onnx", "ja_JP-voice.onnx.json", voice);
    
    // テキストを音声に変換
    std::string text = "こんにちは世界";
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;
    
    textToAudio(config, voice, text, audioBuffer, result);
    
    // 音声データを処理...
    
    return 0;
}
```

### PowerShellスクリプトの例

```powershell
# japanese_tts.ps1
param(
    [Parameter(Mandatory=$true)]
    [string]$Text,
    
    [Parameter(Mandatory=$true)]
    [string]$OutputFile
)

# Piperのパス
$piperPath = ".\build\Release\piper.exe"
$modelPath = ".\models\ja_JP-voice.onnx"

# テキストを音声に変換
$Text | & $piperPath --model $modelPath --output_file $OutputFile

Write-Host "音声ファイルを生成しました: $OutputFile"
```

使用方法：
```powershell
.\japanese_tts.ps1 -Text "今日はいい天気ですね" -OutputFile weather.wav
```

## トラブルシューティング

### OpenJTalkが見つからない

エラー: `OpenJTalk binary not found`

解決方法：
1. ビルドディレクトリに`open_jtalk.exe`が存在することを確認
2. PATHに追加するか、実行ファイルと同じディレクトリに配置

### 辞書のダウンロードエラー

エラー: `Failed to download dictionary`

解決方法：
1. インターネット接続を確認
2. プロキシ設定が必要な場合：
   ```powershell
   $env:HTTP_PROXY = "http://proxy.example.com:8080"
   $env:HTTPS_PROXY = "http://proxy.example.com:8080"
   ```

### 文字化け

症状: 日本語が正しく処理されない

解決方法：
1. テキストファイルがUTF-8エンコーディングであることを確認
2. PowerShellの文字エンコーディングを設定：
   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   ```

### メモリ不足

症状: 長いテキストで失敗する

解決方法：
1. テキストを短く分割して処理
2. 現在の制限は約4KBです（将来的に改善予定）

## 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `OPENJTALK_DICTIONARY_PATH` | 辞書ディレクトリのパス | 自動検出 |
| `OPENJTALK_VOICE` | HTSボイスファイルのパス | 自動ダウンロード |
| `OPENJTALK_DATA_DIR` | データファイルの保存先 | `%APPDATA%\piper` |
| `PIPER_OFFLINE_MODE` | オフラインモード（1で有効） | 0 |
| `PIPER_AUTO_DOWNLOAD_DICT` | 自動ダウンロード（0で無効） | 1 |

## パフォーマンスチューニング

### 高速化のヒント

1. **RAMディスクの使用**
   ```powershell
   $env:TEMP = "R:\Temp"  # RAMディスクを一時ファイルに使用
   ```

2. **バッチ処理**
   複数のテキストを一度に処理する場合は、プロセスの起動を最小限に：
   ```powershell
   Get-Content texts.txt | .\piper.exe --model ja_JP-voice.onnx --output_raw > output.pcm
   ```

## 既知の問題

- 4KB以上のテキストは処理できません（#69で対応予定）
- 非ASCII文字を含むパスで問題が発生する場合があります（#71で対応予定）
- 同時実行はサポートされていません（スレッドセーフではありません）
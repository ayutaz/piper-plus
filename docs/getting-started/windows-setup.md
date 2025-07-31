# Windows環境でのOpenJTalkセットアップガイド

## 概要
このガイドでは、Windows環境でPiperとOpenJTalkを使用して日本語音声合成を行うための手順を説明します。

## 前提条件

### 必須ソフトウェア

- **OS**: Windows 10 (64ビット) 以降
- **Visual Studio**: 2019以降（Community版でも可）
  - インストール時に「**C++によるデスクトップ開発**」ワークロードを選択
  - コンポーネント: MSVC v143, Windows 10 SDK
- **CMake**: 3.13以降
  - [CMake公式サイト](https://cmake.org/download/)からインストーラーをダウンロード
  - インストール時に「Add CMake to the system PATH」を選択
- **Git for Windows**
  - [Git公式サイト](https://git-scm.com/download/win)からダウンロード

### 推奨ソフトウェア

- **Python**: 3.8以降（テストやスクリプト実行用）
- **PowerShell**: 7.0以降（Windows PowerShell 5.1でも動作します）

## ビルド手順

### 1. 環境の確認

PowerShellを管理者として実行し、以下を確認：

```powershell
# Visual Studioの確認
& "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -property installationPath

# CMakeの確認
cmake --version

# Gitの確認
git --version
```

### 2. リポジトリのクローン

```powershell
# 作業ディレクトリを作成
New-Item -ItemType Directory -Path C:\workspace -Force
Set-Location C:\workspace

# リポジトリをクローン
git clone https://github.com/rhasspy/piper.git
Set-Location piper
```

### 3. ビルドの実行

```powershell
# ビルドディレクトリを作成
New-Item -ItemType Directory -Path build -Force
Set-Location build

# Visual Studioのバージョンに合わせて選択
# VS 2022の場合：
cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release

# VS 2019の場合：
# cmake .. -G "Visual Studio 16 2019" -A x64 -DCMAKE_BUILD_TYPE=Release

# ビルド実行
cmake --build . --config Release --parallel

# ビルド結果の確認
Get-ChildItem -Path .\Release -Filter "*.exe"
```

### 4. ビルド後の確認

以下のファイルが生成されていることを確認：

```powershell
# 必須ファイルの確認
$requiredFiles = @(
    "Release\piper.exe",
    "Release\open_jtalk.exe",
    "Release\*.dll"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "✓ $file" -ForegroundColor Green
    } else {
        Write-Host "✗ $file" -ForegroundColor Red
    }
}
```

### 5. OpenJTalkのセットアップ

#### 自動セットアップ（推奨）

OpenJTalkは自動的にビルドされ、必要な辞書とHTS音声ファイルは初回実行時に自動ダウンロードされます。

```powershell
# 自動ダウンロードのテスト
.\Release\piper.exe --help
# 初回実行時に辞書が自動ダウンロードされます
```

#### 手動セットアップ（オフライン環境用）

インターネット接続がない場合、手動で辞書をダウンロード：

```powershell
# 辞書ディレクトリを作成
$dictPath = "$env:APPDATA\piper\openjtalk_dic"
New-Item -ItemType Directory -Path $dictPath -Force

# 辞書をダウンロード（別のPCでダウンロードしてコピー）
# URL: https://jaist.dl.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz

# 環境変数を設定
[Environment]::SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", $dictPath, [EnvironmentVariableTarget]::User)

# オフラインモードを有効化
[Environment]::SetEnvironmentVariable("PIPER_OFFLINE_MODE", "1", [EnvironmentVariableTarget]::User)
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

```powershell
# 1. open_jtalk.exeの存在確認
$openJtalkPath = Get-ChildItem -Path . -Filter "open_jtalk.exe" -Recurse
if ($openJtalkPath) {
    Write-Host "OpenJTalk found at: $($openJtalkPath.FullName)" -ForegroundColor Green
} else {
    Write-Host "OpenJTalk not found. Rebuilding..." -ForegroundColor Red
    cmake --build . --config Release --target open_jtalk
}

# 2. PATHに追加
$buildPath = (Get-Location).Path + "\Release"
$env:PATH = "$buildPath;$env:PATH"

# 3. または環境変数で指定
[Environment]::SetEnvironmentVariable("OPENJTALK_PATH", "$buildPath\open_jtalk.exe", [EnvironmentVariableTarget]::User)
```

### 辞書のダウンロードエラー

エラー: `Failed to download dictionary`

解決方法：

```powershell
# 1. インターネット接続を確認
Test-NetConnection -ComputerName "jaist.dl.sourceforge.net" -Port 443

# 2. プロキシ設定が必要な場合
[Environment]::SetEnvironmentVariable("HTTP_PROXY", "http://proxy.example.com:8080", [EnvironmentVariableTarget]::User)
[Environment]::SetEnvironmentVariable("HTTPS_PROXY", "http://proxy.example.com:8080", [EnvironmentVariableTarget]::User)

# 3. PowerShellのプロキシ設定
[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy("http://proxy.example.com:8080")
[System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultNetworkCredentials

# 4. 手動ダウンロードスクリプト
Invoke-WebRequest -Uri "https://jaist.dl.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz" -OutFile "openjtalk_dic.tar.gz"

# 5. 解凍（7-Zipまたはtarコマンドを使用）
tar -xzf openjtalk_dic.tar.gz -C "$env:APPDATA\piper"
```

### 文字化け

症状: 日本語が正しく処理されない

解決方法：

```powershell
# 1. PowerShellのエンコーディング設定
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 2. システムロケールの確認
Get-WinSystemLocale
Get-Culture

# 3. UTF-8テキストファイルの作成
$text = "こんにちは世界"
$text | Out-File -FilePath "test.txt" -Encoding UTF8NoBOM

# 4. テスト実行
Get-Content "test.txt" -Encoding UTF8 | .\Release\piper.exe --model ja_JP-voice.onnx --output_file test.wav

# 5. Windows Terminalを使用（推奨）
# Microsoft StoreからWindows Terminalをインストールし、
# 設定でプロファイルのエンコーディングをUTF-8に設定
```

### メモリ不足・長いテキストの処理

症状: 長いテキストで失敗する

解決方法：

```powershell
# 1. テキスト分割スクリプト
function Split-TextForTTS {
    param(
        [string]$Text,
        [int]$MaxLength = 1000  # 安全なサイズ
    )
    
    $sentences = $Text -split '。'
    $chunks = @()
    $currentChunk = ""
    
    foreach ($sentence in $sentences) {
        if (($currentChunk.Length + $sentence.Length) -lt $MaxLength) {
            $currentChunk += $sentence + "。"
        } else {
            if ($currentChunk) { $chunks += $currentChunk }
            $currentChunk = $sentence + "。"
        }
    }
    if ($currentChunk) { $chunks += $currentChunk }
    
    return $chunks
}

# 2. バッチ処理スクリプト
$longText = Get-Content "long_text.txt" -Encoding UTF8 -Raw
$chunks = Split-TextForTTS -Text $longText

$i = 0
foreach ($chunk in $chunks) {
    $chunk | .\Release\piper.exe --model ja_JP-voice.onnx --output_file "output_$i.wav"
    $i++
}

# 3. 音声ファイルの結合（ffmpeg使用）
# ffmpeg -i "concat:output_0.wav|output_1.wav|output_2.wav" -c copy merged.wav
```

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

## 既知の問題と回避策

### 1. テキストサイズ制限
- **問題**: 4KB以上のテキストは処理できません（#69で対応予定）
- **回避策**: 上記のテキスト分割スクリプトを使用

### 2. パスの文字エンコーディング
- **問題**: 非ASCII文字を含むパスで問題が発生（#71で対応予定）
- **回避策**: 
  ```powershell
  # ASCII文字のみのパスを使用
  Set-Location "C:\workspace\piper"
  
  # または一時ファイルを使用
  $tempDir = [System.IO.Path]::GetTempPath()
  ```

### 3. 同時実行の制限
- **問題**: スレッドセーフではありません
- **回避策**: 
  ```powershell
  # ミューテックスを使用した排他制御
  $mutex = New-Object System.Threading.Mutex($false, "PiperTTSMutex")
  try {
      $mutex.WaitOne() | Out-Null
      # Piper実行
      .\Release\piper.exe --model ja_JP-voice.onnx --output_file output.wav
  } finally {
      $mutex.ReleaseMutex()
  }
  ```

### 4. ウイルス対策ソフトの誤検知
- **問題**: open_jtalk.exeがウイルスとして誤検知される場合がある
- **解決方法**: Windows Defenderの除外リストに追加

## パフォーマンス最適化

### GPUアクセラレーション（ONNX Runtime）

```powershell
# CUDAが利用可能な場合
$env:ORT_USE_CUDA = "1"

# DirectML（Windows標準）を使用
$env:ORT_USE_DML = "1"
```

### バッチ処理の最適化

```powershell
# 並列処理スクリプト
$texts = Get-Content "texts.txt" -Encoding UTF8
$jobs = @()

foreach ($text in $texts) {
    $job = Start-Job -ScriptBlock {
        param($text, $index)
        $text | & "C:\workspace\piper\build\Release\piper.exe" `
            --model "C:\workspace\piper\models\ja_JP-voice.onnx" `
            --output_file "output_$index.wav"
    } -ArgumentList $text, $texts.IndexOf($text)
    $jobs += $job
}

# ジョブの完了を待つ
$jobs | Wait-Job | Receive-Job
```
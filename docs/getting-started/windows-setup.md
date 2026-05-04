# Windows環境でのOpenJTalkセットアップガイド

## 概要
このガイドでは、Windows環境でPiperとOpenJTalkを使用して日本語音声合成を行うための手順を説明します。

> **ビルド不要で使いたい方へ**: [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) からプリビルドバイナリ (`piper-windows-x64.zip`) をダウンロードすれば、ビルドせずにすぐ使えます。ビルドが必要なのは、ソースコードを変更したい開発者のみです。

## 前提条件

### 必須ソフトウェア

- **OS**: Windows 10 (64ビット) 以降
- **Visual Studio**: 2022以降（Community版でも可）
  - インストール時に「**C++によるデスクトップ開発**」ワークロードを選択
  - コンポーネント: MSVC v143, Windows 10 SDK
- **CMake**: 3.15以降
  - [CMake公式サイト](https://cmake.org/download/)からインストーラーをダウンロード
  - インストール時に「Add CMake to the system PATH」を選択
- **Git for Windows**
  - [Git公式サイト](https://git-scm.com/download/win)からダウンロード

### 推奨ソフトウェア

- **uv**: Python パッケージマネージャー（[公式サイト](https://docs.astral.sh/uv/)）
  - インストール: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
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

**PowerShell:**
```powershell
# 作業ディレクトリを作成
New-Item -ItemType Directory -Path C:\workspace -Force
Set-Location C:\workspace

# リポジトリをクローン
git clone https://github.com/ayutaz/piper-plus.git
Set-Location piper-plus
```

**コマンドプロンプト (cmd):**
```cmd
REM 作業ディレクトリを作成
mkdir C:\workspace
cd C:\workspace

REM リポジトリをクローン
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
```

### 3. ビルドの実行

**PowerShell:**
```powershell
# ビルドディレクトリを作成
New-Item -ItemType Directory -Path build -Force
Set-Location build

# Visual Studio 2022を使用
cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release

# ビルド実行
cmake --build . --config Release --parallel

# ビルド結果の確認
Get-ChildItem -Path .\Release -Filter "*.exe"
```

**コマンドプロンプト (cmd):**
```cmd
REM ビルドディレクトリを作成
mkdir build
cd build

REM Visual Studio 2022を使用
cmake .. -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release

REM ビルド実行
cmake --build . --config Release --parallel

REM ビルド結果の確認
dir Release\*.exe
```

> **ビルド中の警告について**: `warning C4996` (strcpy/fopen 関連) が大量に表示されますが、これは正常です。最終的に `piper.exe` が生成されていれば、ビルドは成功しています。`error` ではなく `warning` であれば無視して問題ありません。

### 4. ビルド後の確認

以下のファイルが生成されていることを確認：

```powershell
# 必須ファイルの確認
$requiredFiles = @(
    "Release\piper.exe",
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

OpenJTalkは自動的にビルドされ、必要な辞書 (NAIST-JDIC) は初回実行時に自動ダウンロードされます。HTS 音声ファイル (`*.htsvoice`) は piper-plus では不要です (PR #342 で依存削除済み)。

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

### C# CLI のセットアップ (オプション)

C++ ビルドの代わりに C# CLI を使用する場合:

1. **.NET 10 SDK** のインストール: https://dotnet.microsoft.com/download/dotnet/10.0
2. ビルド:
```powershell
dotnet build src\csharp\PiperPlus.sln -c Release
```
3. 実行:
```powershell
dotnet run --project src\csharp\PiperPlus.Cli -- --model path\to\model.onnx --text "テスト"
```

## 使用例

### 基本的な使用方法

**PowerShell:**
```powershell
# 日本語テキストを音声ファイルに変換
echo "こんにちは世界" | .\piper.exe --model ja_JP-voice.onnx --output_file hello.wav
```

**コマンドプロンプト (cmd):**
```cmd
REM 日本語テキストを音声ファイルに変換（chcp 65001でUTF-8に切り替え）
chcp 65001
echo こんにちは世界 | piper.exe --model ja_JP-voice.onnx --output_file hello.wav
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

## Python環境のセットアップ

テストやスクリプト実行にはuvを使用します。

```powershell
# uvのインストール（未インストールの場合）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# リポジトリのルートディレクトリに移動（build/ 内では実行不可）
Set-Location $env:USERPROFILE\piper-plus

# 依存関係のインストール（uv が自動的にvenv作成・パッケージインストールを行います）
uv sync

# Pythonスクリプトの実行例
uv run python -m piper_train.infer_onnx --help
```

## トラブルシューティング

### OpenJTalkが見つからない

エラー: `OpenJTalk dictionary not found` または初回実行時に辞書の自動ダウンロードが失敗する場合

> **注意**: OpenJTalk は `piper.exe` に静的リンク済みです。別途バイナリは不要です。このエラーは辞書ファイルが見つからない場合に発生します。

解決方法：

```powershell
# 1. piper.exeの存在確認（念のため）
if (Test-Path ".\Release\piper.exe") {
    Write-Host "piper.exe OK" -ForegroundColor Green
} else {
    Write-Host "piper.exe not found. Rebuild with: cmake --build . --config Release" -ForegroundColor Red
}

# 2. OpenJTalk辞書ディレクトリの確認
$dictPath = "$env:APPDATA\piper\open_jtalk_dic_utf_8-1.11"
if (Test-Path $dictPath) {
    Write-Host "辞書ディレクトリが見つかりました: $dictPath" -ForegroundColor Green
} else {
    Write-Host "辞書ディレクトリが見つかりません。以下の手順でダウンロードしてください。" -ForegroundColor Red
}

# 3. 辞書を手動でダウンロード・展開する（自動DLが失敗した場合）
New-Item -ItemType Directory -Path "$env:APPDATA\piper" -Force | Out-Null
Invoke-WebRequest -Uri "https://jaist.dl.sourceforge.net/project/open-jtalk/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz" `
    -OutFile "$env:TEMP\open_jtalk_dic_utf_8-1.11.tar.gz"
tar -xzf "$env:TEMP\open_jtalk_dic_utf_8-1.11.tar.gz" -C "$env:APPDATA\piper"

# 4. 辞書パスを環境変数で明示指定
[Environment]::SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", "$env:APPDATA\piper\open_jtalk_dic_utf_8-1.11", [EnvironmentVariableTarget]::User)
Write-Host "OPENJTALK_DICTIONARY_PATH を設定しました。PowerShellを再起動してください。" -ForegroundColor Green
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

### 日本語テキストの文字化け・文字化けによる音声生成失敗

症状: 日本語テキストをパイプで `piper.exe` に渡すと、文字化けして正しい音声が生成されない

**原因**: WindowsのコンソールはデフォルトでShift_JIS (コードページ932) を使用するため、UTF-8の日本語テキストがパイプ経由で渡される際に破損します。

#### 解決方法1: `chcp 65001` でUTF-8に切り替え（cmd）

```cmd
chcp 65001
echo こんにちは世界 | piper.exe --model ja_JP-voice.onnx --output_file hello.wav
```

#### 解決方法2: ファイル経由で入力

UTF-8 (BOMなし) のテキストファイルを作成し、`type` コマンドで渡します。

**PowerShell:**
```powershell
# UTF-8 BOMなしテキストファイルを作成
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText("input.txt", "こんにちは世界", $utf8NoBom)

# ファイルからパイプで入力
Get-Content "input.txt" -Encoding UTF8 | .\Release\piper.exe --model ja_JP-voice.onnx --output_file output.wav
```

**コマンドプロンプト (cmd):**
```cmd
chcp 65001
type input.txt | piper.exe --model ja_JP-voice.onnx --output_file output.wav
```

#### 解決方法3: `speak.bat` スクリプトを使用（推奨）

エンコーディング処理を自動化するバッチスクリプトを使用します。以下の内容を `speak.bat` として保存してください。

```bat
@echo off
setlocal
set "PIPER_DIR=%~dp0build\Release"
set "MODEL=%PIPER_DIR%\models\tsukuyomi-chan-6lang-fp16.onnx"
set "CONFIG=%PIPER_DIR%\models\config.json"
set "TMPFILE=%PIPER_DIR%\input_utf8.txt"

if "%~1"=="" (
    echo Usage: speak.bat "読み上げたい文章"
    exit /b 1
)

set "INPUT_TEXT=%~1"
powershell -NoProfile -Command "param($t,$f); $utf8 = New-Object System.Text.UTF8Encoding($false); [System.IO.File]::WriteAllText($f, $t, $utf8)" -args "%INPUT_TEXT%" "%TMPFILE%"

pushd "%PIPER_DIR%"
chcp 65001 >nul
type "input_utf8.txt" | piper.exe --model "%MODEL%" --config "%CONFIG%" --output_file output.wav
popd

if exist "%TMPFILE%" del "%TMPFILE%" >nul 2>&1
if exist "%PIPER_DIR%\output.wav" start "" "%PIPER_DIR%\output.wav"
endlocal
```

使用方法：
```cmd
speak.bat "今日はいい天気ですね"
```

#### 補足: PowerShellでのエンコーディング設定

```powershell
# PowerShellセッションのエンコーディングをUTF-8に設定
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# システムロケールの確認
Get-WinSystemLocale
Get-Culture

# Windows Terminalを使用（推奨）
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
- **問題**: ~~4KB以上のテキストは処理できません~~ — **解決済み (#69)**。`main.cpp` のstdinループは `getline()` で行単位読み取りを行うため、4KBの上限はありません。

### 2. パスの文字エンコーディング
- **問題**: ~~非ASCII文字を含むパスで問題が発生~~ — **解決済み (#71)**。コードは `std::filesystem::path` を使用し、Windows上でのUTF-8引数を正しく処理します。

### 3. 同時実行の制限
- **現状**: 単一のエンジンインスタンスはスレッドセーフではありません。ただし、スレッドごとに独立したインスタンスを使用することで、複数スレッドからの並列実行が可能です。
- **回避策**:
  ```powershell
  # 単一インスタンスを共有する場合はミューテックスで排他制御
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
- **問題**: ビルドした実行ファイルがウイルスとして誤検知される場合がある
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

# Windows上での日本語TTS (Text-to-Speech) について

## 現在の状況

Windows版のpiperでは、OpenJTalkをソースからビルドすることで日本語TTSをサポートしています。

### 機能

1. **OpenJTalkの完全実装**
   - Windows版では、OpenJTalkをソースからビルドして使用します
   - MeCabベースの形態素解析による正確な日本語音素変換が可能です

2. **日本語テキストの処理**
   - 日本語テキストを正しく解析し、音素に変換します
   - Unix版と同等の日本語TTS機能を提供します

### 技術的な実装

Windows上でのOpenJTalkビルドは以下のように実現されています：

1. **HTSEngineのビルド**
   - オーディオ出力を簡略化したHTSEngineをビルド
   - Windows SDK互換性のための修正を適用

2. **OpenJTalkのビルド**
   - CMakeベースのビルドシステムを使用
   - MeCab（形態素解析器）を含む完全な実装
   - Windows向けの設定ファイル（config.h）を自動生成

### ビルド要件

Windows上でpiperをビルドする際の要件：

1. **Visual Studio 2022**
   - C++コンパイラとWindows SDKが必要

2. **CMake 3.13以降**
   - ビルドシステムとして使用

3. **インターネット接続**
   - OpenJTalk辞書の自動ダウンロードに必要

### 使用方法

日本語TTSを使用するには：

```bash
echo "こんにちは、世界" | piper.exe --model ja_JP-model.onnx --output_file output.wav
```

辞書は初回実行時に自動的にダウンロードされます。

## 開発者向け情報

Windows向けのOpenJTalk実装は以下のファイルにあります：
- `src/cpp/openjtalk_wrapper.c` - Windows実装を含む
- `cmake/openjtalk_CMakeLists.txt` - Windows向けビルド設定
- `cmake/openjtalk_config.h.in` - Windows向け設定テンプレート
- `cmake/hts_audio_windows.c` - HTSEngine用のWindows向け音声出力実装

ビルドプロセスはCMakeによって自動化されており、必要な依存関係は自動的に処理されます。
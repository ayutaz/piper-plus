# Windows上での日本語TTS (Text-to-Speech) について

## 現在の状況

Windows版のpiperでは、プリビルド済みOpenJTalkバイナリを使用することで日本語TTSをサポートします。

### 機能

1. **完全なOpenJTalkサポート（バイナリ提供時）**
   - プリビルド済みのOpenJTalkバイナリが提供されている場合、完全な日本語TTSが利用可能
   - MeCabベースの形態素解析による正確な日本語音素変換

2. **自動フォールバック**
   - バイナリがダウンロードできない場合は、最小限の機能を持つラッパーにフォールバック
   - この場合、日本語TTSの品質は制限されます

### 技術的な実装

Windows版piperは以下の方法で日本語TTSを実現します：

1. **プリビルド済みバイナリの自動ダウンロード**
   - CMakeビルド時に自動的にOpenJTalkバイナリをダウンロード
   - GitHub ReleasesまたはCDNからの取得

2. **フォールバック機構**
   - ダウンロードが失敗した場合、最小限のラッパーを自動生成
   - これによりビルドは常に成功し、基本的な動作は保証される

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

### プリビルド済みバイナリの提供

完全な日本語TTSサポートを提供するには、プリビルド済みのOpenJTalkバイナリが必要です：

1. **バイナリの作成**
   - MinGW/MSYS2環境でOpenJTalkをビルド
   - 静的リンクで依存関係を最小化
   - 詳細は`OPENJTALK_WINDOWS_BINARY.md`を参照

2. **バイナリの配置**
   - GitHub Releasesにアップロード
   - CMakeLists.txtのURLを更新

### 関連ファイル

- `src/cpp/openjtalk_wrapper.c` - Windows実装を含む
- `cmake/open_jtalk_windows_wrapper.cpp.in` - フォールバック用ラッパー
- `cmake/hts_audio_windows.c` - HTSEngine用のWindows向け音声出力実装
- `OPENJTALK_WINDOWS_BINARY.md` - バイナリ作成手順

ビルドプロセスはCMakeによって自動化されており、バイナリのダウンロードも自動的に行われます。
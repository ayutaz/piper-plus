# Windows上での日本語TTS (Text-to-Speech) について

## 現在の状況

Windows版のpiperでは、日本語TTSのサポートが制限されています。

### 制限事項

1. **OpenJTalkのスタブ実装**
   - Windows版では、OpenJTalkの完全な実装ではなく、スタブ（仮実装）が使用されています
   - このスタブは、ダミーの音素ラベルを返すだけで、実際の日本語解析は行いません

2. **日本語テキストの処理**
   - 日本語テキストを入力しても、正しい音素変換が行われません
   - 出力される音声は意味不明なものになる可能性があります

### 技術的な背景

Windows上でOpenJTalkをビルドする際に以下の問題があります：

1. **HTSEngineのビルド問題**
   - Windows SDKとの互換性問題により、HTSEngineのビルドが困難
   - 特にARM64関連の構造体定義でコンパイルエラーが発生

2. **OpenJTalkの複雑な依存関係**
   - MeCab（形態素解析器）を含む多くの依存関係
   - Windowsネイティブビルドが非常に困難

### 回避策

Windows上で日本語TTSを使用したい場合：

1. **WSL2 (Windows Subsystem for Linux) を使用**
   - WSL2上でLinux版のpiperを実行することで、完全な日本語TTSサポートが利用可能

2. **MinGW/MSYS2環境でのビルド**
   - MinGW環境でOpenJTalkをビルドし、そのバイナリを使用する方法

3. **事前ビルド済みバイナリの使用**
   - 他のプロジェクトで提供されているOpenJTalkバイナリを手動で配置

### 将来の改善

Windows上での完全な日本語TTSサポートを実現するため、以下の改善を検討しています：

1. OpenJTalkのWindows向けビルドプロセスの改善
2. 事前ビルド済みバイナリの提供
3. 代替の日本語音素変換ライブラリの使用

## 開発者向け情報

Windows向けのOpenJTalk実装は以下のファイルにあります：
- `src/cpp/openjtalk_wrapper.c` - Windows実装を含む
- `cmake/open_jtalk_stub.c` - スタブ実装（CMakeLists.txt内で生成）

完全な実装を行いたい場合は、上記のファイルを参考に改善を行ってください。
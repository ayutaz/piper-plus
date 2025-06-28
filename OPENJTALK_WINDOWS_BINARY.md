# Windows向けOpenJTalkバイナリの提供方法

## 概要

Windows版piperで完全な日本語TTSサポートを提供するため、プリビルド済みのOpenJTalkバイナリが必要です。

## バイナリの作成方法

### 方法1: MinGW/MSYS2でビルド

1. MSYS2をインストール
2. 必要なパッケージをインストール：
   ```bash
   pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake make
   ```

3. HTSEngineをビルド：
   ```bash
   wget https://downloads.sourceforge.net/project/hts-engine/hts_engine%20API/hts_engine_API-1.10/hts_engine_API-1.10.tar.gz
   tar xzf hts_engine_API-1.10.tar.gz
   cd hts_engine_API-1.10
   ./configure --prefix=/mingw64
   make
   make install
   ```

4. OpenJTalkをビルド：
   ```bash
   wget https://downloads.sourceforge.net/project/open-jtalk/Open%20JTalk/open_jtalk-1.11/open_jtalk-1.11.tar.gz
   tar xzf open_jtalk-1.11.tar.gz
   cd open_jtalk-1.11
   ./configure --prefix=/mingw64 --with-charset=UTF-8
   make
   # open_jtalk.exeが生成される
   ```

5. 静的リンクを確認：
   ```bash
   ldd open_jtalk.exe
   # MinGW DLL以外に依存していないことを確認
   ```

### 方法2: 既存のプロジェクトから取得

- [VOICEVOX](https://github.com/VOICEVOX/voicevox_engine)
- [Open JTalk Windows builds](https://github.com/r9y9/open_jtalk)

## バイナリの配置

### GitHub Releasesへのアップロード

1. piper-plusリポジトリでリリースを作成
2. `open_jtalk_win64.exe`としてアップロード
3. CMakeLists.txtのURLを更新：
   ```cmake
   set(OPENJTALK_WINDOWS_URL "https://github.com/ayutaz/piper-plus/releases/download/v1.0.0/open_jtalk_win64.exe")
   ```

### 代替方法

1. **クラウドストレージ**
   - Google Drive、Dropbox等に配置
   - 直接ダウンロード可能なURLを使用

2. **Git LFS**
   - リポジトリ内にバイナリを含める
   - `prebuilt/windows/open_jtalk.exe`として配置

3. **CDN**
   - jsDelivr等のCDNサービスを使用
   - GitHubリポジトリのファイルを配信

## 必要なファイル

最低限必要なファイル：
- `open_jtalk.exe` - メインの実行ファイル

オプション（辞書は自動ダウンロードされるため不要）：
- 辞書ファイル（naist-jdic）
- HTSボイスモデル

## テスト方法

```powershell
# バイナリが正しく動作するか確認
echo "こんにちは" > test.txt
./open_jtalk.exe -x dic -m voice.htsvoice -ot output.lab test.txt
```

## 注意事項

- 64ビット版Windows向けにビルド
- Visual C++ランタイムに依存しないよう静的リンク推奨
- ファイルサイズは10-20MB程度になる見込み
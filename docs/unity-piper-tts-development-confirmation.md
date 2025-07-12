# Unity Piper TTS 開発環境確認事項

## 開発環境の確認

### プロジェクトフォルダ
- **Unityプロジェクトパス**: `/Users/s19447/Desktop/uPiper`
- **GitHubリポジトリ**: https://github.com/ayutaz/uPiper
- **開発作業**: すべてuPiperフォルダ内で実施

### 重要な確認事項

1. **開発場所**
   - ✅ Unity Piper TTSプラグインは `/Users/s19447/Desktop/uPiper` 内で開発
   - ✅ piperフォルダ（`/Users/s19447/Desktop/piper`）は参照・ドキュメント用
   - ✅ 実装コードはすべてuPiperリポジトリにコミット

2. **フォルダ構造**
   ```
   /Users/s19447/Desktop/uPiper/
   ├── Assets/
   │   ├── PiperTTS/           # ← ここにプラグインを作成
   │   │   ├── package.json
   │   │   ├── Runtime/
   │   │   ├── Editor/
   │   │   ├── Tests/
   │   │   ├── Models/
   │   │   └── Plugins/
   │   └── (その他のUnityアセット)
   ├── Packages/
   ├── ProjectSettings/
   └── (その他のUnityプロジェクトファイル)
   ```

3. **Gitリポジトリ**
   - プライマリ: `https://github.com/ayutaz/uPiper`
   - コミットはuPiperリポジトリに対して実行
   - ブランチ戦略:
     - `main`: 安定版
     - `develop`: 開発版
     - `feature/piper-tts`: Piper TTS統合用

4. **ドキュメント管理**
   - 技術ドキュメント: `/Users/s19447/Desktop/piper/docs/` に保存済み
   - READMEやCHANGELOG: uPiperリポジトリ内で管理
   - APIドキュメント: uPiper内の `Assets/PiperTTS/Documentation~/` に配置

## 開発ワークフロー

### Phase 0-1の作業場所

1. **Unity Package作成**
   ```bash
   cd /Users/s19447/Desktop/uPiper
   mkdir -p Assets/PiperTTS
   # package.json作成
   # フォルダ構造セットアップ
   ```

2. **ネイティブライブラリビルド**
   - ビルド作業: piperフォルダで実施（参照実装）
   - 成果物配置: `uPiper/Assets/PiperTTS/Plugins/`

3. **C#実装**
   - すべて `uPiper/Assets/PiperTTS/Runtime/` 内で開発
   - Unity 6000.0.35f1で動作確認

4. **テスト実装**
   - `uPiper/Assets/PiperTTS/Tests/` 内で作成
   - Unity Test Frameworkを使用

## 注意事項

### やること
- ✅ uPiperフォルダ内で開発
- ✅ uPiperリポジトリにコミット
- ✅ Unity 6000.0.35f1で動作確認
- ✅ Assets/PiperTTS/をUnity Package構造に

### やらないこと
- ❌ piperフォルダでの実装作業（参照のみ）
- ❌ 別リポジトリの作成
- ❌ piperリポジトリへのコミット

## 次のステップ

1. uPiperプロジェクトを開く
2. Assets/PiperTTS/フォルダ作成
3. package.json作成
4. 基本的なフォルダ構造セットアップ
5. Sentis 2.1.2パッケージインストール

これらの確認事項に基づいて、Phase 0から開発を進めます。
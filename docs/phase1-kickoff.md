# Phase 1: Windows/Linux 基盤実装 キックオフドキュメント

## 🎯 Phase 1のゴール

**「日本語テキストを入力して、Windows/LinuxのUnity上で実際の音声が再生される」**

## ✅ 成功基準

### 機能要件
- [ ] 日本語テキスト入力 → 音声出力の完全なパイプライン
- [ ] OpenJTalkによる高精度な日本語音素化
- [ ] Piper TTSモデルによる自然な音声生成
- [ ] Unity Editor上でのリアルタイム再生

### 非機能要件
- [ ] 処理速度: 100ms/文以下（50文字の日本語）
- [ ] メモリ使用量: 100MB以下（モデル含む）
- [ ] 音素化精度: 98%以上

### プラットフォーム
- [ ] Windows 10/11（x64）
- [ ] Ubuntu 20.04/22.04（x64）

## 📋 主要コンポーネント

### 1. 音素化システム
```
テキスト → OpenJTalk → 音素列 → 音素ID
"こんにちは" → [k o N n i ch i w a] → [25, 11, 22, 50, 8, ...]
```

### 2. 音声合成システム
```
音素ID → Piper ONNX Model → 音声波形 → AudioClip
[25, 11, 22, ...] → Inference → float[] → Unity Audio
```

### 3. アーキテクチャ
```
┌─────────────────┐
│  Unity UI/API   │
├─────────────────┤
│ PiperTTS Core   │
├─────────────────┤
│ Phonemizer      │ Unity AI Interface
│ (OpenJTalk)     │ (Inference Engine)
├─────────────────┼─────────────────┤
│ Native Library  │ ONNX Runtime    │
│ (.dll/.so)      │                 │
└─────────────────┴─────────────────┘
```

## 🚀 実装優先順位

### Week 1（第1週）
1. **アーキテクチャ設計** (1日)
   - 全体設計図
   - インターフェース定義
   - パッケージ構造

2. **コア実装** (3日)
   - IPiperTTS インターフェース
   - 基本クラス実装
   - ユーティリティ

3. **音素化基盤** (2日)
   - BasePhonemizer
   - キャッシュシステム
   - テキスト正規化

### Week 2（第2週）
4. **OpenJTalk統合** (5日)
   - ネイティブライブラリビルド
   - P/Invoke バインディング
   - OpenJTalkPhonemizer実装

5. **音声合成** (3日)
   - Unity AI Interface統合
   - ONNX推論実装
   - AudioClip生成

### Week 3（第3週）
6. **統合とテスト** (4日)
   - E2Eテスト
   - サンプルシーン
   - デバッグツール
   - ドキュメント

## 📂 ディレクトリ構造

```
Assets/
└── uPiper/
    ├── Runtime/
    │   ├── Core/           # IPiperTTS, PiperTTS
    │   ├── Phonemizers/    # BasePhonemizer, OpenJTalkPhonemizer
    │   ├── Synthesis/      # InferenceAudioGenerator
    │   ├── Utils/          # Logger, Cache, Platform
    │   └── Native/         # P/Invoke定義
    ├── Editor/
    │   └── Inspector/      # カスタムインスペクター
    ├── Plugins/
    │   ├── Windows/
    │   │   └── x64/
    │   │       └── openjtalk.dll
    │   └── Linux/
    │       └── x64/
    │           └── libopenjtalk.so
    ├── Models/
    │   └── ja_JP/          # Piperモデルファイル
    ├── Tests/
    │   ├── Runtime/
    │   └── Editor/
    └── Samples/
        └── BasicTTS/
```

## 🔧 開発環境要件

### 必須
- Unity 6000.0.35f1
- Visual Studio 2022 / VS Code
- Git / Git LFS
- CMake 3.20+（ネイティブビルド用）

### Windows開発
- Visual Studio 2022 with C++ development
- Windows SDK

### Linux開発
- GCC 9+
- build-essential
- cmake

## 📊 リスクと対策

### リスク1: OpenJTalkのサイズ
- **問題**: 辞書データが大きい（~50MB）
- **対策**: 
  - 必要最小限の辞書に削減
  - 圧縮形式での配布
  - 遅延ロード実装

### リスク2: プラットフォーム差異
- **問題**: Windows/Linuxでの動作差異
- **対策**:
  - 抽象化レイヤーの実装
  - CI/CDでの継続的テスト
  - プラットフォーム別のテストケース

### リスク3: パフォーマンス
- **問題**: 初回実行時の遅延
- **対策**:
  - 音素化結果のキャッシュ
  - モデルのプリロード
  - 非同期処理の実装

## 📝 Phase 1完了時の成果物

1. **ソースコード**
   - コアシステム実装
   - OpenJTalk統合
   - テストスイート

2. **バイナリ**
   - openjtalk.dll (Windows)
   - libopenjtalk.so (Linux)

3. **ドキュメント**
   - APIリファレンス
   - 統合ガイド
   - サンプルコード

4. **サンプル**
   - BasicTTSシーン
   - デモアプリケーション

## 🎯 最初のタスク

1. `feature/phase1-architecture-design`ブランチ作成
2. `Architecture.md`の作成
3. インターフェース定義（`IPiperTTS.cs`）
4. 基本的なプロジェクト構造のセットアップ

---

準備ができたら、Phase 1の実装を開始しましょう！
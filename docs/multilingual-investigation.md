# マルチ言語モデル調査レポート

## 1. 調査概要

issue #23「マルチ言語モデル作成のための学習・推論コードの対応」に基づき、日本語（OpenJTalk）と他言語（espeak-ng）を組み合わせたマルチ言語TTSモデルの実現可能性を調査しました。

## 2. 現在の実装状況

### 2.1 音素化処理の仕組み

#### 日本語処理 (OpenJTalk)
- **実装場所**: `src/python/piper_train/phonemize/japanese.py`
- **処理内容**:
  - pyopenjtalkでフルコンテキストラベルを抽出
  - Kurihara方式によるプロソディマーク挿入
  - 58個の音素（有声・無声母音を含む）
  - 特殊記号: `^` (文頭), `$/?` (文末), `_` (短い休止), `#` (アクセント句境界), `[/]` (上昇/下降マーク)

#### その他言語処理 (espeak-ng)
- **実装場所**: `src/python/piper_train/preprocess.py`の`phonemize_batch_espeak()`
- **処理内容**:
  - espeak-ngライブラリによる音素化
  - 40以上の言語をサポート
  - 言語固有の音素マッピング

### 2.2 前処理パイプライン

```
1. テキスト正規化
2. 言語に応じた音素化処理
   - 日本語: phonemize_batch_openjtalk()
   - その他: phonemize_batch_espeak()
3. 音素をIDに変換
4. 音声データの正規化
5. JSONL形式でデータセット出力
```

## 3. マルチ言語対応の技術的課題

### 3.1 音素体系の統合
- **課題**: 日本語とその他言語で異なる音素体系
- **OpenJTalk**: 58音素 + プロソディマーク
- **espeak-ng**: 言語ごとに異なる音素セット

### 3.2 音素IDマッピング
- 現在は言語ごとに独立したIDマップを使用
- マルチ言語では統一されたIDマップが必要

### 3.3 プロソディ情報の扱い
- 日本語: アクセント情報が豊富
- その他言語: espeak-ngのプロソディ情報は限定的

## 4. 実装提案

### 4.1 統合音素化クラスの作成

```python
class MultilingualPhonemizer:
    def __init__(self):
        self.japanese_phonemizer = JapanesePhonemizer()
        self.espeak_phonemizer = EspeakPhonemizer()
        self.unified_phoneme_map = self._create_unified_map()
    
    def phonemize(self, text: str, language: str) -> List[str]:
        if language == "ja":
            phonemes = self.japanese_phonemizer.phonemize(text)
        else:
            phonemes = self.espeak_phonemizer.phonemize(text, language)
        
        # 言語タグを追加
        return [f"<{language}>"] + phonemes + [f"</{language}>"]
```

### 4.2 統一音素IDマップの設計

```json
{
  "special_tokens": {
    "<ja>": 0,
    "</ja>": 1,
    "<en>": 2,
    "</en>": 3,
    "<pad>": 4,
    "<unk>": 5
  },
  "japanese_phonemes": {
    "a": 10,
    "i": 11,
    "u": 12,
    // ... 日本語音素
  },
  "english_phonemes": {
    "æ": 100,
    "ɑ": 101,
    "ə": 102,
    // ... 英語音素
  }
}
```

### 4.3 前処理の修正

1. **言語検出機能の追加**
   - 文章ごとに言語を自動検出
   - 手動での言語指定オプション

2. **混合テキストの処理**
   ```python
   def process_mixed_text(text: str) -> List[Tuple[str, str]]:
       # 例: "こんにちは、Hello world!"
       # → [("こんにちは、", "ja"), ("Hello world!", "en")]
   ```

3. **データセット形式の拡張**
   ```json
   {
     "text": "こんにちは、Hello!",
     "audio_path": "path/to/audio.wav",
     "phonemes": ["<ja>", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "</ja>", 
                  "<en>", "h", "ə", "l", "oʊ", "</en>"],
     "languages": ["ja", "en"]
   }
   ```

## 5. 実装計画

### Phase 1: 基礎実装（1-2週間）
1. MultilingualPhonemizer クラスの実装
2. 統一音素IDマップの作成
3. 単体テストの作成

### Phase 2: 前処理パイプライン統合（1週間）
1. preprocess.pyへの統合
2. 混合言語テキストの処理実装
3. データセット出力形式の対応

### Phase 3: モデル学習対応（2週間）
1. モデルアーキテクチャの調整（言語埋め込み層の追加）
2. 学習スクリプトの修正
3. 推論コードの対応

### Phase 4: 評価・最適化（1週間）
1. マルチ言語モデルの品質評価
2. パフォーマンス最適化
3. ドキュメント作成

## 6. 予想される利点

1. **単一モデルで複数言語対応**
   - モデルサイズの削減
   - 言語間の知識転移

2. **コードスイッチング対応**
   - 同一文内での言語切り替え
   - より自然な多言語音声

3. **保守性の向上**
   - 言語追加が容易
   - 統一されたパイプライン

## 7. リスクと対策

### リスク
1. 音素体系の違いによる品質低下
2. 学習データの不均衡
3. 推論速度の低下

### 対策
1. 言語固有の特徴を保持する設計
2. データ拡張とバランシング
3. 効率的なモデルアーキテクチャ

## 8. 次のステップ

1. このレポートのレビューと承認
2. Phase 1の実装開始
3. プロトタイプの作成と評価

## 参考資料

- [Multilingual TTS Models: A Survey](https://arxiv.org/...)
- [Cross-lingual Transfer Learning for TTS](https://...)
- [Piper TTS Documentation](https://github.com/rhasspy/piper)
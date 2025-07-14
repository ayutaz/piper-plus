# マルチ言語モデル実装サマリー

## 実装完了事項

### 1. 統一音素IDマップ (`multilingual_phoneme_map.py`)
- **機能**: 日本語（OpenJTalk）と英語（espeak-ng）の音素を統一IDで管理
- **ID割り当て**:
  - 0-99: 特殊トークン（`<pad>`, `<unk>`, 言語タグ等）
  - 100-199: 日本語音素（58音素 + プロソディマーク）
  - 200-299: 英語音素（54音素）
  - 400-499: 共通音素（将来の最適化用）
- **総語彙数**: 132個

### 2. マルチ言語音素化器 (`multilingual.py`)
- **LanguageDetector**: 文字ベースの言語検出
  - 日本語: ひらがな、カタカナ、漢字
  - 英語: ラテン文字
  - 韓国語、中国語等の検出も対応可能
- **MultilingualPhonemizer**: 混合言語テキストの音素化
  - 言語ごとにセグメント分割
  - 適切な音素化エンジン（OpenJTalk/espeak-ng）を選択
  - 言語タグの自動付与

### 3. データセットフォーマッター (`multilingual_dataset.py`)
- **データ形式**: 言語タグ埋め込み型JSONL
- **メタデータ**: 言語比率、主要言語、セグメント情報
- **自動生成**: config.json、phoneme_map.json

### 4. 前処理パイプライン統合 (`preprocess.py`)
- **新オプション**: `--multilingual` フラグ
- **新処理関数**: `phonemize_batch_multilingual()`
- **自動検出**: 日本語テキストは自動的にOpenJTalk使用

## 使用方法

### 1. マルチ言語データセットの前処理
```bash
python preprocess.py \
  --input-dir /path/to/dataset \
  --output-dir /path/to/output \
  --language mixed \
  --multilingual \
  --sample-rate 22050 \
  --dataset-format ljspeech
```

### 2. Pythonコードでの使用
```python
from piper_train.phonemize.multilingual import phonemize_multilingual

# 単一言語
phonemes = phonemize_multilingual("こんにちは", "ja")
# ['<lang:ja>', 'k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a', '</lang:ja>']

# 混合言語（自動検出）
phonemes = phonemize_multilingual("こんにちは、Hello!")
# ['<lang:ja>', 'k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a', '_', '</lang:ja>',
#  '<lang:en>', 'h', 'ə', 'l', 'oʊ', '</lang:en>']
```

### 3. データセット形式
```json
{
  "audio_path": "audio001.wav",
  "text": "こんにちは、Hello world!",
  "text_language": "mixed",
  "segments": [
    {"text": "こんにちは、", "language": "ja", "start_idx": 0, "end_idx": 6},
    {"text": "Hello world!", "language": "en", "start_idx": 6, "end_idx": 18}
  ],
  "phonemes": ["<lang:ja>", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "_", "</lang:ja>",
               "<lang:en>", "h", "ə", "l", "oʊ", "_", "w", "ɜ", "r", "l", "d", "</lang:en>"],
  "phoneme_ids": [10, 110, 104, 124, 116, 101, 137, 101, 123, 100, 4, 20,
                  11, 244, 202, 248, 213, 4, 250, 215, 249, 248, 233, 21],
  "duration": 2.5,
  "speaker_id": 0,
  "metadata": {
    "primary_language": "ja",
    "language_ratio": {"ja": 0.6, "en": 0.4}
  }
}
```

## テスト結果

### 音素マッピングテスト (`test_phoneme_map_only.py`)
- ✓ 全132個の音素が正しくマッピング
- ✓ 言語タグの付与・除去が正常動作
- ✓ 日本語・英語の音素ID変換が正常
- ✓ 混合言語シーケンスの処理が正常

## 次のステップ

### Phase 1 完了項目
- [x] 統一音素IDマップ
- [x] マルチ言語音素化器
- [x] データセットフォーマッター
- [x] preprocess.py統合
- [x] 単体テスト

### Phase 2 実装予定
- [ ] モデルアーキテクチャの修正（言語埋め込み層追加）
- [ ] 学習スクリプトの対応
- [ ] 推論コードの対応
- [ ] 実データでの検証

### Phase 3 拡張予定
- [ ] 中国語、スペイン語、フランス語、ドイツ語、韓国語対応
- [ ] 音素共通化の最適化
- [ ] ストリーミング推論対応

## 技術的な注意点

1. **piper_phonemize依存**: espeak-ng音素化にはpiper_phonemizeパッケージが必要
2. **文字エンコーディング**: UTF-8必須（特に日本語、特殊音素記号）
3. **メモリ使用量**: 言語数に比例して音素マップが増大

## 参考資料
- [設計仕様書](multilingual-model-specification.md)
- [調査レポート](multilingual-investigation.md)
- [テストコード](../test/test_phoneme_map_only.py)
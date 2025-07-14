# マルチ言語モデル設計仕様書

## 1. プロジェクトスコープ

### 1.1 目的
日本語（OpenJTalk）と他言語（espeak-ng）を単一のモデルで扱えるマルチ言語TTSシステムの構築

### 1.2 フェーズ分け
- **Phase 1 (MVP)**: 日本語＋英語の2言語対応
- **Phase 2**: 主要5言語追加（中国語、スペイン語、フランス語、ドイツ語、韓国語）
- **Phase 3**: 全espeak-ng対応言語への拡張

## 2. データセット設計

### 2.1 データセットフォーマット

#### Option A: 言語タグ埋め込み型（推奨）
```json
{
  "audio_path": "path/to/audio.wav",
  "text": "こんにちは、Hello world!",
  "text_language": "mixed",
  "segments": [
    {
      "text": "こんにちは、",
      "language": "ja",
      "start_idx": 0,
      "end_idx": 6
    },
    {
      "text": "Hello world!",
      "language": "en",
      "start_idx": 6,
      "end_idx": 18
    }
  ],
  "phonemes": ["<lang:ja>", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "_", "</lang:ja>",
               "<lang:en>", "h", "ə", "l", "oʊ", "_", "w", "ɜ", "r", "l", "d", "</lang:en>"],
  "phoneme_ids": [300, 45, 67, 23, 23, 34, 12, 34, 89, 45, 5, 301,
                  302, 123, 145, 167, 189, 5, 201, 223, 245, 167, 178, 303],
  "duration": 2.5,
  "speaker_id": 0,
  "metadata": {
    "primary_language": "ja",
    "language_ratio": {"ja": 0.6, "en": 0.4}
  }
}
```

#### Option B: 言語別音素配列型
```json
{
  "audio_path": "path/to/audio.wav",
  "text": "こんにちは、Hello world!",
  "phonemes_by_language": {
    "ja": {
      "phonemes": ["k", "o", "N", "n", "i", "ch", "i", "w", "a", "_"],
      "positions": [0, 10]
    },
    "en": {
      "phonemes": ["h", "ə", "l", "oʊ", "_", "w", "ɜ", "r", "l", "d"],
      "positions": [11, 21]
    }
  },
  "unified_phoneme_ids": [45, 67, 23, 23, 34, 12, 34, 89, 45, 5,
                         123, 145, 167, 189, 5, 201, 223, 245, 167, 178],
  "language_ids": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
}
```

### 2.2 推奨フォーマットの理由
Option Aを推奨する理由：
1. 言語の切り替わりが明確
2. ストリーミング処理に適している
3. 既存のPiperアーキテクチャとの互換性が高い
4. 言語埋め込みの学習が容易

## 3. 音素IDマッピング設計

### 3.1 ID割り当て方針
```
0-99:     特殊トークン（PAD, UNK, 言語タグ等）
100-199:  日本語専用音素
200-299:  英語専用音素  
300-399:  中国語専用音素
400-499:  共通音素（複数言語で共有）
500-:     将来の拡張用
```

### 3.2 特殊トークン定義
```python
SPECIAL_TOKENS = {
    "<pad>": 0,
    "<unk>": 1,
    "<bos>": 2,
    "<eos>": 3,
    "_": 4,  # pause/silence
    
    # 言語タグ（開始）
    "<lang:ja>": 10,
    "<lang:en>": 11,
    "<lang:zh>": 12,
    "<lang:es>": 13,
    "<lang:fr>": 14,
    "<lang:de>": 15,
    "<lang:ko>": 16,
    
    # 言語タグ（終了）
    "</lang:ja>": 20,
    "</lang:en>": 21,
    "</lang:zh>": 22,
    "</lang:es>": 23,
    "</lang:fr>": 24,
    "</lang:de>": 25,
    "</lang:ko>": 26,
}
```

## 4. 対応言語の優先順位

### 4.1 Phase 1 (MVP) - 2言語
1. **日本語 (ja)** - OpenJTalk
2. **英語 (en-us)** - espeak-ng

### 4.2 Phase 2 - 主要7言語
3. **中国語 (zh-cn)** - 話者数が多い
4. **スペイン語 (es)** - 話者数が多い
5. **フランス語 (fr)** - 国際言語
6. **ドイツ語 (de)** - 技術文書で使用頻度高
7. **韓国語 (ko)** - アジア圏の主要言語

### 4.3 Phase 3 - 追加言語
8. ポルトガル語 (pt-br)
9. イタリア語 (it)
10. ロシア語 (ru)
11. アラビア語 (ar)
12. ヒンディー語 (hi)
（以降、需要に応じて追加）

## 5. 学習データ要件

### 5.1 データ量の目安
- **Phase 1 (2言語)**:
  - 日本語: 10時間以上
  - 英語: 10時間以上
  - 混合データ: 2時間以上

- **Phase 2以降**:
  - 各言語: 5時間以上
  - 言語ペアごとの混合: 30分以上

### 5.2 データ品質要件
- サンプリングレート: 22050Hz以上
- 録音品質: スタジオ品質推奨
- 発話スタイル: 自然な会話調
- 話者: 各言語ネイティブスピーカー

## 6. モデルアーキテクチャの変更

### 6.1 追加コンポーネント
```python
class MultilingualVITS(nn.Module):
    def __init__(self, config):
        super().__init__()
        # 既存のVITSコンポーネント
        self.text_encoder = TextEncoder(config)
        self.flow = Flow(config)
        self.decoder = HifiGANDecoder(config)
        
        # 新規追加
        self.language_embedding = nn.Embedding(
            num_languages=16,  # 最大対応言語数
            embedding_dim=config.hidden_channels
        )
        self.language_encoder = LanguageEncoder(config)
```

### 6.2 言語埋め込みの統合
- テキストエンコーダへの言語情報注入
- 言語固有の特徴と共通特徴の分離学習
- アテンション機構での言語考慮

## 7. 実装上の考慮事項

### 7.1 前処理の並列化
```python
class MultilingualPreprocessor:
    def __init__(self):
        self.processors = {
            'ja': JapanesePhonemizer(),
            'en': EnglishPhonemizer(),
            # 他言語...
        }
    
    def process_mixed_text(self, text: str) -> List[PhonemeSegment]:
        # 言語検出と分割
        segments = self.detect_and_split(text)
        
        # 並列処理
        with ThreadPoolExecutor() as executor:
            results = executor.map(self.process_segment, segments)
        
        return self.merge_results(results)
```

### 7.2 キャッシュ戦略
- 言語別の音素化結果キャッシュ
- 頻出フレーズの事前計算
- 言語検出結果のキャッシュ

### 7.3 メモリ効率
- 言語別の動的モデルロード
- 使用頻度の低い言語の遅延読み込み
- 音素マップの圧縮保存

## 8. 評価指標

### 8.1 品質評価
- **MOS (Mean Opinion Score)**: 各言語で4.0以上
- **言語切り替え自然性**: 専門家評価で3.5以上
- **発音正確性**: ネイティブ評価で90%以上

### 8.2 性能評価
- **推論速度**: リアルタイムファクター < 0.5
- **メモリ使用量**: 2GB以下（全言語ロード時）
- **初回起動時間**: 5秒以内

## 9. リスク管理

### 9.1 技術的リスク
| リスク | 影響度 | 対策 |
|--------|--------|------|
| 言語間の音声品質差 | 高 | 言語別の品質調整パラメータ |
| モデルサイズ増大 | 中 | 量子化、プルーニング |
| 学習の収束困難 | 高 | カリキュラム学習の採用 |

### 9.2 運用リスク
| リスク | 影響度 | 対策 |
|--------|--------|------|
| データ不足 | 高 | 合成データ拡張 |
| 言語追加の複雑性 | 中 | モジュラー設計 |
| 後方互換性 | 低 | バージョニング戦略 |

## 10. 次のステップ

1. **設計レビュー**: この仕様書のレビューと承認
2. **プロトタイプ開発**: Phase 1の2言語モデル実装
3. **データ収集**: 日本語・英語の混合データセット作成
4. **実験**: 小規模モデルでの実現可能性検証
5. **本実装**: フルスケールモデルの開発

## 付録A: 音素マッピング例

### 日本語音素（OpenJTalk）
```
100: "a", 101: "i", 102: "u", 103: "e", 104: "o",
105: "ka", 106: "ki", 107: "ku", 108: "ke", 109: "ko",
...
```

### 英語音素（espeak-ng）
```
200: "æ", 201: "ɑ", 202: "ə", 203: "ɛ", 204: "ɪ",
205: "i", 206: "ɔ", 207: "ʊ", 208: "u", 209: "ʌ",
...
```

## 付録B: 参考実装

既存のマルチ言語TTSプロジェクト：
- Google's Tacotron 2 Multilingual
- Facebook's MMS (Massively Multilingual Speech)
- Microsoft's YourTTS
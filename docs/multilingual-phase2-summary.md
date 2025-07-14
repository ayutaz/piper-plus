# マルチ言語モデル Phase 2 実装サマリー

## Phase 2 完了事項

### 1. モデルアーキテクチャの拡張

#### 1.1 言語埋め込み層の追加 (`models_multilingual.py`)
- **MultilingualTextEncoder**: 言語埋め込みをサポートするテキストエンコーダー
  - 言語埋め込み次元: 64次元（設定可能）
  - 最大8言語をサポート（拡張可能）
  - 文全体または音素単位での言語埋め込み対応
- **MultilingualSynthesizerTrn**: マルチ言語対応VITS
  - 既存のVITSモデルを継承
  - 言語IDを入力として受け取る
  - 推論時も言語指定可能

#### 1.2 主な変更点
```python
# 言語埋め込みの追加
self.lang_emb = nn.Embedding(n_languages, lang_embedding_dim)

# forwardメソッドに言語ID追加
def forward(self, x, x_lengths, y, y_lengths, sid=None, lang_ids=None):
    x, m_p, logs_p, x_mask = self.enc_p(x, x_lengths, lang_ids)
    # ...
```

### 2. 学習インフラストラクチャ

#### 2.1 マルチ言語データセット (`dataset_multilingual.py`)
- **MultilingualDataset**: 言語情報を含むデータセット
- **MultilingualBatch**: 言語IDを含むバッチ構造
- **MultilingualCollate**: バッチ作成時の言語ID処理
- コードスイッチング対応（音素単位の言語ID）

#### 2.2 PyTorch Lightning統合 (`lightning_multilingual.py`)
- **MultilingualVitsModel**: 学習・検証ループ実装
- 言語統計のロギング
- チェックポイント変換機能（単一言語→マルチ言語）

#### 2.3 学習スクリプト (`train_multilingual.py`)
- マルチ言語専用の学習スクリプト
- 品質設定（x-low, low, medium, high）
- 単一言語モデルからの転移学習サポート

### 3. 設定・ツール

#### 3.1 モデル設定 (`multilingual_vits_config.json`)
- 8言語対応の設定
- 言語ごとの音素化設定
- 学習・推論パラメータ

#### 3.2 データセット準備 (`prepare_multilingual_dataset.py`)
- サンプルデータ生成
- ダミー音声ファイル作成（テスト用）
- 混合言語・コードスイッチングの例

## 使用方法

### 1. データセット準備
```bash
# サンプルデータセット作成
python scripts/prepare_multilingual_dataset.py \
  --output-dir multilingual_dataset \
  --create-dummy-audio \
  --validation-split 0.2
```

### 2. モデル学習
```bash
# 新規学習
python -m piper_train.train_multilingual \
  --dataset-dir multilingual_dataset \
  --max_epochs 100 \
  --batch-size 16 \
  --quality medium \
  --gpus 1

# 単一言語モデルからの転移学習
python -m piper_train.train_multilingual \
  --dataset-dir multilingual_dataset \
  --convert-from-single-lang path/to/checkpoint.ckpt \
  --max_epochs 50
```

### 3. 推論（実装例）
```python
# モデルロード
model = MultilingualSynthesizerTrn.load_from_checkpoint("checkpoint.ckpt")

# 日本語の音声生成
phoneme_ids = [10, 110, 104, 124, 116, 101, 137, 101, 123, 100, 20]  # こんにちは
lang_ids = torch.tensor([0])  # 日本語
audio = model.infer(phoneme_ids, lang_ids=lang_ids)

# 英語の音声生成
phoneme_ids = [11, 244, 202, 248, 213, 21]  # hello
lang_ids = torch.tensor([1])  # 英語
audio = model.infer(phoneme_ids, lang_ids=lang_ids)
```

## 技術的詳細

### 言語埋め込みの実装
1. **音素埋め込み + 言語埋め込み**: 両方の情報を組み合わせて表現学習
2. **位置**: テキストエンコーダーの最初の層で結合
3. **次元**: デフォルト64次元（品質設定により可変）

### メモリ効率
- バッチ処理時の言語IDは効率的にパディング
- 未使用言語の埋め込みは学習されない

### 拡張性
- 新言語追加: `num_languages`を増やすだけ
- 言語固有の処理: `language_settings`で設定

## 制限事項と今後の課題

### 現在の制限
1. **データ要件**: 各言語に十分な学習データが必要
2. **計算リソース**: 単一言語モデルより学習時間が長い
3. **品質バランス**: 言語間の品質差が生じる可能性

### 今後の改善案
1. **言語適応層**: 言語固有の特徴をより効果的に学習
2. **クロスリンガル学習**: 言語間の知識転移を促進
3. **動的言語埋め込み**: 使用言語のみをロード

## まとめ

Phase 2では、VITSモデルをマルチ言語対応に拡張し、学習・推論の完全なパイプラインを実装しました。これにより：

- ✅ 日本語（OpenJTalk）と英語（espeak-ng）の統合モデル学習が可能
- ✅ コードスイッチング（文内での言語切り替え）に対応
- ✅ 既存の単一言語モデルからの転移学習をサポート
- ✅ PyTorch Lightningによる効率的な学習

次のPhase 3では、実データでの検証と追加言語への拡張を行う予定です。
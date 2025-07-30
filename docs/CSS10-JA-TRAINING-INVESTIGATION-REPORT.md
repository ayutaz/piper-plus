# CSS10日本語TTSモデル学習調査報告書

## 概要
CSS10日本語データセットを使用してPiper TTSモデルを10,000エポック学習したが、生成される音声が「意味がわからない単語の羅列」となり、正常な日本語発音が得られなかった問題の調査報告と解決策。

## 問題の詳細

### 症状
- **学習エポック数**: 10,000エポック（約2.2日）
- **症状**: 生成される音声が正常な日本語発音にならず、意味不明な音の連続になる
- **影響範囲**: すべての日本語テキスト入力で発生

### 使用環境
- **GPU**: NVIDIA L4 × 4台
- **データセット**: CSS10日本語（6,841ファイル、約5時間）
- **モデル**: VITS with F0 Predictor, AccentProcessor, Prosody Embeddings (PR #98後)
- **ブランチ**: training/css10-ja-accuracy-v1

## 調査結果

### 1. TensorBoardログ分析

#### 損失値の異常
```
loss_gen_all (最終値):
- version_7: 28.313（237,049ステップ）
- 正常値: 10-20程度であるべき
- 問題: 初期値33から28までしか減少していない

loss_disc_all:
- 約2.2-2.3で安定（正常範囲）

val_loss:
- 約31.7-32.0（学習損失とほぼ同じ）
```

**診断**: モデルが正しく学習できていない。Generatorの損失が異常に高いまま収束。

### 2. 学習設定の分析

#### hparams.yaml
```yaml
learning_rate: 0.0032  # 自動スケーリング後
base_lr: 0.0002
auto_lr_scaling: true
batch_size: 64
devices: 4
resume_from_checkpoint: output-css10-ja-accuracy-v1/lightning_logs/version_5/checkpoints/epoch=1499-step=291000.ckpt
```

**問題点**:
1. 学習率が高すぎる（0.0032）
2. version_5から継続学習している

### 3. データセット検証

#### dataset.jsonl分析
```json
{
  "phonemes": ["^", "k", "o", "[", "n", "o", "m", "a", "]", "e", ...],
  "phoneme_ids": [1, 25, 11, 5, 50, 11, 52, 7, 6, 10, ...],
  "prosody_ids": [0, 14, 14, 5, 14, 14, 14, 14, 6, 14, ...]
}
```

**発見**:
- prosody_idsに値14が大量に含まれている（通常の音素に対するPAD値）
- 最大prosody値: 14（0-14の範囲）

### 4. モデルアーキテクチャの問題

#### F0 Predictorの初期化
```python
self.prosody_embed = nn.Embedding(16, hidden_channels)  # 16 prosody types
# PyTorchデフォルト: Normal(0, 1)で初期化される
```

**問題点**:
1. Embeddingのデフォルト初期化（std=1.0）は大きすぎる
2. 各層の初期化が明示的でない
3. 新しいコンポーネントの初期化が不適切

### 5. 推論時の問題

#### ONNXモデルの入力
```
Model inputs:
  input: ['batch_size', 'phonemes']
  input_lengths: ['batch_size']
  scales: [3]
```

**問題**: prosody_ids入力がONNXモデルに含まれていない

## 根本原因

### 主要因
1. **不適切な重み初期化**: F0 Predictor等の新コンポーネントの初期化が大きすぎる
2. **高すぎる学習率**: 自動スケーリング後の0.0032は高すぎる
3. **prosody情報の不整合**: 学習時は使用されるが、推論時に渡されない

### 副次的要因
- 継続学習による影響（version_5→version_7）
- prosody embedding数とデータの不整合の可能性

## 実施した対策

### 1. F0 Predictorの重み初期化を修正

```python
def _init_weights(self):
    """Initialize weights for better training stability."""
    # Initialize prosody embedding with small values
    nn.init.normal_(self.prosody_embed.weight, mean=0.0, std=0.02)
    
    # Initialize conv layers
    for module in self.modules():
        if isinstance(module, nn.Conv1d):
            nn.init.kaiming_normal_(module.weight, mode='fan_out', nonlinearity='relu')
            if module.bias is not None:
                nn.init.constant_(module.bias, 0)
        elif isinstance(module, nn.Linear):
            nn.init.xavier_uniform_(module.weight)
            if module.bias is not None:
                nn.init.constant_(module.bias, 0)
```

### 2. 前処理スクリプトの修正

config.json生成時にprosody情報を自動追加：

```python
# Add prosody information for Japanese
**(
    {
        "prosody_num_symbols": 11,
        "prosody_id_map": {
            str(i): [i] for i in range(11)
        }
    }
    if args.language == "ja"
    else {}
),
```

## 新規学習の推奨設定

### コマンド
```bash
# ディレクトリ作成
mkdir -p /data/piper/output-css10-ja-accuracy-v1-fixed-init/

# 学習実行
python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-accuracy-v1/ \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 32 \
    --num-workers 16 \
    --disable_auto_lr_scaling \
    --base_lr 1e-4 \
    --max_epochs 15000 \
    --checkpoint-epochs 100 \
    --save-top-k -1 \
    --ema-decay 0.9999 \
    --default_root_dir /data/piper/output-css10-ja-accuracy-v1-fixed-init/
```

### 重要な変更点
1. **学習率を手動設定**: 1e-4（以前の0.0032から大幅削減）
2. **自動学習率スケーリングを無効化**
3. **バッチサイズを削減**: 64→32（より安定した学習）
4. **チェックポイント頻度を増加**: 500→100エポックごと
5. **新規学習**: 継続学習ではなく最初から

## 監視ポイント

### 初期段階（0-100エポック）
1. **loss_gen_all**: 40-60から開始し、徐々に減少することを確認
2. **loss_disc_all**: 0.5-2.0の範囲で安定
3. **学習率**: 1e-4で固定されていることを確認

### 中期段階（100-1000エポック）
1. **音声品質**: 100エポックごとにONNXエクスポートしてテスト
2. **損失の収束**: loss_gen_allが20以下に減少することを期待

### 推論テスト
```bash
# ONNXエクスポート
python -m piper_train.export_onnx \
    /path/to/checkpoint.ckpt \
    /path/to/model.onnx

# config.jsonをコピー
cp dataset-css10-ja-accuracy-v1/config.json /path/to/model_dir/

# 音声生成テスト
echo "こんにちは" | python -m piper \
    --model /path/to/model.onnx \
    --output_file test.wav
```

## 期待される結果

1. **損失値の改善**: loss_gen_allが10-20の範囲に収束
2. **音声品質**: 明瞭な日本語発音
3. **学習時間**: 4GPU（L4）で約10-12日

## 今後の課題

1. **prosody対応ONNXエクスポート**: 現在prosody_ids入力が含まれていない
2. **F0 Predictorの効果検証**: 新アーキテクチャの利点を最大化
3. **マルチスピーカー対応**: 現在はシングルスピーカーのみ

## 結論

10,000エポックの学習が失敗した主要因は、F0 Predictorなど新コンポーネントの不適切な初期化と高すぎる学習率でした。これらを修正し、新規学習を開始することで、正常な日本語TTSモデルの学習が期待できます。

---
作成日: 2024-07-30
作成者: Claude (Anthropic)
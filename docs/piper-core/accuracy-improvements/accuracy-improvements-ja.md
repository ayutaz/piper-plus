# Piper-Plus 精度向上実装ガイド

## 概要

本ドキュメントでは、piper-plusの音声合成品質を向上させるための3つの主要な改善実装について説明します。これらの改善は、モデルサイズを大幅に増加させることなく、MOS（Mean Opinion Score）を向上させることを目的としています。

## 改善項目と期待される効果

| 改善項目 | 期待されるMOS向上 | 実装の複雑さ | ONNX互換性 |
|---------|-----------------|------------|-----------|
| F0予測器の追加 | +0.10 | 中 | ✓ |
| アクセント記号埋め込み | +0.05-0.08 | 低 | ✓ |
| HiFi-GAN EMA平均化 | +0.03-0.06 | 低 | ✓ |

## 1. F0予測器の追加

### 概要
F0（基本周波数）予測器は、テキストから直接ピッチ情報を予測することで、より自然なイントネーションとアクセントを実現します。

### 実装詳細

#### ファイル: `src/python/piper_train/vits/f0_predictor.py`

主要コンポーネント：
- **F0Predictor**: FastSpeech2ベースのF0予測モジュール
- **離散F0ビン**: 連続的なF0値を256個のビンに離散化
- **プロソディ埋め込み**: 日本語のアクセント記号を学習可能な埋め込みに変換
- **不確実性モデリング**: F0の分散を予測して不確実性を考慮

### 統合方法

#### 1. VITSモデルへの統合

```python
# src/python/piper_train/vits/models.py の修正

class SynthesizerTrn(nn.Module):
    def __init__(self, ...):
        # 既存のコード...
        
        # F0予測器を追加
        self.f0_predictor = F0Predictor(
            hidden_channels=hidden_channels,
            filter_channels=filter_channels,
            n_heads=n_heads,
            gin_channels=gin_channels
        )
        
    def forward(self, x, x_lengths, y=None, y_lengths=None, speaker_ids=None, f0=None):
        # テキストエンコーダの後
        x, m_p, logs_p, x_mask = self.enc_p(x, x_lengths)
        
        # F0予測
        if f0 is None and self.training:
            f0_pred, f0_values, f0_var = self.f0_predictor(x, x_mask, g=g)
            # F0を条件として使用
            x = x + self.f0_encoder(f0_values)
```

#### 2. 損失関数の追加

```python
# src/python/piper_train/vits/lightning.py の修正

def training_step_g(self, batch: Batch):
    # 既存のコード...
    
    # F0損失を追加
    if hasattr(self.model_g, 'f0_predictor'):
        f0_loss_fn = F0Loss()
        f0_pred, f0_values, f0_var = self.model_g.f0_predictor(...)
        loss_f0, f0_metrics = f0_loss_fn(f0_pred, f0_values, f0_var, batch.f0_true)
        loss_gen_all += loss_f0 * 0.1  # 重み係数
```

## 2. アクセント記号埋め込みの強化

### 概要
既存の日本語プロソディマークを拡張し、より詳細なアクセント制御を実現します。

### 実装詳細

#### ファイル: `src/python/piper_train/phonemize/accent_processor.py`

拡張されたアクセントマーク：
- `↑`: アクセント核の上昇
- `↓`: アクセント核後の下降
- `→`: 平坦なイントネーション
- `⤴`: 句末の上昇
- `⤵`: 句末の下降
- `|`: 小句境界
- `‖`: 大句境界

### 前処理の統合

```python
# src/python/piper_train/preprocess.py の修正

def phonemize_batch_openjtalk(args, queue_in, queue_out):
    # アクセント処理器を初期化
    accent_processor = JapaneseAccentProcessor()
    
    # 既存のコード...
    
    # 音素化の後にアクセント処理を追加
    utt.phonemes = phonemize_japanese(casing(utt.text))
    
    # アクセントマークを追加
    enhanced_phonemes, prosody_ids = accent_processor.process_text_with_accent(
        utt.text,
        utt.phonemes,
        accent_dict=load_accent_dict()  # オプション：アクセント辞書
    )
    
    utt.phonemes = enhanced_phonemes
    utt.prosody_ids = prosody_ids  # F0予測器で使用
```

## 3. EMA（指数移動平均）の実装

### 概要
HiFi-GANジェネレータのパラメータに対してEMAを適用することで、学習の安定性を向上させ、ファインチューニング時の品質劣化を防ぎます。

### 実装詳細

#### ファイル: `src/python/piper_train/vits/ema.py`

主要機能：
- **適応的減衰率**: 更新回数に基づいて減衰率を動的に調整
- **選択的適用**: HiFi-GANデコーダのみに適用（計算効率のため）
- **チェックポイント対応**: EMA状態の保存と復元

### PyTorch Lightningへの統合

```python
# src/python/piper_train/__main__.py の修正

from piper_train.vits.ema import EMACallback

def main():
    # 既存のコード...
    
    # EMAコールバックを追加
    ema_callback = EMACallback(
        decay=0.999,
        apply_ema_every_n_steps=1,
        start_step=1000  # ウォームアップ後に開始
    )
    
    # トレーナーにコールバックを追加
    callbacks = trainer.callbacks or []
    callbacks.append(ema_callback)
    trainer.callbacks = callbacks
```

## パフォーマンスへの影響

### メモリ使用量
- F0予測器: +約50MB（モデルサイズ）
- アクセント埋め込み: +約2MB
- EMA: 既存モデルサイズの2倍（影パラメータ用）

### 推論速度
- F0予測器: +約10-15%の計算時間
- アクセント処理: 無視できる程度
- EMA: 推論時は影響なし（学習時のみ）

### ONNX変換
全ての改善はONNX互換性を維持：

```python
# ONNX変換時の注意点
def export_to_onnx(model, ...):
    # EMAの影パラメータを適用
    if hasattr(model, 'ema_generator'):
        model.ema_generator.apply_shadow()
    
    # 通常のONNXエクスポート
    torch.onnx.export(model, ...)
    
    # 元のパラメータに戻す
    if hasattr(model, 'ema_generator'):
        model.ema_generator.restore()
```

## 段階的な実装推奨

### フェーズ1: EMAの実装（1-2日）
- 最も実装が簡単で、即座に効果が期待できる
- 既存のコードへの変更が最小限

### フェーズ2: アクセント記号の強化（2-3日）
- 前処理パイプラインの修正が必要
- 既存の日本語処理を拡張

### フェーズ3: F0予測器の追加（3-5日）
- 最も複雑だが、最大の改善が期待できる
- データセットにF0情報の追加が必要

## トレーニングのベストプラクティス

### 1. 段階的ファインチューニング
```bash
# ステップ1: EMAを有効にして基本モデルを学習
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --use-ema \
    --batch-size 32

# ステップ2: F0予測器を追加して継続学習
python -m piper_train \
    --resume-from-checkpoint model.ckpt \
    --enable-f0-predictor \
    --f0-loss-weight 0.1
```

### 2. 学習率スケジューリング
```python
# F0予測器用の個別学習率
optimizer_g = torch.optim.AdamW([
    {'params': model.model_g.enc_p.parameters(), 'lr': 1e-4},
    {'params': model.model_g.f0_predictor.parameters(), 'lr': 2e-4},  # 高めの学習率
    {'params': model.model_g.dec.parameters(), 'lr': 1e-4}
])
```

## トラブルシューティング

### 問題: F0予測が不安定
**解決策**: F0損失の重みを小さくし、段階的に増加させる

### 問題: アクセント記号が認識されない
**解決策**: phoneme_id_mapにアクセント記号のIDが含まれているか確認

### 問題: EMAモデルの品質が低い
**解決策**: decay値を0.9995など、より高い値に調整

## まとめ

これらの3つの改善により、piper-plusは以下の品質向上が期待できます：

1. **より自然なイントネーション**: F0予測器による正確なピッチ制御
2. **改善されたアクセント表現**: 詳細なアクセント記号による韻律制御
3. **安定した音質**: EMAによる学習安定性とファインチューニング耐性

実装は段階的に行うことが推奨され、各改善は独立して適用可能です。Unity Sentisとの互換性も維持されるため、既存のワークフローへの統合も容易です。
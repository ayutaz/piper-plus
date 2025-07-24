# PR #98による日本語TTS性能低下の原因分析

## 概要

PR #98（v1精度向上のための実装済みコンポーネント追加）により、日本語TTSで「意味がわからない単語の羅列の発音」になる問題が発生しました。本ドキュメントでは、この問題の詳細な調査結果と根本原因、解決策について記載します。

## 調査期間
2025年7月24日

## 問題の症状

- CSS10日本語データセットで1500エポック学習後、正しい日本語発音が生成されない
- v1.3.0では同じ1500エポックで正常に動作していた
- openjtalk-binaries-latestでは正常動作

## 調査プロセス

### 1. 初期仮説と検証

#### 仮説1: 音素化処理のバグ
- **検証結果**: 音素化処理は正しく実装されていた
- 文末マーカー（`$`）も正しく生成されている
- `phonemize_japanese()`関数は2025年6月6日の初期実装から正しく動作

#### 仮説2: Prosody ID生成の不一致
- **検証結果**: 学習時と推論時のprosody ID生成は完全に一致
- AccentProcessorのID割り当て:
  - `^`: 0, `$`: 1, `?`: 2, `_`: 3, `#`: 4, `[`: 5, `]`: 6
  - 通常の音素: 14（`<PAD>`）
- 推論時も同じID割り当てを使用

#### 仮説3: F0 Predictorの実装問題
- **検証結果**: F0 Predictorは正しく動作
- ONNXエクスポートもONNXFriendlyAttentionで対応済み
- 設計通り、F0出力はエンコーダー出力に加算されない

## 根本原因

### PR #98によるアーキテクチャの複雑化

PR #98で以下のコンポーネントが追加されました：

1. **F0 Predictor**
   - 4層のTransformerベースモジュール
   - 日本語のピッチ/韻律モデリング用
   - 追加パラメータ数: 約200万

2. **AccentProcessor**
   - 日本語アクセント・韻律の詳細処理
   - 拡張アクセントマーク対応
   - Prosody embedding層の追加

3. **Prosody Embeddings**
   - 新しい入力次元の追加
   - 韻律情報の埋め込み表現

### 学習不足が真の原因

```
v1.3.0（シンプル）: 1500エポックで十分
PR #98後（複雑）: 1500エポックでは不十分
```

**証拠：**
- 音素化、prosody ID生成、モデルアーキテクチャはすべて正しい
- CSS10の5時間データでは、新しい複雑なアーキテクチャに1500エポックでは不十分
- パラメータ数の増加により、収束に必要なエポック数も増加

## 推奨される解決策

### 1. 追加学習（推奨）

既存のチェックポイントから追加学習：

```bash
# L4 24GB × 4枚での追加学習
python -m piper_train \
    --dataset-dir dataset-css10-ja-accuracy-v1/ \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 16 \
    --num-workers 16 \
    --auto_lr_scaling \
    --base_lr 1e-4 \
    --max_epochs 5000 \
    --checkpoint-epochs 100 \
    --resume_from_checkpoint output-css10-ja-accuracy-v1/lightning_logs/version_2/checkpoints/last.ckpt \
    --gradient_clip_val 1.0 \
    --precision 16-mixed \
    --accumulate_grad_batches 2 \
    --default_root_dir output-css10-ja-accuracy-v1/
```

### 2. データセットの拡張

より大規模なデータセットの使用を検討：
- JVSコーパス（100話者、30時間）
- ITAコーパス（高品質単一話者）
- JSUT（10時間）

### 3. 学習戦略の改善

- **段階的学習**: まずF0 Predictorなしで基本モデルを学習
- **転移学習**: 大規模データで事前学習後、ターゲット話者でファインチューニング
- **学習率スケジューリング**: warmup + cosine annealing

## 技術的詳細

### モデルアーキテクチャの変更点

```python
# PR #98前
def forward(self, x, x_lengths, y, y_lengths, sid=None):
    # シンプルなVITS

# PR #98後  
def forward(self, x, x_lengths, y, y_lengths, sid=None, prosody_ids=None):
    # F0 Predictor追加
    if prosody_ids is not None:
        f0_pred_bins, f0_pred, f0_variance = self.f0_predictor(
            x, x_mask, prosody_ids, g
        )
```

### 学習データ形式

```json
{
  "audio_path": "path/to/audio.wav",
  "text": "こんにちは",
  "phonemes": ["^", "k", "o", "[", "n", "n", "i", "ch", "i", "w", "a", "$"],
  "phoneme_ids": [1, 46, 30, ...],
  "prosody_ids": [0, 14, 14, 5, 14, 14, 14, 14, 14, 14, 14, 1]
}
```

## まとめ

PR #98自体にバグはありませんが、アーキテクチャの複雑化により必要な学習エポック数が大幅に増加しました。CSS10のような小規模データセットでは、少なくとも3000-5000エポックの学習が必要です。

## 参考情報

- PR #98: feat: v1精度向上のための実装済みコンポーネントを追加
- コミット: 7fb813b8ebfb36af5a5f7fdf7532f264c2fdcd4a
- 影響を受けるバージョン: v1.3.0以降でPR #98を含むもの
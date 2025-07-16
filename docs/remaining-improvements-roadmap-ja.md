# Piper-Plus 残りの精度向上策ロードマップ

## 実装状況サマリー

### v1ブランチで実装済み ✅
- **gin_channels増加（PR #97）**: MOS +0.04-0.06達成
- **F0予測器（PR #98）**: MOS +0.10達成
- **AccentProcessor（PR #98）**: MOS +0.05-0.08達成
- **EMA実装（PR #98）**: MOS +0.03-0.06達成

### v2ブランチで実装済み ✅
- **Multi-Resolution STFT Discriminator**: MOS +0.08-0.12達成
- **アクセント強度レベル（3段階）**: MOS +0.03-0.05達成
- **質問文検出の改善**: MOS +0.02-0.03達成
- **データ拡張（SpecAugment等）**: MOS +0.05-0.10達成
- **Duration正則化**: MOS +0.02-0.04達成
- **Transformer blocks**: 既にVITSアーキテクチャに統合済み

### 累積改善効果
- **v1ブランチ合計**: MOS +0.20-0.30
- **v2ブランチ合計**: MOS +0.26-0.46
- **現在の合計改善**: MOS +0.46-0.76

## 真に残っている改善策（3つのみ）

### 1. WavLM Discriminator（最優先）❌
**期待効果**: MOS +0.15-0.25（単独で最大の改善）

**概要**: 
- StyleTTS2やFLY-TTSで採用されている最先端技術
- 事前学習済みWavLMモデルを識別器として使用
- 人間の聴覚特性により近い音声品質評価

**実装時間**: 2週間

**実装内容**:
```python
# src/python/piper_train/vits/wavlm_discriminator.py
class WavLMDiscriminator(nn.Module):
    def __init__(self, pretrained_model="microsoft/wavlm-base"):
        super().__init__()
        self.wavlm = WavLMModel.from_pretrained(pretrained_model)
        # Lower layers frozen for feature extraction
        # Custom discriminator head on top
```

**利点**:
- プロソディの自然性が大幅に向上
- ポーズや呼吸音の扱いが改善
- 感情表現が豊かになる

### 2. 日本語BERT埋め込み ❌
**期待効果**: MOS +0.06-0.10

**概要**:
- 日本語特化BERT（tohoku-bert、waseda-roberta等）を使用
- 文脈理解に基づく韻律生成
- アクセント予測の精度向上

**実装時間**: 1.5週間

**実装内容**:
```python
# src/python/piper_train/vits/bert_encoder.py
class JapaneseBERTEncoder(nn.Module):
    def __init__(self, model_name="cl-tohoku/bert-base-japanese-v3"):
        super().__init__()
        self.bert = AutoModel.from_pretrained(model_name)
        # Alignment mechanism to map BERT tokens to phonemes
```

**注意点**:
- ONNXエクスポート時は事前計算が必要
- メモリ使用量が増加（+500MB）

### 3. Conditional Flow Matching ❌
**期待効果**: MOS +0.10-0.15

**概要**:
- Matcha-TTS方式の最新フロー技術
- 従来のNormalizing Flowを置き換え
- 推論速度も2-3倍向上

**実装時間**: 3週間

**実装内容**:
```python
# src/python/piper_train/vits/flow_matching.py
class ConditionalFlowMatching(nn.Module):
    def __init__(self, channels, hidden_channels):
        super().__init__()
        # ODE-based flow instead of normalizing flow
        # Faster training and inference
```

**利点**:
- 高品質と高速推論の両立
- 学習の安定性向上
- メモリ効率の改善

## 実装優先順位の根拠

### 最優先：WavLM Discriminator
1. **効果が最大**: 単独でMOS +0.15-0.25
2. **実装が独立**: 既存コードへの影響が最小
3. **最新研究で実証済み**: 2024年の複数の論文で有効性確認

### 次優先：日本語BERT
4. **日本語特有の改善**: 文脈理解が重要な日本語に特に有効
5. **比較的実装が簡単**: 既存のBERTモデルを活用

### 後回し：Conditional Flow Matching
6. **実装が複雑**: VITSの中核部分の変更が必要
7. **リスクが高い**: 既存の学習済みモデルとの互換性問題

## 実装スケジュール案

### Phase 1: WavLM Discriminator（2週間）
- **Week 1**: 基本実装とVITSへの統合
- **Week 2**: ハイパーパラメータ調整と評価

**期待効果**: MOS +0.15-0.25

### Phase 2: 日本語BERT（1.5週間）
- **Day 1-5**: BERT統合とアライメント実装
- **Day 6-10**: ONNXエクスポート対応

**期待効果**: MOS +0.06-0.10（累計 +0.21-0.35）

### Phase 3: Conditional Flow Matching（3週間）
- **Week 1**: 基本実装
- **Week 2**: VITSへの統合
- **Week 3**: 最適化と評価

**期待効果**: MOS +0.10-0.15（累計 +0.31-0.50）

## 最終的な品質目標

### 現在の達成レベル
- **実装済み改善**: MOS +0.46-0.76
- **ベースラインからの改善**: 既に商用レベルに近い

### 全実装完了時の期待値
- **追加改善**: MOS +0.31-0.50
- **総合改善**: MOS +0.77-1.26
- **品質レベル**: 人間の音声と区別困難なレベル

## 実装時の注意点

### ONNX互換性の維持
- WavLM: 推論時は不要（discriminatorは学習時のみ）
- BERT: 事前計算により対応可能
- Flow Matching: ONNX対応実装が必要

### モデルサイズの管理
- 現在の使用量: 約60MB増加（v1+v2）
- 残り許容量: 約40MB
- BERTは別途管理が必要

### 後方互換性
- 既存モデルとの互換性維持が重要
- フラグによる機能の有効/無効化

## 推奨される次のステップ

1. **WavLM Discriminatorの実装開始**
   - 最も効果的で、実装リスクが低い
   - 2週間で大幅な品質向上が期待できる

2. **並行してBERT統合の設計**
   - 日本語特有の改善として重要
   - ONNXエクスポート方法の検討

3. **Flow Matchingは慎重に評価**
   - 効果は大きいが実装が複雑
   - 他の改善の効果を見てから判断

これらの3つの改善により、piper-plusは真に最先端のTTSシステムとなり、商用システムを超える品質を実現できる可能性があります。
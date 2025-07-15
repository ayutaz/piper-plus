# Piper-Plus 残りの精度向上策ロードマップ

## 実装済み
- ✅ **gin_channels増加（PR #97）**: MOS +0.04-0.06達成

## 残りの改善策（優先順位順）

### 1. 既存コンポーネントの統合（すぐに実装可能）

#### 1-1. AccentProcessor統合（実装時間：3-4時間）
**現状**: `accent_processor.py`は実装済みだが未使用

**期待効果**: MOS +0.05-0.08

**実装内容**:
- 拡張アクセントマーク（↑↓→⤴⤵|‖）の有効化
- 前処理パイプラインへの統合
- F0予測器との連携準備

**ファイル**:
- `src/python/piper_train/phonemize/accent_processor.py`（作成済み）
- `src/python/piper_train/preprocess.py`（修正必要）

#### 1-2. EMA実装（実装時間：1-2日）
**現状**: `ema.py`は実装済みだが未使用

**期待効果**: MOS +0.03-0.06

**実装内容**:
- HiFi-GANジェネレータへのEMA適用
- PyTorch Lightningコールバックの統合
- ファインチューニング時の品質保持

**ファイル**:
- `src/python/piper_train/vits/ema.py`（作成済み）
- `src/python/piper_train/__main__.py`（修正必要）

### 2. 軽量な新規実装（1週間以内）

#### 2-1. アクセント強度レベル（実装時間：2-3時間）
**期待効果**: MOS +0.03-0.05

**実装内容**:
```python
# 3段階のアクセント強度
ACCENT_STRENGTH = {
    '[1': 'weak_rise',
    '[2': 'medium_rise', 
    '[3': 'strong_rise',
    ']1': 'weak_fall',
    ']2': 'medium_fall',
    ']3': 'strong_fall',
}
```

**ファイル**:
- `src/python/piper_train/phonemize/japanese.py`
- `src/python/piper_train/phonemize/jp_id_map.py`

#### 2-2. 質問文検出の改善（実装時間：1-2時間）
**期待効果**: MOS +0.02-0.03

**実装内容**:
- 質問タイプの詳細判定（Yes/No、WH、修辞疑問）
- 文末パターンの拡張
- イントネーションマークの使い分け

**ファイル**:
- `src/python/piper_train/phonemize/japanese.py`

### 3. 本格的な新機能（2週間以内）

#### 3-1. F0予測器統合（実装時間：3-5日）
**現状**: `f0_predictor.py`は実装済みだが未統合

**期待効果**: MOS +0.10（最大の改善）

**実装内容**:
- VITSモデルへのF0予測器統合
- 損失関数の追加
- プロソディ情報との連携

**ファイル**:
- `src/python/piper_train/vits/f0_predictor.py`（作成済み）
- `src/python/piper_train/vits/models.py`（修正必要）
- `src/python/piper_train/vits/lightning.py`（修正必要）

#### 3-2. Transformerブロック追加（実装時間：1週間）
**期待効果**: MOS +0.06-0.08

**実装内容**:
- テキストエンコーダーへの軽量Transformer追加
- 長期依存性のモデリング改善
- 文脈を考慮した韻律生成

**ファイル**:
- `src/python/piper_train/vits/modules.py`（新規追加）
- `src/python/piper_train/vits/models.py`（修正必要）

## 実装スケジュール案

### Phase 1: Quick Wins（1週間）
1. **Day 1-2**: AccentProcessor統合
2. **Day 3-4**: アクセント強度レベル実装
3. **Day 5**: 質問文検出改善
4. **Day 6-7**: EMA実装とテスト

**期待効果合計**: MOS +0.13-0.21

### Phase 2: Major Features（2週間目）
1. **Week 2 前半**: F0予測器統合
2. **Week 2 後半**: Transformerブロック実装

**期待効果合計**: MOS +0.16-0.18

### 総合効果
- **実装済み（gin_channels）**: MOS +0.04-0.06
- **Phase 1完了時**: MOS +0.17-0.27
- **Phase 2完了時**: MOS +0.33-0.45

## 実装優先順位の根拠

### 最優先：既存コンポーネントの活用
1. **AccentProcessor**: すでにコード完成、統合のみ
2. **EMA**: すでにコード完成、安定性向上に重要

### 次優先：軽量な改善
3. **アクセント強度**: 既存システムの拡張で実現
4. **質問文検出**: シンプルな実装で効果あり

### 後回し：大規模な変更
5. **F0予測器**: 効果は最大だが統合が複雑
6. **Transformer**: 新規実装が必要

## 実装時の注意点

### ONNX互換性の維持
- すべての改善はONNXエクスポート可能
- Unity Sentis 2.1での動作確認必須

### モデルサイズの管理
- 現在: gin_channels増加で+10MB
- 残り許容量: 約40-50MB
- F0予測器（+50MB）実装時は要注意

### 後方互換性
- 既存モデルとの互換性維持
- フラグによる機能の有効/無効化

## 推奨される次のステップ

1. **即座に開始**: AccentProcessor統合（最もコスパが高い）
2. **並行作業**: EMAとアクセント強度の実装
3. **効果測定**: Phase 1完了後にA/Bテスト実施
4. **判断**: 効果を見てPhase 2の実装可否を決定

これらの改善により、piper-plusは段階的に商用レベルの品質に近づいていきます。
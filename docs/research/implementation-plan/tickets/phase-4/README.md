# Phase 4: PE-A Emotion Loss 学習側統合

| 項目 | 値 |
|------|-----|
| Phase | 4 |
| マイルストーン | [#14](https://github.com/ayutaz/piper-plus/milestone/14) |
| 期日 | 2026-05-02 |
| Claude Code 工数目安 | 1〜2 日 |
| 関連 PR | PR-F (`feat(train): PE-A emotion loss 統合 + CLI + docs`) |
| 依存 Phase | Phase 0 (PE-A loader)、Phase 1 (style_vector conditioning)、Phase 3 (style bank 生成) |
| 後続 Phase | Phase 5 (CREMA-D fine-tune 実験) |

---

## 概要

Phase 4 は PE-A (Perception Encoder Audio-Visual) を使った知覚感情 loss を VITS 学習に統合する。Phase 1 の style_vector 条件付けに加えて、生成音声と target 感情 embedding の距離ベースの 3 項合成 loss を追加する:

- **direction loss**: 生成音声 embedding → target emotion 方向 (global centroid からの変位) との cosine 一致
- **centroid loss**: 生成音声 embedding → target emotion centroid との cosine 類似度 (1 - cos)
- **margin loss**: target centroid と max_other centroid の類似度差分に対する hinge margin (contrastive)

Fork `yusuke-ai/piper-plus` コミット `314b3355` の実装を忠実に移植し、9 個の `--pea-emotion-*` 系 CLI オプションと `lightning.py` の `training_step_g` に loss 合算を追加する。

---

## チケット一覧

| チケット | タイトル | 工数 | 優先度 | 担当ファイル |
|---------|---------|------|-------|-----------|
| [P4-T01](P4-T01-pea-loader-style-bank.md) | PE-A model loader + style bank loader 実装 | 2〜3h | 高 | `perception/pea_loader.py`, `vits/lightning.py` |
| [P4-T02](P4-T02-compute-pea-emotion-loss.md) | `_compute_pea_emotion_loss` 実装 (3項合成) | 2〜3h | 高 | `vits/lightning.py` |
| [P4-T03](P4-T03-training-step-integration.md) | `training_step_g` への loss 合算 + warmup | 2〜3h | 高 | `vits/lightning.py` |
| [P4-T04](P4-T04-cli-pea-emotion-options.md) | CLI オプション 9 個 追加 | 1h | 中 | `__main__.py`, `vits/lightning.py` |
| [P4-T05](P4-T05-pea-emotion-loss-tests.md) | PE-A loss Unit テスト | 1〜2h | 高 | `tests/test_pea_emotion_loss.py` |

**合計工数**: 8〜12h (約 1〜2 日)

---

## 依存関係図

```
Phase 0 (PE-A loader PoC)
     │
     ▼
Phase 3 (style bank 生成) ─── P3-T02 (build_pea_style_bank.py)
     │                              │
     │                              ▼ (style_bank.npz を provide)
     ▼
┌───────────────────────────────────────┐
│  Phase 4                               │
│                                        │
│  P4-T01 (loader)                       │
│     │                                  │
│     ▼                                  │
│  P4-T02 (loss 計算) ──┐                │
│     │                  │               │
│     ▼                  ▼               │
│  P4-T03 (統合)    P4-T04 (CLI)         │
│     │                  │               │
│     └──────┬───────────┘               │
│            ▼                           │
│  P4-T05 (tests)                        │
└───────────────────────────────────────┘
     │
     ▼
Phase 5 (CREMA-D fine-tune 実験)
```

**並列可能**:
- P4-T02 と P4-T04 は独立 (T01 のみに依存)
- P4-T03 と P4-T04 も部分的に並列可能 (T03 は T01/T02 依存、T04 は T01 のみ依存)
- P4-T05 は他すべてが完了後に一括実装

**クリティカルパス**: P4-T01 → P4-T02 → P4-T03 → P4-T05 (合計 7〜11h)

---

## 成功基準

以下をすべて満たせば Phase 4 完了と判定:

- [ ] 1 epoch dry-run (style bank + loss weight=0.1 with warmup=0) で NaN なく完走
- [ ] `--pea-emotion-loss-weight 0.0` (disabled) で Phase 1 時点と基本 loss (loss_fm/mel/kl/gen_adv) が bit-for-bit 一致 (差分 ε 以下)
- [ ] warmup ステップ完了前は `loss_pea_emotion` が wandb に記録されない
- [ ] warmup 完了後に `loss_pea_emotion` が非ゼロ値で wandb に記録される
- [ ] 必須 6 テスト (P4-T05 §1.2) が pass
- [ ] `--help` で 9 個の `--pea-emotion-*` オプションが表示される

---

## 一から考えたら

Phase 4 の設計を白紙から検討するとしたら、以下の問い直しが必要。

### 1. 3 項合成 loss の妥当性 (fork 側の実験的知見への依存)

Fork `314b3355` は direction + centroid + margin の 3 項合成を採用しているが、各項の寄与は未検証:

- **direction only**: 「emotion 間の関係 (global からの相対方向)」のみ学習
- **centroid only**: 「emotion の絶対位置」のみ学習
- **margin only**: contrastive learning style (InfoNCE に類似)

Phase 5 のアブレーション実験で、各項を個別 on/off した A/B テストを実施し、最小構成を確認すべき。3 項すべて必要な根拠は fork の実験的知見のみで、数学的・理論的裏付けは弱い。

**代替案**: 単一 InfoNCE loss で十分な可能性:
```
L = -log(exp(sim(z_hat, c_target) / τ) / Σ_i exp(sim(z_hat, c_i) / τ))
```
temperature τ 1 個のハイパーパラメータで済み、3 weight 調整が不要になる。

### 2. PE-A embedding vs WavLM features vs MFCC (従来手法)

感情表現の抽出には複数選択肢がある:

| 手法 | GPU メモリ | 感情表現の分離 | 実装済み |
|------|---------|-----------|--------|
| **PE-A** (本 Phase) | 500MB-1GB | 高 (想定) | fork 実装のみ |
| **WavLM** | 既存ロード済み | 中 | `WavLMDiscriminator` として既存 |
| **ECAPA-TDNN** | 小 | 中 (話者特徴に偏る) | `src/python/piper_train/speaker_encoder/` で既存 |
| **MFCC** | ゼロ | 低 (音素特徴に偏る) | - |

WavLM を再利用すれば追加 GPU メモリゼロで、既存の `WavLMDiscriminator` と同じモデルインスタンスを使い回せる。ただし感情表現 task では PE-A の方が精度が高い想定 (fork の採用根拠)。Phase 5 で実験的に検証する価値あり。

### 3. Gradient 伝播: PE-A model は凍結するか、end-to-end で fine-tune するか

Fork 実装は PE-A を `requires_grad_(False)` で完全凍結し、DAC (Discrete Audio Codec) の勾配のみ制御する。代替案:

- **完全凍結** (fork): 実装単純、GPU メモリ節約、収束は target centroid の精度に依存
- **LoRA fine-tune**: PE-A を LoRA で VITS 出力分布に適応、収束が早い可能性、実装複雑
- **End-to-end fine-tune**: PE-A パラメータも更新、最も柔軟、GPU メモリ増大、catastrophic forgetting リスク

Phase 4 は完全凍結でスタートし、Phase 5 の結果次第で LoRA を検討するのが現実的。

### 4. loss の重みを固定値 vs dynamic adjustment (例: uncertainty weighting)

Fork 実装は `pea_emotion_loss_weight=0.1` 等の固定値を使用。問題点:

- Loss scale が学習段階で変化 (warmup 中はゼロ、warmup 後は 0.1 相当)
- VITS 本体の loss (`loss_mel ~ 1-10`, `loss_gen_adv ~ 0.1-5`) との相対関係が不定
- Phase 5 のアブレーション実験で最適 weight を手動探索 (Optuna 使用も困難な計算コスト)

**動的調整案**:
- **Uncertainty weighting** (Kendall et al. 2018): 各 loss に学習可能な対数分散パラメータを設け、自動調整
- **GradNorm** (Chen et al. 2018): 各 loss の勾配ノルムを均等化
- **PCGrad** (Yu et al. 2020): 勾配衝突を幾何的に解消

いずれも Phase 4 の範囲外だが、Phase 5 の実験で収束が不安定なら検討する。

### 5. style_vector_dim=0 (emotion 条件なし) でも PE-A loss を適用する意味はあるか

Phase 1 で導入した `style_vector` は推論時の感情条件付け用。Phase 4 の PE-A loss は学習時の感情 supervision のみで、推論時は不要。両者の組み合わせ:

| style_vector_dim | PE-A loss | 用途 |
|----------------|----------|------|
| > 0 | 有効 | 感情条件付け + 感情 supervision (fork 想定、Phase 5 のメインシナリオ) |
| 0 | 有効 | 感情 supervision のみ (副次効果として emotion embedding 学習を誘導) |
| > 0 | 無効 | 感情条件付けのみ (PE-A なしでも style_vector で条件付けは可能) |
| 0 | 無効 | ベース VITS (Phase 0 時点) |

**`style_vector_dim=0` + PE-A loss 有効** のシナリオは直感に反するが、以下の効果が期待できる:
- Hidden state が感情を表現するように誘導される (emergent emotion representation)
- style_vector を追加実装する前の実験段階で、PE-A loss の単独効果を検証できる

Phase 5 の実験設計で、A/B test として `style_vector_dim=0 + PE-A loss=0.1` vs `style_vector_dim=256 + PE-A loss=0.1` を比較することで、style_vector の寄与を分離できる。

---

## Phase 4 実装上の鍵

### 1. hparams snapshot のタイミング

CLAUDE.md の「`--freeze-dp` の hparams snapshot 問題」と同じパターン。`VitsModel.__init__` 内で:

1. `self.save_hyperparameters()` を呼ぶ (すべての __init__ kwargs を snapshot)
2. その後に `self._pea_emotion_model = None` などの runtime state を設定
3. **最後に** `_init_pea_emotion_loss()` を呼ぶ (buffer 登録)

この順序を守らないと、checkpoint restore 時に hparams が再現されず、PE-A loss が誤った weight で計算される。

### 2. register_buffer vs nn.Parameter

Style bank の centroid は **register_buffer** で登録する:

- `register_buffer`: 学習対象外、checkpoint に保存される、device 移動に追従
- `nn.Parameter`: 学習対象、勾配が流れる

Centroid は固定値 (pre-compute 済み) なので buffer が正しい。誤って `nn.Parameter` にすると centroid が学習更新され、PE-A loss の意図が崩れる。

### 3. DAC 勾配制御の副作用

`grad_enabled_embedder_forward` は `torch.cuda.amp.autocast(enabled=False)` と `torch.backends.cudnn.flags(enabled=False)` の 2 重 context で forward を包む。影響:

- **autocast off**: PE-A の forward が FP32 固定、mixed-precision の恩恵を受けられない
- **cudnn off**: 畳み込みの cuDNN 最適化を無効化、速度 -10〜20%

両方とも PE-A 側の量子化層 (DAC) の勾配計算の安定性を優先した設計。学習速度への影響は `every_n_steps 4` で緩和。

### 4. NaN ガードの 2 層防御

PE-A loss は NaN 発生リスクが高い (F.normalize が 0-vector で NaN、初期学習で y_hat が 0 近傍など)。本 Phase では 2 層で防御:

1. **Loss 値レベル** (P4-T02): `_compute_pea_emotion_loss` 内で `torch.isnan(loss).any()` 検査、検出時は `None` を返す
2. **Gradient レベル** (P4-T03): `on_after_backward` hook で全パラメータの grad を検査、検出時は `zero_grad(set_to_none=True)` で全勾配クリア

両層で防御することで、学習停止を回避しつつ問題発生を監視できる。

---

## 学習時パフォーマンス見積もり

| 項目 | 値 | 備考 |
|-----|-----|------|
| PE-A model GPU メモリ | 500MB-1GB | `facebook/pe-av-small` の想定値 |
| PE-A forward 1 回 | ~50ms | V100, batch_size=20, audio_length=1s |
| Per-step オーバーヘッド | ~12.5ms | every_n_steps=4 による平均 |
| Base VITS step 時間 | ~200ms | V100, batch_size=20 |
| 合計速度低下 | ~6% | `(200+12.5)/200 - 1 = 0.0625` |
| cuDNN off 影響 | -10〜20% | PE-A forward 内のみ |

Phase 5 の CREMA-D fine-tune (1〜2 日) に対して 6% のオーバーヘッドは許容範囲。

---

## 参考リンク

### 前提資料
- 実装計画全体: [../README.md](../../README.md)
- Phase 3-4 詳細: [../../phase-3-4.md](../../phase-3-4.md)
- 全体調査: [../../../peav-style-conditioning.md](../../../peav-style-conditioning.md)

### Fork 元
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- Fork コミット: https://github.com/yusuke-ai/piper-plus/commit/314b3355

### 外部リソース
- `facebook/pe-av-small`: https://huggingface.co/facebook/pe-av-small (Apache-2.0)
- Perception Encoder 論文: https://arxiv.org/abs/2512.19687
- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D (ODbL、商用可)

### 本家の関連実装
- `--freeze-dp`: `src/python/piper_train/__main__.py`, `vits/lightning.py`
- `--c-wavlm` / WavLM Discriminator: `vits/models.py` (`WavLMDiscriminator`), `vits/lightning.py`
- `--style-vector-dim` (Phase 1): `vits/models.py`, `vits/lightning.py`

# Zero-Shot TTS 話者再現性向上 — 調査結果レポート

## Context

現在のPiper Plus Zero-Shot TTSは20話者でVITS + CAM++ (192次元) アーキテクチャを使用。
v8学習は話者再現に失敗（dataset.pyのspeaker_embeddings消失・CamPP入力名バグが原因）。
v9再学習のための2件のバグ修正が完了し、v9コマンドが確定済み（v9-training-handoff.md参照）。
さらなる話者再現精度向上のため、最新論文・OSS・コードベースを10エージェントで徹底調査した。

**制約**: モデルサイズ ~74MB ONNX、CPU リアルタイム推論維持

---

## レビュー結果 (3エージェントによる検証済み)

### 修正された誤り

| # | 元の記載 | 修正 |
|---|---------|------|
| 1 | ~~DINO softmax dim=-1はバグ、dim=0が正しい~~ | **dim=-1は正しい** (DINO論文の標準実装) |
| 2 | SEED: 192次元embedding上で動作 | **SEED: 512次元** (nOut=512)。192次元CAM++には要adapt |
| 3 | StyleTTS-ZS CFG amp=1.7倍 | **omega=5** が論文値。1.7は誤記 |
| 4 | CosyVoice 10K+話者 | **話者数は非公開**。170K時間は確認済み |
| 5 | DP g detach: models.py:147 | **実際はline 156** (DurationPredictor), line 65 (SDP) |
| 6 | CLN +332Kパラメータ | **共有bottleneck前提**。素朴実装では~1.2-2.4M |
| 7 | CosyVoice2 "TextEncoder条件付け除去" | **LLMからの除去** (VITSのTextEncoderとは異なる構造) |
| 8 | TiCa: Samsung 2025 | **Interspeech 2023** |

### 重要な追加知見

1. **CFGはDINOと直接競合**: embedding=0にするとDINO teacherのcenter EMAが汚染される。同時使用には設計が必要
2. **SCLは非微分** (`torch.no_grad()`): InfoNCEを追加してもSCLの勾配問題は解決しない
3. **DP g detachは元VITS設計**: 除去はDP崩壊リスクあり。要慎重検証
4. **Phase 1に7変更同時は危険**: ablation不可能。2-3変更ずつ段階投入すべき

---

## 調査結果サマリ: 4カテゴリ

### A. データ・話者多様性（最大インパクト、最優先）

**最重要発見: 20話者は根本的に不足。100話者が最低ライン。**

| # | 施策 | 期待効果 | 工数 | 根拠 |
|---|------|---------|------|------|
| A1 | **JVS/JVNV追加 (100話者)** | +15-25% SECS | 3-5日 | CC BY-SA 4.0、日本語スタジオ品質。要フォーマット変換 |
| A2 | **LibriTTS-R clean-100 (~600話者)** | +10-20% SECS | 3-5日 | 英語phonemizer既存。full版(200GB)は容量不足、clean-100(20GB)を使用 |
| A3 | **Speed perturbation (0.9x-1.1x)** | +5-10% SECS | 1日 | CosyVoice/CAM++標準手法 |
| A4 | **Speaker embedding mixup** | +3-5% SECS | 0.5日 | lam~Beta(2,2)。**注意: 補助lossのみに適用、reconstruction pathには使わない** |
| A5 | **Formant shifting** | +5-10% SECS | 2日 | CAM++がpitch-robust、formantで真の多様性 |

### B. 学習Loss・正則化

| # | 施策 | 期待効果 | 工数 | リスク |
|---|------|---------|------|--------|
| B1 | **InfoNCE対比学習loss** | +5-10% SECS | 3-5日 | batch内5話者で負例少。温度/重みチューニング必要 |
| B2 | **R1勾配ペナルティ** | 安定性改善 | 1日 | d_update_interval=1との相互作用要検証。autocast無効必須 |
| B3 | **VICReg for spk_proj** | +3-5% SECS | 1日 | DINOと相補的 |
| B4 | **Embedding perturbation L2再正規化** | バグ修正 | 0.5日 | **検証済み実バグ** |
| B5 | **Embedding perturbation annealing** | +2-3% SECS | 0.5日 | 0.1→0.02 cosine schedule |
| B6 | **Multi-scale mel SCL** | +2-5% SECS | 0.5日 | FFT 512/1024/2048 |
| B7 | **CFG (Classifier-Free Guidance)** | +5-10% SECS | 3-5日 | **⚠ DINO競合あり。推論2パス必要。ONNX変更必要** |

### C. アーキテクチャ微調整

| # | 施策 | 期待効果 | +パラメータ | ONNX互換 |
|---|------|---------|-----------|---------|
| C1 | **Snake活性化 (Decoder)** | 音質改善 | +1.8K | ✅ sin/pow対応 |
| C2 | **Anti-aliased upsampling** | 音質改善 | 0 | ✅ Resize op |
| C3 | **TextEncoder FiLM化** | +3-5% SECS | +微量 | ✅ |
| C4 | **spk_proj残差接続** | +2-3% SECS | 0 | ✅ |
| C5 | **TextEncoder CLN** | +5-10% SECS | +1.2-2.4M | ✅ layer_norm対応 |
| C6 | **SC-CNN** | +5-10% SECS | +微量 | ✅ VITS検証済み |

### D. 推論時テクニック（学習不要）

| # | 施策 | 期待効果 | 追加レイテンシ |
|---|------|---------|-------------|
| D1 | **複数参照音声平均 (N=3-5)** | +5-15% SECS | 0ms (事前計算) |
| D2 | **参照音声VAD+正規化** | +3-10% SECS | ~30ms |
| D3 | **最適noise_scale探索** | +2-8% SECS | 0ms (事前計算) |
| D4 | **参照音声10-20秒確保** | +2-10% SECS | 0ms |
| D5 | **Robust aggregation (中央値)** | +3-7% SECS | 0ms |

---

## コードベースの検証済みバグ・改善点

### 検証済み実バグ

| # | 問題 | 場所 | 検証結果 |
|---|------|------|---------|
| 1 | **Perturbation後L2未再正規化** | `lightning.py:642-644` | ✅ 確認済み。要修正 |
| 2 | **SCL NaN→loss=0** | `losses.py:79-80` | ✅ 確認済み。エラーをマスク |
| 3 | **TextEncoder additive only** | `models.py:214` | ✅ 確認済み。FiLM化推奨 |
| 4 | **FiLM scale固定[0.5,1.5]** | `models.py:377` | ✅ 確認済み |
| 5 | **Flow WN additive only** | `modules.py:186-197` | ✅ 確認済み |

### 誤判定（バグではない）

| # | 元の指摘 | 実際 |
|---|---------|------|
| 1 | ~~DINO softmax dim~~ | dim=-1は**正しい** (DINO標準) |
| 2 | ~~DP g detach除去~~ | **元VITS設計**。除去はDP崩壊リスク |

---

## 最新論文の注目テクニック

| 手法 | 出典 | 概要 | 適用性 |
|------|------|------|--------|
| **SEED** | Interspeech 2025 | embedding拡散モデル(512次元)。192→512にadapt要 | 中 |
| **DINO-VITS** | Interspeech 2024 | 参照音声ノイズaugmentation (MUSAN 50%) | **高** |
| **SC-CNN** | IEEE SPL 2023 | 話者依存conv kernel。**VITS検証済み** | **高** |
| **StyleTTS-ZS** | NAACL 2025 | CFG (omega=5)。DINO競合に注意 | 中 |
| **F5R-TTS** | arXiv 2025 | RL fine-tuning (GRPO + SIM reward) | 中 |
| **ERes2NetV2** | arXiv 2024 | CAM++後継。同192次元、EER改善。Drop-in交換 | **高** |

---

## 修正済みロードマップ

### Phase 0: v9完了 + ベースライン確立（学習不要）

1. **D1-D5** 推論時テクニック全適用
2. SECS/MCD評価パイプライン構築
3. v9 ベースライン測定（v8は話者再現失敗のため廃棄）

### Phase 1a: バグ修正 + 低リスク改善 (v9a, 2-3変更のみ)

1. **B4** Embedding perturbation L2再正規化
2. **B5** Embedding perturbation annealing (0.1→0.02)
3. **A4** Speaker embedding mixup

→ v9ベースライン比較で効果測定

### Phase 1b: 追加Loss改善 (v9b, 効果確認後)

1. **B1** InfoNCE対比学習loss
2. **B2** R1勾配ペナルティ
3. **B6** Multi-scale mel SCL

→ v9a比較で効果測定

### Phase 2: データ拡充（最大インパクト）

1. **A1** JVS/JVNV追加 (20→120話者)
2. **A3** Speed perturbation
3. **A2** LibriTTS-R clean-100 (cross-lingual)
4. **ERes2NetV2** speaker encoder交換 (検証)

→ 期待: 最大の改善幅

### Phase 3: アーキテクチャ進化

1. **C1** Snake活性化 + **C2** Anti-aliased upsampling
2. **C3** TextEncoder FiLM化
3. **C5** TextEncoder CLN (効果次第)
4. **C6** SC-CNN (実験的)

### Phase 4: 大規模データ + 高度テクニック

1. ReazonSpeech filtered (200-500話者)
2. CFG (DINO競合解決後)
3. RL fine-tuning (F5R-TTS式)

---

## 重要な注意事項

1. **各Phaseは2-3変更ずつ段階投入**し、ablation可能な状態を維持する
2. **各Phase間でSECS測定**して効果を定量的に確認
3. **SCLは非微分** — InfoNCE追加はspk_proj空間での分離に効く（SCLの代替ではない）
4. **SECS評価にCAM++を使う場合**、SCL訓練と同一encoderなので循環的。ERes2NetV2での交差評価を推奨
5. **ディスク容量**: 184GB空き。LibriTTS-Rはclean-100 (20GB)のみ。JVS/JVNV (~60GB) は収容可能
6. **max_epochs=200必須** (メモリフィードバックで検証済み)
7. **d_update_interval=1必須** (メモリフィードバックで検証済み)

---

## 参考文献

- [SEED: Speaker Embedding Enhancement Diffusion (Interspeech 2025)](https://arxiv.org/abs/2505.16798)
- [DINO-VITS: Data-Efficient Zero-Shot TTS (Interspeech 2024)](https://arxiv.org/abs/2311.09770)
- [SC-CNN: Speaker-Conditioned CNN Kernels (IEEE SPL 2023)](https://github.com/hcy71o/SC-CNN)
- [DiffGAN-ZSTTS: Multi-Head Speaker Encoder (Scientific Reports 2025)](https://www.nature.com/articles/s41598-025-90507-0)
- [StyleTTS-ZS: Classifier-Free Guidance (NAACL 2025)](https://aclanthology.org/2025.naacl-long.242/)
- [EMM-TTS / SEALN: Adaptive LayerNorm (arXiv 2025)](https://arxiv.org/abs/2510.11124)
- [F5R-TTS: RL with Speaker Reward (arXiv 2025)](https://arxiv.org/abs/2504.02407)
- [CosyVoice 2: Scalable Streaming (arXiv 2024)](https://arxiv.org/abs/2412.10117)
- [BigVGAN: Snake Activation (NVIDIA, ICLR 2023)](https://github.com/NVIDIA/BigVGAN)
- [ERes2NetV2: Better Speaker Encoder (arXiv 2024)](https://arxiv.org/abs/2406.02167)
- [Information Perturbation for Zero-Shot TTS](https://pmc.ncbi.nlm.nih.gov/articles/PMC10708733/)
- [SLERP Embedding Interpolation (arXiv 2025)](https://arxiv.org/abs/2508.19210)
- [Selective CFG for Zero-Shot TTS (arXiv 2025)](https://arxiv.org/abs/2509.19668)
- [TiCa: Timbre-Cadence Encoder (Interspeech 2023)](https://research.samsung.com/blog/Hierarchical-Timbre-Cadence-Speaker-Encoder-for-Zero-shot-Speech-Synthesis)
- [AdaSpeech: CLN for Custom Voice](https://arxiv.org/abs/2103.00993)
- [YourTTS: VITS Zero-Shot](https://arxiv.org/abs/2112.02418)
- [Speaker Encoder Comparison (TSD 2025)](https://arxiv.org/abs/2506.20190)

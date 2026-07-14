# piper-plus 5 軸改善調査 (2026-07-14)

ユーザー指定の 5 軸 — **①voice cloning 話者類似度 / ②アクセント正確性 (日本語+多言語) / ③明瞭性 (はっきりした発音) / ④学習・推論の高速化 / ⑤メモリ最適化** — について、2024-2026 の文献・実装事例を並列調査し、リポジトリ実装状態監査 (コード実体確認) と突き合わせた統合レポート。

> **位置づけ**: [改善調査 統合レポート 2026-06-15](improvement-survey-2026-06-15.md) (31 アクション) の**補完**。同レポートが厚い領域 (decoder 置換 = A-1/A-4/A-5、量子化一般論 = B-4〜B-7、G2P 言語拡張 = C 系) は重複調査せず、手薄だった軸 (アクセント精度・明瞭性・学習高速化) と、31 アクション以降の新知見 (2026 前半) を埋める。
>
> **調査方法**: Web 調査エージェント 5 並列 (話者類似度 / アクセント / 明瞭性 / 学習速度 / 推論速度) + リポジトリ監査エージェント 1 (file:line 実体確認)。提案が「実装済みか」をコードで検証済み。
>
> **調査日**: 2026-07-14。ブランチ `feat/wavenext-decoder-ablation` (Stage 0 完了時点) のコードを監査対象とした。

---

## 目次

1. [エグゼクティブサマリ (全軸横断 Top 10)](#1-エグゼクティブサマリ-全軸横断-top-10)
2. [実装状態監査 — 提案の前提となる ground truth](#2-実装状態監査--提案の前提となる-ground-truth)
3. [軸①: 話者類似度 (voice cloning)](#3-軸-話者類似度-voice-cloning)
4. [軸②: アクセント正確性](#4-軸-アクセント正確性)
5. [軸③: 明瞭性 (はっきりした発音)](#5-軸-明瞭性-はっきりした発音)
6. [軸④a: 学習高速化・学習時メモリ](#6-軸a-学習高速化学習時メモリ)
7. [軸④b: 推論高速化・ランタイムメモリ](#7-軸b-推論高速化ランタイムメモリ)
8. [統合ロードマップ (Phase 0-3)](#8-統合ロードマップ-phase-0-3)
9. [既存ドキュメントへの訂正・更新事項](#9-既存ドキュメントへの訂正更新事項)
10. [進行中ワークとの関係](#10-進行中ワークとの関係)
11. [参考文献 (一次ソース)](#11-参考文献-一次ソース)

---

## 1. エグゼクティブサマリ (全軸横断 Top 10)

**最大の発見は「作る前に測れ」が 3 軸で同時に成立していること。** 話者類似度は評価バイアス (SCL と同じ encoder で SECS を測っている)、推論速度は FP16 配布の x86 CPU 逆効果疑い、学習速度は真のボトルネック未計測 — いずれも「現状の数字を信じて次の施策を積む」前に計測基盤の整備が必要。

| # | 施策 | 軸 | 期待効果 | コスト | 確度 |
|---|------|----|---------|--------|------|
| 1 | **独立 encoder (WavLM-base-plus-sv) での SECS cross-check** — 現行 0.6879/0.7749 は CAM++ 空間内スコアで過大評価の可能性 | ① | 評価の信頼性確保 (全施策の前提) | **極小** | 高 |
| 2 | **FP32 vs FP16 ONNX の x86 実機 A/B** — sherpa-onnx 実測で Piper medium は FP32 の方が速い (Apple Silicon ですら 8%、非対応 x86 では cast 挿入で最大 4x 遅い報告) | ④b⑤ | CPU 推論 大幅改善の可能性 | **極小** (計測) | 高 (要実測) |
| 3 | **Whisper CER/WER + UTMOS の CI 自動評価ゲート** — 明瞭性/自然性の回帰検知 | ③ | 以降の全品質施策を測定駆動化 | 小 | 高 |
| 4 | **推論時 duration floor (音素長下限)** — stochastic DP の子音潰れ・音素スキップを直接防止 | ③ | 子音明瞭性 高 | **極小** | 高 |
| 5 | **アクセント評価基盤** — accent nucleus accuracy (JSUT ラベル比較) + Joyo-Kanji-Yomi-Benchmark (MIT) の CI 化 | ② | アクセント改善の定量ゲート | 小 | 高 |
| 6 | **ユーザー辞書のアクセント核指定対応** — 現行 CustomDictionary は読み置換のみ。pyopenjtalk の user_dict (CSV アクセント型付き) を露出 | ② | 固有名詞アクセント誤り対策 (要望最多クラス) | 小-中 | 高 |
| 7 | **長さ bucketing sampler** (SpeakerBalancedBatchSampler に統合) — padding 削減 + torch.compile/cudnn.benchmark の形状安定化 | ④a | throughput 1.2-1.5x (未実証) | 中 | 中 |
| 8 | **UTMOS/speechMOS moderate フィルタ + BS.1770 ラウドネス正規化** — データ品質起因の明瞭性改善 (top 80% 選別で WER 20.45→18.79% の実証例) | ③① | 中-高 | 小 | 高 |
| 9 | **speaker encoder A/B (CAM++ → ERes2NetV2)** — Apache-2.0、同 3D-Speaker toolkit で差し替え容易。ただし「SV EER 改善 ≠ TTS SECS 改善」の警告あり、571 話者で実測してから v8 採用判断 | ① | 中 (要実測) | 中 | 中 |
| 10 | **LoRA 話者 FT** — full FT (51 分/927MB ckpt) を rank 8-16 adapter に置換、話者パック数 MB 配布 + FT 高速化 | ① | FT 経路の UX 大幅改善 | 中 | 中 |

**非推奨と確定したもの** (詳細は各軸): ECAPA2 (cc-by-nc-4.0 で商用不可 → §9 訂正)、tdmelodic_openjtalk (非商用)、NHK アクセント辞典 (データ利用不可)、明瞭性目的の 44.1kHz 化 (自然性改善せずコスト大)、VITS decoder の sub-sentence chunk streaming (境界 artifact)、FP8 学習 (A100 非対応)、kNN retrieval TTS / flow matching hybrid (エビデンス不足 or アーキ不適合)。

---

## 2. 実装状態監査 — 提案の前提となる ground truth

改善提案の重複・空振りを防ぐため、コード実体を確認した (2026-07-14、`feat/wavenext-decoder-ablation`)。

### 実装済み (提案から除外すべきもの)

| 機構 | 場所 |
|------|------|
| DINO 自己蒸留 (EMA teacher + center 汚染防御) | `losses.py:89-155`, `lightning.py:929-991` |
| SCL 2 経路 (CAM++ ONNX / mel フォールバック) | `losses.py:68-86,186-263`, `lightning.py:894-927` |
| WavLM disc step gating (loss スケール補正付き) | `lightning.py:994-995,1040-1041` |
| KL annealing (線形 0.1→1.0) | `lightning.py:864-873` |
| d_update_interval | `lightning.py:623-625` (CLI 既定 1) |
| **fused AdamW** (G/D 両方 `fused=cuda`) | `lightning.py:1274-1289` |
| **torch.compile** (`--compile`、model_g/d 全体に reduce-overhead + dynamic=True) | `__main__.py:528-538,829-840` |
| TF32 + cudnn.benchmark (DR-007) / bf16-mixed 既定 (DR-008) | `__main__.py:667-673,413-418` |
| Multi-scale FiLM (zero-init、input-stage + 各 upsample 段) | `mb_istft.py:222-233,245,267-282` |
| SpeakerBalancedBatchSampler (DDP 対応 + 言語均等) | `dataset.py:447-700` |
| decoder-arch tri-state 分類器 (WaveNeXt Stage 0) | `__main__.py:52-103,134-158` |
| **日本語アクセント記号の音素列注入** — `[` (句頭上昇) `]` (核下降) `#` (アクセント句境界) を A1/A2 遷移から規則挿入 (ESPnet `pyopenjtalk_prosody` と同方式) | `japanese.py:185-198` |
| prosody_features A1/A2/A3 (DP 入力) | `japanese.py:33,139,169-176` |

### 未実装 (改善余地が実在するもの)

| 機構 | 備考 |
|------|------|
| InfoNCE / contrastive loss | zero-shot 計画 Tier 2 #7 のまま未着手 |
| R1 gradient penalty | 同 Tier 2 #8。判別器は LSGAN のみ |
| embedding noise スケジュール (cosine) | 固定 σ=0.05 のみ (`lightning.py:795-802`) |
| embedding mixup / multi-scale·delta mel SCL | Tier 2 #11/#12 |
| G/D/spk_proj 別学習率 | G/D は別 optimizer だが同一 lr |
| FiLM 1+tanh / spk_proj 残差·spectral_norm / Snake / TextEncoder pre-attention 条件付け | Tier 3 全滅 (未着手)。条件付けは attention **後** (`models.py:228-230`) |
| SDPA / FlashAttention | attention は手書き matmul (`attentions.py:235-271`)、relative position embedding あり |
| 長さ bucketing | batch 内降順ソートのみ (`dataset.py:383-386`) |
| ONNX 量子化フラグ (`--quantize`) | export_onnx.py に無し |
| VITS 本体の gradient checkpointing | WavLM のみ (`models.py:520`) |
| ユーザー辞書のアクセント核 override | CustomDictionary は読み置換のみ (`japanese.py:23,237-248`) |
| 推論時 duration floor | 無し |

---

## 3. 軸①: 話者類似度 (voice cloning)

### 3.1 【最優先】評価バイアスの解消 — 独立 encoder での SECS cross-check

現行は **SCL の学習信号も SECS 評価も同じ CAM++** を使っている。モデルは CAM++ 空間に最適化されるため、CAM++ で測る SECS は**構造的に過大評価**になる。業界標準の SECS は ERes2Net-large / WavLM-base-plus-sv の 2 系統が主流であり、**学習に使っていない encoder での併記が必須**。

- v7 の 0.6879 (zero-shot) / 0.7749 (Tsukuyomi FT) は「CAM++ 空間内スコア」。WavLM-SV で再計測すると下がる可能性が高い。**v8 の go/no-go 判断や encoder A/B の前に、この基準線を確定させること。**
- 報告プロトコルの落とし穴 ([arXiv:2510.06927](https://arxiv.org/html/2510.06927v1)): (a) SECS は channel/noise に敏感、(b) **0.77 は既に知覚閾域** — 以降の改善は SECS でなく SMOS (人手) で判定すべき、(c) 参照音声を prompt に含めるか除外するかで数値が非互換 (VALL-E は除外 / VALL-E2 は包含)。piper-plus の測定条件を明文化して記録する。
- **推奨レポートセット**: ①CAM++ SECS (継続比較用) ②WavLM-base-plus-sv SECS (バイアス除去) ③SMOS (閾値超え領域) ④測定条件 (prompt 包含/除外・参照長)。
- コスト: 極小 (`compute_secs.py` に encoder を 1 つ足すだけ)。

### 3.2 Speaker encoder の選択肢 (2025-2026)

**前提となる警告**: 「SV encoder の EER が良い = TTS conditioning での類似度が上がる」は**成立しない**。Interspeech 2025 の系統的実験 ([arXiv:2506.20190](https://arxiv.org/html/2506.20190)) で、SV SOTA の ECAPA-TDNN より H/ASP の方が TTS 話者類似度の聴取試験で有意に上 (p<0.001)、x-vector 最下位。**EER だけで採用せず、必ず小規模 A/B (現 571 話者 + 独立 encoder 評価) で実測すること。**

| encoder | dim | Vox1-O EER | ライセンス | ONNX | 判定 |
|---------|-----|-----------|-----------|------|------|
| CAM++ (現行) | 192 | ~0.7% | Apache-2.0 | ○ | baseline |
| **ERes2NetV2** | 192 | 0.61% (full) / 0.98% (3s) | Apache-2.0 (3D-Speaker) | ○ | **第一候補**。同 toolkit・同 API で抽出パイプラインほぼ変更なし。短尺 (3s) に強い = 短い参照音声の zero-shot に効く可能性 |
| ReDimNet2 (B2/B3) | 可変 | 0.29% (B6) | **MIT** (PalabraAI) | ○ (WeSpeaker export) | 第二候補。次元変更時は 497k 個の事前計算 embedding 再生成 + spk_proj 入力次元変更が必要 |
| WeSpeaker ResNet34 | 256 | 0.3-0.8% | CC-BY-4.0 / Apache-2.0 | ○ (HF 直配布) | 要 attribution |
| **ECAPA2** | 192 | SOTA 級 | **cc-by-nc-4.0** | 非公式のみ | **❌ 商用不可 → 除外** (§9 訂正参照) |

- 差し替えコスト: embedding 再抽出 (497k utterance、GPU 数時間) + A/B 学習。ERes2NetV2 なら 192-dim のため spk_proj / ONNX contract 無変更。
- 一次ソース: [ERes2NetV2 (arXiv:2406.02167)](https://arxiv.org/abs/2406.02167) / [3D-Speaker (arXiv:2403.19971)](https://arxiv.org/html/2403.19971v3) / [ReDimNet2 (MIT)](https://github.com/PalabraAI/redimnet2)

### 3.3 参照音声エンコーディングの高度化 (中期)

- **Multi-level 話者表現 (global timbre + temporal style)** — [arXiv:2501.08566](https://arxiv.org/html/2501.08566v1) が直接のテンプレ: 固定 SV encoder (global timbre) + trainable mel encoder (pitch/duration/energy = temporal style) を **AdaIN** で decoder 注入。**non-AR single-pass / 22.5M params / CPU RTF 0.13 / SIM 0.73** と piper-plus と同クラスで実証済み。AdaIN は affine 変換なので ONNX export も問題なし。FiLM との統合/置換の設計判断が必要。期待効果: 中-大 (timbre/prosody 分離)。コスト: 中。
- **XTTS Perceiver / IndexTTS Conformer の full 移植は不適合** — cross-attention 条件付けは single-pass FiLM と ONNX 静的形状を壊す。縮退版 (CAM++/ERes2NetV2 の frame-level 出力への軽量 attention pooling → global embedding の質改善に閉じる) なら可。
- **複数参照音声の重み付き平均** — 計画済みの単純平均の上位互換 (品質/長さで重み付け)。低コスト。

### 3.4 学習 loss (2024-2026 の新知見)

- **DINO-VITS ([arXiv:2311.09770](https://arxiv.org/html/2311.09770v3)) は現行実装の裏付け** — piper-plus の DINO + SCL 構成はこの論文と同型。現行維持が正しい。
- **Data-level 自己蒸留** (2501.08566) — teacher が「同一内容・別話者」の parallel data を生成し、student に content/speaker 分離を強制。現行 DINO (表現蒸留) と**相補的**。効果中-大だがコスト大 (teacher 学習 + 生成の 2 段)。中期。
- **Flow matching の VITS prior への部分投入は見送り** — 直接エビデンスなし。full flow-matching 系は別アーキ (06-15 レポート A-4 の議論と同じ結論)。
- Tier 2 計画済み (InfoNCE / R1 / noise schedule / mixup / multi-scale SCL) は引き続き有効。§2 の通り全て未実装なので v8 学習前に投入判断。

### 3.5 LoRA 話者 FT (FT 経路の刷新)

- **LoRP-TTS ([arXiv:2502.07562](https://arxiv.org/html/2502.07562v1))**: LoRA (rank=16, α=16) を dense 層に挿入 (+2.3% params)、**100 step・参照 1 発話**で話者類似度 +30pp。
- piper-plus 適用像: spk_proj / FiLM / decoder の一部にだけ LoRA を当て、**話者パックを adapter 差分 (数 MB) で配布**。ONNX へは merge して export するため**全 7 ランタイム無変更**。現行 full FT (51 分 / ckpt 927MB) の UX を大幅改善。
- 注意: rank を上げすぎる (64) と話者適応能力が落ちる報告あり → **rank 8-16**。
- これは FT 経路の改善であり zero-shot SECS 自体は上げない。

### 3.6 データスケーリング (v8 の妥当性確認)

- **話者数 > 話者あたり発話数** が zero-shot 汎化の支配要因 (複数ソースで一貫)。**v8 の 571→3,250 話者拡大は方向として正しい**。
- 総データ量は逓減 (10k vs 50k utterance で SECS ほぼ同等の ablation あり) → 話者あたり発話は中程度で十分。
- ただし 0.77 (FT) は知覚閾域なので、**v8 の改善判定は SECS 単独でなく SMOS 併用**で行うこと (§3.1)。

---

## 4. 軸②: アクセント正確性

### 4.0 重要な前提 — 「アクセント記号注入」は実装済み

文献調査での最有力手法「OpenJTalk full-context から `[` `]` `#` を規則抽出して音素列に注入 (ESPnet `pyopenjtalk_prosody` / Style-Bert-VITS2 方式)」は、**piper-plus は既に実装済み** (`japanese.py:185-198`、A1/A2 遷移由来)。よって日本語アクセントの残る改善余地は「**入力ラベルの正しさ**」(辞書・推定器) と「**ユーザーによる上書き手段**」「**評価基盤**」に絞られる。

### 4.1 アクセント辞書の現実 (ライセンスで選択肢が狭い)

| 辞書 | ライセンス | 商用 | 判定 |
|------|-----------|------|------|
| naist-jdic (現用、OpenJTalk 同梱) | NAIST BSD-style | ✅ | 継続。複合語・固有名詞・数詞で誤りが集中するのが弱点 |
| UniDic | 版依存 (GPL/LGPL/BSD trilicense) | ⚠️ | 語彙が薄く複合語除外方針。積極採用の理由なし |
| tdmelodic (PKSHA) | コード BSD-3-Clause | ⚠️ | 生成辞書は NEologd 由来語彙。手法 (NN 推定→CSV 生成) の自前再現なら可 |
| **tdmelodic_openjtalk** (sarulab) | **研究目的のみ** | ❌ | **採用不可** |
| **NHK 日本語発音アクセント新辞典** | データ利用/再配布不可 | ❌ | **採用不可** (学習データにも不可) |

**現実解**: naist-jdic ベース + **marine/BERT でオフライン推定したアクセントを自前 CSV として増補** (権利が明確な語彙に限定)。既製の大語彙アクセント辞書に商用フリーの選択肢は存在しない。

### 4.2 ニューラルアクセント推定 — 学習側限定で使う

| 手法 | 精度 | ライセンス |
|------|------|-----------|
| **marine / marine-plus** (Interspeech 2022) | 文単位アクセント正解率 **80.4%** (従来比 +6.67pt)、TTS prosody MOS 4.29 | コード Apache-2.0 / 同梱モデルは JSUT 由来 **CC-BY-SA 4.0** |
| PLM (BERT) + 明示特徴 (Interspeech 2022) | accent nucleus **95.99%** / AP boundary F1 96.30 | 論文手法 |

- **7 ランタイム移植は非現実的** (PyTorch/BERT 依存) — 過去のニューラル G2P 見送り判定 (06-15 G-B4) と同じ。**使い方は 2 つに限定**: (a) **学習データ前処理**でアクセントラベル品質を上げる (pyopenjtalk は v0.3.0+ で `run_marine=True` に対応、marine-plus は pyopenjtalk-plus と同一メンテナ)、(b) オフラインで辞書 CSV を増補し、**生成物 (データ) として全ランタイムに配る** (ZH-EN loanword JSON と同じミラーパターン)。
- 同梱モデルの CC-BY-SA が生成 CSV へ波及するかは配布前に法務確認 (事実データなので通常問題になりにくいが明記)。
- 一次ソース: [marine-plus](https://github.com/tsukumijima/marine-plus) / [Park+ Interspeech 2022](https://www.isca-archive.org/interspeech_2022/park22b_interspeech.html)

### 4.3 ユーザー向けアクセント制御 (要望が多く、業界標準が明確)

現行 CustomDictionary は**表層→読みの置換のみ**で、アクセント核は指定できない。業界標準 (VOICEVOX の辞書登録 UI / AudioQuery 編集) に照らした段階案:

1. **ユーザー辞書 CSV のアクセント型対応** — pyopenjtalk `update_global_jtalk_with_user_dict` (CSV に `2/3` 形式のアクセント型) を CLI/API に露出。データ駆動なので 7 ランタイム parity と相性が良い (C 側は OpenJTalk の user dict 機構をそのまま使える)。**最優先**。
2. `[[ phoneme ]]` インライン記法のアクセント核指定拡張 (例: カタカナ+`'` 記法)。
3. SSML `<phoneme>` のアクセント拡張。
4. VOICEVOX 型 AudioQuery (mora 単位編集 API) は最終段階 (HTTP サーバー経路のみなら parity 負担小)。

### 4.4 中国語・その他言語

- **ZH tone sandhi 3 規則の明示実装**: ①三声連続 (最後以外を二声化)、②「不」(四声前で二声)、③「一」(四声前で二声・他で四声・序数は一声)。pypinyin の補正は不完全。規則ベースなので 7 ランタイム parity 良好。低コスト。
- **ZH 多音字**: pypinyin 単体 ~87%。**g2pW** (Apache-2.0、ONNX 版あり) は SOTA だが BERT 依存 → marine と同様 **Python 学習側限定** (学習データの声調ラベル品質向上に使い、ランタイムには載せない)。
- **FR liaison 後処理規則** — 規則ベース FR の正確性向上の主レバー (決定木/規則でモデル化する先行研究あり)。
- **EN homograph** — 06-15 レポート C-9 (HomoFast 型統計層) と同方向。g2p-en は OOV stress でも崩れるため「1 語 1 主強勢」制約の後処理が有効。
- 一次ソース: [g2pW (arXiv:2203.10430)](https://arxiv.org/abs/2203.10430) / [liaison modeling (Interspeech 2010)](https://www.isca-archive.org/interspeech_2010/pontes10_interspeech.pdf)

### 4.5 アクセント評価基盤 (改善の前にゲートを作る)

| 指標 | 内容 | 備考 |
|------|------|------|
| accent nucleus accuracy / mora accuracy / 文単位 exact match | G2P 出力のアクセントを JSUT 等の公開アクセントラベルと比較 | marine/PLM 論文の標準指標。安価・自動・回帰検知向き |
| **Joyo-Kanji-Yomi-Benchmark** (sbintuitions) | 常用漢字 2,136 字 / 13,095 文、Kana-CER | **MIT、即 CI 採用可** (読み = 多音字評価) |
| PASQA ([arXiv:2606.20137](https://arxiv.org/html/2606.20137)) | アクセント品質の自動評価 (人手と SRCC 0.828) | 合成音声そのもののアクセント評価 |

推奨: ①G2P 段の accent nucleus accuracy を pytest 化 → ②Joyo benchmark を CI に → ③モデル出力は PASQA + 少数専門家評価。

---

## 5. 軸③: 明瞭性 (はっきりした発音)

### 5.1 結論 — モデルより先にデータ品質、その前に評価ゲート

明瞭性の最短経路は学習データの品質改善であり、推論コスト増がゼロ。ただし効果判定のため **Whisper CER/WER ゲートを先に作る**こと。

### 5.2 評価基盤 (CI 自動化)

- **Whisper-large-v3 による合成音声の CER (ja/zh) / WER (en/es/fr/pt)** が業界標準の明瞭性代理指標。固定評価文セット (数字・固有名詞・子音連続を含む) → 合成 → ASR → 前モデル比で悪化したら fail、の回帰ゲート。
- 限界: 低 WER ≠ 完全な明瞭性 (SP-MCQA の指摘 — key-info 精度は別)。**CER/WER (明瞭性) + UTMOS (自然性) の 2 本立て**が実務解。UTMOSv2 は run 間分散が大きいので複数回平均。
- STOI/PESQ は参照必須 + TTS では時間構造が合わず不適。データ前処理の検証専用に限定。
- 一次ソース: [SP-MCQA (arXiv:2510.26190)](https://arxiv.org/html/2510.26190v1)

### 5.3 データ品質 (優先度順)

1. **MOS フィルタリング** — 推奨閾値は「TTS は 4.0 相当・moderate」。**過剰フィルタは逆効果** (top 80% 選別が top 72% を上回る実証)。効果実証例: 上位 80% 選別で UTMOS 3.64→3.80 / **WER 20.45%→18.79%**。
   - v8 の ja (moe-speech-plus) は「MOS floor 0.0、cap 120 の順位付けのみ」というユーザー決定済み方針があるため、**まず既存 571 話者データに遡って UTMOS 分布を可視化し、下位除外の A/B を小規模実験**してから v8 方針に反映するのが筋 (決定の上書きではなく検証)。
2. **BS.1770 ラウドネス正規化** (-23 LUFS、pyloudnorm/MIT で数行) — zero-shot 計画 Tier 4 #23 として計画済み。話者間音量差が揃うと判別器学習が安定し子音エネルギーの一貫性が上がる。
3. **音声修復の非対称性解消** — en は LibriTTS-R (Miipher 修復済み) だが **ja/zh/es/fr/pt は未修復**。Miipher 本体は非公開のため、**DeepFilterNet3 (MIT/Apache-2.0 デュアル、CPU 可) の保守的 denoise** が第一候補。Resemble Enhance (MIT) の enhancer 段は音色を創作し**話者性を変えるリスク**があるため denoise 段のみ。per-utterance speaker embedding の再抽出が必要になる点に注意。
- 一次ソース: [LibriTTS-R (arXiv:2305.18802)](https://arxiv.org/abs/2305.18802) / [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) / [TTSOps (arXiv:2506.15614)](https://arxiv.org/html/2506.15614)

### 5.4 モデル/学習側

1. **推論時 duration floor** — stochastic DP が重要音素に極端に短い duration を割り当てて子音が潰れる問題 (複数論文で実証) への最も直接的な対策。infer 経路に min-duration クランプを足すだけ。**低コスト・高効果**。deterministic DP モード (noise_scale_w=0 相当) の「明瞭性優先モード」提供も同系。
2. **multi-band / multi-resolution discriminator の追加** — 高域エイリアスを判別器が検出して generator に除去させる。**学習時のみで推論不変** = CPU 制約に抵触しない。over-smoothing (L1 mel loss による子音・高域の張り消失) 対策として MPD+MRD 併用が定石。
3. **固定 PQMF の高域ノイズ問題** — MB-iSTFT の固定 pseudo-QMF は**高域に定常ノイズ (スペクトログラム水平線)** を出す既知問題 (44.1kHz 日本語実装で顕在化した報告)。**合成フィルタを学習可能化 (MS-iSTFT 化)** すると解消した報告あり。WaveNeXt ablation で decoder を見直すタイミングと合わせて検討 (§10)。
4. **noise_scale の追加チューニング余地は小** — 現行 0.4/0.5 は元 VITS (0.667/0.8) より既にかなり保守的 = 明瞭性寄り。短文・固有名詞での grid A/B (ゼロコスト) の価値はあるが、本丸は duration 側。
5. **44.1/48kHz 化は明瞭性目的では非推奨** — full-band VITS が 22.05kHz 比で自然性を改善しなかった報告あり。子音弁別は 8kHz 以下が支配的。音質目的で 3 とセットの場合のみ。
6. **軽量 "clear mode"** — Lombard/clear speech の音響特徴 (1-3kHz 増強、話速低下、F0 上昇) のうち、length_scale + gain + 高域 pre-emphasis の後処理で再現できる範囲を推論オプション化する案。フル Lombard スタイル転移は 6 言語分のデータ調達が難で不適合。
- 一次ソース: [SANE-TTS (arXiv:2206.12132)](https://arxiv.org/pdf/2206.12132) / [DP 改善 (arXiv:2406.19243)](https://arxiv.org/pdf/2406.19243) / [MB-iSTFT-VITS 44.1kHz Ja (固定→学習フィルタ)](https://github.com/tonnetonne814/MB-iSTFT-VITS-44100-Ja) / [Revisiting Over-Smoothness (arXiv:2202.13066)](https://arxiv.org/pdf/2202.13066)

---

## 6. 軸④a: 学習高速化・学習時メモリ

### 6.0 前提 — easy win の大半は取得済み

bf16-mixed / TF32 / fused AdamW / torch.compile フラグ / Super-MAS / 事前計算 speaker emb / VAD キャッシュ / WavLM gating は**実装済み** (§2)。文献調査の「積み上げ 3.2x」事例のうち最大寄与 (AMP 2.0x) は取得済みで、残るレバーは中規模。**v8 (A100 80GB) 着手前に 1 回 profile を取り、真のボトルネック (decoder か disc か外部 ONNX 待ちか data か) を確定させるのが全判断の前提** (torch.profiler は常時 ON で iter 20-44% 膨張するので短窓で)。

### 6.1 優先順位

| 施策 | 期待効果 | コスト | リスク | 備考 |
|------|---------|--------|--------|------|
| ① nsys + torch.profiler で 1 回計測 (host-sync / dataloader stall / CAM++ CPU-ORT 待ちの可視化) | 判断材料 | 低 | 低 | `.item()` 系 host-sync が DINO/SCL 集約に潜む可能性 |
| ② **長さ bucketing** を SpeakerBalancedBatchSampler に統合 | 1.2-1.5x (padding 30-70% 削減、VITS 未実証) | 中 | 低 | 話者バランス + 長さ bucket の合成 sampler。cudnn.benchmark / compile の形状安定化という副次効果が大きい |
| ③ **gradient checkpointing (decoder/disc) → batch 拡大** | 実効 1.1-1.4x | 中 | 低 | activation ~3-5x 削減 ≒ 20-30% 低速を batch 2x で上回る (compute-bound 前提)。A100 80GB を埋める |
| ④ torch.compile の適用形態見直し | 1.2-1.8x の可能性 (未実証) | 中 | **高** | 現行 `--compile` は model_g/d **全体**に適用。CAM++/WavLM ONNX 呼び出しで graph break するため、**decoder + MPD/MSD の submodule 単位**適用 + bucketing 後の形状離散化で再コンパイル爆発を抑える方が安全 |
| ⑤ MPD/MSD の warmup ゲート (mel-only で N step → adversarial 投入) | 学習安定 + 早期 step 削減 | 低 | 中 | 20k step 後に disc 投入の実例あり。WavLM gating と同思想の拡張 |
| ⑥ d_update_interval=2 の A/B | G 実効 step 増 | 極小 | 中 | 更新比に普遍最適はない (データ依存)。品質 A/B 必須 |

### 6.2 見送り / 条件付き

- **SDPA/FlashAttention 化**: relative position bias があるため Flash パス不可 (memory-efficient backend に bias テンソルを渡す形なら可能だがメモリ削減が主)。phoneme 系列は ≤400 と短く、ボトルネックは decoder/disc 側 → **全体への効果は数%未満、優先度低**。
- **DDP static_graph 化**: WavLM gating / d_update_interval で used/unused パラメータ集合が step 間変動するため**現行設計では不可**。gating を「forward は毎回、loss 係数 0」に変えれば道が開けるが要設計変更。
- **8-bit optimizer (bitsandbytes、MIT)**: A100 80GB では通常不要。超大 batch を狙う時のみ。GAN では数値安定性に注意。
- **FP8**: **A100 非対応** (Hopper/Blackwell 専用)。音声 GAN での実証例も未見。v8 環境では対象外。
- **channels_last**: 4D 画像専用、1D 音声 conv には非適用。
- **WaveNeXt ablation 特有**: decoder 差し替え実験では **text encoder / posterior / flow を凍結し decoder + disc のみ学習する部分転移**で収束を大幅短縮できる可能性 (vocoder 転移の先行研究あり、[arXiv:2508.17874](https://arxiv.org/html/2508.17874v1))。
- 一次ソース: [state of torch.compile 2025-08](https://blog.ezyang.com/2025/08/state-of-torch-compile-august-2025/) / [dynamic bucket sampler (arXiv:2503.05931)](https://arxiv.org/pdf/2503.05931) / [PyTorch 3x 実測ブログ](https://arikpoz.github.io/posts/2025-05-25-speed-up-pytorch-training-by-3x-with-nvidia-nsight-and-pytorch-2-tricks/)

---

## 7. 軸④b: 推論高速化・ランタイムメモリ

> decoder アーキ置換 (WaveNeXt / iSTFTNet2-MB / Matcha 等) と量子化一般論・モバイル EP・WebGPU は調査済みのため除外 ([improvement-survey-2026-06-15](improvement-survey-2026-06-15.md) B 系 / [wavenext-decoder-ablation](../design/wavenext-decoder-ablation/README.md))。本節はそれ以外の新規論点。

### 7.1 【最重要・新規】FP16 デフォルト配布の x86 CPU 逆効果疑い

piper-plus は FP16 ONNX (~38MB) を既定配布しているが、**ネイティブ FP16 非対応 CPU (AVX512-FP16 未満の大半の x86) では ORT が層ごとに Cast ノードを挿入し FP32 より遅くなる**:

- sherpa-onnx 実測 (Piper medium ≈ piper-plus 同型アーキ、Apple Silicon / 1 thread): **FP32 RTF 0.114 < FP16 0.123 < INT8 0.320**。ネイティブ FP16 がある Apple ですら FP16 が 8% 遅い。
- x86/ARM の非対応環境では **cast だけで全推論時間の 53.95%、FP16 が FP32 の 4x 遅い**報告 (ORT issue #25824 / #16778)。CPU の MatMul/Conv カーネルが MLFloat16 未実装のため。**ORT 1.26 でも未修正**。
- MB-iSTFT decoder は Conv/ConvTranspose/MatMul 主体で、まさにこのペナルティを受ける層構成。

**推奨アクション**: ①canonical 環境 (Xeon E5-2650 v4) で FP32/FP16 の p50 A/B (README ベンチの再検証を兼ねる) → ②悪化が確認されたら「CPU ターゲット = FP32 既定、FP16 は GPU/Apple 向け asset」への配布方針転換、または最低限 docs で `--no-fp16` を強く案内。**モデル asset の選択なので 7 ランタイムに一括で効く**。
なお WaveNeXt ablation の速度比較 (04-pre-stage0 の PoC) も FP16/FP32 どちらで測ったかで結論が変わり得るため、canonical 実測時に条件を明記すること。

- 一次ソース: [sherpa-onnx PR#2460](https://github.com/k2-fsa/sherpa-onnx/pull/2460) / [ORT issue #25824](https://github.com/microsoft/onnxruntime/issues/25824) / [issue #16778](https://github.com/microsoft/onnxruntime/issues/16778)

### 7.2 低コストの session/graph 設定

- **スレッド設定の明示**: `execution_mode=SEQUENTIAL` / `inter_op_num_threads=1` / `intra_op=物理コア数` を ort-session-contract.toml に明記 (現 contract は intra 中心)。近年の ORT は `OMP_NUM_THREADS` を無視することがあるため session 設定必須。p50 だけでなく p95 でスイープ。
- **batch 次元の 1 固定**: `AddFreeDimensionOverrideByName` (session option、**再 export 不要**) で shape 推論が確定し fusion/kernel 選択が改善。時間軸は可変のまま。
- **`.opt.onnx` キャッシュの徹底確認**: ロード時に `GraphOptimizationLevel=DISABLE_ALL` まで下げているか (最適化を毎回かけていると意味半減)。
- **IOBinding は CPU では投資不要** (GPU の H2D/D2H 回避が主目的)。

### 7.3 メモリフットプリント (サーバー/WebUI 常駐向け)

- 複数モデル常駐時: **shared arena allocator** / **PrePackedWeightsContainer** (session 間で prepack 済み重み共有) / 外部データ mmap。単発 CLI では効果薄、OpenAI 互換 API・WebUI・Wyoming で効く。
- **memory arena shrinkage** (run option): 発話長で確保がぶれて RSS が膨らむ長時間常駐サーバーのみ。常時 ON は非推奨。
- ORT 1.26 の `.ort` mmap ロード / Arm64 BF16 fast-math conv は bump だけで恩恵 (ARM サーバーは BF16 export も検討余地)。

### 7.4 WASM 限定の INT8 variant

- native CPU では INT8 dynamic が FP32 の 2.8x 遅い (7.1 の表) 一方、**WASM は SIMD の int8 パック演算で INT8 が FP32 の 2-3x 速い** (Kokoro-ONNX は fp32/fp16/q8/q4 のマルチ配布を採用)。→ **JS-WASM ランタイム限定で q8 variant を追加配布**する価値あり。品質検証 (06-15 B-5 の測定スイート) とセットで。
- 一次ソース: [Kokoro ONNX 量子化解説](https://www.adrianlyjak.com/p/onnx/)

### 7.5 ストリーミング

- **VITS の sub-sentence chunk streaming は見送り** — 非自己回帰なので原理上可能だが、チャンク境界 artifact + PQMF/iSTFT 受容野の問題。sherpa-onnx / piper1-gpl / KittenTTS いずれも VITS 系では実装していない (chunk streaming は AR/codec 系の技術)。
- 代替: **text_splitter に「最初のセグメントを短くする」ヒューリスティック** (最初だけ読点等で早期 flush) で体感 TTFB を下げる。低コストだが 7 ランタイム同期が必要 (text-splitter-contract 改定)。

---

## 8. 統合ロードマップ (Phase 0-3)

### Phase 0: 計測基盤 (全ての前提、1-2 週間)

1. WavLM-base-plus-sv SECS cross-check を `compute_secs.py` 系に追加、v7/FT の基準線を再確定 (§3.1)
2. Whisper CER/WER + UTMOS の自動評価スクリプト + CI 回帰ゲート (§5.2)
3. accent nucleus accuracy (JSUT) + Joyo-Kanji-Yomi-Benchmark の CI 化 (§4.5)
4. FP32 vs FP16 の canonical Xeon A/B (§7.1)
5. 学習 profile 1 回 (nsys + torch.profiler 短窓) (§6.1-①)

### Phase 1: 低コスト・即効 (数日〜)

- 推論時 duration floor + noise_scale_w grid A/B (§5.4-1)
- BS.1770 ラウドネス正規化を前処理に追加 (§5.3-2)
- ORT スレッド設定明示 + batch 次元固定 + `.opt.onnx` ロード径路確認 (§7.2)
- ZH tone sandhi 3 規則 (§4.4)
- ユーザー辞書アクセント型対応 — まず Python で PoC (§4.3-1)
- first-segment-short ストリーミング (§7.5)

### Phase 2: 中コスト (v8 前後に判断、数週間)

- **v8 学習前**: ERes2NetV2 A/B (571 話者 + 独立 encoder 評価) (§3.2) / UTMOS フィルタの遡及 A/B (§5.3-1) / Tier 2 loss (InfoNCE / R1 / noise schedule) の投入判断 / 長さ bucketing sampler (§6.1-②) / gradient checkpointing + batch 拡大 (§6.1-③)
- **学習時のみ (推論不変)**: multi-band discriminator 追加 (§5.4-2) / MPD-MSD warmup ゲート (§6.1-⑤)
- **データ**: ja/zh/es/fr/pt への DeepFilterNet denoise (emb 再抽出とセット) (§5.3-3) / marine-plus 前処理でアクセントラベル品質向上 (§4.2)
- **配布**: WASM q8 variant (§7.4)
- LoRA 話者 FT (§3.5)

### Phase 3: 高コスト・要判断 (中期)

- multi-level 話者表現 (temporal style encoder + AdaIN) (§3.3)
- MS-iSTFT 学習可能フィルタ化 — WaveNeXt ablation の結論と合わせて decoder 方針を一本化 (§5.4-3, §10)
- torch.compile の submodule 適用 A/B (bucketing 完了後) (§6.1-④)
- サーバー常駐メモリ最適化 (shared arena / PrePacked) (§7.3)
- Data-level 自己蒸留 (§3.4)
- アクセント編集 API (AudioQuery 型) / SSML アクセント拡張 (§4.3)

---

## 9. 既存ドキュメントへの訂正・更新事項

本調査で判明した、既存ドキュメントの要更新点:

| ドキュメント | 訂正内容 |
|--------------|---------|
| [improvement-survey-2026-06-15](improvement-survey-2026-06-15.md) **A-6 (ECAPA2)** | ECAPA2 の公開重みは **cc-by-nc-4.0 (非商用)** — 「条件付き検討」から**除外**へ格下げすべき。代替は ERes2NetV2 (Apache-2.0) / ReDimNet2 (MIT) (§3.2) |
| [zero-shot-quality-improvement-plan](../design/zero-shot-quality-improvement-plan.md) **§4 評価パイプライン** | SECS を CAM++ (=SCL と同一 encoder) で測る設計はバイアスあり。独立 encoder 併記を必須化 (§3.1)。また SECS 0.77 超は知覚閾域のため SMOS 併用を明記 |
| 同 **Tier 3 #16 (Snake)** | Snake + anti-aliasing up/down sampling は CPU 推論コスト増のため、generator 側は不適合寄り。判別器側 (multi-band disc) で高域品質を取る方が制約適合 (§5.4-2) |
| CLAUDE.md / README のベンチ表 | FP16 既定配布の前提が x86 CPU で崩れている可能性 (§7.1)。canonical A/B 後に配布方針・ベンチ値を再確認 |
| [wavenext-decoder-ablation/04](../design/wavenext-decoder-ablation/04-pre-stage0-verification.md) | 速度 PoC の FP16/FP32 測定条件を明記すべき (§7.1 の cast 問題が比較結果を歪め得る) |

---

## 10. 進行中ワークとの関係

| ワーク | 本調査との接続 |
|--------|----------------|
| **v8 話者スケーリング** (docs/design/zero-shot-v8-dataset-scaling-plan.md — **注: 2026-07-14 時点で dev 未コミット**) | 話者数優先の方針は文献と整合 (§3.6)。着手前に Phase 0 の評価基盤 (特に独立 SECS) と encoder A/B (§3.2)、Tier 2 loss 投入判断を済ませるのが理想。学習効率は bucketing + checkpointing (§6) が直接効く |
| **WaveNeXt decoder ablation** (feat/wavenext-decoder-ablation、Stage 0 完了) | Stage 1 の学習は部分転移 (encoder 凍結) で短縮可能 (§6.2)。速度比較は FP16/FP32 条件を固定 (§7.1)。decoder を触るなら MS-iSTFT 学習可能フィルタ化 (§5.4-3) も同じ土俵で比較する価値あり |
| **PR #567** (istftnet2-mb / fly-tts スケルトン) | decoder 系譜は 06-15 レポート A-1 系。本調査は decoder 置換を重複調査していない |
| **PR #355** (感情条件付き TTS) | §5.4-6 の "clear mode" は style vector とは直交 (軽量後処理)。Lombard スタイル転移をやるなら #355 の style 経路が受け皿になり得る |
| **PR #386** (Hardware EP) | §7 の session 設定 / FP32-FP16 asset 選択は EP 選択と直交、契約 (ort-session-contract) 側で統合 |

---

## 11. 参考文献 (一次ソース)

### 話者類似度

- [SV encoder と TTS 類似度の乖離 (arXiv:2506.20190)](https://arxiv.org/html/2506.20190) — Interspeech 2025
- [ERes2NetV2 (arXiv:2406.02167)](https://arxiv.org/abs/2406.02167) / [3D-Speaker toolkit (arXiv:2403.19971)](https://arxiv.org/html/2403.19971v3)
- [ReDimNet2 (MIT)](https://github.com/PalabraAI/redimnet2) / [ECAPA2 (cc-by-nc-4.0)](https://huggingface.co/Jenthe/ECAPA2)
- [軽量 self-distilled disentanglement TTS (arXiv:2501.08566)](https://arxiv.org/html/2501.08566v1) — multi-level 話者表現 + AdaIN、CPU RTF 0.13
- [DINO-VITS (arXiv:2311.09770)](https://arxiv.org/html/2311.09770v3) — 現行実装の裏付け
- [LoRP-TTS (arXiv:2502.07562)](https://arxiv.org/html/2502.07562v1) — LoRA 話者適応
- [Responsible TTS Evaluation (arXiv:2510.06927)](https://arxiv.org/html/2510.06927v1) — SECS 報告プロトコル
- [XTTS (arXiv:2406.04904)](https://arxiv.org/html/2406.04904v1) — Perceiver reference encoder (不適合判定の根拠)

### アクセント

- [marine-plus (Apache-2.0)](https://github.com/tsukumijima/marine-plus) / [Park+ Interspeech 2022 (marine)](https://www.isca-archive.org/interspeech_2022/park22b_interspeech.html)
- [PLM ベースアクセント予測 (ar5iv 2201.09427)](https://ar5iv.labs.arxiv.org/html/2201.09427)
- [tdmelodic (BSD-3, PKSHA)](https://github.com/PKSHATechnology-Research/tdmelodic) / [tdmelodic_openjtalk (非商用)](https://github.com/sarulab-speech/tdmelodic_openjtalk)
- [naist-jdic (BSD-style)](https://github.com/jpreprocess/naist-jdic) / [OpenJTalk](https://open-jtalk.sourceforge.net/readme_open_jtalk.php)
- [ESPnet pyopenjtalk_prosody 実装](https://github.com/espnet/espnet/blob/master/espnet2/text/phoneme_tokenizer.py) / [Kakegawa+ Interspeech 2021 (アクセント記号入力)](https://www.isca-archive.org/interspeech_2021/kakegawa21_interspeech.html)
- [g2pW (Apache-2.0, arXiv:2203.10430)](https://arxiv.org/abs/2203.10430)
- [Joyo-Kanji-Yomi-Benchmark (MIT)](https://github.com/sbintuitions/Joyo-Kanji-Yomi-Benchmark) / [PASQA (arXiv:2606.20137)](https://arxiv.org/html/2606.20137)
- [FR liaison モデリング (Interspeech 2010)](https://www.isca-archive.org/interspeech_2010/pontes10_interspeech.pdf)

### 明瞭性

- [LibriTTS-R / Miipher (arXiv:2305.18802)](https://arxiv.org/abs/2305.18802) / [Miipher-2 (arXiv:2505.04457)](https://arxiv.org/html/2505.04457v4)
- [DeepFilterNet (MIT/Apache-2.0)](https://github.com/Rikorose/DeepFilterNet) / [Resemble Enhance (MIT)](https://github.com/resemble-ai/resemble-enhance)
- [TTSOps corpus 最適化 (arXiv:2506.15614)](https://arxiv.org/html/2506.15614) / [Confidence-based Filtering (arXiv:2601.12254)](https://arxiv.org/pdf/2601.12254)
- [EBU R128](https://tech.ebu.ch/docs/r/r128.pdf)
- [Revisiting Over-Smoothness (arXiv:2202.13066)](https://arxiv.org/pdf/2202.13066)
- [SANE-TTS (arXiv:2206.12132)](https://arxiv.org/pdf/2206.12132) / [DP 改善 (arXiv:2406.19243)](https://arxiv.org/pdf/2406.19243) / [Aligner-Guided Training (arXiv:2412.08112)](https://arxiv.org/pdf/2412.08112)
- [MB-iSTFT-VITS (arXiv:2210.15975)](https://arxiv.org/pdf/2210.15975) / [44.1kHz Ja 実装 (学習可能フィルタ)](https://github.com/tonnetonne814/MB-iSTFT-VITS-44100-Ja) / [BigVGAN (arXiv:2206.04658)](https://arxiv.org/pdf/2206.04658)
- [SP-MCQA (arXiv:2510.26190)](https://arxiv.org/html/2510.26190v1) / [ESPnet2-TTS full-band 検証 (arXiv:2110.07840)](https://arxiv.org/pdf/2110.07840)
- [Lombard style embeddings (arXiv:2601.12966)](https://arxiv.org/abs/2601.12966) / [vocal effort 制御 (arXiv:2606.23176)](https://arxiv.org/pdf/2606.23176)

### 学習高速化

- [state of torch.compile (ezyang, 2025-08)](https://blog.ezyang.com/2025/08/state-of-torch-compile-august-2025/)
- [PyTorch Dynamic Shapes](http://docs.pytorch.org/docs/main/user_guide/torch_compiler/torch.compiler_dynamic_shapes.html) / [SDPA tutorial](https://docs.pytorch.org/tutorials/intermediate/scaled_dot_product_attention_tutorial.html)
- [dynamic bucket sampler (arXiv:2503.05931)](https://arxiv.org/pdf/2503.05931)
- [GAN 更新比 (arXiv:2006.06900)](https://arxiv.org/pdf/2006.06900) / [disc 遅延投入 (arXiv:2509.02244)](https://arxiv.org/pdf/2509.02244) / [vocoder 転移 disc (arXiv:2508.17874)](https://arxiv.org/html/2508.17874v1)
- [bitsandbytes (MIT)](https://huggingface.co/docs/bitsandbytes/optimizers) / [Lightning DDP discussion #6761](https://github.com/Lightning-AI/pytorch-lightning/discussions/6761)
- [3x 高速化実測ブログ (nsight + PyTorch2)](https://arikpoz.github.io/posts/2025-05-25-speed-up-pytorch-training-by-3x-with-nvidia-nsight-and-pytorch-2-tricks/) / [ARGUS profiler オーバーヘッド (arXiv:2606.20374)](https://arxiv.org/pdf/2606.20374)

### 推論高速化

- [sherpa-onnx PR#2460 (Piper FP32/FP16/INT8 実測)](https://github.com/k2-fsa/sherpa-onnx/pull/2460)
- [ORT FP16 CPU cast 問題 #25824](https://github.com/microsoft/onnxruntime/issues/25824) / [#16778](https://github.com/microsoft/onnxruntime/issues/16778)
- [ORT v1.26.0 release](https://github.com/microsoft/onnxruntime/releases/tag/v1.26.0) / [ORT threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html) / [ORT memory tuning](https://onnxruntime.ai/docs/performance/tune-performance/memory.html)
- [make_dynamic_shape_fixed](https://onnxruntime.ai/docs/tutorials/mobile/helpers/make-dynamic-shape-fixed.html) / [graph optimizations (offline)](https://onnxruntime.ai/docs/performance/model-optimizations/graph-optimizations.html)
- [Kokoro ONNX 量子化 (WASM q8)](https://www.adrianlyjak.com/p/onnx/) / [KittenTTS #40 (Piper より遅い)](https://github.com/KittenML/KittenTTS/issues/40)

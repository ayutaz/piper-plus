# 04. Stage 0 着手前検証結果 (pre-Stage 0 verification)

> **実施日**: 2026-07-14
> **手段**: ultracode workflow (run `wf_5f1094ad-ed9`、15 agents = 調査 8 + ローカル PoC 1 + adversarial verify 5 + 統合 1、約 32 分)
> **結論**: **Stage 0 は GO**。ただし計画の価値前提に 1 つ重大な下方修正 (速度・サイズ) と 1 つ重大な上方修正 (fixture blocker 撤回) あり。
> **doc 反映**: 本検証で判明した誤り・stale 行番号は README / 01 / 02 / 03 に反映済み (§7 正誤表参照)。

---

## TL;DR

1. **Stage 0 (tri-state 化 + `--decoder-arch` factory) は着手可** — blocker の実在・発火経路・互換 wrapper 設計・v8 先行適用可能性まで verify 済み。着手を妨げる未知は残っていない。
2. **速度前提が反転 (最重要)**: ORT session contract 準拠 (intra=4 threads) のローカル実測で **WaveNeXt v1 は MB-iSTFT 比 30-40% 遅い** (2 回独立再現)。「+10-15% 高速」「配布サイズ 5-10% 縮小」(02 doc 旧 M1/M2) は撤回。decoder 単体 param は **8.57x 増** (1.65M → 14.12M)、ONNX fp32 は **8.5x 増** (6.3MB → 53.8MB)。
3. **Stage 1 の主目的を再定義**: 「CPU 速度 win」→「**bf16 安定化 + iSTFT/PQMF/complex トリック ~630 行撤去の保守性 + WaveNeXt 2 への足場 + canonical 環境 (Xeon) での速度白黒付け**」。
4. **fixture blocker (旧 D8 medium) は誤りと確定**: parity gate は informational (全 7 job continue-on-error)、opt-in 追加なら**既存 fixture 再生成ゼロ**。「24 個再エクスポート + CI 1-2 週間赤化」は完全置換時のみの話。Stage 1-2 のリスクはむしろ下がった。
5. Unknown **#1/#2/#3 は机上解消**、**#4/#7/#8 は部分解消**。残るは **#5/#6/#9** (学習安定性 / zero-shot SECS / JA-ZH サ行品質) の smoke 学習必須項目のみ。

---

## 1. 検証項目と結果一覧

| # | 項目 | verdict | verify | 要点 |
|---|------|---------|--------|------|
| 1 | WaveFit loss 係数 λ + weight sharing (Unknown #1/#2) | resolved | — | λ セット確定 (§5)。WaveNeXt 2 sub-model は**weight 独立**、headline は **4 sub-models** (3-pass ではない)。「最悪 ~179M」は不成立 |
| 2 | BSC-LT/wavenext-mel byte-compat (warm-start 前提) | resolved | — | **f_max のみ非互換** (8000 vs None→11025)。83 keys / 13.72M params 実測、80/83 転用可。Apache-2.0 確定 |
| 3 | wetdog 実装仕様抽出 | resolved | — | `wetdog/wavenext_pytorch@d45d544` を pin、全ファイル読了。LayerScale init は **1/num_layers=0.125** (1e-6 ではない)、clip(-1,1) は wetdog 独自、MRD は DAC band-split 型 |
| 4 | tri-state 分類器設計 (critical blocker) | resolved | **confirmed** | call site は `__main__.py:479` / `:854` の 2 箇所のみ。マーカー仕様・第 4 状態 (None)・互換 wrapper 確定 (§3)。既存 14 tests 無変更 PASS |
| 5 | loss/discriminator diff 計画 | resolved | — | MRD は repo 不在 (新規実装)。**mel loss 二重化罠** + **mel_processing global cache バグ** を発見 (§6)。SCL/DINO/WavLM の o_mb 非依存を grep 網羅確認 |
| 6 | fixture/CI 影響 (旧 D8 blocker 再評価) | resolved | partially-correct | **opt-in なら既存 fixture 再生成ゼロ** (上記 TL;DR-4)。committed 共有 ONNX は実質 2 種のみ |
| 7 | config.json forward-compat (全 runtime) | resolved | **confirmed** | **全 6+1 runtime lenient** (Rust piper-wasm 経路含む)。`decoder_arch` stamp はゼロリスク。hop_size は全 runtime が config 読み取り済み |
| 8 | opset 15 vs 17 | resolved | partially-correct | **一括 17 bump は撤回** (blocking gate `EXPECTED_TTS_OPSET=15` が確定赤化)。wavenext 分岐のみ opset 17 (§4) |
| 9 | ローカル PoC (export + bench + clip×post-trim) | completed | partially-correct | export/ORT 全成功、parity 1.13e-06。**verify が contract 準拠スレッド設定で速度結論を反転させた** (§2)。clip×post-trim は低リスク確定、残余は head bias floor |

---

## 2. PoC 実測: 速度・サイズの価値前提が反転

### 実測条件

- 環境: AMD Ryzen 9 5900X (12C/24T) / Windows 11 / torch 2.11.0 CPU / ORT 1.26.0
- WaveNeXt v1 (z=192 入力, dim 512 / intermediate 1536 / ConvNeXt×8 / head 1026→256): wetdog 仕様準拠の最小実装
- MB-iSTFT decoder 単体 (quality=medium 実引数、`remove_weight_norm` 済 + `onnx_export_mode=True`)
- z=randn(1,192,200) 固定 seed、warmup 5 + 30 runs、出力 51,200 samples (≈2.32s @22050Hz)
- 成果物: scratchpad `wavenext_poc/` (poc_wavenext.py / bench_rerun.py / results*.json / ONNX ×6)

### 結果

| 指標 | MB-iSTFT (medium) | WaveNeXt v1 | 比 |
|------|-------------------|-------------|-----|
| decoder param 数 | **1,647,752** | **14,124,034** | **8.57x** |
| ONNX fp32 サイズ | 6.30MB (134 nodes) | 53.8MB (op17: 214 nodes / op15: 314 nodes) | **8.5x** |
| ORT optimized nodes | 73 | 89 (op17) / 124 (op15) | — |
| torch↔ORT parity | — | max abs diff **1.13e-06** (op15/17 とも) | — |
| ORT CPU p50 (default threading ~12T) | 34-35ms | 32-33ms (op17) | ほぼ同等 |
| **ORT CPU p50 (contract 準拠 intra=4/inter=1/SEQUENTIAL)** | **29.2ms** | **41.7ms** | **WaveNeXt が 30-40% 遅い** |

- **contract 準拠設定での劣位は adversarial verify が 2 回独立再現** (T=200 / T=60 とも)。piper-plus 実運用は `docs/spec/ort-session-contract.toml` L23-24 で max_intra_threads=4 / SEQUENTIAL を規定しているため、**実運用条件では WaveNeXt が遅い**が正しい読み。default threading での同等は「スレッドを潤沢に使えば MatMul 大行列が並列で回収できる」ことを示すに過ぎない。
- torch CPU の速度方向は run 間ノイズと同オーダーで頑健でない (方向の言及は無意味)。
- paper の「CPU 4x」は WaveNeXt 2 vs **HiFi-GAN** の値。piper-plus は既に HiFi-GAN 比 2.21x の MB-iSTFT なので、この数字は本比較に適用不能 (02 doc 旧 M1 の根本的誤り)。
- 本ベンチはこのマシン内の相対比較のみ有効。**GO/NO-GO の最終速度判定は canonical 環境 (Xeon E5-2650 v4 相当、contract 準拠) での end-to-end 実測待ち** — ただしローカルの負方向 prior は明記した上で臨む。

### export 検証 (op 互換)

- opset 15: LayerNorm×10 が primitive chain に decompose (314 nodes) → ORT が 9/10 を SimplifiedLayerNormalization + BiasGelu×8 に fusion (1 個未 fusion 残存)。**opset 15 のままでも動作する** (PoC 実証)。
- opset 17: native LayerNormalization×10、214 nodes、クリーン。速度差はノイズレベル。
- 使用 op は Conv/MatMul/LayerNorm/Gelu(Erf)/Reshape/Clip/Transpose のみ。動的 T の Reshape も問題なし → 全 runtime 互換の事前調査と整合。

---

## 3. tri-state 分類器 仕様確定 (Stage 0 実装仕様)

verify **confirmed**。03-ablation-plan.md に反映済みの確定仕様:

1. **call site は 2 箇所のみ**: `__main__.py:479` (`load_multispeaker_checkpoint`、無条件) と `__main__.py:854` (trainer.fit 失敗後の graceful-resume fallback 内のみ)。旧 doc の 607/981/1063 は stale。
2. **発火条件の訂正**: 「WaveNeXt ckpt 書き出し瞬間に RuntimeError」ではなく**読み込み時の 2 経路** (`--resume-from-multispeaker-checkpoint` は即時 raise / `--resume_from_checkpoint` は fit 失敗後 fallback でのみ raise)。
3. **マーカーは完全修飾 prefix + 末尾ドット必須**:
   - mb_istft: `startswith(("model_g.dec.subband_conv_post.", "model_g.dec.pqmf.", "model_g.dec.istft."))` を hifigan 判定より**先に**評価
   - wavenext: `startswith(("model_g.dec.convnext.", "model_g.dec.head."))`
   - hifigan: 上記いずれもなく `model_g.dec.ups.` 系が存在
   - **footgun**: `conv_post` は `subband_conv_post` の部分文字列 — substring (`in`) 判定禁止
4. **第 4 状態**: decoder キーが 1 つもない部分 ckpt は `None` を返し raise しない (現行 False 挙動保存、v8 partial-transfer 保護)。
5. hparams タグ `checkpoint["hyper_parameters"].get("decoder_arch")` を優先、state_dict マーカーと矛盾時は warning + タグ採用。
6. bool 互換 wrapper 維持 → 既存 `test_hifigan_ckpt_rejection.py` 12 + `test_export_onnx.py` 1 + `test_python313_migration.py` 1 tests が無変更 PASS。
7. **pqmf 注入 gate は正当性要件 (cleanliness ではない)**: `lightning.py:320` の `self.model_g.dec.pqmf = self.pqmf` は decoder 種別によらず無条件実行される。gate し忘れると WaveNeXt ckpt に `model_g.dec.pqmf.*` buffer が混入 → tri-state fallback が mb_istft 誤分類。Stage 1 テストに「wavenext ckpt に `model_g.dec.pqmf.*` が無い」assert を追加。
8. **WaveNeXt モジュール命名を wetdog/BSC-LT 準拠に pin**: `embed` (Conv1d、`conv_pre` は 3 アーキ衝突で禁止) / `norm` / `convnext` (ModuleList) / `final_layer_norm` / `head`。
9. **factory の `decoder_arch` は default='mb_istft' の keyword 引数必須** — `tests/fixtures/mb_istft_speaker_embedding/build_fixture.py` が 3 CI workflow で `SynthesizerTrn` を直接 instantiate するため、後方互換なしでは即赤化 (逆にこの fixture が factory の無償 smoke test になる)。

---

## 4. opset 方針: 一括 17 bump は撤回

- `scripts/check_onnx_export_contract.py:27` の `EXPECTED_TTS_OPSET=15` ハードコードで **model-quality-gate (blocking) が確定的に赤化**、かつ `onnx-export-contract.toml:116-118` の「opset bump = 全公式 ONNX 再生成 + 全 7 runtime 検証」義務が発火する。これが**本計画で唯一の確定 CI 赤化要因**。
- 対応: **wavenext 分岐のみ opset 17**。新定数は check script の regex `OPSET_VERSION\s*=\s*(\d+)` (re.search) を踏まない命名 (例 `OPSET_VERSION_WAVENEXT`) にするか、contract toml + check script を同 PR 更新。
- opset 17 の rationale は「機能的必然」ではなく「convert_fp16 の LN keep-list safeguard 有効化 + ORT fusion/.opt.onnx キャッシュ非依存化」(opset 15 でも動作自体は PoC 実証済)。
- 互換性: 全 8 runtime pin (min ORT>=1.20、Rust は ort rc.12 の multiversioning + api-24 feature = ORT 1.24 ターゲット) で opset 17 受理を確認済み。既存 opset 15 配布物との**混在可** → 既存モデル再 export 不要。
- Stage 1 テスト: `test_export_onnx_wavenext.py` に「LayerNormalization node ×10 (post-embed 1 + block 8 + final 1) 存在」assert。

---

## 5. WaveFit loss 係数の確定 (Stage 3 用) + WaveNeXt 2 訂正

- **WaveFit は単一 denoiser の weight 共有反復** (WaveGrad Base 13.8M、iteration index t を入力)。venue は **IEEE SLT 2022** (旧 doc の Interspeech 2022 は誤り)。loss 定義の参照先は **§4.2 (定義) / §4.4 (STFT resolution) / §5.1 (λ 値)** — 旧 doc の「§3.3 から逆算必要」は誤ポインタで、**逆算作業自体が不要になった**。
- **WaveNeXt 2 の sub-model は weight 独立**: Table 1 の param が iteration 数に厳密線形 (2/3/4/5 iter = 29.97/44.96/59.94/74.93M = T×~14.99M)。headline 構成 (CPU RTF 0.20 / UTMOS 4.04) は **4 sub-models** — 旧 doc の「3-pass」「最悪 ~179M」は両方誤り。5 iter は UTMOS 向上なしで param のみ増。
- **移植用係数セット (LibriTTS 構成、medium-confidence 推定)**:

| 項目 | 値 |
|------|-----|
| Adversarial | MelGAN MSD×3 (raw / 2x / 4x downsample)、hinge、係数 1.0 基準 |
| Feature matching | λ_FM = 10 |
| MR-STFT (Sc + logMag) | λ_STFT = 2.5、win 360/900/1800 / hop 80/150/300 / fft 512/1024/2048 @24kHz |
| mel-MAE (F=128) | **除外** (LibriTTS 構成) |
| 適用 | 全 T output の 1/T 平均 (G/D とも) |
| WaveNeXt 2 変更 | gain adjustment 削除・初期ノイズ不要 |

- 注意: Stage 1 (Vocos 系 MPD+MRD) と Stage 3 (WaveFit MelGAN MSD×3) は **discriminator セット非互換** — Stage 3 で Stage 1 の D を流用すると paper 再現から乖離する。λ_STFT∈{1, 2.5} の保険 ablation を Stage 3 に 1 本残す。22050Hz 適合時の MR-STFT rescale は paper 外の独自判断。

---

## 6. loss 実装の罠 2 件 (Stage 1 実装者向け)

1. **mel loss 二重化罠**: wetdog の MelSpecReconstructionLoss (128-mel / f_max 11025 / slaney / clamp 1e-5 / L1, coeff 45) を「追加」すると、既存 `loss_mel` (80-mel log-mel L1, `c_mel=45`, `lightning.py:874`) と**二重計上**になる。「維持 or 置換」の明示的設計判断が必要 (03 doc に反映済み)。
2. **mel_processing global cache バグ**: cache キーが fmax のみで **num_mels を無視** → 128-mel 要求時に silent に 80-mel basis が返る。128-mel 採用時は `losses.py:_get_mel_basis` を使用し、`mel_processing.py` の cache 経由は禁止。
3. その他確定事項: MRD は repo 不在 (DAC band-split 型 fft 2048/1024/512 / channels 32 を新規実装)、fullband MR-STFT は既存 `MultiResolutionSTFTLoss` の別サイズ再インスタンスで済む、wetdog は hinge + sub-discriminator 数正規化 (MPD /5、MRD /3) で piper 既存 LSGAN 非正規化和と実効スケールが異なる (一本化 or ablation を Stage 1 の設計判断に)、`configure_optimizers` (`lightning.py:1264-1267`) の d_params と D grad clip (`:693-696`) への mrd 追加要。SCL/DINO/WavLM は全て fullband 波形 or embedding のみ入力で **o_mb/PQMF 非依存を grep 網羅確認済み**。

---

## 7. BSC-LT warm-start の格下げと loader 仕様

- **「byte-compat」は過大主張だった**: n_fft・hop・win・n_mels・f_min・mel scale/norm・log clamp・padding・window は完全一致だが、**f_max が非互換** (BSC-LT 8000 vs piper None→11025、filterbank 実測 diff 0.0265 = 別物) + magnitude epsilon 差 (sqrt(+1e-6))。
- ただし **warm-start 可否の結論は不変**: VITS 統合では mel feature extractor を使わず、embed は 80→192ch でどのみち再初期化。
- `--wavenext-init` loader 仕様 (03 doc 反映済み): (a) `feature_extractor.*` 2 buffer drop、(b) `backbone.embed.weight` (512,80,7) skip → 192ch スクラッチ init、(c) `backbone.convnext.{N}.*` → piper モジュール名リネームマップ。**転送可能 80/83 テンソル**。ckpt は generator のみ (discriminator 含まず) → Stage 1 の MPD/MRD は必ずスクラッチ。
- BSC-LT init の standalone sanity check では piper の `mel_spectrogram_torch` デフォルト (fmax=None) 使用禁止 — f_max=8000/slaney で計算すること。

---

## 8. Unknown #1-9 ステータス (01 doc §5 対応)

| # | Unknown | status | 根拠 |
|---|---------|--------|------|
| 1 | WaveNeXt 2 sub-model weight sharing | ✅ resolved | weight 独立で確定 (Table 1 線形性)。~179M 懸念は不成立 |
| 2 | WaveNeXt 2 損失係数 λ | ✅ resolved | WaveFit §4.2/§4.4/§5.1 で pin (§5 の表)。逆算不要 |
| 3 | 公式コード/重み release | ✅ resolved (リスクとして) | wetdog@d45d544 pin + 全読了、BSC-LT Apache-2.0 + 83 keys 実測。paper 乖離 4 点文書化済み |
| 4 | 22050Hz 適合 | 🟡 partially | v1 は解消 (wetdog 自体が 22050Hz/hop256、PoC 実証)。v2 (24kHz→22050Hz rescale) は Stage 3 学習でのみ |
| 5 | VITS + WaveNeXt E2E 学習安定性 | ❌ needs-training | 実装前提は完全整理済み。数値安定性は smoke 必須 |
| 6 | AdaLayerNorm zero-shot conditioning | ❌ needs-training | wetdog に AdaLayerNorm 実在確認 (FiLM 注入ポイント流用可)。SECS 0.6879 比較は学習必須 |
| 7 | v7 encoder half partial-transfer | 🟡 partially | 機構面解消 (None 返し設計 + loader 仕様)。実効性 (収束加速) は smoke |
| 8 | clip × post-trim | 🟡 partially | **clip 直接リスクは低確定** (primary trim は durations ベースで振幅非依存、完全直交)。残余は **head bias floor** (z=0 で abs_max 0.045、学習後に RMS 1% 閾値を下回るか要再測定) |
| 9 | sub-band STFT loss 撤去の音質影響 | ❌ needs-training | 実装前提は解消 (§6)。JA/ZH サ行の品質同等性は smoke + PESQ/STOI + 聴感 A/B 必須 |

---

## 9. 残 unknown (smoke 学習でのみ解消可能)

1. **CPU RTF 最終判定**: canonical 環境 (Xeon E5-2650 v4 相当、contract 準拠 intra=4) での end-to-end 実測。ローカル PoC は負方向 (30-40% 遅い) prior。
2. Unknown #5: DINO + CAM++ SCL + bf16-mixed + WavLM 併用の数値安定性。
3. Unknown #6: FiLM/AdaLayerNorm conditioning で zero-shot SECS ≥ 0.6879 が出るか。
4. Unknown #9: JA/ZH サ行での MRD + fullband loss vs sub-band STFT loss。
5. BSC-LT init の実効性 (スクラッチ init 比で収束加速するか)。
6. 学習後の head bias floor vs `_trim_silence` 閾値 (正規化ピーク比 RMS 1%)。
7. FP16 export 品質: 学習後 LayerScale γ 分布 (init 0.125 だが学習で subnormal 域に落ちる可能性) + `convert_fp16 --validate` 通過。
8. MRD loss 形式 (wetdog 忠実 hinge+正規化 vs piper 一貫 LSGAN) の最終確定。

---

## 10. 正誤表 (01/02/03/README へ反映済みの主な訂正)

| 旧記述 | 訂正 | 反映先 |
|--------|------|--------|
| M1「10-15% 高速 (推定)」/ README「MB-iSTFT × 0.8-0.9」 | contract 準拠実測で **30-40% 遅い** (default threading では同等) | 02, README |
| M2「配布サイズ 5-10% 縮小見込」 | 撤回 — decoder 単体 fp32 8.5x 増。M2 は保守性 + bf16 安定化のみに縮小 | 02 |
| D8「fixture 24 個再エクスポート、CI 1-2 週赤化 (medium)」 | opt-in なら既存 fixture 再生成ゼロ。parity gate は informational | 01, 02 |
| D5「最悪 3x = ~179M」 | weight 独立で 59.94M が確定総数 (隠れ倍率なし) | 01, 02 |
| 「3-pass fixed-point iteration」 | headline は **4 sub-models** (Table 1 で 2-5 ablation 済) | 01, 03 |
| 「WaveFit §3.3 から逆算必要」 | §4.2/§4.4/§5.1 で pin 済、逆算不要 | 02, 03 |
| WaveFit venue「Interspeech 2022」 | **IEEE SLT 2022** | 01 |
| 「BSC-LT byte-compat」 | f_max 非互換 (8000 vs None→11025)、他項目は完全一致 | 01, README |
| 「WaveNeXt ckpt 書き出し瞬間に RuntimeError」 | 読み込み時 2 経路 (即時 raise / fit 失敗後 fallback) | README, 02 |
| LayerScale「γ init 1e-6」 | wetdog default は **1/num_layers = 0.125** | 01, 03 |
| MB-iSTFT decoder「~15M 相当」 | 実測 **1.65M** (WaveNeXt 14.12M で 8.57x) | 02 |
| 13.68M (WaveNeXt params) | 13.72M (BSC-LT 実測 13,722,626) / z=192 版 14.12M | 01, 02, README |
| call site `__main__.py:607/981/1063` 等の stale 行番号 | `:479` / `:854`、factory は `models.py:757-766`、PQMF instantiate `lightning.py:317-325`、loss 適用 `:883-887` | 01, 03, README |
| OPSET 15→17 一括 bump 推奨 | 撤回 — wavenext 分岐のみ 17 (blocking gate 回避) | 03 |
| hygiene fix「export_onnx.py が hop_size emit」 | export_onnx.py は config.json を書かない。emit 先は preprocess.py:292-306 / prepare_multilingual_dataset.py:1428-1447 | 01 |

---

## 11. PoC 再現情報

- スクリプト・結果・ONNX: scratchpad `wavenext_poc/` (session 一時領域のため揮発性 — 再現は poc_wavenext.py を再実行)
  - `poc_wavenext.py` (実装 + export + bench) / `bench_rerun.py` (verify 用再実行)
  - `results.json` / `results_bench_rerun.json`
  - `wavenext_op15.onnx` / `wavenext_op17.onnx` / `mb_istft_op15.onnx` + 各 `.ort_optimized.onnx`
- workflow スクリプト: session `workflows/scripts/wavenext-pre-stage0-verification-wf_5f1094ad-ed9.js` (resumeFromRunId `wf_5f1094ad-ed9` で再実行可)
- attribution 要件 (Stage 1 `wavenext.py` ヘッダ): (1) Vocos (Copyright 2023 Charactr Inc., MIT)、(2) wetdog/wavenext_pytorch@d45d544 (WaveNextHead 追加分、MIT)、(3) Okamoto et al. ASRU 2023 (DOI 10.1109/ASRU57964.2023.10389765)。BSC-LT 重み利用時は Apache-2.0 NOTICE 保持。

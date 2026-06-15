# AI-16: PR #537 merge 後の bf16-mixed + TF32-on 再 benchmark

## メタ情報

- ID: AI-16
- 親マイルストーン: [M6](../milestones/M6-pr-rebase-integration.md)
- 工数見積: 2 日
- 依存チケット: AI-15 (regression guard CI gate 整備)、 **PR #537 merge** (Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一)
- 後続チケット: AI-17 (PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期、 本チケットの再 baseline を前提とする)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-16 / §2.2 PR #537 状態 / §4.6 Benchmarks 目標値 / §7 R5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは M6 (PR #222 / #537 rebase 取込と統合判定) の第一段階を担う。 計画 §6 AI-16 が要求する「ubuntu-24.04 + py3.13 + torch 2.11 で全 variant 5 epoch sanity + ONNX export + benchmark 再測定」 「TF32 が招く 1e-3 magnitude drift を audio-parity-contract.toml の tolerance に反映」 を本チケットで完了させる。 PR #537 merge により持ち込まれる **TF32-on + bf16-mixed default + NumPy 2.x + pytest 9** 環境で、 M1-M5 で確定した 4 variant (`mb_istft_1d` baseline / `istftnet2_mb_1d2d` / `fly_convnext6` / `mswavehax` companion) の audio parity が保てるかを正面突破で検証する。

上流の AI-15 (regression guard CI gate) が用意した `scripts/check_audio_parity_baseline.py` + `scripts/check_a1_a2_isolation.py` の機械 check が、 PR #537 merge 後の torch-2.11 sandbox でも稼働することが本チケットの前提である。 計画 §3 Conflict Map で `tools/benchmark/ + tests/` 行が NONE / LOW、 `lightning.py` 行が LOW (bf16-mixed) と分類されているとおり、 コード衝突は最小に局所化されている。 ただし計画 §7 R5 が警告するとおり、 NumPy 2.x の torch.fft / wavelet ops 互換と pytest 7→9 fixture deprecation はランタイム挙動で正面から exercise しないと検出できないため、 本チケットの 5 epoch sanity がその責務を負う。

下流の AI-17 (PR #222 merge 後の `_apply_film` rank-aware 化 + ONNX I/O `sid → speaker_embedding[192]` 同期) は、 本チケットで確定する **新 baseline 数値と拡張 tolerance** を入力として消費する。 AI-17 で FiLM rank-aware 化が pairwise SNR ≥ 30 dB を維持できるかを判断する際の audio parity 基準値は、 PR #537 merge 後の TF32-on 環境で再測定された本チケットの数値とする。 計画 §5 が示すとおり、 PR #537 の数値ドリフトを A-1/A-2 PoC 後に **1 度だけ再 baseline 化** する戦略を本チケットで実行することで、 `[mb_istft_1d]` baseline 編集禁止 gate を維持しつつ新 variant section の tolerance 拡張のみに編集を局所化する。

## 実装内容の詳細

### 編集対象ファイル

- `/Users/s19447/Documents/piper-plus/docs/spec/audio-parity-contract.toml`
  - **新 variant section の tolerance 拡張のみ編集可** (AI-14 で追加された `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]`)
  - 新 key 追加: `bf16_tolerance_db` (default 30 dB に対し bf16-mixed 環境で許容する SNR floor の緩和、 暫定 28 dB)、 `tf32_drift_threshold` (TF32-on 環境での 1e-3 magnitude drift 許容、 暫定 `1.5e-3`)
  - **`[mb_istft_1d]` section は absolutely touch しない** (G-1.2 baseline 編集禁止 gate / `scripts/check_audio_parity_baseline.py`)
- `/Users/s19447/Documents/piper-plus/tools/benchmark/results/css10-ja-poc-py313-torch211/` (新規ディレクトリ)
  - variant 別 JSON: `{variant}-py313-torch211-bf16.json` (5 epoch sanity ログ + ONNX export 成功フラグ + benchmark p50)
  - 4 variant × 5 entry の構造: `mb_istft_1d` / `istftnet2_mb_1d2d` / `fly_convnext6` / `mswavehax`
- `/Users/s19447/Documents/piper-plus/README.md` (Benchmark 表追記のみ)
  - 既存の `27ms` (Xeon E5-2650 v4 / 25 phoneme 英文 / torch 2.2 / py3.11) を canonical として残置
  - 新行追加: ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed の Xeon p50 を 1 列追加
- `/Users/s19447/Documents/piper-plus/tools/benchmark/run_5epoch_sanity.py` (新規、 ~120 LoC)
  - 4 variant 各 5 epoch sanity 学習 + ONNX export + Xeon p50 計測を 1 コマンドで実行
  - 既存 `generate_samples.py` / `compute_metrics.py` を内部呼出し、 `--py313` フラグで torch 2.11 環境分岐
- `/Users/s19447/Documents/piper-plus/src/python/tests/test_bf16_mixed_sanity.py` (新規、 ~80 LoC)
  - bf16-mixed default 下で `torch.fft.rfft` / `OnnxISTFT` / PQMF の出力 magnitude drift が `1.5e-3` 以下であることを assert
  - NumPy 2.x で `numpy.asarray(torch.Tensor)` の dtype 推論が変わらないことを assert

### PR #537 merge 後の差分吸収 (計画 §2.2 / §7 R5)

計画 §2.2 から引用:

> 現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で A-1/A-2 PoC を完走
> PR #537 merge 後に bf16-mixed + pytest 9 で **再 benchmark** (audio-parity-contract.toml の tolerance 拡張)

計画 §7 R5 mitigation:

> A-2 PoC は PR #537 merge 前に現行 torch 2.2 で完走、 PR #537 merge 後に torch-2.11 sandbox で FFT op 互換 check + 5 epoch sanity 再学習。 pytest 9 deprecation は別 PR で独立追従し A-1/A-2 PR を blocking させない

実装手順:

1. **環境構築:** PR #537 merge 後の dev branch を fetch、 `uv sync --python 3.13` で torch 2.11 / CUDA 12.8 / NumPy 2.x / pytest 9 環境を構築
2. **5 epoch sanity 学習:** 4 variant 各 `--max_epochs 5` で CSS10 JA PoC データセットを学習、 acc_loss / disc_loss / mel_loss を WandB に記録 (audio-log-epochs=1 で全 epoch ログ)
3. **ONNX export:** 各 variant を `python -m piper_train.export_onnx --no-fp16 --simplify` (FP16 ドリフトと混在しないよう一旦 FP32 で export)、 op coverage を `tools/benchmark/audit_onnx_ops.py` で audit
4. **Xeon p50 計測:** `tools/benchmark/run_5epoch_sanity.py --xeon-p50 --warmup 5 --runs 30` で README canonical 設定 (25 phoneme 英文) で計測
5. **tolerance 拡張提案:** sanity 結果から各 variant の TF32 drift / bf16 SNR drop を集計し、 `audio-parity-contract.toml` の新 variant section に `bf16_tolerance_db` / `tf32_drift_threshold` を追記 (`[mb_istft_1d]` は touch しない)

### PR #222 / PR #537 conflict 回避策

計画 §3 Conflict Map から該当行を引用:

> `lightning.py` | `_collect_g_params` hook、 wavehax LR | MEDIUM (WavLM-D + DINO 拡張) | **LOW (bf16-mixed)** | A-1/A-2 先行で hook 化
> `tools/benchmark/` + `tests/` | 3 variant 追加、 regression guard | NONE | **LOW (pytest 9)** | A-1/A-2 先行で OK

- **vs PR #537:** 本チケットは PR #537 merge **後** に着手するため、 conflict ではなく 「merge 結果の検証」 が責務。 lightning.py の bf16-mixed 影響は 5 epoch sanity 学習の数値ログで定量化、 tools/benchmark/ の pytest 9 deprecation は `test_bf16_mixed_sanity.py` を fixture less に書くことで sidestep (計画 §7 R5 mitigation の pytest 7/9 両対応戦略を継続)
- **vs PR #222:** PR #222 は本チケット時点で未 merge。 ただし `audio-parity-contract.toml` の編集競合を避けるため、 本チケットで追加する `bf16_tolerance_db` / `tf32_drift_threshold` は **新 variant section 末尾の専用 key** として追加し、 PR #222 が触る予定の `[mb_istft_1d]` / FiLM 関連 key とは独立 namespace に置く。 AI-17 で PR #222 rebase 時に key 衝突が起きないことを `scripts/check_a1_a2_isolation.py` (M5 AI-15 導入) で機械 check
- **`[mb_istft_1d]` baseline 編集禁止 gate (G-1.2):** 本チケットでは PR #537 merge 後の TF32 drift が 1D baseline の audio parity を破壊する可能性があるが、 `[mb_istft_1d]` を編集する代わりに、 baseline section の参照側 (test 側) で TF32-on 環境かどうかを判定し新 key (`tf32_drift_threshold`) を別 variant 経由で参照する間接構造とする

### 設定 default 値 / 新規 CLI フラグ

- `tools/benchmark/run_5epoch_sanity.py --py313` — PR #537 merge 後の torch 2.11 / CUDA 12.8 環境で実行する opt-in フラグ。 省略時は現行 dev (torch 2.2 / py3.11) で動く
- `tools/benchmark/run_5epoch_sanity.py --bf16-mixed` — `--precision bf16-mixed` を学習に渡す (PR #537 後の default 想定)
- `tools/benchmark/run_5epoch_sanity.py --tf32-on` — `torch.backends.cuda.matmul.allow_tf32 = True` を明示有効化
- `audio-parity-contract.toml` 新 key default 値: `bf16_tolerance_db = 28.0` (default 30 dB から 2 dB 緩和)、 `tf32_drift_threshold = 1.5e-3` (FP32 同士の 1e-4 想定に対し 1 桁緩和)

### tolerance 拡張差分スケッチ (TOML、 20 数行)

```toml
# audio-parity-contract.toml の新 variant section に追記 (既存 [mb_istft_1d] は touch しない)

[istftnet2_mb_1d2d]
# (AI-14 で追加された既存 key は維持)
# expected_p50_ms = 18
# pairwise_snr_floor_db = 30.0
# AI-16 追加: PR #537 merge 後の TF32-on + bf16-mixed 環境向け
bf16_tolerance_db = 28.0           # default 30 dB に対し 2 dB 緩和 (bf16-mixed mantissa loss)
tf32_drift_threshold = 1.5e-3      # TF32 matmul の magnitude drift 許容
torch_version_pin = "2.11"         # この tolerance が確定した torch version
runtime_env = "ubuntu-24.04+py3.13+cuda12.8"

[mswavehax]
bf16_tolerance_db = 28.0
tf32_drift_threshold = 1.5e-3
torch_version_pin = "2.11"
runtime_env = "ubuntu-24.04+py3.13+cuda12.8"

[fly_convnext6]
bf16_tolerance_db = 28.0
tf32_drift_threshold = 1.5e-3
torch_version_pin = "2.11"
runtime_env = "ubuntu-24.04+py3.13+cuda12.8"

# [mb_istft_1d] は absolutely touch しない (G-1.2 baseline 編集禁止 gate)
```

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Platform Engineer (PR #537 fetch + 環境構築) | 1 | uv / Python 3.13 / CUDA 12.8 / NumPy 2.x / pytest 9 | PR #537 merge 後の dev branch fetch、 `uv sync --python 3.13` で torch 2.11 環境構築、 pytest 9 fixture deprecation の影響範囲調査 |
| ML Sanity Engineer (5 epoch sanity 学習) | 1 | PyTorch Lightning / bf16-mixed / TF32 / WandB | 4 variant 各 5 epoch sanity を CSS10 JA PoC データセットで完走、 acc_loss / mel_loss / disc_loss を比較、 異常 drift を検出 |
| ONNX & Benchmark Engineer | 1 | ONNX export / ONNX Runtime / Xeon E5-2650 v4 / NumPy 2.x | 4 variant の ONNX export + op coverage audit + Xeon p50 計測 (warmup 5 + runs 30 / 25 phoneme 英文) を再実行 |
| Contract Editor + Test Engineer | 1 | TOML / pytest 7/9 両対応 / audio parity gate | `audio-parity-contract.toml` の新 variant section に `bf16_tolerance_db` / `tf32_drift_threshold` を追記、 `test_bf16_mixed_sanity.py` を fixture less で実装、 `[mb_istft_1d]` 編集禁止 gate が green を確認 |

4 名構成。 学習・export・benchmark・contract 編集を直列で実施するため担当を分離し、 contract 編集権限を 1 名に集約することで `[mb_istft_1d]` baseline への誤編集リスクを構造的に下げる (M6 milestone §一から作り直すとしたら の「権限分離」 観点と整合)。

## 提供範囲 (Scope)

### 含むもの

- PR #537 merge 後の ubuntu-24.04 + py3.13 + torch 2.11 + CUDA 12.8 + NumPy 2.x + pytest 9 環境で 4 variant の 5 epoch sanity 学習完走
- 4 variant の ONNX export (FP32 + simplify) と op coverage audit
- 4 variant の Xeon E5-2650 v4 p50 再測定 (25 phoneme 英文 / warmup 5 + 30 runs)
- `audio-parity-contract.toml` の新 variant section (`[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]`) に `bf16_tolerance_db` / `tf32_drift_threshold` / `torch_version_pin` / `runtime_env` の 4 key 追加
- `tools/benchmark/results/css10-ja-poc-py313-torch211/` に variant 別 JSON 4 件 artifact 化
- `README.md` の Benchmark 表に ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed の新行追加
- `tools/benchmark/run_5epoch_sanity.py` 新規 (5 epoch sanity + ONNX export + p50 計測を一気通し)
- `src/python/tests/test_bf16_mixed_sanity.py` 新規 (FFT / iSTFT / PQMF の magnitude drift assert)

### 含まないもの (Out of Scope)

- **PR #222 の `_apply_film` rank-aware 化 + ONNX I/O 同期** — AI-17 で扱う (本チケットの新 baseline 数値を入力として消費する側)
- **`[mb_istft_1d]` section の編集** — G-1.2 baseline 編集禁止 gate に従い absolutely touch しない (baseline 27ms は canonical 値として残置)
- **採否判定レポート作成と統合 PR 提出** — AI-18 で扱う (4 指標による A-1 採用 / FLY-TTS 切替 / 1D 継続の判断)
- **CSS10 JA 以外のデータセット (6lang base / 多話者 FT) での再 benchmark** — 別 epic、 本 PoC ステージでは CSS10 JA 単一話者のみ
- **pytest 7→9 fixture deprecation の全 PR 適用** — 計画 §7 R5 mitigation により別 PR で独立追従、 本チケットは benchmark スクリプト範囲のみ対応
- **AI-12 で確定した `models.yaml` の `expected_p50_ms` 上書き** — 本チケットは新 environment 列を `tools/benchmark/results/css10-ja-poc-py313-torch211/` に artifact 化するのみで、 `models.yaml` の torch 2.2 / py3.11 値は touch しない
- **mobile EP (iOS CoreML / Android NNAPI) での再検証** — 計画 §7 R7 mitigation により PoC 範囲外

## テスト項目

### Unit Tests

- `src/python/tests/test_bf16_mixed_sanity.py::test_fft_magnitude_drift_under_tf32`
  - assert: `torch.backends.cuda.matmul.allow_tf32 = True` 下で `torch.fft.rfft(x).abs().max()` の FP32 同条件比 drift が `< 1.5e-3`
- `src/python/tests/test_bf16_mixed_sanity.py::test_onnx_istft_bf16_continuity`
  - assert: `OnnxISTFT(hop=4)` を bf16-mixed dtype で実行した結果と FP32 結果の SNR が `≥ 28 dB` (新 `bf16_tolerance_db`)
- `src/python/tests/test_bf16_mixed_sanity.py::test_pqmf_numpy_2x_dtype_inference`
  - assert: NumPy 2.x で `numpy.asarray(pqmf_output)` の dtype が `numpy.float32` 維持 (1.x との互換性確認)
- `src/python/tests/test_bf16_mixed_sanity.py::test_audio_parity_contract_baseline_untouched`
  - assert: `audio-parity-contract.toml` の `[mb_istft_1d]` section 全 key が PR 開始時の SHA から不変 (G-1.2 baseline 編集禁止 gate)
- `src/python/tests/test_bf16_mixed_sanity.py::test_new_variant_sections_have_bf16_keys`
  - assert: `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` の 3 section に `bf16_tolerance_db` / `tf32_drift_threshold` / `torch_version_pin` / `runtime_env` の 4 key が全て存在
- `tools/benchmark/test_benchmark.py::test_run_5epoch_sanity_resolves_4_variants`
  - assert: `run_5epoch_sanity.py --dry-run` が 4 variant (`mb_istft_1d` / `istftnet2_mb_1d2d` / `fly_convnext6` / `mswavehax`) を全て resolve
- 既存 `test_mb_istft_generator.py` / `test_istftnet2_generator.py` / `test_audio_parity.py` は touch しない (G-1.9 後方互換 gate)

### E2E Tests

- **4 variant 5 epoch sanity 一気通し:**
  ```
  uv run python tools/benchmark/run_5epoch_sanity.py \
      --py313 --bf16-mixed --tf32-on \
      --variants mb_istft_1d,istftnet2_mb_1d2d,fly_convnext6,mswavehax \
      --dataset-dir /data/piper/dataset-css10-ja-poc \
      --output-dir tools/benchmark/results/css10-ja-poc-py313-torch211
  ```
  - assert: 4 variant 全てが 5 epoch 完走 (mel_loss / disc_loss が divergence しない)、 各 ONNX export 成功、 Xeon p50 が新環境 baseline ± 5ms 以内
- **audio-parity test green (新 tolerance):**
  ```
  uv run --no-sync pytest src/python/tests/test_audio_parity.py --no-cov -v
  ```
  - assert: 4 variant 全てが新 `bf16_tolerance_db = 28.0` / `tf32_drift_threshold = 1.5e-3` で pass、 `[mb_istft_1d]` baseline section 編集禁止 gate `scripts/check_audio_parity_baseline.py` も green
- **ONNX op coverage audit (FP32 + simplify):**
  - assert: 4 variant 全て op set が AI-12 / AI-15 で記録した set と完全一致 (PR #537 の torch 2.11 で op 数が増減していないことを確認)
- **README canonical 27ms baseline 不変確認:**
  - assert: 既存 README Benchmark 表の 27ms 行が touch されておらず、 新行 (ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed) が独立 1 行として追加されている
- **WandB audio log (任意):** 4 variant × 5 sample を WandB へアップロード、 audio-log-epochs=1 で全 epoch 視聴可能

### 受入基準 (Acceptance Criteria)

計画 §4.6 / §6 AI-16 / §7 R5 から該当数値を引用:

- **5 epoch sanity 完走率**: 4 variant 全てで 5 epoch 完走、 mel_loss / disc_loss が divergence しない (NaN / Inf 検出なし)
- **ONNX export 成功率**: 4 variant 全てで `python -m piper_train.export_onnx --no-fp16 --simplify` 成功、 op set が AI-12 / AI-15 baseline と完全一致
- **Xeon E5-2650 v4 p50** (25 phoneme 英文 / warmup 5 + runs 30): 各 variant が AI-12 で確定した torch 2.2 / py3.11 baseline ± 5ms 以内 (TF32-on で僅か速度低下、 bf16-mixed で僅か向上の可能性、 ± 5ms で吸収)
- **TF32 drift** (FP32 同条件比): 4 variant 全てで `< 1.5e-3` magnitude drift (新 `tf32_drift_threshold`)
- **bf16-mixed SNR floor**: 4 variant 全てで FP32 結果との pairwise SNR が `≥ 28 dB` (新 `bf16_tolerance_db`)
- **pytest 7/9 両対応**: `test_bf16_mixed_sanity.py` の全 case が pytest 7 (現行 dev) と pytest 9 (PR #537 後) の両方で pass
- **G-1.2 baseline 編集禁止 gate green**: `scripts/check_audio_parity_baseline.py` が `[mb_istft_1d]` section 全 key の SHA 不変を確認
- **G-1.9 後方互換 gate green**: `models.yaml` の既存 entry / `test_benchmark.py` 既存 case / `test_audio_parity.py` 既存 case が全て touch されていない

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から関連項目:

- **R5 (MEDIUM/MEDIUM): PR #537 の TF32-on + bf16-mixed default + NumPy 2.x + pytest 9 が A-2 MS-Wavehax の torch.fft / wavelet ops を破壊、 もしくは pytest 7→9 で既存 mb_istft fixture が deprecation で fail** — 本チケットの正面突破対象。 mitigation: 4 variant 5 epoch sanity で torch.fft / OnnxISTFT / PQMF の dtype 連鎖を exercise、 fixture less assertion で pytest 7/9 両対応、 NumPy 2.x の `asarray` dtype 推論変化を test_bf16_mixed_sanity.py で gate
- **R6 (MEDIUM/HIGH): `[mb_istft_1d]` baseline regression を silently 招く** — 本チケットの最大の構造的リスク。 mitigation: contract 編集権限を 1 名 (Contract Editor + Test Engineer) に集約、 `scripts/check_audio_parity_baseline.py` を pre-commit hook で 100% 強制、 PR body checklist で `[mb_istft_1d]` への touch なしを機械 check (`git diff docs/spec/audio-parity-contract.toml` の context 行が新 variant section のみであることを CI gate 化)
- **R8 (MEDIUM/LOW): 1 GPU 占有との競合** — 5 epoch sanity × 4 variant は CSS10 JA PoC dataset で 1 GPU × 約 8 時間 (各 2 時間想定)、 他作業との GPU 競合で延期する可能性。 mitigation: PR #537 merge を待つ間に CSS10 JA dataset の cached spec を事前生成しておくことで sanity 着手後の GPU 占有時間を短縮
- **TF32 drift が 1.5e-3 を超える variant 発見時の判断:** Acceptance Criteria の `tf32_drift_threshold = 1.5e-3` は計画 §1 の「TF32 が招く 1e-3 magnitude drift」 を 1.5 倍緩和した暫定値。 これを超える variant が見つかった場合は、 (a) tolerance を更に緩和 (品質劣化を許容)、 (b) 該当 variant を `torch.backends.cuda.matmul.allow_tf32 = False` で学習し直す、 (c) AI-18 で 「PR #537 後の TF32-on 環境では非対応」 として variant 棄却、 の 3 択を AI-17 / AI-18 で再協議する
- **NumPy 2.x で `numpy.asarray(torch.Tensor)` dtype 推論変化:** NumPy 1.x → 2.x で integer type promotion ルールが厳格化されたため、 `PQMF` / `OnnxISTFT` の numpy 連携で silently dtype が upcast される懸念。 mitigation: `test_pqmf_numpy_2x_dtype_inference` で 4 variant 全てで `numpy.float32` 維持を assert
- **PR #537 が rebase ループに入った場合のスケジュール影響:** PR #537 は計画 §2.2 で「mergeable=CONFLICTING/DIRTY、 rebase 必須」 とされており、 本チケット着手は PR #537 merge 完了が前提。 mitigation: PR #537 進捗を `/loop /watch-pr 537` で週次監視 (計画 §8 Immediate Next Steps と整合)、 merge 遅延時は M6 milestone § 一から作り直すとしたら の「kill switch」 (AI-16 fail で AI-17/AI-18 中止) 発動条件に該当しないか AI-18 で再協議

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 `mb_istft_1d` を default として保持)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止、 `scripts/check_audio_parity_baseline.py` green)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避、 本チケットでは `speaker_embedding[192]` 列を触らない / `sid` 経路維持)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (`bf16_tolerance_db` / `tf32_drift_threshold` の 4 key が新 variant section に追記)
- [ ] `[mb_istft_1d]` section への `git diff` 差分行ゼロ (CI gate `scripts/check_audio_parity_baseline.py` の SHA 比較で機械 check)
- [ ] 4 variant 全てで 5 epoch sanity 完走 (mel_loss / disc_loss divergence なし、 NaN/Inf なし)
- [ ] 4 variant 全てで ONNX export 成功 + op set が AI-12 / AI-15 baseline と完全一致
- [ ] Xeon p50 が AI-12 baseline ± 5ms 以内 (TF32-on / bf16-mixed の影響を吸収)
- [ ] `test_bf16_mixed_sanity.py` が pytest 7 / pytest 9 両環境で pass (fixture less 確認)
- [ ] NumPy 2.x で `numpy.asarray(torch.Tensor)` の dtype 推論が `numpy.float32` 維持
- [ ] `tools/benchmark/results/css10-ja-poc-py313-torch211/` に variant 別 JSON 4 件が artifact 化されている
- [ ] `README.md` Benchmark 表の既存 27ms 行 touch なし、 新行 (ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed) が独立 1 行として追加されている
- [ ] AI-17 への引き渡し: 新 tolerance section の値が AI-17 の FiLM rank-aware 化検証で消費可能な形式 (TOML key 階層 + 値 + 単位コメント) になっている

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「PR #537 merge **完了後** に正面突破で 5 epoch sanity + ONNX export + benchmark を 1 度だけ走らせ、 新 tolerance を `audio-parity-contract.toml` の新 variant section に追記する」 という直列順序である。 これは計画 §5 が要求する「PR #537 の数値ドリフトを A-1/A-2 PoC 後に **1 度だけ再 baseline 化**」 戦略に最も忠実な実装で、 contract 編集権限を 1 名に集約することで `[mb_istft_1d]` baseline regression リスク (R6) を構造的に下げる現実解である。 代替案 1 として 「**PR #537 merge を待たずに torch 2.11 sandbox を docker で事前構築し、 5 epoch sanity を先行実施**」 する案があり、 これは PR #537 が rebase ループに入った場合の schedule risk を mitigate できる利点があるが、 PR #537 の最終 merge commit (rebase 後の SHA) と sandbox の torch version が乖離する場合に再実行が必要になるため、 net では工数増となるリスクが高い。

代替案 2 は **integration-test 先行 (audio-parity test を先に変更し sanity 後追い)** で、 これは `audio-parity-contract.toml` の新 tolerance を「予想値」 で先に書いて test を pass させ、 sanity 学習結果で fine-tune する逆順序である。 利点は「contract 編集が PR の最初の commit」 として明示化されレビュアーが gate 編集の合意を最速で得られる点だが、 欠点は予想値が大きく外れた場合に test 修正の往復が発生する点。 採用案 (sanity 先行) では sanity 数値を見てから tolerance を決めるため少し review iteration が後ろ倒しになるが、 数値根拠が PR の最後の commit で明示されるためレビュー時の合意形成がスムーズで、 計画 §1 の「TF32 が招く 1e-3 magnitude drift」 を 1.5 倍緩和した暫定値が現実と乖離していた場合の手戻りを最小化できる。

代替案 3 として **4 variant を別々の sub-PR に分割** する設計も検討した。 これは「`mb_istft_1d` baseline sanity」 「`istftnet2_mb_1d2d` sanity + tolerance」 「`fly_convnext6` sanity + tolerance」 「`mswavehax` sanity + tolerance」 の 4 PR を直列に提出する案で、 各 PR の review burden は下がるメリットがあるが、 `audio-parity-contract.toml` を 4 PR で順番に編集することになり中間 PR で contract が一時的に不整合 (例えば 2 variant 分の tolerance だけ追記された状態) になる懸念がある。 採用案では 1 PR で 4 variant を atomic に追記することで contract の中間不整合を回避し、 G-1.2 gate (`scripts/check_audio_parity_baseline.py`) が常に green を維持する。

採用案を 「現実解」 として位置づけ、 別案の利点 (代替 1 の sandbox 事前構築 / 代替 2 の test 先行 / 代替 3 の 4 PR 分割) は本チケットの 2 日工数の範囲外になるため捨てた。 早期失敗指標は「**5 epoch sanity で 1 variant でも mel_loss が divergence した時点で AI-17 着手を停止し、 M6 milestone の kill switch (PR #222 後追い諦め)** 発動条件に該当するか AI-18 で再協議」 を本チケット内で明示し、 PR #537 後の TF32 / bf16-mixed が想定外の数値破壊を引き起こした場合の escape hatch を確保する。

## 後続タスクへの連絡事項

AI-17 (PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期) に引き渡す具体的成果物:

- **新 tolerance section 確定値:**
  - `audio-parity-contract.toml` の `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` 3 section に `bf16_tolerance_db` / `tf32_drift_threshold` / `torch_version_pin = "2.11"` / `runtime_env = "ubuntu-24.04+py3.13+cuda12.8"` の 4 key が確定済み
  - AI-17 の FiLM rank-aware 化 (1D / 2D 両 path) で pairwise SNR ≥ 30 dB を測る際の基準値は本チケットの `bf16_tolerance_db` (暫定 28.0) を継続利用すること。 PR #222 後に更に SNR drop が観測される場合のみ追加緩和を AI-17 で協議
- **再 benchmark 数値 (artifact):**
  - `tools/benchmark/results/css10-ja-poc-py313-torch211/{variant}-py313-torch211-bf16.json` (4 件) に Xeon p50 / params_m / ONNX op set / mel_loss / disc_loss の 5 epoch sanity ログが格納
  - AI-17 で `_apply_film` rank-aware 化を入れた後の 5 epoch sanity を再実行する際、 本チケットの数値を「FiLM 変更前 baseline」 として参照
- **ONNX export 経路:**
  - 4 variant の ONNX は `--no-fp16 --simplify` で export 済み、 FP16 dtype のドリフトと TF32 drift を分離して評価可能
  - AI-17 で PR #222 の ONNX I/O 変更 (`sid → speaker_embedding[192]`) を A-1/A-2 export 経路に同期する際、 本チケットの ONNX file を「I/O 変更前 baseline」 として diff 比較
- **`[mb_istft_1d]` baseline section 不変保証:**
  - PR 開始時の SHA を `scripts/check_audio_parity_baseline.py --record-baseline-sha` で記録、 AI-17 / AI-18 でも継続して `[mb_istft_1d]` 編集禁止 gate を稼働
- **pytest 7/9 両対応の確認:**
  - `test_bf16_mixed_sanity.py` は fixture less に書いてあり pytest 9 deprecation 影響なし
  - AI-17 の追加 test (FiLM rank-aware 化検証) も同じ fixture less 方針で書くこと (計画 §7 R5 mitigation の継続)
- **NumPy 2.x dtype 推論変化の影響範囲:**
  - PQMF / OnnxISTFT の numpy 連携部分は本チケットで確認済み (`numpy.float32` 維持)
  - AI-17 で `_apply_film` rank-aware 化を実装する際、 channel-axis split (dim=1) の dtype 連鎖で NumPy 2.x の integer type promotion ルール変化が影響しないことを再確認
- **TF32 drift > 1.5e-3 variant が存在する場合:**
  - 該当 variant 名と drift 実測値を `tools/benchmark/results/css10-ja-poc-py313-torch211/tf32_drift_outliers.md` に記録
  - AI-17 / AI-18 で「(a) tolerance 更に緩和 / (b) `allow_tf32 = False` で学習し直し / (c) variant 棄却」 の 3 択を再協議
- **PR #222 rebase 時の注意:**
  - 本チケットで追加した `bf16_tolerance_db` / `tf32_drift_threshold` の 4 key は新 variant section 末尾の専用 namespace に置いてあり、 PR #222 が触る予定の `[mb_istft_1d]` / FiLM 関連 key とは独立
  - AI-17 で PR #222 rebase 時に `audio-parity-contract.toml` の merge conflict が起きた場合、 本チケットの 4 key は維持しつつ PR #222 の `[mb_istft_1d]` 関連 (もしあれば) は absolutely 棄却すること
- **AI-18 採否判定への引き渡し:**
  - 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) のうち **CPU RTF (p50) と ONNX op coverage** は本チケットの再 benchmark 数値が canonical 入力
  - AI-18 の判定表に「torch 2.2 / py3.11 (AI-12 確定) と torch 2.11 / py3.13 + bf16-mixed (本チケット確定) の 2 列を併載」 することを推奨

## 関連ドキュメント

- 親マイルストーン: [../milestones/M6-pr-rebase-integration.md](../milestones/M6-pr-rebase-integration.md)
- 親計画 §6 AI-16 / §2.2 / §4.6 / §7 R5: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査統合: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 前チケット: [AI-15 regression guard CI gate 整備](AI-15-regression-guard-ci.md)
- 後続チケット: [AI-17 PR #222 FiLM rank-aware 化 + ONNX I/O 同期](AI-17-pr222-rebase-integration.md)
- 影響 PR:
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — 本チケットの merge 前提
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — AI-17 の merge 前提、 本チケットでは contract namespace 分離で衝突回避
- 関連 spec:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — 新 variant section 3 つに `bf16_tolerance_db` / `tf32_drift_threshold` / `torch_version_pin` / `runtime_env` の 4 key 追記対象 (G-1.2 `[mb_istft_1d]` 編集禁止 gate 継続)
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — bf16-mixed 環境での ORT session 設定継続性 (本チケットでは触らない、 AI-18 で参照のみ)
- ORT バージョン表: [../../reference/ort-versions.md](../../reference/ort-versions.md)
- canonical 27ms baseline: `README.md` Benchmark 表 (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs / torch 2.2 / py3.11)

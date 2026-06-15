# AI-14: audio-parity-contract.toml に新 variant section 追加

## メタ情報

- ID: AI-14
- 親マイルストーン: [M5](../milestones/M5-runtime-abi-parity.md)
- 工数見積: 1 日
- 依存チケット: AI-13 (7 ランタイム smoke + pairwise SNR 検証)
- 後続チケット: AI-15 (regression guard CI gate 整備)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 AI-14 / §4.6 Benchmarks / §3 Conflict Map](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

M2 / M3 / M4 で生成された 3 つの新 variant (`istftnet2_mb_1d2d` / `mswavehax` / `fly_convnext6`) を、 piper-plus の cross-runtime parity contract である `docs/spec/audio-parity-contract.toml` に「**新規 section として併載**」する。 親計画 §6 AI-14 が掲げる「`[mb_istft_1d]` section は absolutely touch しない (G-1.2 gate)」を絶対前提とし、 既存 baseline を 1 byte も変えずに 3 variant の SNR / PESQ / chromaprint / mel-MSE tolerance を pinning する。

このチケットは M5 の本丸である「採否判定の数値根拠を contract として固定する」工程に当たる。 AI-13 が出力する 7 ランタイム × 3 variant の実測 pairwise SNR / mel-MSE / chromaprint Hamming 値を入力とし、 「PoC 段階の現実的な数値特性」を反映した tolerance を section ごとに pin する。 親計画 §1 の核心トレードオフ 3 で示された「PR #537 merge 前の TF32-off / fp32 baseline で測定」原則を厳守し、 各 section の冒頭コメントに測定環境 (torch 2.2 / py3.11 / CUDA 12.6) を明示することで、 M6 AI-16 が PR #537 merge 後に bf16-mixed / TF32-on で再測定して tolerance を緩める rebase 差分を出せる余地を残す。

下流の AI-15 はこのチケットが pin した tolerance 値を canonical として、 `scripts/check_audio_parity_baseline.py` の `[mb_istft_1d]` SHA256 pinning と `.github/workflows/contract-gates.yml` の required check 化を完成させる。 AI-14 の出力 (3 新 section + `[meta]` 更新 + 測定環境コメント) が atomic に決まらなければ AI-15 の SHA256 pinning が空振りするため、 1 commit で 3 section + meta + コメントを揃えて固定することが完了条件となる。

## 実装内容の詳細

**編集対象ファイル (フルパス + 行範囲):**

- `docs/spec/audio-parity-contract.toml` (現状 65 行)
  - L19-28 `[meta]` section: `schema_version = 1 → 2` に bump、 `referencing_scripts` に `scripts/check_audio_parity_baseline.py` を追加 (AI-15 で実装)
  - L30-37 `[thresholds]` section: **変更しない** (default fallback 値として温存、 各 variant section の値が override する設計)
  - L38-58 `[runtimes]` section: **変更しない** (7 ランタイム CLI 経路は M5 内で不変)
  - L59-64 `[models]` section: 3 entry を追記 (`css10_ja_1d_baseline` / `css10_ja_istftnet2_mb` / `css10_ja_mswavehax_companion` / `css10_ja_fly_convnext6` の 4 entry に拡張)
  - L65 以降: 3 新 section を末尾追加 (詳細下記)

**新規 section 構造 (各 variant ごとに同一スキーマで pin):**

```toml
# ====================================================================
# Variant: istftnet2_mb_1d2d (M2 AI-05 / iSTFTNet2-MB 1D-2D backbone)
# ====================================================================
# 測定環境: torch 2.2.0 / py 3.11.8 / CUDA 12.6 / cudnn 9.0 / fp32 only
#           (PR #537 merge 前の現行 dev baseline、 M6 AI-16 で要再測定)
# 測定 ckpt: /data/piper/output-css10-ja-istftnet2-mb/last.ckpt (50 epoch)
# 測定 ONNX: out/css10-ja-istftnet2-mb-1d2d.onnx (FP16 export, EMA on)
# 測定 utt: CSS10 JA test split 200 utt (utt 平均、 7 ランタイム pairwise)
# Reference runtime: python (canonical)
[istftnet2_mb_1d2d]
peak_rms_max_diff = 0.005          # baseline 同等を要求 (1D-2D backbone のみ差し替え)
chromaprint_max_hamming = 32       # 同上
mel_spec_max_mse = 1.0e-3          # 同上
snr_min_db = 30.0                  # AI-13 pairwise SNR ≥ 30 dB の lower bound
pesq_min = 3.8                     # UTMOS proxy baseline ± 0.1 (参考値)
expected_p50_ms = 18.0             # Xeon E5-2650 v4 / 25 phoneme 英文 (target × 0.7)
expected_p50_ms_tolerance_pct = 10 # ±10% 以内で再現性確認
params_m = 0.83                    # 0.83M ± 0.05M (forward param count)
params_m_tolerance = 0.05
onnx_io_signature = "input:phoneme_ids[int64,B,T] / output:audio[float32,B,1,T]"
onnx_ops_allowed = ["Conv1d","Conv2d","Reshape","Transpose","Mul","Add","OnnxISTFT","PixelShuffle"]
onnx_ops_forbidden = ["ConvTranspose2d"]   # Risk R7: mobile EP CPU fallback 回避
```

`[mswavehax]` と `[fly_convnext6]` も同一スキーマで追加するが、 variant 固有値を pin:

- `[mswavehax]`: `snr_min_db = 25.0` (Risk R6 受容、 `n_fft=64 hop=16` の極短 FFT で 30 dB 維持困難、 variant-specific 緩和)、 `params_m = 0.332`、 `onnx_io_signature` は companion ONNX 用に `"input:mel_features[float32,B,80,T] / output:audio[float32,B,1,T]"`、 `mswavehax_pairing` で `pairs_with = "istftnet2_mb_1d2d"` を明示
- `[fly_convnext6]`: `snr_min_db = 30.0`、 `params_m = 0.63`、 `onnx_ops_allowed` から `PixelShuffle` を除外し `LayerNorm` / `GELU` を追加 (ConvNeXt 構造)、 `expected_p50_ms = 23.0` (× 0.85 conservative)

**既存 default 値 / 互換維持の制約 (G-1.9 後方互換):**

- `[meta] schema_version` は 1 → 2 に bump、 ただし `forward_compat_policy = "strict"` は維持。 v1.x 系の `scripts/audio_parity.py` が知らない新フィールド (`pesq_min` / `expected_p50_ms` / `params_m` 等) を**読み飛ばす**実装に AI-15 で改修するため、 schema bump 自体は AI-14 内で完結
- `[mb_istft_1d]` section は **本 PR では新規作成しない**。 既存の `[thresholds]` global section がそのまま `[mb_istft_1d]` 相当として機能している (canonical baseline) ため、 AI-15 で `scripts/check_audio_parity_baseline.py` が `[thresholds]` の値を SHA256 pinning する設計とする。 G-1.2 gate は「`[thresholds]` 値の不変性」をもって担保する
- `[runtimes]` / `[models]` の既存 entry は完全不変 (新 model entry は**追記のみ**)

**PR #222 / PR #537 との conflict 回避策 (計画 §3 Conflict Map):**

- vs PR #222: 計画 §3 で `audio-parity-contract.toml` は Conflict Map 9 ファイルに含まれていない (M5 内の AI-14 で扱う仕様変更は PR #222 の diff に含まれない)。 AI-17 で PR #222 rebase 後に ONNX I/O が `sid → speaker_embedding[192]` に変わる際、 各 variant section の `onnx_io_signature` 文字列のみ update する rebase 差分を AI-17 が提出する設計とする。 AI-14 時点では `phoneme_ids` ベースで pin
- vs PR #537: 計画 §3 で LOW (Python 3.13 binding 影響なし)。 ただし TF32-on / bf16-mixed default で 1e-3 magnitude drift が想定されるため、 各 section コメントに `# 測定環境: torch 2.2.0 / py 3.11.8 / CUDA 12.6 / cudnn 9.0 / fp32 only (PR #537 merge 前)` を明記し、 AI-16 が tolerance 緩和の根拠を持てるようにする

**設定 default 値、 新規 CLI フラグ:**

- 新規 CLI フラグなし (本チケットは仕様 file の変更のみ)
- `scripts/audio_parity.py` の挙動 default は `--variant mb_istft_1d` (既存 `[thresholds]` を読む既存挙動)、 `--variant istftnet2_mb_1d2d / mswavehax / fly_convnext6` で新 section を読む拡張は AI-15 の責務

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Spec Author (Lead) | 1 | TOML / piper-plus contract 規約 / audio metrics (PESQ / SNR / chromaprint) | 3 新 section の起草、 既存 `[thresholds]` との整合性確保、 G-1.2 / G-1.9 gate 制約を section コメントに反映、 1 commit atomic 化の責任者 |
| Measurement Engineer | 1 | Python / piper-plus benchmark harness (`tools/benchmark/`) / Xeon E5-2650 v4 環境 | AI-13 の実測値 (7 ランタイム pairwise SNR / mel-MSE / chromaprint Hamming) を再集計、 各 variant の tolerance 値を p99 から逆算、 `expected_p50_ms` 測定再現性確認 |
| ONNX Auditor | 1 | onnx / onnxruntime / opset / mobile EP (CoreML / NNAPI) op coverage | 3 variant の export 済み ONNX を `onnx.helper` で読み、 `onnx_ops_allowed` / `onnx_ops_forbidden` リストの実体準拠を assert、 ConvTranspose2d 不使用を独立検証 (Risk R7) |

合計 3 名。 全員が `audio-parity-contract.toml` の単一 PR に集約レビュー (3 人 reviewer 並列) する。 工数 1 日見積の内訳: Spec Author 0.5d (草案 + section コメント) + Measurement Engineer 0.3d (実測値再集計 + tolerance 逆算) + ONNX Auditor 0.2d (op set audit + cross-check)。

## 提供範囲 (Scope)

### 含むもの

- `docs/spec/audio-parity-contract.toml` への 3 新 section 追加 (`[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]`)
- `[meta] schema_version` の 1 → 2 bump と `referencing_scripts` 拡張 (AI-15 で実装される `scripts/check_audio_parity_baseline.py` を予告参照)
- `[models]` section への 3 新 entry 追加 (`css10_ja_1d_baseline` 既存維持 + 3 新 entry)
- 各 section の `onnx_io_signature` / `onnx_ops_allowed` / `onnx_ops_forbidden` リスト pin
- 各 section の測定環境コメント (torch / py / CUDA / cudnn / precision モード) 明記
- `pairs_with` field の導入 (mswavehax companion ONNX が istftnet2_mb_1d2d を acoustic として要求する pairing 関係)

### 含まないもの (Out of Scope)

- `[mb_istft_1d]` section の新規作成 (現状 `[thresholds]` が baseline canonical として機能、 AI-15 で SHA256 pinning 対象とする)
- `scripts/check_audio_parity_baseline.py` の実装 (AI-15 の責務)
- `.github/workflows/contract-gates.yml` への required check 統合 (AI-15)
- `scripts/audio_parity.py` の `--variant` 引数追加実装 (AI-15)
- ONNX I/O の `sid → speaker_embedding[192]` 変更反映 (M6 AI-17、 PR #222 rebase 後)
- bf16-mixed / TF32-on での tolerance 緩和 (M6 AI-16、 PR #537 merge 後)
- 7 ランタイムの companion ONNX load 経路 (M5 AI-13 既完了)
- HuggingFace upload URL への `models` entry 置換 (M6 AI-18)

## テスト項目

### Unit Tests

- `src/python/tests/test_audio_parity_contract.py::test_schema_version_bumped_to_2`
  - assert: `tomllib.load("docs/spec/audio-parity-contract.toml")["meta"]["schema_version"] == 2`
- `src/python/tests/test_audio_parity_contract.py::test_thresholds_baseline_unchanged`
  - assert: `[thresholds]` の 5 key (`peak_rms_max_diff` / `chromaprint_max_hamming` / `mel_spec_max_mse` / `snr_min_db` / `sample_rate`) が pinning 値と完全一致 (G-1.2 baseline 編集禁止 gate の dry-run)
- `src/python/tests/test_audio_parity_contract.py::test_three_new_sections_exist`
  - assert: `"istftnet2_mb_1d2d" in data` かつ `"mswavehax" in data` かつ `"fly_convnext6" in data`
- `src/python/tests/test_audio_parity_contract.py::test_new_sections_have_required_fields`
  - assert: 各 variant section が `snr_min_db / mel_spec_max_mse / chromaprint_max_hamming / peak_rms_max_diff / expected_p50_ms / params_m / onnx_io_signature / onnx_ops_allowed / onnx_ops_forbidden` の 9 key を必ず含む (forward-compat schema 強制)
- `src/python/tests/test_audio_parity_contract.py::test_mswavehax_pairs_with_istftnet2`
  - assert: `data["mswavehax"]["pairs_with"] == "istftnet2_mb_1d2d"` (companion ONNX pairing の宣言的整合性)
- `src/python/tests/test_audio_parity_contract.py::test_convtranspose2d_forbidden_in_all_variants`
  - assert: 3 variant 全てで `"ConvTranspose2d" in section["onnx_ops_forbidden"]` (Risk R7 mitigation)
- `src/python/tests/test_audio_parity_contract.py::test_mswavehax_snr_floor_relaxed`
  - assert: `data["mswavehax"]["snr_min_db"] == 25.0` かつ 他 2 variant は `30.0` (variant-specific 閾値の意図的緩和を明示)
- 既存 `src/python/tests/test_audio_parity.py` は **touch しない** (G-1.9 後方互換、 AI-15 で `--variant` 拡張時に新規ファイルで追加)

### E2E Tests

- `audio-parity-contract.toml` を実行入力とした smoke: 3 variant それぞれに対し、 AI-12 で生成された UTMOS proxy MOS 値が `pesq_min` を満たすか手動検算 (1 回限り、 AI-14 PR 時の eyeball review)
- 7 ランタイム pairwise SNR を AI-13 の出力 CSV (`tools/benchmark/results/pairwise_snr_2026-06-16.csv`) から再読込し、 各 variant section の `snr_min_db` が全 21 ペア (3 variant × 7 runtime) で達成可能であることを `python -c "import csv, tomllib; ..."` で検算
- Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs で 3 variant の p50 を再測定し、 各 section の `expected_p50_ms ± 10%` 内に収まることを確認 (CI 非実行、 ローカル測定値を `docs/reference/benchmark-results.md` に追記、 AI-15 の `check_audio_parity_baseline.py` が将来 gate 化)
- pre-commit hook `check-audio-parity-toml-syntax` で `tomllib.load()` が成功することを ensure (TOML 構文 error の早期検出)

### 受入基準 (Acceptance Criteria)

親計画 §4.6 / §5 の数値目標を contract として pin した状態で以下を満たす:

- `[mb_istft_1d]` (= 既存 `[thresholds]`) の 5 key 値が **完全不変** (SHA256 で pinning、 G-1.2 baseline gate)
- 3 新 section が同一スキーマで揃い、 必須 9 key が全て pin されている
- UTMOS proxy MOS: 各 variant section の `pesq_min` が baseline ± 0.1 以内 (`fly_convnext6` のみ ± 0.15 許容)
- CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文): `[istftnet2_mb_1d2d]` で `expected_p50_ms < 20.0` (target × 0.7、 README.md baseline 27ms から逆算)
- params: `[istftnet2_mb_1d2d]` で `params_m = 0.83 ± 0.05`、 `[mswavehax]` で `0.332 ± 0.02`、 `[fly_convnext6]` で `0.63 ± 0.05`
- 7 runtime smoke: AI-13 の pairwise SNR 実測値が、 各 section の `snr_min_db` を 21 ペア (3 variant × 7 runtime) で全達成 (`mswavehax` のみ 25.0、 他 30.0)
- ONNX op coverage: 3 variant 全てで `ConvTranspose2d` が `onnx_ops_forbidden` に明示され、 AI-15 の `scripts/check_onnx_op_coverage.py` が assert 可能な状態
- `tomllib.load(...)` で構文 error なし、 `forward_compat_policy = "strict"` 維持
- PR body checklist で「測定環境 (torch 2.2 / py 3.11 / CUDA 12.6 / fp32) を全 section コメントに明記済み」「`[thresholds]` 5 key 不変」「`pairs_with` 宣言済み」を機械 check

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

- **R6 (audio-parity baseline 誤書換による silent regression)** — 本チケットが M5 で対面する最大のリスク。 `[thresholds]` (= 現在の baseline) の 5 key を 1 文字でも変えると、 既存 `tools/benchmark/run.py` / `scripts/audio_parity.py` の挙動が silent に変化する。 AI-14 PR 時点では SHA256 pinning は AI-15 で実装されるため、 **AI-14 内では「目視 + pre-commit hook で `[thresholds]` 差分検出」のみの簡易 gate**で運用する (AI-15 完了までの 1.5 日間は人力ガード)
- **R7 (2D op の mobile EP CPU fallback)** — `[istftnet2_mb_1d2d]` の `onnx_ops_forbidden` に `ConvTranspose2d` を入れ忘れると、 将来の iOS CoreML / Android NNAPI でも CPU fallback が起きうる。 ONNX Auditor 役割が `onnx.helper` で実体準拠を独立検証することで二重チェックを確保
- **R5 (PR #537 TF32-on / bf16-mixed が招く 1e-3 magnitude drift)** — 各 section の tolerance 値は torch 2.2 / fp32 baseline で pin。 PR #537 merge 後に bf16-mixed default で 1e-3 magnitude drift が観測されたら、 各 section の `snr_min_db` / `mel_spec_max_mse` を緩める rebase 差分が M6 AI-16 で出る。 AI-14 PR 段階で「測定環境コメント」を section に明記しないと、 AI-16 が tolerance 緩和の根拠を見失う
- **schema_version bump の forward-compat 互換**: `schema_version = 1 → 2` bump に対して、 既存 `scripts/audio_parity.py` が schema_version の値を assert する gate を持っていれば AI-14 単独で red。 事前に `scripts/audio_parity.py:_validate_thresholds` を grep し、 schema_version 参照箇所の有無を確認する必要あり
- **tolerance 値の主観性**: `mswavehax` の `snr_min_db = 25.0` への緩和は AI-13 の実測値 (7 runtime pairwise SNR の最小値) を根拠とする必要がある。 AI-13 の `tools/benchmark/results/pairwise_snr_2026-06-16.csv` が未完成の場合、 AI-14 の tolerance 値は仮置きとなり M5 完了基準を満たさない (AI-13 完了を依存に明示している理由)
- **`[models]` section の 4 entry 化**: 既存 `multilingual_test_medium` / `tsukuyomi_6lang_v2` / `mb_istft_base` の 3 entry は維持し、 新 entry 4 つを末尾追加するが、 既存 entry を**並べ替えない** (TOML は順序不問だが diff レビューでノイズを増やさない配慮)

### レビュー項目 (チェックリスト)

- [ ] `[thresholds]` 5 key (peak_rms_max_diff / chromaprint_max_hamming / mel_spec_max_mse / snr_min_db / sample_rate) の値が**完全不変** (G-1.2 baseline 編集禁止)
- [ ] `[runtimes]` 7 entry の `id` / `cli` / `supports_dump_wav` が完全不変
- [ ] `[models]` 既存 3 entry の key / value が完全不変、 4 新 entry が末尾追記のみ
- [ ] 3 新 section (`[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]`) が必須 9 key を全て含む (forward-compat schema)
- [ ] 各 section の冒頭コメントに測定環境 (torch 2.2.0 / py 3.11.8 / CUDA 12.6 / cudnn 9.0 / fp32 only / PR #537 merge 前) を明記
- [ ] `ConvTranspose2d` が 3 variant 全ての `onnx_ops_forbidden` に明示 (Risk R7)
- [ ] `pairs_with` が `[mswavehax]` のみに含まれ、 値が `"istftnet2_mb_1d2d"` (companion ONNX pairing)
- [ ] `[meta] schema_version` が 1 → 2 に bump され、 `forward_compat_policy = "strict"` 維持
- [ ] `[meta] referencing_scripts` に `scripts/check_audio_parity_baseline.py` 追加 (AI-15 予告)
- [ ] `tomllib.load("docs/spec/audio-parity-contract.toml")` が構文 error なしに完走
- [ ] 既存 `src/python/tests/test_audio_parity.py` 等が **touch されていない** (G-1.9 後方互換)
- [ ] PR #222 rebase で `onnx_io_signature` の `phoneme_ids → speaker_embedding[192]` 同期更新が AI-17 で必要であることを PR body に明記
- [ ] PR #537 merge 後の bf16-mixed / TF32-on で tolerance 緩和が AI-16 で必要であることを section コメントに明記
- [ ] ONNX op coverage 実体準拠を ONNX Auditor 役割が `onnx.helper` で独立検証済み
- [ ] AI-13 の実測 pairwise SNR CSV (`tools/benchmark/results/pairwise_snr_2026-06-16.csv`) を根拠として `snr_min_db` 値を逆算した記録が PR body に残る

## 一から作り直すとしたら (Ticket-level rethinking)

このチケットを一から再設計するなら、 **「3 variant を 1 つの contract file に押し込む」 方針自体を疑い直す**ところから始めるべきだろう。 現状の親計画は `audio-parity-contract.toml` に `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` を併載する方針だが、 これは「contract file が変更されるたびに 3 variant 全部の review が走る」副作用がある。 代替案として **variant ごとに別 file 化 (`audio-parity-contract.toml` / `audio-parity-contract-istftnet2.toml` / `audio-parity-contract-mswavehax.toml` / `audio-parity-contract-fly.toml`)** にすれば、 PoC stage で fail する variant の section 更新が他 variant の contract review を blocking しない。 ただし「7 ランタイムが parse すべき contract file が 4 個に増える」副作用と、 AI-15 の SHA256 pinning が file 単位で 4 重になる工数増を踏まえると、 親計画の単一 file 集約案が pragmatically 正しい。 別 file 化案は M6 で 1 variant が dropped されたケースで「contract file ごと削除」が綺麗に効く副次的利点があるが、 それは「採否判定後の整理」フェーズで考えれば良い問題で、 PoC stage では単一 file の方が atomic review が効く。

第二に、 **`[mb_istft_1d]` section を明示的に新設するか、 既存 `[thresholds]` を canonical baseline として温存するか**の選択肢がある。 親計画と本チケットは後者 (`[thresholds]` を `[mb_istft_1d]` 相当として温存) を採るが、 これは「`[thresholds]` が global default」 という現行スキーマの semantic を変えないために選んだ妥協である。 代替案として、 **`[thresholds]` を deprecation comment 付きで残しつつ `[mb_istft_1d]` を新設 + 同値 copy** すれば、 contract reader 視点で「全 variant が同じ section 構造を持つ」可読性が上がる。 ただし `[thresholds]` を読む既存 `scripts/audio_parity.py` の挙動を変えないために `[thresholds]` を temporarily 残す必要があり、 「同値 copy が 2 箇所」 という drift 源を新規に作ることになる。 PoC stage では「`[thresholds]` を `[mb_istft_1d]` の暗黙 alias とする」現案が、 既存 script への影響を 0 にする点で堅い。 M6 完了後 (採否判定後) に `[thresholds]` → `[mb_istft_1d]` rename refactor を別 PR で扱う方が、 contract reader UX も script 互換性も両立する。

第三に、 **`pairs_with` field の semantic** を「declarative pairing 宣言のみ」 にとどめるか、 「ランタイムが companion ONNX load 時に必ず参照する hard 制約」 にするかの選択がある。 本チケットは前者 (宣言のみ、 enforcement は AI-15 以降の機械 check) を採るが、 後者 (hard 制約) にすれば「companion ONNX を acoustic model なしで load しようとした際に runtime error」 という強い保証が得られる。 ただし、 hard 制約化は 7 ランタイム全部に `pairs_with` の parse 実装を要求し、 ABI 互換性のリスク (R4) を増やす。 PoC stage では declarative 宣言にとどめ、 ランタイム enforcement は M6 統合判定後に別チケットで扱うのが trade-off として現実的。 採用案を「現実解」 と位置付けつつ、 PoC stage で「pairs_with = ... の hard enforcement 案」 を section コメントに残しておけば、 統合判定 PR で議論の起点として使える。

## 後続タスクへの連絡事項

AI-15 (regression guard CI gate 整備) への引き渡し物:

- **canonical pinning file 確定**: `docs/spec/audio-parity-contract.toml` の commit hash と内容 SHA256 を AI-15 開始時点で固定。 AI-15 は `scripts/check_audio_parity_baseline.py` 内で `[thresholds]` section の値を hardcode で hold し、 `tomllib.load(...)` 結果と比較する設計。 pinning は値の SHA256 (file 全体ではない) で行う
- **`[thresholds]` section が `[mb_istft_1d]` の暗黙 alias** であることを AI-15 で明示 enforcement。 `scripts/check_audio_parity_baseline.py` のドキュメント文字列に「`[thresholds]` の 5 key は M5 完了時点で `[mb_istft_1d]` baseline として絶対不変」 と明記する
- **schema_version = 2 の forward-compat 挙動**: 既存 `scripts/audio_parity.py:_validate_thresholds` が schema_version の値を assert している箇所があれば、 AI-15 で `schema_version >= 1` に緩める update を同 PR で行う (`forward_compat_policy = "strict"` 維持しつつ、 未知フィールドの読み飛ばしを許容)
- **3 新 section の `expected_p50_ms` gate 化**: AI-15 の `scripts/check_audio_parity_baseline.py` が `--variant istftnet2_mb_1d2d` で起動された時、 ローカル測定結果と各 section の `expected_p50_ms ± expected_p50_ms_tolerance_pct%` 比較を assert する設計。 CI 非実行 (Xeon E5-2650 v4 限定) で、 ローカル `make benchmark-canonical` 経由で呼ぶ
- **`onnx_ops_forbidden` gate 化**: AI-15 の `scripts/check_onnx_op_coverage.py` が `--variant <name>` 引数で起動し、 該当 ONNX を `onnx.load(...)` して `onnx_ops_forbidden` リストに含まれる op が現れたら fail。 3 variant 全てで `ConvTranspose2d` 不在を assert (Risk R7)
- **`.github/workflows/contract-gates.yml` への required check 統合**: AI-15 で `audio-parity-baseline` job を新設、 `paths: docs/spec/audio-parity-contract.toml` で trigger、 PR で `[thresholds]` 5 key が変更されたら fail。 required status check 昇格は AI-15 完了時に branch protection rule に追加 (`docs/reference/branch-protection-history.md` に history 追記)
- **暫定値とパス**:
  - `pesq_min` 値: AI-12 の UTMOS proxy MOS 実測値から逆算 (200 test utt 平均 - 0.1 を下限)。 AI-14 PR 時点で AI-12 が未完了なら、 AI-13 baseline の MOS 値で仮置きし AI-15 で再計算
  - `snr_min_db` 値: AI-13 の `tools/benchmark/results/pairwise_snr_2026-06-16.csv` から逆算 (7 ランタイム pairwise の最小値を切り下げ)。 `mswavehax` のみ 25.0 (variant-specific 緩和)
  - `expected_p50_ms` 値: ローカル Xeon E5-2650 v4 で warmup 5 + 30 runs / 25 phoneme 英文の p50 実測。 CI 非再現性のため `tolerance_pct = 10` で緩める
- **PR #222 rebase 時の注意箇所** (M6 AI-17 で対処、 AI-14 → AI-15 間では監視のみ):
  - 各 variant section の `onnx_io_signature` 文字列を `"input:phoneme_ids[int64,B,T]"` → `"input:speaker_embedding[float32,B,192]"` に同期更新
  - `[models]` の 4 entry の HF repo に PR #222 由来の 200 epoch 再学習 ckpt が反映されたら URL を update
- **PR #537 merge 後の注意箇所** (M6 AI-16 で対処):
  - 各 section コメントの「fp32 only (PR #537 merge 前)」 を 「bf16-mixed / TF32-on (PR #537 merge 後)」 に更新
  - 各 section の `snr_min_db` / `mel_spec_max_mse` を 1e-3 magnitude drift に応じて緩める rebase 差分を AI-16 が提出。 同 commit で `scripts/check_audio_parity_baseline.py` の SHA256 pinning 値も atomic 更新

## 関連ドキュメント

- 親マイルストーン: [../milestones/M5-runtime-abi-parity.md](../milestones/M5-runtime-abi-parity.md)
- 親計画 §6 / §4.6 / §3: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査統合: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 編集対象 spec: [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml)
- 関連 spec:
  - [../../spec/ort-session-contract.toml](../../spec/ort-session-contract.toml) — 7 ランタイム ORT セッション設定 (companion ONNX warmup / `.opt.onnx` cache の cross-reference)
  - [../../spec/short-text-contract.toml](../../spec/short-text-contract.toml) — Strategy A/B/C (companion ONNX 切替時の dynamic scale 影響評価対象)
  - [../../spec/text-splitter-contract.toml](../../spec/text-splitter-contract.toml) — 編集禁止 (decoder-agnostic 維持の確認用 reference)
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — M6 AI-17 で `onnx_io_signature` 同期
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — M6 AI-16 で tolerance 緩和トリガー
- 論文:
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023)
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025)
  - [FLY-TTS PDF (Guo Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) ConvNeXt × 6 + iSTFT

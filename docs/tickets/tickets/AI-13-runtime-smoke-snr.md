# AI-13: 7 ランタイム smoke + pairwise SNR 検証

## メタ情報

- ID: AI-13
- 親マイルストーン: [M5](../milestones/M5-runtime-abi-parity.md)
- 工数見積: 3 日
- 依存チケット: AI-12 (`tools/benchmark/` に 3 variant 追加 + UTMOS proxy MOS)
- 後続チケット: AI-14 (`audio-parity-contract.toml` に新 variant section 追加)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-13 / §4.6 Benchmarks 目標値 / §3 Conflict Map](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは M5 の中核検証フェーズであり、 M2 / M3 / M4 で生成された 3 つの新 variant ONNX (istftnet2-mb-1d2d / fly-convnext6 / mswavehax companion) が piper-plus を支える 7 ランタイム (Python / Rust / Go / C# / WASM / C++ / C-API) で **ABI を壊さずに走り、 かつ Python reference との pairwise SNR ≥ 30 dB を満たす** ことを確定させる。 親計画 §1 が掲げた「核心トレードオフ 2: A-2 dual vocoder の ONNX I/O 二重同期回避」を実証する場であり、 companion ONNX 方式が 7 ランタイム横断で耐えるかどうかをここで決定する。

上流の AI-12 からは `tools/benchmark/models.yaml` の 3 variant entry + `proxy_mos.py` を引き継ぎ、 Python reference 音声を canonical として確定済みの状態でスタートする。 本チケットは Python reference を基準に他 6 ランタイムを並走させ、 pairwise SNR を計算 + 出力 shape `[1, 1, T]` float32 を assert する。 下流の AI-14 へは 7 ランタイム実測の SNR / PESQ tolerance 値を渡し、 それを `audio-parity-contract.toml` の `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` section に pin させる。

加えて本チケットは「ABI 互換維持の現実的設計テスト」の役割を担う。 各ランタイムで companion ONNX を load する経路は新規だが、 既存 constructor / `PiperVoice::new(...)` シグネチャは一切変更しない (R4 mitigation)。 この前提が 7 ランタイム実装段階で破綻しないかどうかを実装フェーズで早期に検知する位置づけでもある。

## 実装内容の詳細

### 編集対象ファイル + 関数 + 概略 LoC

#### Python (reference 基準、 canonical 生成)

- **新規** `tools/benchmark/pairwise_snr.py` (~250 LoC)
  - `compute_pairwise_snr(reference_wav: np.ndarray, candidate_wav: np.ndarray) -> float` — 振幅整合 + zero-padding + 10 \* log10 比
  - `run_runtime_smoke(runtime: str, variant: str, model_path: Path, test_text: str) -> RuntimeSmokeResult` — 各ランタイムの synth CLI を subprocess で叩き wav 取得
  - CLI: `--reference-runtime python --candidates rust,go,csharp,wasm,cpp,capi --variant istftnet2_mb_1d2d --threshold-db 30.0`
  - 非 0 exit を SNR < 30 dB で返却 → CI gate と integrate
- **新規** `src/python_run/tests/test_wavehax_runtime.py` (~120 LoC)
  - `test_python_companion_onnx_load` / `test_python_pairwise_snr_self_consistency` (reference 自己比較で ∞ dB 近く)
- **新規** `tools/benchmark/data/canonical_test_set.jsonl` (~20 LoC、 5 test utt + speaker_id)

#### Rust (`src/rust/piper-core/`)

- **新規** `src/rust/piper-core/src/wavehax.rs` (~180 LoC)
  - `pub struct WavehaxSession { session: ort::Session }` + `pub fn load(path: &Path) -> Result<Self>`
- **編集** `src/rust/piper-core/src/lib.rs` (`PiperVoice` impl block)
  - **新規メソッド** `pub fn new_with_wavehax(model_path: &Path, wavehax_path: &Path, config: ModelConfig) -> Result<Self>` (~30 LoC)
  - 既存 `pub fn new(model_path: &Path, config: ModelConfig)` シグネチャは絶対に touch しない (R4)
- **新規** `src/rust/piper-core/tests/test_wavehax_smoke.rs` (~80 LoC)
  - `#[test] fn test_companion_onnx_load_shape` / `fn test_pairwise_snr_against_python_reference`

#### Go (`src/go/piperplus/`)

- **新規** `src/go/piperplus/wavehax.go` (~140 LoC)
  - Option pattern: `func WithWavehaxModel(path string) Option` + `func (v *PiperVoice) hasWavehax() bool`
- **編集** `src/go/piperplus/voice.go` (`NewPiperVoice` 関数)
  - `opts ...Option` variadic 引数化、 既存 signature は backward-compat (空 opts で従来挙動)
- **新規** `src/go/piperplus/wavehax_test.go` (~70 LoC)
  - `func TestWavehaxCompanionLoad(t *testing.T)` / `func TestPairwiseSNRAgainstPython(t *testing.T)`

#### C# (`src/csharp/PiperPlus.Core/`)

- **新規** `src/csharp/PiperPlus.Core/Wavehax/WavehaxSession.cs` (~130 LoC)
  - `internal sealed class WavehaxSession : IDisposable`
- **編集** `src/csharp/PiperPlus.Core/PiperVoice.cs` (constructor)
  - **optional named arg** 追加: `public PiperVoice(string modelPath, ModelConfig config, string? wavehaxModelPath = null)` (R4 / `feedback_csharp_path_join.md` 準拠で `Path.Join` 使用)
- **新規** `src/csharp/PiperPlus.Core.Tests/Wavehax/WavehaxSmokeTests.cs` (~100 LoC)
  - `[Fact] public void CompanionOnnxLoadsAndReturnsExpectedShape()` / `[Fact] public async Task PairwiseSnrAgainstPythonReferenceExceeds30Db()`

#### WASM (`src/wasm/openjtalk-web/`)

- **新規** `src/wasm/openjtalk-web/src/wavehax.js` (~120 LoC)
  - `export class WavehaxSession { async load(modelPath) {...} }`
- **編集** `src/wasm/openjtalk-web/src/index.js` (`PiperVoice` constructor)
  - constructor option 追加: `new PiperVoice({ modelPath, configPath, wavehaxModelPath })` (既存 `{ modelPath, configPath }` 互換)
- **新規** `src/wasm/openjtalk-web/test/js/wavehax.smoke.test.js` (~80 LoC)

#### C++ + C-API (`src/cpp/`)

- **新規** `src/cpp/wavehax.{hpp,cpp}` (~150 LoC)
  - `class WavehaxSession`
- **編集** `src/cpp/piper_plus.h`
  - **新 C-API entry** `PIPER_PLUS_API piper_plus_voice_t * piper_plus_voice_load_with_wavehax(const char* model_path, const char* wavehax_path, const piper_plus_config_t* config);` (既存 `piper_plus_voice_load(...)` は absolutely touch しない)
- **新規** `src/cpp/tests/test_c_api_wavehax.cpp` (~100 LoC)
  - `TEST(WavehaxSmoke, CompanionOnnxLoad)` / `TEST(WavehaxSmoke, PairwiseSnrAgainstPython)`
- **編集** `cmake/PiperPlusShared.cmake`
  - `wavehax.cpp` を target sources に追加 (既存 target ABI version は不変)

### PR #222 / #537 conflict 回避策

親計画 §3 Conflict Map の以下行を最も重視する:

- 「**7 ランタイム inference (Rust/C#/Go/WASM/C++/C-API)** | A-2 companion ONNX load、 ABI 互換維持 | **HIGH** (PR #222 sid→speaker_embedding[192]) | LOW (Python 3.13 binding 影響なし) | **PR #222 と同時 sync** (二重同期回避)」 (§3 7 行目)
- 「ONNX I/O 不変 (PR #222 と二重同期回避)」 (§4.2 互換性制約)

本チケットは A-2 companion ONNX の **load 経路のみ** を 7 ランタイムに追加し、 ONNX I/O 自体 (sid / speaker_embedding 等の入力テンソル形状) は変更しない。 PR #222 が merge された後の AI-17 で sid → speaker_embedding[192] 変更を 7 ランタイム同期する際、 companion ONNX 側にも同じ I/O 変更が `export_onnx.py --decoder-branch wavehax` 経路で自動追従されることを前提に、 本チケットでは「load 経路の追加」だけに専念して **PR #222 7 ランタイム同期 diff に二重同期を起こさない**。

PR #537 は本チケットの対象ファイルとの code 衝突 NONE。 ただし pytest 9 fixture deprecation が `test_wavehax_runtime.py` の `tmp_path` fixture 使用に影響する可能性があるので、 fixture の `tmp_path` は legacy `tmpdir` 形式を使わず、 pytest 9 互換の `tmp_path: pathlib.Path` 引数形式で書く。

### 設定 default 値 / 新規 CLI フラグ

- 全ランタイムで wavehax は **opt-in** (default 無効)。 companion ONNX path を渡した場合のみ session 切替が起きる。
- `tools/benchmark/pairwise_snr.py` のデフォルト `--threshold-db 30.0` (M5 milestone exit criteria 準拠)
- `pairwise_snr.py --variant-specific-threshold mswavehax=25` で variant 別閾値 (M5 一から作り直すとしたら §3 で議論された pragmatic 緩和案、 default は 30.0 統一)

### 疑似コード (Rust new_with_wavehax)

```rust
impl PiperVoice {
    // 既存 (絶対 touch しない)
    pub fn new(model_path: &Path, config: ModelConfig) -> Result<Self> { ... }

    // 新規 (R4 mitigation: 既存 new を呼び出して wavehax session を後付け)
    pub fn new_with_wavehax(
        model_path: &Path,
        wavehax_path: &Path,
        config: ModelConfig,
    ) -> Result<Self> {
        let mut voice = Self::new(model_path, config)?;
        voice.wavehax = Some(WavehaxSession::load(wavehax_path)?);
        Ok(voice)
    }

    pub fn synthesize(&self, text: &str) -> Result<Vec<f32>> {
        let phoneme_ids = self.phonemize(text)?;
        // streaming threshold で session 切替
        if let Some(ref wavehax) = self.wavehax {
            if phoneme_ids.len() <= 25 { return wavehax.infer(&phoneme_ids); }
        }
        self.dec.infer(&phoneme_ids)
    }
}
```

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|----------|---------|
| Integration Lead | 1 | Python + ONNX Runtime + 7 ランタイム全般理解 | `pairwise_snr.py` 設計と canonical 化、 SNR 計算ロジック、 7 ランタイム subprocess CLI 呼出 harness、 各担当のレビュー統合 |
| Rust + Go Engineer | 1 | Rust (ort crate / cargo workspace) + Go (Option pattern / cgo 不要部分) | `wavehax.rs` + `new_with_wavehax`、 `wavehax.go` + Option pattern、 各 unit test |
| C# + WASM Engineer | 1 | C# 10 + xUnit v3 + JS/TS + jest + ort-web | `WavehaxSession.cs` + optional named arg + Path.Join 厳守、 `wavehax.js` + constructor option、 ジェスト/xUnit smoke |
| C++ + C-API Engineer | 1 | C++17 + CMake + ONNX Runtime C++ API + C ABI 安定性 | `wavehax.{hpp,cpp}` + 新 C-API entry `piper_plus_voice_load_with_wavehax`、 CMake target 編集、 ctest smoke |
| Test Engineer | 1 | pytest + GitHub Actions matrix + audio DSP (SNR / PESQ 基礎) | `test_wavehax_runtime.py` 整備、 7 ランタイム × 3 variant matrix CI job 設計 (continue-on-error fail allowance 含む)、 canonical_test_set.jsonl 用意 |

合計 5 名。 7 ランタイムを言語ペアで束ねることで、 後続 AI-14 への引き継ぎ時に「ランタイム × variant 21 組合せの実測 SNR 表」を 1 人が責任を持って Integration Lead として集約する設計。 単独メンテナ体制を踏まえると、 単一エンジニアが 5 役を順次回す現実シナリオも想定 (M5 一から作り直すとしたら §4 の論点)。

## 提供範囲 (Scope)

### 含むもの

- `tools/benchmark/pairwise_snr.py` 新規 (Python reference を canonical とした 7 ランタイム SNR 計算)
- `tools/benchmark/data/canonical_test_set.jsonl` 新規 (5 test utt の固定 input)
- Rust: `src/rust/piper-core/src/wavehax.rs` + `new_with_wavehax` メソッド + smoke test
- Go: `src/go/piperplus/wavehax.go` + Option pattern + test
- C#: `src/csharp/PiperPlus.Core/Wavehax/` + optional named arg constructor + xUnit test
- WASM: `src/wasm/openjtalk-web/src/wavehax.js` + constructor option + jest test
- C++ / C-API: `src/cpp/wavehax.{hpp,cpp}` + 新 entry `piper_plus_voice_load_with_wavehax` + ctest
- Python: `src/python_run/tests/test_wavehax_runtime.py` (smoke + 自己 SNR sanity)
- GitHub Actions matrix CI job (7 ランタイム × 3 variant = 21 組合せ、 continue-on-error 付き)

### 含まないもの (Out of Scope)

- `audio-parity-contract.toml` への新 variant section 追加 (AI-14 の責務)
- `scripts/check_audio_parity_baseline.py` の G-1.2 gate 実装 (AI-14 / AI-15 の責務)
- `scripts/check_onnx_op_coverage.py` の ConvTranspose2d 不使用 audit (AI-15 の責務)
- iOS CoreML / Android NNAPI 実機 EP smoke (PoC 範囲外、 R7 mitigation)
- PR #222 の sid → speaker_embedding[192] 変更同期 (AI-17 の責務、 ただし companion ONNX 経路を pre-isolation しておく)
- `audio-parity-contract.toml` baseline 値の pin 化 / SHA256 計算 (AI-14)
- `text_splitter.py` への streaming 閾値ロジック実装 (AI-11 / decoder-agnostic 維持)
- `README.md` の 27ms benchmark 再測定 (AI-15 範囲 / `tools/benchmark/run_canonical.sh` 経由)

## テスト項目

### Unit Tests

- `src/python_run/tests/test_wavehax_runtime.py::test_python_companion_onnx_load`
  - assert: `wavehax_session = WavehaxSession.load(path)` が `ort.InferenceSession` を返し、 input names が `['input_phonemes', 'scales']` を含む
- `src/python_run/tests/test_wavehax_runtime.py::test_python_pairwise_snr_self_consistency`
  - assert: `compute_pairwise_snr(ref, ref) > 100.0` (自己比較で 100 dB 超、 浮動小数誤差の sanity)
- `src/python_run/tests/test_wavehax_runtime.py::test_streaming_threshold_switch`
  - assert: 25 phoneme 以下で wavehax session、 26 phoneme 以上で MB-iSTFT session が呼ばれる
- `src/rust/piper-core/tests/test_wavehax_smoke.rs::test_companion_onnx_load_shape`
  - assert: `voice.synthesize("こんにちは")` の output shape が `[1, 1, T]` かつ `T > 0`
- `src/rust/piper-core/tests/test_wavehax_smoke.rs::test_pairwise_snr_against_python_reference`
  - assert: `compute_snr(python_ref_wav, rust_wav) >= 30.0`
- `src/go/piperplus/wavehax_test.go::TestWavehaxCompanionLoad`
  - assert: `NewPiperVoice(path, WithWavehaxModel(wavehax_path))` が `*PiperVoice` を返す
- `src/go/piperplus/wavehax_test.go::TestPairwiseSNRAgainstPython`
  - assert: `snr >= 30.0` (Python reference との比較)
- `src/csharp/PiperPlus.Core.Tests/Wavehax/WavehaxSmokeTests.cs::CompanionOnnxLoadsAndReturnsExpectedShape`
  - assert: `output.Shape.SequenceEqual(new[] { 1, 1, T })` かつ `output.Dtype == typeof(float)`
- `src/csharp/PiperPlus.Core.Tests/Wavehax/WavehaxSmokeTests.cs::PairwiseSnrAgainstPythonReferenceExceeds30Db`
  - assert: `snr >= 30.0` (xUnit v3 `Assert.True(snr >= 30.0)`)
- `src/wasm/openjtalk-web/test/js/wavehax.smoke.test.js::"loads companion ONNX and returns float32 [1,1,T]"`
  - assert: `expect(audio.shape).toEqual([1, 1, T])` (jest)
- `src/wasm/openjtalk-web/test/js/wavehax.smoke.test.js::"pairwise SNR against Python reference exceeds 30 dB"`
  - assert: `expect(snr).toBeGreaterThanOrEqual(30.0)`
- `src/cpp/tests/test_c_api_wavehax.cpp::CompanionOnnxLoad`
  - assert: `EXPECT_NE(voice, nullptr)` + `EXPECT_EQ(output_shape[0], 1)` + `EXPECT_EQ(output_shape[1], 1)`
- `src/cpp/tests/test_c_api_wavehax.cpp::PairwiseSnrAgainstPython`
  - assert: `EXPECT_GE(snr, 30.0)`

### E2E Tests

- 7 ランタイム × 3 variant matrix smoke (GitHub Actions matrix 21 job 並列、 continue-on-error)
  - 各 job: `tools/benchmark/pairwise_snr.py --reference-runtime python --candidate <runtime> --variant <variant>` を実行、 SNR と exit code を集約
- `tools/benchmark/pairwise_snr.py` 単体実行で 7 ランタイム全合算 report 出力 (markdown 表 + JSON 機械可読)
- ONNX export round-trip: companion ONNX を再 export → load → infer で wav が同一 (Python 内で)
- WandB audio log: pairwise SNR を WandB scalar log + 生成 wav 5 件を Audio log
- canonical benchmark (Xeon E5-2650 v4 / 25 phoneme 英文): mswavehax companion で sub-80ms streaming chunk を観測 (M4 exit criteria 準拠)

### 受入基準 (Acceptance Criteria)

親計画 §4.6 から該当数値目標を引用:

- **7 ランタイム smoke**: Python / Rust / Go / C# / WASM / C++ / C-API すべてで `[1, 1, T]` float32 出力 (T > 0)
- **pairwise SNR**: Python reference との比較で **≥ 30 dB** (3 variant 全てで)
- **CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs)**: baseline 27ms に対して istftnet2-mb p50 < 20ms (target × 0.7、 §4.6 引用)
- **MOS (UTMOS proxy)**: AI-12 で計測済みの proxy MOS が baseline ± 0.1 以内 (AI-13 では再確認のみ)
- **footprint**: A-1 0.83M params ± 0.05M / A-2 companion 0.332M params が ONNX size から逆算可能
- **ABI 互換**: 既存 `PiperVoice::new(...)` / `piper_plus_voice_load(...)` シグネチャ完全不変、 7 ランタイム全てで legacy code path がコンパイル + テスト pass
- **matrix CI**: 7 × 3 = 21 組合せのうち、 mswavehax 行のみ continue-on-error 許容 (PoC 段階で fail allowance、 M6 で required check 昇格)

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

親計画 §7 Risk Register から該当:

- **R4 (companion ONNX の ABI 誤認、 PR #222 rebase 後の ONNX I/O 二重同期)** — 本チケットが直接対面するリスク。 mitigation として 7 ランタイムすべての companion ONNX load 経路を「optional named arg / 新メソッド / Option pattern / 新 C-API entry」に統一し、 既存 constructor / `PiperVoice::new(...)` シグネチャは一切変更しない。 ONNX I/O も companion ONNX を含めて contract に固定し、 M6 で PR #222 の 7 ランタイム同期 diff に乗せる際は 1 回で完了させる。
- **R5 (PR #537 pytest 9 fixture deprecation)** — `test_wavehax_runtime.py` の fixture は `tmp_path: pathlib.Path` 形式で書く (legacy `tmpdir` を避ける)。
- **R7 (mobile EP CPU fallback)** — 本チケットでは iOS CoreML / Android NNAPI 実機 smoke は範囲外だが、 ConvTranspose2d 完全不使用を AI-15 が assert する前提で companion ONNX の op set を変更しない。

チケット固有の細かい懸念:

- **wavehax の `n_fft=64, hop=16` という極めて短い FFT 設定が招く数値精度差** — 30 dB を割る可能性。 M5 一から作り直すとしたら §3 で議論された「variant-specific 閾値」を pragmatic 緩和案として保持 (`--variant-specific-threshold mswavehax=25`)、 default は 30.0 統一とし mswavehax のみ continue-on-error。
- **subprocess CLI 呼出の overhead** — 各ランタイムの synth CLI を `subprocess.run` で叩く設計だと、 21 組合せ × 5 test utt = 105 subprocess 起動で CI 時間が膨らむ。 mitigation として GitHub Actions matrix で 21 job 並列実行 (各 job 内は 5 utt 直列で OK)。
- **macOS local test の `@rpath` 問題** (CLAUDE.md ローカルテスト注記) — `cargo test --workspace` は piper-plus-python で SIGABRT する。 per-crate `cargo test -p piper-plus` 推奨を doc に明記。
- **npm の `file:` link lockfile** — WASM smoke で `npm install "@piper-plus/g2p@file:../g2p"` を CI 内で実行する際、 lockfile-size gate を回避するため generated lockfile は commit しない。
- **ECAPA-TDNN / speaker_embedding 入力経路と wavehax の相互作用未検証** — 本チケットでは speaker_id 経路のみ smoke、 speaker_embedding 経路は AI-17 以降で。

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換): 既存 `PiperVoice::new(...)` を呼ぶ全 7 ランタイム test が touch なしで pass する
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止): AI-13 範囲で `audio-parity-contract.toml` を編集しない (AI-14 の責務)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避): companion ONNX の input / output names と shapes を MB-iSTFT base と同一に保つ
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (本チケットでは pre-PR-537 baseline で測定、 AI-14 / AI-16 で tolerance 更新)
- [ ] 既存 `PiperVoice::new(...)` / `piper_plus_voice_load(...)` シグネチャ完全不変 (R4 mitigation の中核)
- [ ] C# は `Path.Join` 強制、 `Path.Combine` 禁止 (`feedback_csharp_path_join.md` 準拠)
- [ ] Go の variadic Option pattern は空 opts で従来挙動を保つ (backward-compat 検証)
- [ ] C-API: 新 entry `piper_plus_voice_load_with_wavehax(...)` のみ追加、 既存 `piper_plus_voice_load(...)` の ABI version は不変
- [ ] pytest fixture は pytest 9 互換 (`tmp_path: pathlib.Path`、 legacy `tmpdir` 不使用)
- [ ] WASM の lockfile は commit しない (lockfile-size gate)
- [ ] GitHub Actions matrix で mswavehax 行のみ continue-on-error 許容、 他は required
- [ ] pairwise SNR 計算ロジックの自己比較 sanity (`compute_pairwise_snr(x, x) > 100.0`)
- [ ] canonical test set 5 utt は固定 seed + 固定 noise_scale (0.667) で再現可能

## 一から作り直すとしたら (Ticket-level rethinking)

本チケットを一から設計し直すとすると、 最初に問い直すべきは **「Python reference を canonical とする pairwise SNR 設計」が本当に正しいか** である。 採用案は Python reference 音声を 1 セット生成し、 他 6 ランタイム生成音声と SNR を比較する片方向比較設計だが、 これには Python 自体が ABI 不整合の被害者になる ONNX Runtime 側のバグを検知できないという盲点がある。 代替案として **「完全な pairwise マトリクス (7 × 7 = 49 SNR 値)」** を計算すると、 「Python が異常で他 6 が正常」のようなケースも検知できる。 ただし matrix は CI 時間が 2 倍以上に膨らみ、 採否判定の数値根拠としてオーバースペックになる。 piper-plus の他 contract gate (audio-parity SNR) が Python reference を canonical 化しているプロジェクト全体の方針と整合する片方向設計が現実解だが、 「**全 7 自己 SNR sanity (`compute_pairwise_snr(x, x) > 100.0`)**」を加えるだけで Python ORT バグの早期発見 cost を取り戻せる (本チケットの test 設計に反映済み)。

第二に **「optional named arg / 新メソッド / Option pattern / 新 C-API entry」を 7 ランタイムごとに ad-hoc に選ぶ採用案** は、 一見現実的だが「7 ランタイムの ABI 拡張パターンを統一する機会を放棄している」とも言える。 代替案として、 7 ランタイムすべてで **builder pattern** (例: `PiperVoice::builder().model_path(...).wavehax_model_path(...).build()`) を統一採用すれば、 PR #222 以降の更なる拡張 (speaker_embedding / DINO 等) でも同パターンで追加できる。 しかし builder pattern は 7 ランタイムすべてで既存 constructor を deprecate する破壊的変更を伴うため、 「既存 ABI 完全不変 (R4 mitigation の中核)」と両立しない。 現実解としては「言語慣用に従う ad-hoc 拡張」が piper-plus の保守的方針 (`feedback_conservative_changes.md`) に整合しており、 builder pattern は M6 以降の v2.0.0 メジャー breaking 時の検討題に回す。

第三に **「3 日見積」 が楽観的かどうか** を再考する必要がある。 M5 milestone の一から作り直すとしたら §4 でも指摘されている通り、 「test 環境準備のために 1 ランタイムあたり 0.5 日」 の hidden cost が 7 ランタイムで 3.5 日相当発生する可能性がある (macOS `@rpath` / npm `file:` link / cargo workspace 等)。 代替案として **「Python + 1 ランタイムだけで pairwise SNR harness を確立し、 他 5 ランタイムは Issue として展開」** すれば本チケットを 1.5 日に圧縮できるが、 M5 exit criteria (全 7 runtime で smoke) を満たさないため AI-14 を blocking する。 現実解は「3 日見積を 4-5 日にスライドする」覚悟で着手し、 後続 AI-14 / AI-15 の余裕で吸収する。 整数チケットとしての 3 日見積を保ちつつ、 PR body の Risk Level に「工数 over の可能性」を明記して透明性を保つ設計が pragmatic。

## 後続タスクへの連絡事項

AI-14 (`audio-parity-contract.toml` に新 variant section 追加) への引き渡し:

- **実測 SNR / PESQ 値**: `tools/benchmark/pairwise_snr.py --report-json out/pairwise_snr.json` で 7 ランタイム × 3 variant の実測 SNR を JSON 出力。 AI-14 はこれを読み込み、 `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` 各 section の `tolerance_snr_db` / `tolerance_pesq` を pin する。
- **canonical test set**: `tools/benchmark/data/canonical_test_set.jsonl` (5 utt + speaker_id + 固定 noise_scale 0.667) を **AI-14 / AI-15 でも継承**。 別の test set を新規作成しないこと (再現性破壊回避)。
- **暫定閾値**: pairwise SNR 30 dB は全 variant 共通の M5 exit criteria 値。 ただし mswavehax は `n_fft=64, hop=16` の数値精度差で 28-30 dB に落ちる可能性があるため、 AI-14 で `[mswavehax]` section の `tolerance_snr_db` を 25.0 に緩める判断余地を残す (`--variant-specific-threshold mswavehax=25` で本チケットの実測値を取得済み)。
- **companion ONNX 仮置きパス**: M4 で生成された `/data/piper/output-tsukuyomi-finetune-6lang-v2/tsukuyomi.wavehax.onnx` を `tools/benchmark/models.yaml` の `mswavehax-companion` entry に絶対パスで指す **暫定**。 M6 AI-18 で HF (`ayousanz/piper-plus-tsukuyomi-chan` の新規 file) に upload された URL に置き換える。
- **PR #222 rebase 時に注意すべき箇所**: 本チケットで追加した 7 ランタイムの companion ONNX load 経路 (Rust `new_with_wavehax` / Go Option pattern / C# optional named arg / WASM constructor option / C-API 新 entry) は、 PR #222 の sid → speaker_embedding[192] 変更時に **同一経路を辿る** ように設計済み。 AI-17 で PR #222 同期する際は `export_onnx.py --decoder-branch wavehax` を companion ONNX 経路でも呼び、 input names を `speaker_embedding[192]` に統一する。 7 ランタイム × 2 ONNX = 14 load 経路の同期を **1 回の sync PR で完了** させる。
- **CI matrix 状態**: GitHub Actions の 7 × 3 = 21 job matrix のうち、 mswavehax 行のみ `continue-on-error: true` で配置。 AI-15 で regression guard gate を required check に昇格させる際、 mswavehax 行を required に上げるか否かは AI-14 が実測 SNR を確認した上で判断する (M5 milestone exit criteria の `[mswavehax]` tolerance pinning と連動)。
- **WandB 実験記録**: 本チケットで生成した 7 ランタイム × 3 variant の SNR / 生成 wav は WandB run `piper-plus-runtime-smoke-ai13` 配下に保存。 AI-14 が tolerance 値を確定する際に audio sample listening を要する場合はこの run を参照。

## 関連ドキュメント

- 親マイルストーン: [../milestones/M5-runtime-abi-parity.md](../milestones/M5-runtime-abi-parity.md)
- 親計画 §6: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査統合: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 既存仕様:
  - [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — AI-14 で 3 新 section 追加予定、 本チケットでは編集しない
  - [../../spec/ort-session-contract.toml](../../spec/ort-session-contract.toml) — 7 ランタイム ORT セッション設定の canonical (companion ONNX も同 contract を継承)
  - [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — `[mb_istft_1d]` section 編集禁止 (G-1.2 gate、 AI-15 で機械化)
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — AI-17 で 7 ランタイム ABI 同期 diff に合流、 本チケットの load 経路を pre-isolation
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — pytest 9 fixture deprecation を本チケットの test 設計で先回り回避
- 論文:
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025) — companion ONNX の数値特性 (`n_fft=64, hop=16`) の根拠

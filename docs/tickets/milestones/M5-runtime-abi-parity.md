# M5: 7 ランタイム ABI 検証 + audio-parity 再 baseline

## メタ情報

- ID: M5
- 期間見積: 1.5 週
- 依存マイルストーン: M2 (iSTFTNet2-MB 1D-2D backbone), M3 (FLY-TTS 並走 harness), M4 (MS-Wavehax dual vocoder)
- 含まれるチケット: [AI-12](../tickets/AI-12-benchmark-3-variants.md), [AI-13](../tickets/AI-13-runtime-smoke-snr.md), [AI-14](../tickets/AI-14-audio-parity-contract.md), [AI-15](../tickets/AI-15-regression-guard-ci.md)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md §5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## フェーズの目的とゴール

M2 / M3 / M4 で生成された 3 つの新 variant (istftnet2-mb / fly-convnext6 / mswavehax companion) を、 piper-plus が支える 7 ランタイム (Python / Rust / Go / C# / WASM / C++ / C-API) で**ABI を壊さずに走らせられること**を確定させるフェーズである。 親計画 §1 が掲げた「核心トレードオフ 2: A-2 dual vocoder の ONNX I/O 二重同期回避」を実証する場でもあり、 ここで companion ONNX 方式と既存 ONNX I/O 不変原則が 7 ランタイム横断で耐えるかを検証する。

同時に「採否判定の数値根拠」を生成するフェーズでもある。 親計画 §4.6 が定めた 4 指標 (UTMOS proxy MOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) のうち、 後ろ 2 つはこの M5 でしか測れない。 M6 の統合判定 PR が依存する数値を、 ここで一度きりまとめて揃える。

加えて regression guard を CI gate として常設化する位置付けでもある。 M6 で PR #222 / #537 が rebase 取込される時点で、 audio-parity-contract.toml の `[mb_istft_1d]` section が誤って書き換わる事故 (Risk R6) を機械的に防ぐ防波堤を、 このフェーズで先回りで建てる。

## 達成判定 (Exit Criteria)

- 全 7 runtime で新 variant ONNX が `[1, 1, T]` float32 出力を返すこと
  - 検証方法: 各ランタイムの smoke test (`cargo test -p piper-plus --features wavehax`、 `go test ./piperplus/...`、 `dotnet test src/csharp/PiperPlus.Core.Tests`、 `pytest src/python_run/tests/test_wavehax_runtime.py`、 `npm test --workspace=openjtalk-web`、 `ctest --test-dir build`、 C-API は `tests/test_c_api_wavehax.cpp`) を CI matrix で run、 出力 shape を assert
- pairwise SNR ≥ 30 dB を Python 基準で他 6 runtime と相互比較
  - 検証方法: `tools/benchmark/pairwise_snr.py` (新規) が Python reference 音声を canonical とし、 各ランタイム生成音声と SNR を計算、 30 dB 下限を超えなければ非 0 exit
- ONNX op coverage audit が新 variant の使用 op を `Conv1d / Conv2d / Reshape / Transpose / Mul / Add / OnnxISTFT` 等の許可リストに留めること
  - 検証方法: `scripts/check_onnx_op_coverage.py` (新規) が `--variant istftnet2_mb / mswavehax / fly_convnext6` 引数で op set audit、 ConvTranspose2d 不使用を assert (Risk R7 mitigation)
- `audio-parity-contract.toml` に `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` section が追加され、 `[mb_istft_1d]` section が **完全不変** であること
  - 検証方法: `scripts/check_audio_parity_baseline.py` (新規 / G-1.2 gate) が `[mb_istft_1d]` の SHA256 を pinning 値と比較、 不一致なら fail
- README の 27ms benchmark を再測定し、 baseline 値と ±10% 以内で一致 (再現性確認)
  - 検証方法: `tools/benchmark/run_canonical.sh` (新規 / Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs) を CI 非実行 (ローカル測定) で run、 結果を `docs/reference/benchmark-results.md` に追記
- regression guard CI gate が `contract-gates.yml` workflow に統合され、 PR で `audio-parity-contract.toml` が編集されるたびに発動すること
  - 検証方法: 本マイルストーン内で意図的に baseline を書き換える dry-run PR を立て、 fail することを確認した上で revert

## Deliverable

- `tools/benchmark/models.yaml` に 3 variant entry 追加 (`css10-ja-1d-baseline` / `istftnet2-mb-1d2d` / `fly-convnext6` / `mswavehax-companion`)
- `tools/benchmark/proxy_mos.py` 新規 (UTMOS v2 wrapper、 200 test utt 一括評価)
- `tools/benchmark/pairwise_snr.py` 新規 (Python reference を canonical とした 7 ランタイム pairwise SNR 計算)
- `tools/benchmark/run_canonical.sh` 新規 (Xeon canonical benchmark 再測定スクリプト)
- 各ランタイムの wavehax companion ONNX load 経路:
  - Rust: `src/rust/piper-core/src/wavehax.rs` + `PiperVoice::new_with_wavehax(...)` 新メソッド
  - Go: `src/go/piperplus/wavehax.go` + Option pattern (`WithWavehaxModel(path)`)
  - C#: `src/csharp/PiperPlus.Core/Wavehax/` + optional named arg (`PiperVoice(wavehaxModelPath: ...)`)
  - WASM: `src/wasm/openjtalk-web/src/wavehax.js` + `PiperVoice` constructor option
  - C++: `src/cpp/wavehax.cpp` + CMake target、 C-API は `piper_plus_voice_load_with_wavehax(...)` 新 entry
- `docs/spec/audio-parity-contract.toml` 新 section: `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` (各 SNR/PESQ tolerance 値を実測ベースで pin)
- `scripts/check_audio_parity_baseline.py` 新規 (G-1.2 gate、 `[mb_istft_1d]` SHA256 pinning)
- `scripts/check_onnx_op_coverage.py` 新規 (ConvTranspose2d 不使用 assert + 許可 op set audit)
- `.github/workflows/contract-gates.yml` (既存 / 新規) に 2 gate 追加、 PR で audio-parity-contract.toml 編集時に自動発動
- `docs/reference/benchmark-results.md` 追記 (canonical 27ms 再測定結果と 3 variant の measured 値)

## チケット一覧と進捗

| ID | 概要 | 工数 | 依存 | ステータス |
|----|------|------|------|-----------|
| [AI-12](../tickets/AI-12-benchmark-3-variants.md) | `tools/benchmark/` に 3 variant 追加 + UTMOS proxy MOS | 1.5d | AI-05, AI-07, AI-10 (M2/M3/M4 学習完了) | TODO |
| [AI-13](../tickets/AI-13-runtime-smoke-snr.md) | 7 ランタイム smoke + pairwise SNR ≥ 30 dB 検証 | 3d | AI-12 | TODO |
| [AI-14](../tickets/AI-14-audio-parity-contract.md) | `audio-parity-contract.toml` に新 variant section 追加 | 1d | AI-13 | TODO |
| [AI-15](../tickets/AI-15-regression-guard-ci.md) | regression guard CI gate 整備 (`[mb_istft_1d]` 不変 + PR #222/#537 衝突回避 checklist) | 1.5d | AI-14 | TODO |

## このフェーズで考慮すべき主要リスク

- **R4 (companion ONNX の ABI 誤認、 PR #222 rebase 後の ONNX I/O 二重同期)** — M5 が直接対面するリスク。 mitigation として AI-13 で 7 ランタイムすべての companion ONNX load 経路を「**optional named arg / 新メソッド / Option pattern / 新 C-API entry**」に統一し、 既存 constructor / `PiperVoice::new(...)` シグネチャは一切変更しない。 ONNX I/O も companion ONNX を含めて contract に固定し、 M6 で PR #222 の 7 ランタイム同期 diff に乗せる際は 1 回で完了させる。
- **R6 (audio-parity baseline 誤書換による silent regression)** — AI-14 / AI-15 がこのフェーズの本丸として対処する。 `[mb_istft_1d]` section の SHA256 を `scripts/check_audio_parity_baseline.py` で pinning し、 `contract-gates.yml` workflow を required check に昇格させる。 新 variant section は必ず独立した `[istftnet2_mb_1d2d]` 等として併載し、 既存 baseline 値の変更は M5 完了時点で機械的に不可能になる。
- **R7 (2D op の mobile EP CPU fallback)** — AI-15 の ONNX op coverage audit がこの早期発見ゲートになる。 PoC 段階で iOS CoreML / Android NNAPI 実機 EP smoke は範囲外だが、 ConvTranspose2d 完全不使用と pixel-shuffle (Reshape+Transpose) 経路を **CI で assert** することで、 M6 以降に mobile EP smoke を追加する時点で「op set 段階の前提」が壊れていないことを保証する。
- **R5 (PR #537 TF32-on / bf16-mixed が招く 1e-3 magnitude drift)** — M5 完了時点では現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で baseline を確定させる。 M6 の AI-16 で PR #537 merge 後に再 benchmark するため、 `audio-parity-contract.toml` の各 tolerance 値は **「PR #537 前の現行 baseline」** であることを section コメントに明記する (M6 で AI-16 が tolerance を緩める rebase 差分を提出する余地を残す)。

## 一から作り直すとしたら (Phase-level rethinking)

このフェーズ設計を一から問い直すと、 まず **「3 variant を 1.5 週で 7 ランタイム検証する直列スケジュール」 が正しいかどうか**が最大の論点になる。 親計画は AI-13 を 3 日 / AI-15 を 1.5 日と見積もっているが、 7 ランタイム × 3 variant = 21 組合せの smoke と pairwise SNR 計算を直列で回すと、 1 つの ABI 不整合発見が後続 20 組合せを blocker にする。 代替案として、 ランタイム × variant の **マトリクス並列実行 (GitHub Actions matrix 21 job 同時)** を Day 0 から構築すれば、 単一 failure が他組合せの完走を blocking しない設計になる。 ただし matrix 並列は CI minute (OSS public で無制限とはいえ runner 並走数) と secret 配布の複雑性を増やすため、 PoC 段階で「3 variant のうち 1 つは fail 想定」と最初から認め、 fail allowance (continue-on-error) を CI 側に持たせる設計の方が現実的かもしれない。

次に **「companion ONNX 方式」が本当に optimal かどうか**を疑い直すべきだろう。 親計画は A-2 の ONNX I/O 二重同期回避のために companion ONNX (`tsukuyomi.wavehax.onnx`) を別ファイル化する方針を採るが、 これは「7 ランタイム × 2 ONNX = 14 load 経路」を増やす副作用がある。 代替案として **「単一 ONNX 内に 2 つの output branch を持たせ、 ランタイム側で stream switch する」** 設計が考えられる。 この場合 companion ONNX の DL / cache / version 同期コストが消える反面、 ONNX I/O が `output / output_wavehax` の 2 出力に変わり、 結局 PR #222 の sid→speaker_embedding[192] と同時に「output 1 つ → 2 つ」変更を 7 ランタイムに同期する必要が出る。 トレードオフは「load 経路の数 vs ONNX I/O の安定性」であり、 piper-plus は v1.13.0 までずっと **ONNX I/O 安定性を最優先** してきた歴史を踏まえると、 親計画の companion ONNX 方式が保守的に正しい。 ただし PoC 段階で「単一 ONNX dual-output」のフィージビリティを 0.5d で確認しておくと、 M6 統合判定で選択肢が増える。

第三に **「pairwise SNR ≥ 30 dB」 の閾値が適切かどうか**を見直す余地がある。 30 dB は piper-plus の他 contract gate (audio-parity SNR の既存 baseline) と整合する数値だが、 wavehax が `n_fft=64, hop=16` という極めて短い FFT 設定を持つことから、 数値精度の差で 30 dB を割る可能性がある。 代替案として **variant-specific な閾値 (mswavehax のみ 25 dB に緩める)** を最初から allow し、 「全 variant で同一閾値を貫く」プライドを捨てる設計が考えられる。 これは「regression guard の予測可能性」を犠牲にする代わりに「companion ONNX の現実的な数値特性」を許容する妥協であり、 PoC 段階では後者を採るのが pragmatic だろう。

最後に **TDD vs integration-first** の選択について再考する。 親計画は AI-13 を「7 ランタイム smoke」と表現し、 各ランタイムで test を書いてから ABI を整える順を暗黙の前提にしているが、 これは 7 言語 × test framework の差異 (Rust の cargo test / Go の testing / C# の xUnit / pytest / npm の jest / ctest) で着手障壁が高い。 代替案として **「Python smoke が走ったら 1 日以内に他 6 ランタイムへ Issue として展開し、 各ランタイムオーナーが個別 PR で integration test を追加する」** 分散型 integration-first 設計がある。 これは「1 人で全 7 ランタイム test を書く工数」を「6 人で並列に書く工数」に分散できる反面、 ABI 整合性の保証が分散して脆くなる。 piper-plus のメインテナがほぼ単独であることを踏まえると、 集中型 TDD で確実に 7 ランタイム同期する親計画の方が安全である。 ただし `cargo test --workspace` を macOS で動かす際の `@rpath` 問題 (CLAUDE.md ローカルテスト注記) や、 npm の `file:` link の lockfile 問題は、 「test 環境準備のために 1 ランタイムあたり 0.5 日」 の hidden cost を含んでおり、 工数 3 日は楽観的すぎる可能性が高い。 AI-13 の見積を 4-5 日に見直す余地がある。

## 後続マイルストーンへの連絡事項

- M6 (AI-16 / AI-17 / AI-18) への引き渡し物:
  - `audio-parity-contract.toml` の 3 新 section (`[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]`) は **「PR #537 merge 前の現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で測定」** された tolerance 値。 AI-16 で PR #537 merge 後に bf16-mixed / TF32-on で 1e-3 magnitude drift が観測されたら、 各 section の `tolerance_snr_db` / `tolerance_pesq` を緩める rebase 差分を AI-16 で提出する。
  - 7 ランタイムの companion ONNX load 経路は **既存 constructor / `new` メソッドを完全に変えずに** 拡張済み。 AI-17 で PR #222 の sid→speaker_embedding[192] 変更を反映する際は、 companion ONNX 側にも同じ I/O 変更が**自動的に適用される**ように `export_onnx.py --decoder-branch wavehax` 経路で同 contract に追従させる。
  - `scripts/check_audio_parity_baseline.py` の `[mb_istft_1d]` SHA256 pinning 値は、 M5 完了時点の baseline 文字列の SHA256。 AI-16 で PR #537 由来の数値 drift により baseline を更新する場合、 pinning 値も同時更新 (1 commit で baseline + pinning を atomic に変更) すること。 別 PR に分けると pinning と現値の drift で M6 全体の CI が red になる。
- 仮置きパスと暫定設定:
  - `tools/benchmark/models.yaml` の `mswavehax-companion` entry は M4 で生成された companion ONNX (`/data/piper/output-tsukuyomi-finetune-6lang-v2/tsukuyomi.wavehax.onnx`) を絶対パスで指す **暫定**。 M6 の AI-18 で HuggingFace に upload された URL に置き換える (HF repo `ayousanz/piper-plus-tsukuyomi-chan` の新規 file として追加予定)。
  - `docs/reference/benchmark-results.md` の canonical 27ms 再測定値は **「M5 着手時点 = 2026 年 6 月 16 日以降の Xeon E5-2650 v4 実測」** であり、 README.md の 27ms 値とは ±10% 以内であるべき。 もし differ するなら README.md 側も同時更新が必要 (M6 で `docs/reference/benchmark-results.md` を canonical 値とし README.md の表記を「Benchmark Results ページ参照」に置換する案を AI-18 で提案する余地あり)。
- 注意点:
  - `[mb_istft_1d]` section は M5 / M6 全期間で **絶対に編集禁止** (G-1.2 gate)。 PR #222 の Multi-scale FiLM 改造が 1D 経路にも数値影響を及ぼした場合、 改造を `_forward_1d` に持ち込まずに `_forward_1d2d` 内に閉じ込めることで対処する (AI-17 の責務)。
  - regression guard CI gate (`contract-gates.yml`) は M5 完了時点で required check に昇格させる。 M6 の AI-16 / AI-17 が baseline 更新の rebase 差分を提出する際は、 「baseline + pinning + tolerance + section コメント」 を 1 commit で更新するルール (PR body checklist に明記) を厳守する。

## 関連ドキュメント

- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 既存仕様:
  - [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` section を M5 で追加、 `[mb_istft_1d]` は不変
  - [../../spec/ort-session-contract.toml](../../spec/ort-session-contract.toml) — 7 ランタイム ORT セッション設定 (warmup / `.opt.onnx` cache) の canonical
  - [../../spec/short-text-contract.toml](../../spec/short-text-contract.toml) — Strategy A/B/C 仕様 (companion ONNX 切替時の dynamic scale 影響評価対象)
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — M6 AI-17 で 7 ランタイム ABI 同期 diff に合流
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — M6 AI-16 で再 benchmark トリガー
- 論文:
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023)
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025)
  - [FLY-TTS PDF (Guo Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) ConvNeXt × 6 + iSTFT

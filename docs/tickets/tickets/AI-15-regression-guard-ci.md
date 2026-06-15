# AI-15: regression guard CI gate 整備

## メタ情報

- ID: AI-15
- 親マイルストーン: [M5](../milestones/M5-runtime-abi-parity.md)
- 工数見積: 1.5 日
- 依存チケット: AI-14 (`audio-parity-contract.toml` に `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` section 追加)
- 後続チケット: AI-16 (PR #537 merge 後の bf16-mixed + TF32-on 再 benchmark の基盤)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-15 / §4.6 Benchmarks 目標値 / §3 Conflict Map / §7 Risk Register R6](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) / A-2 (MS-Wavehax dual vocoder) / FLY-TTS 保険ラインの 3 variant が新規 `decoder_type` 分岐として導入された結果、 **既存 1D MB-iSTFT への regression が silently 入り込む経路が複数発生する**。 計画 §7 R6 (audio-parity baseline 誤改竄) と §3 Conflict Map で繰り返し強調されているとおり、 `[mb_istft_1d]` baseline は 「絶対に touch しない」 ものとし、 新 variant 側に変更を局所化する必要がある。 本チケットでは AI-14 で section 追加が完了した `audio-parity-contract.toml` を入力に、 **default decoder_type 不変 / ONNX I/O 不変 / expected_p50_ms 退化なし / freeze-dp 互換 / PR #222 #537 衝突回避** の 5 観点を CI で機械 check する gate を整備する。

計画 §6 AI-15 で要求される 「default decoder_type assert、 ONNX I/O 不変 audit、 expected_p50_ms gate、 freeze-dp 互換 test、 PR #222/#537 衝突回避 checklist 機械 check」 を、 既存 `.pre-commit-config.yaml` と `.github/workflows/contract-gates.yml` に統合する。 計画 §8 Immediate Next Steps では 「skeleton を先に書き、 commit-msg hook として登録」 が推奨されており、 本チケットはその skeleton (AI-15 部分着手で先行作成済みと仮定) を最終形に仕上げる位置づけとなる。

このチケットは AI-14 (contract section 追加) を受けて gate 化を完了させる役割を持ち、 後続 AI-16 (PR #537 merge 後の再 benchmark) では本 gate が tolerance 拡張前の baseline を保証する **基盤** として機能する。 AI-16 は本 gate を一時的に bypass せず、 tolerance 拡張を contract 側に正規に取り込む手順を本チケットで規定する。

## 実装内容の詳細

### 編集対象ファイル

- `/Users/s19447/Documents/piper-plus/.pre-commit-config.yaml` — 既存 contract gate 群 (ZH-EN loanword / PUA / Swedish LID 等) と並ぶ位置に AI-15 由来 5 hook を追記 (既存 hook の id / files / pass_filenames は不変)
- `/Users/s19447/Documents/piper-plus/.github/workflows/contract-gates.yml` — 既存 job 群末尾に `regression-guard` job を追加 (matrix・runner 設定は既存 contract-gates と同型)
- `/Users/s19447/Documents/piper-plus/docs/spec/audio-parity-contract.toml` — **読み取り専用**。 本チケットでは編集しない (G-1.2 baseline 編集禁止、 R6 mitigation)。 AI-14 で section 追加された前提
- `/Users/s19447/Documents/piper-plus/.github/pull_request_template.md` — Risk Level セクション直下に AI-15 由来 5 checkbox を追記 (既存 checkbox は touch しない、 G-1.9 後方互換)

### 新規ファイル

- `/Users/s19447/Documents/piper-plus/scripts/check_audio_parity_baseline.py` (~120 LoC)
  - `audio-parity-contract.toml` を parse、 `[mb_istft_1d]` section の全 key の値が repo 既知 baseline (`expected_p50_ms`, `expected_proxy_mos_mean`, `expected_params_m`, `expected_snr_floor_db`, `sample_rate`) と byte-for-byte 一致するかを assert
  - 期待 baseline は `scripts/audio_parity_baseline.lock.json` に pin (本チケット内で同時作成)。 値変更には `--update-baseline` 引数を要求し、 commit メッセージに `audio-parity-baseline-bump` trailer がない場合 hook を fail
- `/Users/s19447/Documents/piper-plus/scripts/audio_parity_baseline.lock.json` (~20 行)
  - `{"[mb_istft_1d]": {"expected_p50_ms": 27, "expected_proxy_mos_mean": 4.05, "expected_params_m": 1.10, "expected_snr_floor_db": 30, "sample_rate": 22050}}` — CLAUDE.md README canonical 値を pin
- `/Users/s19447/Documents/piper-plus/scripts/check_a1_a2_isolation.py` (~150 LoC)
  - 4 つの isolation invariant を順に検査:
    1. `src/python/piper_train/vits/mb_istft.py` で `_forward_1d` 関数定義が残存し、 default `decoder_type='mb_istft_1d'` 分岐が `MBiSTFTGenerator.forward` 内に存在 (AST walk)
    2. `src/python/piper_train/vits/models.py` の `infer_forward` 経路が `model_g.dec(...)` 呼び出しを残し、 `dec_wavehax` 経路が `enable_wavehax` flag 越しの追加分岐になっていること (sibling 形)
    3. `src/python_run/piper/text_splitter.py` が前 commit から touch されていないこと (`git diff HEAD~1 --stat` で 0 行)
    4. `src/python/piper_train/export_onnx.py` の ONNX 入出力 spec (input names: `input` / `input_lengths` / `scales` / `sid`、 output names: `output`) が変更されていない (AST から `dynamic_axes` と `input_names` を抽出、 lock.json と比較)
- `/Users/s19447/Documents/piper-plus/scripts/onnx_io_spec.lock.json` (~30 行)
  - 既存 ONNX export の input_names / output_names / dynamic_axes を pin。 PR #222 の `sid → speaker_embedding[192]` 切替は AI-17 で本 lock を別 trailer 付きで更新する規約
- `/Users/s19447/Documents/piper-plus/scripts/check_expected_p50_ms_gate.py` (~100 LoC)
  - `tools/benchmark/metrics.json` (AI-12 出力) を読み込み、 各 variant の `rtf_p50_ms` が `audio-parity-contract.toml` の `expected_p50_ms` を超えていないかを assert
  - `[mb_istft_1d]` は ±10% tolerance (R5 TF32 ドリフト想定)、 新 variant (`[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]`) は target 値以下を厳格に要求
  - `--from-metrics <path>` で metrics.json パス指定、 CI artifact からの読み込みを許可
- `/Users/s19447/Documents/piper-plus/scripts/check_freeze_dp_compat.py` (~80 LoC)
  - `src/python/piper_train/__main__.py` の `--resume-from-multispeaker-checkpoint` 経路で `freeze_dp=True` が自動セットされる logic が **AST 上に残存** することを assert
  - 新 `decoder_type` 分岐で freeze-dp フラグが落ちる回帰を防ぐ
  - 既存テスト `src/python/tests/test_freeze_dp.py` は touch しない (G-1.9 後方互換)
- `/Users/s19447/Documents/piper-plus/scripts/check_pr222_pr537_isolation_checklist.py` (~60 LoC)
  - PR body から 5 checkbox (`- [x] default decoder_type 不変` 等) の存在を grep、 PR description が pull_request_template.md の Risk Level section 構造を保持しているかを assert
  - `--pr-body <path>` で PR body markdown ファイルを受領、 hook と CI 両方から呼べる

### `.pre-commit-config.yaml` 追加 hook スケッチ (15 行程度)

```yaml
  - repo: local
    hooks:
      - id: check-audio-parity-baseline
        name: AI-15 audio-parity baseline immutability gate
        entry: uv run python scripts/check_audio_parity_baseline.py
        language: system
        files: ^(docs/spec/audio-parity-contract\.toml|scripts/audio_parity_baseline\.lock\.json)$
        pass_filenames: false
      - id: check-a1-a2-isolation
        name: AI-15 A-1/A-2 isolation invariants
        entry: uv run python scripts/check_a1_a2_isolation.py
        language: system
        files: ^src/python/piper_train/vits/(mb_istft|models|export_onnx)\.py$|^src/python_run/piper/text_splitter\.py$
        pass_filenames: false
      - id: check-freeze-dp-compat
        name: AI-15 freeze-dp compatibility (AST)
        entry: uv run python scripts/check_freeze_dp_compat.py
        language: system
        files: ^src/python/piper_train/__main__\.py$
        pass_filenames: false
```

### 既存 default 値 / 互換維持の制約

- **G-1.9 後方互換 gate:** 既存 `.pre-commit-config.yaml` の他の hook (ZH-EN loanword / PUA / Swedish LID / CHANGELOG unreleased / ruff version sync 等) を **絶対に touch しない**。 AI-15 hook は末尾追記のみ
- **G-1.2 baseline 編集禁止:** `audio-parity-contract.toml` の `[mb_istft_1d]` section は本チケットでは read-only。 lock.json (`audio_parity_baseline.lock.json`) に pin した既知 baseline と byte-for-byte 一致しない変更は hook で fail
- **既存テスト不変:** `src/python/tests/test_freeze_dp.py` / `test_mb_istft_generator.py` / `test_audio_parity.py` は touch しない。 本チケットで追加するのは scripts/ 配下の hook 用 helper のみ
- **default `decoder_type` 不変:** `mb_istft_1d`。 リリース時の切替判断は M6 AI-18 で行う旨を pull_request_template.md のレビュー観点に明記
- **expected_p50_ms tolerance:** `[mb_istft_1d]` は ±10% (R5 PR #537 TF32 drift 想定)、 新 variant は厳格 (target 値以下)

### PR #222 / PR #537 conflict 回避策

計画 §3 Conflict Map から該当行を引用:

> `tools/benchmark/` + `tests/` | 3 variant 追加、 regression guard | NONE | LOW (pytest 9) | A-1/A-2 先行で OK

- **vs PR #222:** `scripts/check_a1_a2_isolation.py` の ONNX I/O spec lock (`scripts/onnx_io_spec.lock.json`) は **現行 dev の input_names `sid` を pin** する。 PR #222 が `sid → speaker_embedding[192]` 切替を入れる際は、 AI-17 (PR #222 merge 後) で lock.json を更新する規約とし、 更新コミットに `onnx-io-spec-bump` trailer を要求 (`check_a1_a2_isolation.py --strict-trailer`)。 これにより PR #222 が silently I/O を変えても CI gate で検出 (R6 mitigation 拡張)
- **vs PR #537:** TF32-on / bf16-mixed default が招く 1e-3 magnitude drift は `[mb_istft_1d]` の ±10% tolerance で吸収。 AI-16 (PR #537 merge 後) で tolerance を実測値に合わせて拡張する際は `audio-parity-contract.toml` 側を更新し、 `scripts/audio_parity_baseline.lock.json` の baseline は **絶対に書き換えない** (TF32 drift で baseline を緩めると永久に regression を見落とす)。 pytest 9 deprecation は本チケットの hook が pytest fixture 非依存 (純粋 CLI 経由) なので影響なし

### 新規 CLI フラグ

- `scripts/check_audio_parity_baseline.py --update-baseline` — baseline を 1 回だけ更新するための escape hatch、 commit message に `audio-parity-baseline-bump:` trailer を要求
- `scripts/check_a1_a2_isolation.py --strict-trailer` — ONNX I/O spec lock 更新時に `onnx-io-spec-bump:` trailer を要求
- `scripts/check_expected_p50_ms_gate.py --from-metrics <path>` — `tools/benchmark/metrics.json` のパス指定 (CI artifact path)
- `scripts/check_pr222_pr537_isolation_checklist.py --pr-body <path>` — PR body markdown を受領 (local pre-commit と CI 両方から呼べる)

### 疑似コード: `check_audio_parity_baseline.py` 骨子 (15 行)

```python
import tomllib, json, sys
from pathlib import Path

CONTRACT = Path("docs/spec/audio-parity-contract.toml")
LOCK = Path("scripts/audio_parity_baseline.lock.json")

contract = tomllib.loads(CONTRACT.read_text())
expected = json.loads(LOCK.read_text())["[mb_istft_1d]"]
actual = contract["mb_istft_1d"]

diff = {k: (expected[k], actual[k]) for k in expected if actual.get(k) != expected[k]}
if diff:
    sys.exit(f"AI-15 baseline drift: {diff}. "
             f"To intentionally bump, add 'audio-parity-baseline-bump: <reason>' "
             f"trailer to the commit message and run with --update-baseline.")
```

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Lead Implementer (CI Gate) | 1 | Python AST / tomllib / pre-commit hook 設計 / `.pre-commit-config.yaml` | 5 つの `scripts/check_*.py` 新規実装、 `.pre-commit-config.yaml` への hook 登録、 lock.json 2 ファイル作成 |
| CI Engineer | 1 | GitHub Actions / contract-gates.yml / matrix runner / artifact upload-download | `.github/workflows/contract-gates.yml` への `regression-guard` job 追加、 AI-12 metrics.json artifact からの consume 配線、 PR body checklist 機械 check の workflow 統合 |
| Test Engineer | 1 | pytest / AST walk テスト / pre-commit hook の dry-run / fail-loud assertion | `scripts/check_*.py` の単体テスト (`tests/scripts/test_check_audio_parity_baseline.py` 等)、 wrong-trailer / right-trailer / silent-bump の 3 シナリオを fixture で再現、 pytest 7/9 互換 |

3 名構成。 PoC ステージで surface を CI gate に閉じ込めるため、 ランタイム横断テストや 7 ランタイム ABI 検証は AI-13 に分離済み。 本チケットは Python script 5 ファイル + YAML 2 ファイル編集に閉じ、 別ランタイムへ波及しない。

## 提供範囲 (Scope)

### 含むもの

- `scripts/check_audio_parity_baseline.py` 新規実装 + `scripts/audio_parity_baseline.lock.json` pin
- `scripts/check_a1_a2_isolation.py` 新規実装 + `scripts/onnx_io_spec.lock.json` pin
- `scripts/check_expected_p50_ms_gate.py` 新規実装 (AI-12 `metrics.json` を入力)
- `scripts/check_freeze_dp_compat.py` 新規実装 (AST walk)
- `scripts/check_pr222_pr537_isolation_checklist.py` 新規実装 (PR body markdown grep)
- `.pre-commit-config.yaml` に上記 5 hook を末尾追記 (既存 hook 不変)
- `.github/workflows/contract-gates.yml` に `regression-guard` job を追加 (既存 job 不変)
- `.github/pull_request_template.md` の Risk Level セクションに 5 checkbox 追記
- `tests/scripts/test_check_*.py` の 5 つの unit test (right-trailer / wrong-trailer / silent-bump シナリオ)
- README / docs/spec への gate 説明 1 段落追記 (`docs/spec/audio-parity-contract.toml` のヘッダーコメント)

### 含まないもの (Out of Scope)

- **`audio-parity-contract.toml` の section 編集** — AI-14 で完了済み前提 (本チケットは read-only)
- **7 ランタイム smoke + pairwise SNR の CI 化** — AI-13 で扱う
- **AI-12 `tools/benchmark/metrics.json` の生成 logic** — AI-12 で完了済み前提 (本チケットは consume のみ)
- **PR #537 merge 後の TF32 / bf16-mixed tolerance 拡張** — AI-16 で扱う (本チケットは ±10% tolerance を pin、 実測拡張は AI-16)
- **PR #222 merge 後の ONNX I/O spec lock 更新** — AI-17 で扱う (本チケットは `sid` 列を pin)
- **新 `decoder_type` の runtime side default 切替** — M6 AI-18 採否判定 PR で扱う
- **既存 `.pre-commit-config.yaml` hook の再編成 / 統廃合** — surface 拡大回避のため別 PR

## テスト項目

### Unit Tests

- `tests/scripts/test_check_audio_parity_baseline.py::test_baseline_drift_detected`
  - assert: `audio-parity-contract.toml` で `[mb_istft_1d].expected_p50_ms` を 27 → 28 に書き換えた状態で `check_audio_parity_baseline.py` を呼ぶと exit code 非 0、 stderr に `AI-15 baseline drift` 文字列を含む
- `tests/scripts/test_check_audio_parity_baseline.py::test_baseline_bump_with_trailer_accepted`
  - assert: commit message に `audio-parity-baseline-bump: PR #537 TF32 drift +1ms` trailer を含めた状態で `--update-baseline` を渡すと exit code 0、 lock.json も更新される
- `tests/scripts/test_check_a1_a2_isolation.py::test_forward_1d_branch_present`
  - assert: `mb_istft.py` の AST に `_forward_1d` 関数定義が存在し、 `MBiSTFTGenerator.forward` 本体に `if self.decoder_type == "mb_istft_1d"` 分岐が含まれる
- `tests/scripts/test_check_a1_a2_isolation.py::test_text_splitter_untouched`
  - assert: `git diff HEAD~1 -- src/python_run/piper/text_splitter.py` が 0 行 (decoder-agnostic 維持)
- `tests/scripts/test_check_a1_a2_isolation.py::test_onnx_io_spec_pinned`
  - assert: `onnx_io_spec.lock.json` の `input_names == ["input", "input_lengths", "scales", "sid"]`、 `export_onnx.py` の AST 抽出値と一致
- `tests/scripts/test_check_expected_p50_ms_gate.py::test_mb_istft_1d_tolerance_10pct`
  - assert: `metrics.json` で `mb_istft_1d.rtf_p50_ms = 29.6` (27 × 1.10 ぎりぎり下) は通過、 `29.8` は exit 非 0
- `tests/scripts/test_check_expected_p50_ms_gate.py::test_istftnet2_mb_strict_target`
  - assert: `metrics.json` で `istftnet2_mb_1d2d.rtf_p50_ms = 18` は通過、 `19` は exit 非 0 (新 variant は target 値以下を厳格要求)
- `tests/scripts/test_check_freeze_dp_compat.py::test_freeze_dp_auto_enable_path_exists`
  - assert: `__main__.py` の AST に `if args.resume_from_multispeaker_checkpoint: args.freeze_dp = True` 相当の logic が残存
- `tests/scripts/test_check_pr222_pr537_isolation_checklist.py::test_5_checkboxes_present`
  - assert: PR body markdown に 5 つの `- [ ]` checkbox (default decoder_type / audio parity / ONNX I/O / PR #537 / freeze-dp) が含まれる
- 既存 `src/python/tests/test_freeze_dp.py` / `test_audio_parity.py` は touch しない (G-1.9 後方互換)

### E2E Tests

- **pre-commit dry-run E2E:**
  ```
  uv run pre-commit run check-audio-parity-baseline --all-files
  uv run pre-commit run check-a1-a2-isolation --all-files
  uv run pre-commit run check-freeze-dp-compat --all-files
  ```
  - assert: 5 hook 全てが現行 dev (`fcddb997`) の HEAD で exit 0
- **silent drift simulation E2E:**
  - 一時 branch を切り `[mb_istft_1d].expected_p50_ms` を silently 27 → 30 に書き換えて commit、 pre-commit hook が fail で commit がブロックされることを確認
- **CI workflow E2E:**
  - `.github/workflows/contract-gates.yml` の `regression-guard` job が PR body markdown を受領し、 5 checkbox 欠落で `actions/github-script` が失敗する dry-run を再現
- **AI-12 metrics.json consume E2E:**
  - AI-12 生成の `tools/benchmark/metrics.json` を入力に `check_expected_p50_ms_gate.py --from-metrics tools/benchmark/metrics.json` を実行、 3 variant の `rtf_p50_ms` が全て pass する dry-run
- **計画 §4.6 数値目標との照合:** `[mb_istft_1d] expected_p50_ms = 27` / `[istftnet2_mb_1d2d] = 18` / `[mswavehax]` streaming chunk / `[fly_convnext6] = 23` が `audio-parity-contract.toml` から読めることを確認 (read-only)

### 受入基準 (Acceptance Criteria)

計画 §4.6 / §6 AI-15 / §7 R6 から該当する数値目標を引用:

- **default decoder_type 不変:** `mb_istft_1d` (`check_a1_a2_isolation.py` で AST assert)
- **`[mb_istft_1d]` audio parity 不変:** `audio_parity_baseline.lock.json` と byte-for-byte 一致 (CLAUDE.md README canonical 値 `expected_p50_ms: 27`、 `expected_snr_floor_db: 30`)
- **新 variant target 達成:** `istftnet2_mb_1d2d.rtf_p50_ms <= 18ms` / `fly_convnext6.rtf_p50_ms <= 23ms` (計画 §4.6)
- **ONNX I/O 不変:** `input_names == ["input", "input_lengths", "scales", "sid"]` (PR #222 二重同期回避、 AI-17 で正規切替まで)
- **freeze-dp 互換:** `--resume-from-multispeaker-checkpoint` 経路の auto-enable logic が AST 上に残存 (CLAUDE.md 「実装済み機能 / 学習補助」 と整合)
- **PR body 5 checkbox:** pull_request_template.md の構造 + 5 AI-15 checkbox が機械 check で pass
- **7 ランタイム ABI 不変:** Python/Rust/Go/C#/WASM/C++/C-API いずれも `[1,1,T]` float32、 pairwise SNR ≥ 30 dB (計画 §4.6) — 本チケットでは contract 値の存在のみを assert、 実測は AI-13
- **CI 実行時間:** 5 hook 全件で pre-commit 30 秒以内、 CI `regression-guard` job 2 分以内
- **hook の冪等性:** 同一 HEAD で連続 2 回呼んでも結果不変 (R6 mitigation)

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から関連項目:

- **R6 (audio-parity-contract baseline regression を誤って書き換え):** 本チケットの中核懸念。 `audio_parity_baseline.lock.json` を別ファイル化して二重 pin する設計を選んだが、 lock.json 自体を silently 編集される穴は残る。 mitigation: lock.json 更新には commit message trailer `audio-parity-baseline-bump:` を要求し、 trailer なしの更新は hook で fail させる。 さらに `.github/CODEOWNERS` で `scripts/*.lock.json` を maintainer 必須レビュー対象に追加することを後続 PR で検討
- **R5 (PR #537 TF32 / bf16-mixed drift):** `[mb_istft_1d]` の ±10% tolerance で吸収するが、 1e-3 magnitude drift が 27ms に対しては影響軽微 (実測誤差レベル)。 ただし `expected_proxy_mos_mean` への drift は ±0.1 を超える可能性あり、 AI-16 で実測拡張する。 本チケットでは ±10% を仮置きとする旨を lock.json コメントに明記
- **R6 派生: ONNX op coverage 変更による silent regression:** A-1 の Conv2d / Reshape / Transpose op 追加が `export_onnx.py` の AST 上では検出できない可能性 (動的 op insertion)。 mitigation: `check_a1_a2_isolation.py` で ONNX export 経路の `torch.onnx.export` 呼び出しの kwargs (特に `opset_version` と `do_constant_folding`) も pin、 変更には別 trailer 要求
- **PR body checklist の人間バイパス:** `check_pr222_pr537_isolation_checklist.py` は markdown grep でしか check できず、 reviewer が checkbox を `- [x]` に手動 tick しても実態と乖離する可能性。 mitigation: 機械 check は「checkbox 構造の存在」 のみを保証し、 実態の verify は `/code-review` / `/review` skill に委ねる設計に留める (本チケットは構造 gate)
- **pre-commit hook の `--all-files` 実行時間:** AST walk 5 つで 30 秒以内を目標とするが、 `mb_istft.py` (1500 LoC) と `models.py` (2800 LoC) の AST walk が遅い場合は LRU cache 化を検討
- **lock.json の merge conflict:** 複数 PR が並走して lock.json を同時更新すると merge conflict が頻発する。 mitigation: lock.json 更新を行う PR は M6 リリース PR と整合的に 1 PR ずつに直列化、 trailer に PR 番号を入れる規約

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 `mb_istft_1d`)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止、 lock.json と byte-for-byte 一致)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避、 `onnx_io_spec.lock.json` の `input_names` に `speaker_embedding` を追加しない)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響は AI-16 で `audio-parity-contract.toml` tolerance に反映 (本チケットでは ±10% 仮置き、 lock.json は不変)
- [ ] freeze-dp 自動有効化 logic が `__main__.py` AST 上に残存 (CLAUDE.md 学習補助 §)
- [ ] 既存 `.pre-commit-config.yaml` の他 hook (ZH-EN loanword / PUA / Swedish LID / ruff sync 等) を touch していない
- [ ] 既存 `audio-parity-contract.toml` の `[mb_istft_1d]` section を read-only として扱い、 編集していない (AI-14 で section 追加された前提)
- [ ] 既存 test (`test_freeze_dp.py` / `test_audio_parity.py` / `test_mb_istft_generator.py`) を touch していない
- [ ] `.github/pull_request_template.md` の既存 checkbox 構造 (Risk Level / Affected Components / Type) を保ち、 末尾追記のみ
- [ ] 5 `scripts/check_*.py` が pytest 7 / pytest 9 両環境で fixture 非依存に動く (R5 mitigation)
- [ ] commit message trailer (`audio-parity-baseline-bump:` / `onnx-io-spec-bump:`) なしの silent 編集が hook で確実に fail する
- [ ] AI-12 `tools/benchmark/metrics.json` の schema (`proxy_mos / rtf_p50_ms / params_m`) と `check_expected_p50_ms_gate.py` の入力契約が一致
- [ ] `.github/workflows/contract-gates.yml` の `regression-guard` job が既存 contract gate (ZH-EN loanword 等) と同型の matrix / runner / cache 設定

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は 「`.pre-commit-config.yaml` に 5 hook を local 登録し、 `scripts/check_*.py` で AST walk + lock.json 比較 + commit trailer enforcement を多層化する設計」 である。 これは既存 contract gate 群 (ZH-EN loanword / PUA / Swedish LID) と同型の文化に揃え、 reviewer が「また同じパターンの gate」 と認識できる学習コスト最小化を狙ったものである。 代替案 1 として **「pre-commit hook ではなく pytest test として実装」** (`src/python/tests/test_regression_guard.py` に 5 つの test を集約) を考えたが、 commit 段階で fail-fast にならず CI で初めて検出することになり、 R6 (silent baseline 編集) を最初の commit で防げない欠点がある。 R6 は 「commit が走り切る前に止める」 ことが核心なので pre-commit hook を採用した。

代替案 2 は **「lock.json 二重 pin をやめて `audio-parity-contract.toml` 単独 source of truth とし、 編集を CODEOWNERS gate に委ねる」** ものである。 これは scripts/ 配下のファイル数を減らせる利点があるが、 CODEOWNERS は merge 時 gate であり commit 段階で止められないため、 R6 mitigation として弱い。 また CODEOWNERS の責務範囲が `*.toml` 全体に広がると noise が増える。 採用案では lock.json を pin 専用の別ファイル化することで、 reviewer の視線を 「lock.json 行が diff にあれば即時警戒」 に集中させられる利点を取った。 代替案 3 として **「expected_p50_ms gate を runtime side ではなく学習側 (`piper_train`) に組み込む」** も考えたが、 学習側は GPU runner 占有で頻繁に走らせられず、 CI 上で 30 秒以内に check したい本チケットの要件と合わない。 軽量 AST walk と lock.json 比較に閉じる本採用案が、 PoC ステージの surface 最小化と R6 mitigation の両立として現実解である。

代替案 4 として **「AI-15 を AI-13 / AI-14 に分割吸収し独立チケットを廃止」** も検討した。 これは ticket count を 18 から 17 に減らせる利点があるが、 AI-13 (7 ランタイム ABI) と AI-14 (contract section 追加) はそれぞれ責務が明確で異質な作業 (ランタイム横断 vs 設定追加) なので、 CI gate を両方に少しずつ混ぜると 「どちらの PR で何が gate されたか」 が曖昧になる。 独立チケットとして 1.5 日工数を確保し、 5 hook を 1 つの skeleton 起源にまとめる設計の方が、 後続 AI-16 / AI-17 / AI-18 で gate の責務を引用しやすい。 採用案を 「現実解」 として位置づけ、 別案の利点は本チケット範囲外の規模になるため捨てた。

## 後続タスクへの連絡事項

AI-16 (PR #537 merge 後の bf16-mixed + TF32-on 再 benchmark) に引き渡す具体的成果物:

- **`scripts/audio_parity_baseline.lock.json` の所在と更新規約:**
  - パス: `/Users/s19447/Documents/piper-plus/scripts/audio_parity_baseline.lock.json`
  - 現行 pin: `{"[mb_istft_1d]": {"expected_p50_ms": 27, "expected_proxy_mos_mean": 4.05, "expected_params_m": 1.10, "expected_snr_floor_db": 30, "sample_rate": 22050}}`
  - AI-16 で TF32 / bf16-mixed 実測 drift を反映する場合は `audio-parity-contract.toml` 側の `[mb_istft_1d].expected_p50_ms` の tolerance を ±10% から実測値ベースに拡張し、 lock.json は **絶対に書き換えない** (baseline 緩和の防壁)
- **`scripts/onnx_io_spec.lock.json` の所在と更新規約:**
  - パス: `/Users/s19447/Documents/piper-plus/scripts/onnx_io_spec.lock.json`
  - 現行 pin: `input_names == ["input", "input_lengths", "scales", "sid"]`、 `output_names == ["output"]`
  - PR #222 merge 後 (AI-17) は `sid → speaker_embedding` 切替で lock.json を更新、 commit trailer に `onnx-io-spec-bump: PR #222 zero-shot TTS speaker_embedding[192]` を必須とする
- **`tools/benchmark/metrics.json` 入力契約:**
  - AI-12 で生成された `{variant: {proxy_mos: {...}, rtf_p50_ms: float, params_m: float}}` schema を AI-16 でも同 schema で生成すること (再 benchmark の出力先)
  - AI-16 では `--from-metrics tools/benchmark/metrics-pr537.json` のように TF32 / bf16-mixed 個別 path を持たせ、 現行 metrics.json と並走比較
- **暫定 tolerance 値:** `[mb_istft_1d]` ±10% は **PR #537 merge 前の仮置き**。 AI-16 で TF32-on 実測 drift (恐らく ±2% 程度) を測定し、 audio-parity-contract.toml 側を tightening する余地あり。 lock.json と contract の二重定義状態を AI-16 完了後に 「contract = 緩い実測 tolerance」 / 「lock.json = 厳格 canonical 値」 として役割分担を明文化する
- **5 hook の skip 方法 (緊急時のみ):**
  - `SKIP=check-audio-parity-baseline git commit ...` で個別 bypass 可能 (pre-commit 標準)
  - bypass した場合 pre-push hook (`pre-commit install --hook-type pre-push`) で再度 fail させる二段構え (CLAUDE.md 開発環境セットアップ §)
  - AI-16 で bypass せざるを得ない場面 (TF32 drift の暫定確認) では `--update-baseline` + `audio-parity-baseline-bump:` trailer を使う正規ルートに従う
- **pull_request_template.md 5 checkbox の位置:** Risk Level セクション直下、 `## Test Plan` の前に挿入。 AI-17 (PR #222 merge 後) で 「ONNX I/O spec 切替済み」 checkbox の意味が変わるため、 AI-17 でレビュー観点文言を更新する余地あり
- **PR #222 rebase 時の注意:** `scripts/check_a1_a2_isolation.py` の ONNX I/O lock 行を AI-17 で更新する際は、 必ず `onnx-io-spec-bump:` trailer 付きで lock.json を bump し、 同じ PR で `audio-parity-contract.toml` の `[mb_istft_1d]` `expected_snr_floor_db: 30` を **絶対に touch しない** こと
- **PR #537 rebase 時の注意:** 5 `scripts/check_*.py` は pytest fixture 非依存に書いてあるため pytest 9 deprecation 影響なし。 ただし `tomllib` (Python 3.11+ 標準) は Python 3.13 でも使える前提 (PR #537 互換) であることを AI-16 で再確認

## 関連ドキュメント

- 親マイルストーン: [../milestones/M5-runtime-abi-parity.md](../milestones/M5-runtime-abi-parity.md)
- 親計画 §6 AI-15 / §4.6 / §3 Conflict Map / §7 R6: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- companion deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md) §2.5 Phase 4 Risk 評価
- 改善調査統合: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md) §A-1, §A-2
- audio parity contract (G-1.2 baseline 編集禁止 gate): [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml)
- 既存 contract gate 文化 (ZH-EN loanword): [../../reference/zh-en-loanword/README.md](../../reference/zh-en-loanword/README.md)
- 既存 contract gate 文化 (Swedish LID): [../../reference/swedish-lid/README.md](../../reference/swedish-lid/README.md)
- pre-commit / pre-push gate 集約 (CLAUDE.md 開発環境セットアップ §)
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — ONNX I/O spec lock は AI-17 で更新
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — TF32 tolerance 拡張は AI-16 で `audio-parity-contract.toml` 側に
- 前提チケット: AI-14 (audio-parity-contract.toml に variant section 追加)
- 後続チケット: AI-16 (PR #537 merge 後の再 benchmark) / AI-17 (PR #222 merge 後の ONNX I/O 同期) / AI-18 (採否判定レポート)

# AI-12: tools/benchmark/ に 3 variant 追加 + UTMOS proxy MOS

## メタ情報

- ID: AI-12
- 親マイルストーン: [M5](../milestones/M5-runtime-abi-parity.md)
- 工数見積: 1.5 日
- 依存チケット: AI-05 (iSTFTNet2-MB 50 epoch PoC 学習)、 AI-07 (FLY-TTS 50 epoch 並走学習)、 AI-10 (MS-Wavehax 30 epoch vocoder-only FT)
- 後続チケット: AI-13 (smoke の前提となる benchmark 基盤)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-12 / §4.6 Benchmarks 目標値](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) / A-2 (MS-Wavehax dual vocoder) / FLY-TTS (Q13 失敗時の保険) の **3 variant** を共通の評価基盤で横並びに測定するために、 既存 `tools/benchmark/` に各 variant の entry を追加し、 UTMOS v2 をラップした proxy MOS スコアラ `proxy_mos.py` を新規実装する。 計画 §6 AI-12 で要求される「`models.yaml` に css10-ja-1d-baseline / istftnet2-mb / fly-convnext6 の 3 entry」 「`proxy_mos.py` 新規 (UTMOS v2 wrapper)」 を本チケットで完了させる。

このチケットは AI-05 / AI-07 / AI-10 の学習成果物 (3 つの ONNX checkpoint) を **後続 AI-13 (7 ランタイム smoke + pairwise SNR 検証) が消費するための baseline 数値を確定** する役割を持つ。 計画 §4.6 の数値目標 (UTMOS proxy MOS baseline ± 0.1 / CPU RTF p50 < 20ms / params 0.83M ± 0.05M / 7 runtime pairwise SNR ≥ 30 dB) を CI gate-able な形式で出力し、 AI-13 でランタイム間 SNR を測る際の **Python 側 reference オーディオの canonical 生成元** とする。

並行して、 計画 §3 Conflict Map で `tools/benchmark/ + tests/` 行が NONE / LOW と分類されているとおり、 PR #222 / PR #537 とコード衝突しない範囲に作業を局所化することで、 PR #222 / #537 の merge 状態に関係なく即時着手可能な benchmark harness を確立する (§8 Immediate Next Steps に整合)。

## 実装内容の詳細

### 編集対象ファイル

- `/Users/s19447/Documents/piper-plus/tools/benchmark/models.yaml` — 末尾に 3 entry 追記 (既存 6lang-base / tsukuyomi / external 群は touch しない)
- `/Users/s19447/Documents/piper-plus/tools/benchmark/compute_metrics.py` — 既存 `--utmos` フラグ経路から `proxy_mos.compute_proxy_mos()` を呼び出すよう内部 import を 1 行差し替え (CLI surface 不変、 値経路のみ変更)
- `/Users/s19447/Documents/piper-plus/tools/benchmark/generate_samples.py` — `--variant` argparse オプションを追加し、 `models.yaml` から該当 entry を 1 件だけ抽出して合成 (既存全件モードは default 維持)

### 新規ファイル

- `/Users/s19447/Documents/piper-plus/tools/benchmark/proxy_mos.py` (~150 LoC)
  - `load_utmos_model(device='cpu') -> torch.nn.Module` — UTMOS v2 (sarulab-utmos) を torch hub から lazy load、 `~/.cache/piper-plus/utmos/` にキャッシュ
  - `compute_proxy_mos(wav_path: Path, model, sample_rate=22050) -> float` — 16kHz リサンプル + scoring、 200 utt まとめて評価する `compute_proxy_mos_batch` 併設
  - `format_summary(scores: list[float]) -> dict` — mean / std / p10 / p50 / p90 を返す
- `/Users/s19447/Documents/piper-plus/tools/benchmark/test_benchmark.py` 拡張 (既存ファイル末尾追記)
  - `test_models_yaml_three_variants_present()` — 3 variant 全てがロードでき必須キー (`path` / `decoder_type` / `expected_p50_ms`) を持つことを assert
  - `test_proxy_mos_deterministic()` — 同一 wav に対して 2 回呼んで `|s1 - s2| < 1e-4`

### `models.yaml` 追加 entry スケッチ (10 数行)

```yaml
  # --- AI-12: PoC variants (CSS10 JA single-speaker) ---
  - name: css10-ja-1d-baseline
    path: "${MODELS_DIR}/css10-ja-1d-baseline.onnx"
    config: "${MODELS_DIR}/css10-ja-config.json"
    type: piper-plus
    decoder_type: mb_istft_1d        # default 不変 (G-1.9 後方互換 gate)
    expected_p50_ms: 27               # README canonical baseline (Xeon E5-2650 v4 / 25 phoneme 英文)
    description: "AI-02 baseline (50 epoch, decoder_type=mb_istft_1d)"
    speaker_ids: { ja: 0 }

  - name: istftnet2-mb
    path: "${MODELS_DIR}/css10-ja-istftnet2-mb.onnx"
    config: "${MODELS_DIR}/css10-ja-config.json"
    type: piper-plus
    decoder_type: istftnet2_mb_1d2d
    expected_p50_ms: 18               # 計画 §4.6 target (baseline × 0.7)
    params_m: 0.83                    # 計画 §4.2 目標 ± 0.05M
    description: "AI-05 PoC (50 epoch, 1D-2D backbone)"
    speaker_ids: { ja: 0 }

  - name: fly-convnext6
    path: "${MODELS_DIR}/css10-ja-fly-convnext6.onnx"
    config: "${MODELS_DIR}/css10-ja-config.json"
    type: piper-plus
    decoder_type: fly_convnext6
    expected_p50_ms: 23               # 計画 §4.6 target (baseline × 0.85)
    params_m: 0.63                    # 計画 §4.5 (PQMF 不使用、 sub-band loss 無効)
    description: "AI-07 保険 (50 epoch, ConvNeXt × 6 + iSTFT n_fft=1024)"
    speaker_ids: { ja: 0 }
```

### 互換維持の制約

- **G-1.9 後方互換 gate:** 既存 entry (`piper-plus-6lang-base` / `piper-plus-tsukuyomi`) は **touch しない**。 default `decoder_type` 列を追加するときも欠落値を `mb_istft_1d` として補う logic は loader 側に閉じ込め、 YAML 値の追記 / 削除を行わない
- **既存 CLI 不変:** `generate_samples.py --output-dir ...` の既定挙動は全件モード継続。 `--variant <name>` は opt-in のフィルタとし、 省略時は従来通り全 entry を走らせる
- **proxy MOS は CPU 既定:** UTMOS v2 model load は `device='cpu'` を default にし、 1 GPU を学習に占有している前提 (計画 §4.4) を阻害しない

### PR #222 / PR #537 conflict 回避策

計画 §3 Conflict Map から該当行を引用:

> `tools/benchmark/` + `tests/` | 3 variant 追加、 regression guard | NONE | LOW (pytest 9) | A-1/A-2 先行で OK

- **vs PR #222:** `models.yaml` / `proxy_mos.py` どちらも PR #222 が触る 6 軸 (emb_g 削除 / Flow dilation / MBiSTFTGenerator FiLM / ONNX I/O sid→speaker_embedding[192] / noise_scale default / 7 ランタイム ABI) のいずれにも触れないため衝突なし。 PR #222 が ONNX I/O を `speaker_embedding[192]` に切り替えた後も、 本 entry は `speaker_ids: { ja: 0 }` 経由で互換 wrapper を呼ぶ既存パスを使うため再修正不要 (AI-17 で I/O 同期する側に集約)
- **vs PR #537:** Python 3.13 + pytest 9 への移行は test side で LOW conflict のみ。 `test_proxy_mos_deterministic()` で pytest fixture を使わず純関数アサートに留めることで pytest 7/9 両対応を確保する (計画 §7 R5 / Risk Register pytest 9 deprecation 連動)

### 新規 CLI フラグ

- `generate_samples.py --variant <name>` — `models.yaml` から 1 entry に絞って合成 (省略時は従来挙動)
- `compute_metrics.py --proxy-mos-cache <path>` (任意、 default `~/.cache/piper-plus/utmos/`) — UTMOS v2 model のキャッシュ場所明示

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Lead Implementer (Benchmark) | 1 | Python / PyYAML / argparse / torch hub | `models.yaml` 3 entry 追加、 `generate_samples.py` の `--variant` 追加、 `compute_metrics.py` の差し替え |
| ML Eval Engineer | 1 | UTMOS v2 / torchaudio / sarulab-utmos hub model / WandB | `proxy_mos.py` 新規実装、 UTMOS v2 lazy load + 16kHz リサンプル + バッチ scoring、 200 utt summary 集計 |
| Test Engineer | 1 | pytest / hypothesis / fixture less assertions | `test_benchmark.py` 拡張 (3 variant load assert + proxy MOS determinism)、 pytest 7/9 互換確保 |

3 名構成。 PoC ステージなので 7 ランタイム横断作業は AI-13 に分離し、 本チケットは Python benchmark harness 単独で完結させる。

## 提供範囲 (Scope)

### 含むもの

- `tools/benchmark/models.yaml` への 3 variant entry 追記 (`css10-ja-1d-baseline` / `istftnet2-mb` / `fly-convnext6`)
- `tools/benchmark/proxy_mos.py` 新規実装 (UTMOS v2 wrapper、 lazy load + cache)
- `compute_metrics.py` 内部の UTMOS 呼び出しを `proxy_mos.compute_proxy_mos_batch()` に差し替え (CLI 表面不変)
- `generate_samples.py` への `--variant` opt-in フラグ追加
- `test_benchmark.py` に 3 variant 検証 + proxy MOS determinism test を追加
- 200 test utt × 3 variant の baseline 数値 (UTMOS proxy / RTF p50 / params / file size) を `metrics.json` として artifact 化

### 含まないもの (Out of Scope)

- **7 ランタイム smoke + pairwise SNR 検証** — AI-13 で扱う (Python の reference オーディオは本チケットで生成するが SNR 比較自体は次チケット)
- **`audio-parity-contract.toml` への新 variant section 追加** — AI-14 で扱う (本チケットの数値が AI-14 の `expected_p50_ms` 入力になる)
- **regression guard CI gate 整備 (default decoder_type assert / ONNX I/O 不変 audit)** — AI-15 で扱う
- **`[mb_istft_1d]` baseline 値の再計算** — G-1.2 baseline 編集禁止 gate に従い `expected_p50_ms: 27` は README canonical 値を引用するのみ
- **PR #537 後の TF32 / bf16-mixed 再 benchmark** — AI-16 (PR #537 merge 後) に分離
- **UTMOS v2 以外の MOS proxy (Wav2Vec MOS / DNSMOS)** — 計画 §4.6 は UTMOS proxy のみ指定

## テスト項目

### Unit Tests

- `tools/benchmark/test_benchmark.py::test_models_yaml_three_variants_present`
  - assert: `load_models_yaml()` の戻り値に `css10-ja-1d-baseline` / `istftnet2-mb` / `fly-convnext6` の 3 name が存在
  - assert: 各 entry が `decoder_type` / `expected_p50_ms` / `path` / `speaker_ids.ja == 0` を持つ
  - assert: `css10-ja-1d-baseline.decoder_type == "mb_istft_1d"` (G-1.9 後方互換 gate)
- `tools/benchmark/test_benchmark.py::test_models_yaml_existing_entries_unchanged`
  - assert: `piper-plus-6lang-base` / `piper-plus-tsukuyomi` / `edge-tts` / `gtts` の 4 既存 entry は値完全一致 (G-1.2 baseline 編集禁止 gate)
- `tools/benchmark/test_benchmark.py::test_proxy_mos_deterministic`
  - assert: 同一 22050Hz wav (`tests/fixtures/short_ja_25phoneme.wav`) に対して `compute_proxy_mos()` を 2 回呼び結果差が `< 1e-4`
- `tools/benchmark/test_benchmark.py::test_proxy_mos_summary_keys`
  - assert: `format_summary([4.21, 4.18, 4.25, 4.15, 4.30])` が `{"mean", "std", "p10", "p50", "p90"}` 全 key を返す
- `tools/benchmark/test_benchmark.py::test_generate_samples_variant_filter`
  - assert: `generate_samples.py --variant istftnet2-mb --dry-run` が istftnet2-mb 1 件のみ resolve、 他 2 variant は skip
- 既存 `tools/benchmark/test_benchmark.py` の全 case は **touch しない** (G-1.9 後方互換 gate)

### E2E Tests

- **3 variant generate → metrics 一気通し:**
  ```
  uv run python tools/benchmark/generate_samples.py \
      --models css10-ja-1d-baseline,istftnet2-mb,fly-convnext6 \
      --languages ja --output-dir /tmp/ai12_samples
  uv run python tools/benchmark/compute_metrics.py \
      --samples-dir /tmp/ai12_samples --output /tmp/ai12_metrics.json --utmos
  ```
  - assert: `/tmp/ai12_metrics.json` に 3 variant × 200 utt 分の `proxy_mos` / `rtf_p50_ms` / `params_m` が出力
- **UTMOS v2 model キャッシュ E2E:** 1 回目 download、 2 回目はキャッシュヒット (`~/.cache/piper-plus/utmos/` 存在で torch hub 呼び出しなし)
- **README canonical 環境再現:** Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs で `expected_p50_ms` と実測差 < 3ms (計画 §4.6 / `audio-parity-contract.toml` canonical 値)
- **WandB audio log 連携 (任意):** `--wandb-log` フラグで 3 variant 各 5 sample を WandB へアップロード (CLAUDE.md `--audio-log-epochs` 既存挙動と整合)

### 受入基準 (Acceptance Criteria)

計画 §4.6 / §6 AI-12 から該当数値を引用:

- **UTMOS proxy MOS** (200 test utt): `istftnet2-mb` が baseline (`css10-ja-1d-baseline`) ± 0.1 以内、 `fly-convnext6` が baseline ± 0.1 以内
- **CPU RTF p50** (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs): `istftnet2-mb` < 20ms (baseline 27ms × 0.7 target、 計画 §4.6)、 `fly-convnext6` < 23ms (baseline × 0.85)
- **params**: `istftnet2-mb` 0.83M ± 0.05M (計画 §4.2)、 `fly-convnext6` 0.63M ± 0.05M (計画 §4.5)
- **proxy MOS determinism**: 同一 wav 2 回 scoring 差 < 1e-4
- **YAML 後方互換**: 既存 4 entry (6lang-base / tsukuyomi / edge-tts / gtts) の値完全不変
- **CI 時間**: 3 variant 全件 generate + metrics 一気通しが Xeon E5-2650 v4 単一スレッドで 30 分以内 (200 utt × 3 = 600 utt)

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から関連項目:

- **R3 (Q13 zero prior art):** iSTFTNet2-MB が proxy MOS で -0.3 以上劣化した場合、 本 benchmark が即時可視化する責務を負う。 200 utt が「-0.3 が偶然か恒常か」 を統計的に切り分けるサンプル数として十分か、 `format_summary` で std を併載することで判断可能にする
- **R6 (audio-parity-contract baseline regression):** 本チケットは `[mb_istft_1d]` baseline を読むのみで書かない契約だが、 `expected_p50_ms: 27` を `models.yaml` 側に持つことで `audio-parity-contract.toml` との二重定義になる懸念がある。 mitigation: 本 YAML 値はあくまで「人間レビュー用のヒント」 として扱い、 CI gate は `audio-parity-contract.toml` のみを source of truth とする旨を `models.yaml` コメントに明記
- **UTMOS v2 model download 失敗:** torch hub からの sarulab-utmos の lazy load が CI 環境 (offline runner) で失敗する可能性。 mitigation: `proxy_mos.load_utmos_model()` で `PIPER_UTMOS_CACHE` env var に local path を指定すれば hub 呼び出しをスキップする逃げ道を設ける
- **22050Hz → 16kHz リサンプル品質:** UTMOS v2 は 16kHz 想定。 piper-plus の 22050Hz wav を `torchaudio.functional.resample(orig=22050, new=16000, lowpass_filter_width=64)` で十分かは要検証。 mitigation: 既存 baseline (`piper-plus-6lang-base`) を 1 度だけ scoring し、 公開数値 (CLAUDE.md の README benchmark 表) との乖離が ±0.05 以内であることを CI 起動時 1 度だけ確認

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 `css10-ja-1d-baseline.decoder_type == "mb_istft_1d"`)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止、 `audio-parity-contract.toml` に書き込まない)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避、 `speaker_embedding[192]` 列を models.yaml に追加しない)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響は AI-16 で `audio-parity-contract.toml` tolerance に反映 (本チケットでは触れない)
- [ ] 既存 4 entry (6lang-base / tsukuyomi / edge-tts / gtts) の YAML 値完全不変 (`git diff models.yaml` の context 行が新規 entry のみ)
- [ ] `proxy_mos.py` の UTMOS v2 model load は default で CPU、 GPU 占有しない (計画 §4.4 1 GPU 学習との非干渉)
- [ ] `--variant` フラグ省略時の挙動は既存 generate_samples.py と完全一致 (全件モード)
- [ ] `test_benchmark.py` の既存 case を touch しない (G-1.9 後方互換 gate)
- [ ] proxy MOS determinism `|s1 - s2| < 1e-4` が pytest 7 / pytest 9 両環境で再現 (R5 mitigation)
- [ ] `metrics.json` の出力 schema (proxy_mos / rtf_p50_ms / params_m 列) が AI-13 / AI-14 で消費可能な形式である旨 docstring に明記

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「既存 `tools/benchmark/` 資産 (models.yaml / compute_metrics.py / generate_samples.py) を最大流用し、 `proxy_mos.py` を 1 ファイル新規追加するだけの最小 surface 改造」 である。 これは計画 §3 Conflict Map で `tools/benchmark/` が NONE / LOW と分類されている強みを活かし、 PR #222 / PR #537 のいずれが先に merge されても rebase ノイズを発生させない保守的選択である。 代替案 1 として 「benchmark harness 全体を `tools/eval/` 配下に切り出して MOS / SECS / cFW2VD / RTF を統合する evaluation pipeline 化」 を考えたが、 PR #222 が MOS / SECS 評価の責務を持っているため二重実装になる懸念があり捨てた。

代替案 2 は **integration-test 先行** (TDD ではなく E2E first): 200 utt × 3 variant の E2E pipeline を最初に書き、 後から `proxy_mos.py` unit test を埋めるアプローチである。 これは「UTMOS v2 model の torch hub lazy load が現実に動くか」 を最速で検証できる利点があるが、 1 GPU 占有との競合 (計画 §7 R8) で CI 化が難しく、 ローカル手動検証に依存することになる。 本採用案 (unit test 先行) は CI gate 化が容易で R8 mitigation と整合する。

代替案 3 として **3 variant を別々の YAML ファイル** に分割 (`models.poc.yaml` / `models.production.yaml`) する設計も検討した。 これは「PoC 値が production benchmark に混入しない」 メリットがあるが、 `compute_metrics.py` / `generate_samples.py` の YAML loader が 2 経路を持つことになり surface 拡大に繋がる。 採用案では PoC entry を既存 YAML に追記しコメントで `# --- AI-12: PoC variants ---` 区切りを入れることで、 production / PoC の境界を人間レビューで判別可能にしつつ loader を 1 経路に保った。 リリース時 (M6 採否判定) に PoC entry を削除するか production に昇格させるかは `/release-prep` で判断する。

採用案を 「現実解」 として位置づけ、 別案の利点 (代替 1 の統合 pipeline / 代替 2 の E2E 先行 / 代替 3 の YAML 分割) は本チケット範囲外の規模になるため捨てた。 PoC ステージで surface を最小に保ち、 PR #222 / #537 が安定 merge された後の M6 で再評価する余地を残す。

## 後続タスクへの連絡事項

AI-13 (7 ランタイム smoke + pairwise SNR 検証) に引き渡す具体的成果物:

- **3 variant ONNX path (仮置き):**
  - `/data/piper/output-css10-ja-1d-baseline/css10-ja-1d-baseline.onnx` (AI-02 学習成果、 本チケットで `models.yaml` 経由参照)
  - `/data/piper/output-istftnet2-mb-poc/css10-ja-istftnet2-mb.onnx` (AI-05 学習成果)
  - `/data/piper/output-fly-convnext6-poc/css10-ja-fly-convnext6.onnx` (AI-07 学習成果)
- **Python reference オーディオ canonical 生成元:** `/tmp/ai12_samples/{variant}/ja/{utt_id}.wav` (200 utt × 3 variant)。 AI-13 で Rust / Go / C# / WASM / C++ / C-API 側の合成結果と pairwise SNR を測る際の **Python anchor** として使う
- **`metrics.json` schema:** `{variant: {proxy_mos: {mean, std, p10, p50, p90}, rtf_p50_ms: float, params_m: float, sample_rate: 22050, n_utt: 200}}` の構造を AI-13 / AI-14 で同 schema で拡張すること
- **暫定 decoder_type default:** `mb_istft_1d` 不変 (リリース時に切替判断は M6 AI-18 採否判定 PR で行う)
- **expected_p50_ms 暫定値:** istftnet2-mb 18ms / fly-convnext6 23ms はあくまで計画 §4.6 target。 実測値が大幅に乖離した場合は AI-14 で `audio-parity-contract.toml` 反映前に **再協議**
- **UTMOS v2 キャッシュパス:** `~/.cache/piper-plus/utmos/` に download 済みであれば AI-13 / AI-14 の追加 200 utt scoring 時に再 download 不要 (時間短縮)
- **PR #222 rebase 時の注意:** `models.yaml` の 3 PoC entry は `speaker_ids: { ja: 0 }` (sid 経路) を使っているため、 PR #222 が `speaker_embedding[192]` に切り替えた後は AI-17 で本 YAML の load 経路に互換 wrapper を追加する必要あり (本チケットでは触れない)
- **PR #537 rebase 時の注意:** `test_benchmark.py` の 5 test case は pytest fixture 非依存に書いてあるため pytest 9 deprecation 影響なし。 ただし `torchaudio.functional.resample` の NumPy 2.x 互換は AI-16 で再確認

## 関連ドキュメント

- 親マイルストーン: [../milestones/M5-runtime-abi-parity.md](../milestones/M5-runtime-abi-parity.md)
- 親計画 §6 AI-12 / §4.6 / §3 Conflict Map: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 既存 benchmark 仕様: [../../benchmark-mos.md](../../benchmark-mos.md)
- audio parity contract (G-1.2 baseline 編集禁止 gate): [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml)
- UTMOS v2 出典 (sarulab-utmos hub model): https://github.com/sarulab-speech/UTMOS22
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — `models.yaml` に対しては NONE 衝突
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — pytest 9 deprecation のみ LOW
- 後続チケット: AI-13 (7 ランタイム smoke) / AI-14 (audio-parity-contract.toml に variant section 追加) / AI-15 (regression guard CI gate)

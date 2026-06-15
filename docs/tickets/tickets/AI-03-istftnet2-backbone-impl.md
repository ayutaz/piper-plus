# AI-03: iSTFTNet2-MB 1D-2D backbone 実装 (decoder_type 分岐 + _forward_1d2d)

## メタ情報

- ID: AI-03
- 親マイルストーン: [M2](../milestones/M2-istftnet2-mb-backbone.md)
- 工数見積: 3 日
- 依存チケット: AI-01 (CSS10 JA データセット整備)
- 後続チケット: AI-04 (TDD ユニットテスト), AI-05 (PoC 学習 50 epoch)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items / §4 PoC 設計](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) PoC の中核となる **backbone 置換実装**を本ブランチに投入する。 親計画 §4.2 (`docs/research/implementation-plan-a1-a2-2026-06-16.md`) で示された通り、 既存 `MBiSTFTGenerator` の 1D-only backbone (Conv1d / ConvTranspose1d) を 1D-2D ハイブリッドに改造することで、 論文値 RTF 0.011 / MOS 4.25 / 0.83M params (Kaneko et al., Interspeech 2023) の再現を目指す。 出力段の枠組み (`subband_conv_post` + `OnnxISTFT` + PQMF) は 100% 流用し、 backbone のみを置換する `_forward_1d2d` 新規経路を追加する。

本チケットは AI-01 (CSS10 JA データセット整備) の完了を前提とし、 後続の AI-04 (TDD ユニットテスト) と AI-05 (PoC 50 epoch 学習) に対して **decoder_type 分岐機構を備えた `mb_istft.py`** を引き渡す。 既存 `_forward_1d` 経路を default として温存することで、 親計画 §1 核心トレードオフ 1 で示された PR #222 (Zero-shot TTS) との HIGH conflict (Multi-scale FiLM 改造) を局所化し、 6lang base ckpt の forward-only smoke を維持したまま新経路のみを segregate する。

完了時点では本 ticket は学習結果や benchmark の妥当性を主張しない。 forward path / ONNX export / params 0.83M ± 0.05M / 既存 `[mb_istft_1d]` audio parity 不変、 までを成果物とする。 数値目標 (UTMOS proxy MOS / Xeon p50 / 7 ランタイム smoke) は AI-05 / AI-12 / AI-13 で検証する。

## 実装内容の詳細

### 編集対象ファイル

- **`src/python/piper_train/vits/mb_istft.py`** (現行 296 行)
  - L14 import 行に `Conv2d, ConvTranspose2d` を追記
  - L133 `class MBiSTFTGenerator(nn.Module)` の `__init__` (L142-) に `decoder_type: str = "mb_istft_1d"` 引数を追加 (default 不変)
  - L218 既存 `def forward(self, x, g=None)` を `_forward_1d(self, x, g=None)` にリネーム + thin dispatcher を新規 `forward` として置く
  - `_forward_1d2d` を新規メソッドとして追加 (約 60-80 行)
  - 2D block (kernel 3×3 / 3×5、 dilation `(1,2)` / `(2,1)`) を 4 段、 F 軸 1→2→4 pixel-shuffle で展開
- **`src/python/piper_train/vits/stft_onnx.py`** (touch しない)
  - `OnnxISTFT(hop=4)` は既存 instance を流用 (`subband_conv_post` の後段)
- **`src/python/piper_train/vits/models.py`** (1094 行) — `decoder_type` を config から拾って `MBiSTFTGenerator(decoder_type=...)` に渡すだけの最小編集 (約 10 行)
- **`src/python/piper_train/config.py`** (該当 dataclass / Pydantic model 想定) — `decoder_type: str = "mb_istft_1d"` field 追加 (default 不変、 G-1.9 後方互換 gate)

### 新規ファイル

なし。 本 ticket では既存 `mb_istft.py` 内に閉じる。 `_forward_1d2d` を独立 module 化しないのは、 `subband_conv_post` / `cond` / `OnnxISTFT` / `PQMF` の private state を共有する必要があるため (親計画 §3 Conflict Map の HIGH vs PR #222 評価でも同 module 内に閉じる方が rebase コスト低)。

### default 値 / 互換維持の制約 (G-1.9 後方互換 gate)

| 項目 | 既定 | 不変条件 |
|------|------|--------|
| `decoder_type` config default | `"mb_istft_1d"` | リリース時切替判断まで default 不変。 切替は AI-18 採否判定後 |
| `MBiSTFTGenerator.forward(x, g)` 出力 shape | `[B, 1, T]` | 1D / 1D-2D 両経路で完全一致 |
| `subband_conv_post` / `OnnxISTFT` / `PQMF` 重み | 不変 | 既存 1D ckpt との forward-only smoke を維持 |
| ONNX I/O signature | 不変 | PR #222 の `sid → speaker_embedding[192]` 変更との二重同期回避 (親計画 §1 核心トレードオフ 2) |
| `[mb_istft_1d]` audio-parity baseline | **絶対不変** | `audio-parity-contract.toml` の baseline section は AI-14 で別 section 追加、 本 ticket は touch しない (G-1.2 gate) |

### PR #222 / PR #537 との conflict 回避策

親計画 §3 Conflict Map から該当行抜粋:

> `src/python/piper_train/vits/mb_istft.py` | A-1 backbone 1D-2D 化、 `_forward_1d2d` 追加 | **HIGH** (Multi-scale FiLM 衝突) | NONE | **A-1 先行**、 PR #222 rebase で FiLM rank-aware 化

具体的回避策:

- `forward` を **dispatcher のみ** にし、 1D 経路 (`_forward_1d`) は既存ロジックを **コードレベルで全く変えない** (rename only)。 PR #222 が `_apply_film` を導入する際は `_forward_1d` 側にだけ FiLM を入れる差分を AI-17 (M6) で吸収可能にする
- 2D 経路 (`_forward_1d2d`) は `_apply_film` 非対応の状態で先行 merge し、 PR #222 rebase 時に rank-aware 化 (1D=split dim=1 / 2D=split dim=1 維持) を追加する責務を AI-17 に明示的に委譲
- PR #537 (Python 3.13 / bf16-mixed default / TF32-on) との conflict は NONE。 ただし数値ドリフトは AI-16 で再 baseline 化される予定のため、 本 ticket は `torch.float32` deterministic で実装し bf16 path は明示テストしない

### 疑似コード スケッチ (`_forward_1d2d` 主要部)

```python
def _forward_1d2d(self, x, g=None):
    # x: [B, in_channels, T_mel]
    x = self.conv_pre(x)                       # 既存 1D conv_pre 流用
    if g is not None:
        x = x + self.cond(g)                   # 既存 cond 流用
    # 1D 段で T 軸を hop=4 まで upsample (既存 ups[0]/ups[1])
    for i in range(self.num_upsamples_1d):     # 2 段だけ 1D ConvTranspose1d
        x = F.leaky_relu(x, modules.LRELU_SLOPE)
        x = self.ups[i](x)
        xs = sum(self.resblocks[i * self.num_kernels + j](x)
                 for j in range(self.num_kernels)) / self.num_kernels
        x = xs
    # 1D → 2D: F 軸を 1 から立ち上げて 2D Block × 4
    x = x.unsqueeze(2)                         # [B, C, F=1, T]
    for block in self.blocks_2d:               # Conv2d kernel (3,3)/(3,5),
                                               # dilation (1,2)/(2,1),
                                               # F: 1→2→4 pixel-shuffle
        x = block(x)
    x = x.flatten(1, 2)                        # [B, C*F, T]
    x = F.leaky_relu(x)
    # 既存 subband_conv_post + OnnxISTFT(hop=4) + PQMF はそのまま
    x = self.subband_conv_post(x)
    return self._istft_pqmf_postprocess(x)     # 既存 ヘルパ抽出
```

ConvTranspose2d は使わず F 軸拡大は pixel-shuffle (Reshape+Transpose) で実装する (Risk R7 への対応: 親計画 §7 R7、 mobile EP 用 Conv2d/Reshape/Transpose のみ採用)。

### 設定 default 値、 新規 CLI フラグ

- `decoder_type` config field 追加: `"mb_istft_1d"` (default) / `"istftnet2_mb_1d2d"` の 2 値 string enum
- 新規 CLI フラグは追加しない。 `--decoder-branch` は AI-08 (MS-Wavehax) で別途 export_onnx.py に追加予定 (本 ticket 範囲外)

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|---------|---------|
| ML Architect | 1 | PyTorch、 VITS/HiFi-GAN 内部構造、 iSTFTNet2 論文読み込み、 pixel-shuffle / im2col の挙動把握 | `_forward_1d2d` 内部設計、 2D Block の kernel/dilation/channel schedule 決定、 params 0.83M ± 0.05M の合わせ込み |
| ONNX Engineer | 1 | ONNX opset 17、 Conv2d / Reshape / Transpose の ORT EP coverage (CPU/XNNPACK/CoreML/WebGPU/QNN)、 op set audit | export 経路の検証 (graph dump + op set diff)、 ConvTranspose2d 不使用の機械検証、 親計画 §2.5 Q15 (QNN HTP coverage) との整合確認 |
| Compat & Rebase Engineer | 1 | PR diff 読解 (#222 Multi-scale FiLM)、 contract gate (G-1.2 / G-1.9)、 audio-parity-contract.toml の baseline 編集禁止 gate | `[mb_istft_1d]` baseline 不変の機械 check、 PR #222 rebase 後の FiLM rank-aware 化 (AI-17) との non-conflict 設計、 PR #537 数値ドリフト (TF32) の影響範囲ドキュメント化 |

合計 3 名。 学習 (AI-05) や 7 ランタイム同期 (AI-13) はそれぞれ別チケット担当に渡すため本 ticket チームには含めない。 ML Architect が PR author、 ONNX Engineer と Compat & Rebase Engineer が必須 reviewer。

## 提供範囲 (Scope)

### 含むもの

- `src/python/piper_train/vits/mb_istft.py` への `decoder_type` 引数 + `_forward_1d` rename + `_forward_1d2d` 新規追加
- `src/python/piper_train/vits/models.py` への `decoder_type` propagation (~10 行)
- config dataclass / Pydantic model への `decoder_type` field (default `"mb_istft_1d"`)
- forward path smoke (params 0.83M ± 0.05M 計測 + 出力 shape `[B, 1, T]` assert) を確認できる最小限の Python script (`scripts/check_istftnet2_params.py` 想定、 約 30 行)
- ONNX export 一時 dry-run (Conv2d / Reshape / Transpose のみが op set に出ること、 ConvTranspose2d が含まれないこと)
- 既存 `_forward_1d` の bit-exact 維持を確認する forward-only smoke (6lang base ckpt 読込 → forward → 出力 hash 不変)

### 含まないもの (Out of Scope)

- ユニットテスト (`test_istftnet2_generator.py`) の網羅実装 → **AI-04** で TDD として先行 (実装直前に skeleton のみ用意)
- PoC 50 epoch 学習および UTMOS proxy MOS 評価 → **AI-05**
- benchmark (Xeon E5-2650 v4 p50 < 20ms) 測定 → **AI-12**
- 7 ランタイム smoke + pairwise SNR ≥ 30dB → **AI-13**
- `audio-parity-contract.toml` への `[istftnet2_mb_1d2d]` section 追加 → **AI-14**
- regression guard CI gate (default decoder_type assert / ONNX I/O 不変 audit) → **AI-15**
- PR #222 rebase 後の FiLM rank-aware 化 → **AI-17**
- PR #537 merge 後の bf16-mixed 再 benchmark → **AI-16**

## テスト項目

### Unit Tests

> 本 ticket では skeleton のみ用意し、 fixture とアサート本体は AI-04 で TDD 化する。 ただし以下 4 件は**本 ticket 内で green** にして merge する。

- **`src/python/tests/test_istftnet2_generator.py::test_decoder_type_default_is_mb_istft_1d`**
  - assert: `MBiSTFTGenerator(**default_config).decoder_type == "mb_istft_1d"`
  - 目的: G-1.9 後方互換 gate (default 不変)
- **`src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_output_shape`**
  - input: `x.shape == [1, 192, 50]`, `g.shape == [1, 256, 1]`
  - assert: `gen._forward_1d2d(x, g).shape == [1, 1, 50 * 256]` (T 軸が hop_length 倍に展開)
  - assert: `out.dtype == torch.float32`
- **`src/python/tests/test_istftnet2_generator.py::test_param_count_within_budget`**
  - assert: `0.78e6 <= sum(p.numel() for p in gen.parameters() if p.requires_grad) <= 0.88e6` (0.83M ± 0.05M、 親計画 §4.6 footprint 目標)
- **`src/python/tests/test_istftnet2_generator.py::test_forward_1d_bit_exact_with_baseline`**
  - fixture: 6lang base ckpt の `dec.state_dict()` を 1D-only `MBiSTFTGenerator` に load
  - assert: `gen._forward_1d(x, g)` の出力 hash が baseline ckpt forward 結果と完全一致 (`torch.allclose(rtol=0, atol=0)`)
  - 目的: G-1.2 (既存 baseline 不変) の merge 前 sanity

既存 `src/python/tests/test_mb_istft_generator.py` は **touch しない** (G-1.9 後方互換 gate、 親計画 §6 AI-04 注記)。

### E2E Tests

> 本 ticket では smoke レベルまで、 学習・benchmark は後続。

- **forward-only smoke** (`scripts/check_istftnet2_params.py` 経由)
  - `decoder_type="istftnet2_mb_1d2d"` で random init → `forward(x, g)` → 出力 shape & param count 表示
- **ONNX export dry-run**
  - `uv run python -m piper_train.export_onnx <ckpt> /tmp/a1.onnx --no-stochastic --decoder-type istftnet2_mb_1d2d`
  - assert: `onnx.load(/tmp/a1.onnx)` の op set が `{Conv, Conv2d, Reshape, Transpose, MatMul, ...}` のみで `ConvTranspose2d` を含まない (Risk R7 対応)
  - assert: graph inputs / outputs 名 & shape が baseline と同一 (PR #222 ONNX I/O 二重同期回避)
- **WandB audio log なし** (本 ticket は学習を伴わないため AI-05 へ移譲)
- **pairwise SNR / 7 ランタイム smoke なし** (AI-13 移譲)
- **Xeon p50 benchmark なし** (AI-12 移譲)

### 受入基準 (Acceptance Criteria)

親計画 §4.6 / §5 から該当する目標値を引用 (本 ticket 範囲のみ):

- **params:** `0.83M ± 0.05M` (フル `MBiSTFTGenerator` で計測、 `decoder_type="istftnet2_mb_1d2d"` 時)
- **出力 shape:** `[B, 1, T]` 完全一致 (1D / 1D-2D 両経路)
- **既存 `[mb_istft_1d]` baseline:** 完全不変 (forward bit-exact / audio-parity-contract.toml 編集ゼロ)
- **default decoder_type:** `"mb_istft_1d"` (G-1.9 後方互換 gate)
- **ONNX op set:** `Conv` / `Conv2d` / `Reshape` / `Transpose` / 既存 op のみ。 `ConvTranspose2d` を含まない (Risk R7 mobile EP CPU fallback 回避)
- **ONNX I/O:** name / shape / dtype が baseline と完全一致 (PR #222 二重同期回避)
- **forward smoke 実測時間 (CPU, Xeon E5-2650 v4 / 25 phoneme):** 参考値として記録 (target は AI-05 / AI-12)

以下は AI-05 / AI-12 / AI-13 で検証される目標 (本 ticket では未検証):

- UTMOS proxy MOS: baseline ± 0.1 以内 → AI-05
- CPU RTF p50 < 20ms (target × 0.7) → AI-12
- 7 ランタイム smoke + pairwise SNR ≥ 30dB → AI-13

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

親計画 §7 Risk Register からの該当項:

- **R1 (HIGH/HIGH):** PR #222 Multi-scale FiLM との forward 構造 HIGH conflict。 本 ticket では `_forward_1d2d` を FiLM 非対応で先行 merge し、 `_apply_film` の rank-aware 化を AI-17 に委譲することで局所化
- **R6 (MEDIUM/HIGH):** `audio-parity-contract.toml` の `[mb_istft_1d]` baseline を誤って書き換えるリスク。 本 ticket では同 file を **編集しない**。 AI-14 で別 section として併載
- **R7 (LOW/MEDIUM):** 2D op の mobile EP CPU fallback リスク。 ConvTranspose2d 不使用 + F 軸拡大は pixel-shuffle で実装することで対応

本 ticket 固有の細かい懸念:

- **数値ドリフト:** `unsqueeze(2)` / `flatten(1, 2)` の Reshape / Transpose 経路で torch eager と ONNX runtime の bit-exact が崩れやすい。 export dry-run 時に `torch.onnx.export(verify=True)` で 1e-5 tolerance 確認
- **params 0.83M 合わせ込み:** 2D Block の channel schedule (in_ch → 1D 段で半減 → 2D 段で更に半減) で合わせる必要があるが、 論文 (Kaneko et al. 2023) は実装詳細を全公開していないため、 内部チャネル 64→32→16→8 の試行錯誤が発生する可能性 (1 日想定の追加デバッグ時間)
- **既存 `_forward_1d` の rename による blame churn:** PR レビューで「実質変更なし」を強調する diff 表記 (`git rename detection` が効くよう改行最小化)
- **デバッグの落とし穴:** 2D Block の dilation `(1,2)` / `(2,1)` は F=1 入力に対して padding 計算が直感に反する。 unit test `test_forward_1d2d_output_shape` で F 軸最終サイズを assert することで誤り検知

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (`"mb_istft_1d"`、 G-1.9 後方互換)
- [ ] `[mb_istft_1d]` audio parity 不変 (`audio-parity-contract.toml` 編集ゼロ、 G-1.2 baseline 編集禁止)
- [ ] ONNX I/O 不変 (graph inputs / outputs name & shape が baseline と完全一致、 PR #222 二重同期回避)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映する責務を AI-16 に明示記載
- [ ] PR #222 rebase 後の FiLM rank-aware 化を AI-17 に明示委譲 (本 ticket では FiLM 非対応で merge)
- [ ] `_forward_1d` のロジックがコードレベルで rename only (バイト一致 forward smoke で確認)
- [ ] ConvTranspose2d を使わず F 軸拡大は pixel-shuffle (Reshape+Transpose) で実装 (Risk R7 対応)
- [ ] ONNX op set audit で `ConvTranspose2d` 不在を機械 check
- [ ] params 0.83M ± 0.05M を CI で機械 assert (test_param_count_within_budget)
- [ ] 既存 `test_mb_istft_generator.py` は touch しない
- [ ] forward bit-exact smoke (6lang base ckpt resume → 出力 hash 不変) green

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「既存 `MBiSTFTGenerator` 内に `decoder_type` 分岐を入れ `_forward_1d` / `_forward_1d2d` 2 メソッド共存」だが、 代替案として **独立 module 化** (`istftnet2_generator.py` を新規ファイルとして切り出し、 既存 `MBiSTFTGenerator` を継承しないシブリングクラスとする) が考えられた。 この案の利点は (a) PR #222 Multi-scale FiLM 改造との conflict が file-level NONE になる、 (b) ONNX export 経路で `decoder_type` を condition せず直接 class 名で dispatch できる、 (c) blame churn が完全に 0、 という 3 点。 捨てた理由は `subband_conv_post` / `cond` / `OnnxISTFT` / `PQMF` の private state 共有が必要で、 継承を avoid すると同コードが 2 箇所に重複 (~100 行) して保守コストが膨らむため。 さらに `models.py:754` 付近の `self.dec = MBiSTFTGenerator(...)` で class を switch する分岐ロジックが models.py 側に出現し、 A-2 (AI-08 sibling `dec_wavehax`) との二重 switch で複雑化する懸念があった。

別の代替として **TDD ではなく integration-test 先行** (本 ticket と AI-04 を融合させ、 forward / ONNX export / params count の minimal smoke を実装と同時に commit) も検討した。 採用案で TDD 化したのは、 親計画 §8 Immediate Next Steps 2 が「`test_istftnet2_generator.py` (AI-04) を **TDD** で先に書く」と明示しているため。 ただしこの分割は工数 3+0.5 = 3.5 日で integration-first (~2.5 日) より 1 日長い。 利点は (a) `_forward_1d2d` の output shape 不変条件が unit test の言語で外部化される、 (b) AI-04 がレビュー観点の checklist として明示的に並列実行可能、 という 2 点。 採用判断は「親計画の明示指示」だが、 もし採否判定 (AI-18) で A-1 棄却となった場合 TDD コストが回収できないリスクは残る。

第三の代替案として **dual vocoder と統合した adaptive single vocoder** (decoder_type を runtime で切り替えず、 1D-2D 経路を default としつつ低 RTF 要求時のみ 1D fast path に動的 fallback する) を考えた。 利点は inference 時にユーザが `decoder_type` を意識せず最高品質経路を常用できる点。 捨てた理由は (a) PoC 段階で benchmark 比較ができなくなる、 (b) `audio-parity-contract.toml` の variant section が分割できず regression guard が壊れる、 (c) PR #222 / #537 と同時に merge する場合に conflict 範囲が広がる、 の 3 点。 採用案は「明示 dual path + default 不変」で benchmark / 採否判定の transparency を優先したが、 v1.16.0 リリース時にユーザ向け CLI で `--auto-decoder` flag を追加することで本 rethink 案の利点を別経路で取り込む余地はある。

## 後続タスクへの連絡事項

### AI-04 (TDD ユニットテスト追加) への引き渡し

- `src/python/tests/test_istftnet2_generator.py` は本 ticket で **skeleton + 4 件のみ green** で merge。 AI-04 では以下のテストを **追加** する責務:
  - `test_forward_1d2d_with_lid` (lid=0 固定、 6 言語 lid sweep は AI-05 で)
  - `test_forward_1d2d_grad_flow` (`backward()` で `_forward_1d2d` 経由の勾配が全 param に届く)
  - `test_forward_1d2d_onnx_roundtrip` (export → ORT inference → torch eager 出力の `allclose(rtol=1e-4, atol=1e-5)`)
  - `test_forward_1d2d_dilation_shape` (2D Block の dilation `(1,2)`/`(2,1)` で F 軸が想定通り 1→2→4 展開)
- 既存 `test_mb_istft_generator.py` は touch 禁止 (G-1.9 後方互換)

### AI-05 (PoC 50 epoch 学習) への引き渡し

- ckpt 出力先 (暫定): `/data/piper/output-istftnet2-mb-poc/last.ckpt`
- ONNX 出力先 (暫定): `/data/piper/output-istftnet2-mb-poc/istftnet2-mb-poc.onnx`
- 学習コマンド (Template B base、 config に `decoder_type='istftnet2_mb_1d2d'` 設定):

  ```bash
  uv run python -m piper_train \
      --dataset-dir /data/piper/dataset-css10-ja-poc \
      --resume-from-multispeaker-checkpoint /data/piper/piper-plus-base/model.ckpt \
      --max_epochs 50 --batch-size 4 --samples-per-speaker 4 \
      --base_lr 2e-5 --no-wavlm --precision 32-true \
      --default_root_dir /data/piper/output-istftnet2-mb-poc/
  ```

- noise_scale=0.667 固定 (PR #222 default 変更影響を排除)
- 6lang base ckpt から **1D 部分のみ warm start** (新規 2D Block は init_weights で random init)。 ckpt load 時に missing_keys 警告が出るのは想定動作

### AI-13 (7 ランタイム ABI 検証) への将来引き渡し (AI-05 経由)

- ONNX I/O 不変なので 7 ランタイム側コード変更なし
- ただし内部 op に `Conv2d` / `Reshape` / `Transpose` が増えるため、 op set audit の expected list を AI-14 で更新する旨を明示

### contract / spec 更新箇所 (将来 AI に委譲)

- `audio-parity-contract.toml` への `[istftnet2_mb_1d2d]` section 追加 → **AI-14** (本 ticket は触らない)
- `ort-session-contract.toml` への Conv2d op coverage 追記 → **AI-14** (任意、 必要なら)
- `text-splitter-contract.toml` → **編集禁止** (decoder-agnostic 維持、 親計画 §3 / §4.3)

### PR #222 rebase 時の注意 (AI-17 への引き渡し)

- `forward` dispatcher は変えず、 `_apply_film` を `_forward_1d` 側にだけ追加すれば 1D 経路の Multi-scale FiLM 化は完了
- `_forward_1d2d` 側の FiLM は 2D rank-aware (`x.shape == [B, C, F, T]` で `dim=1` split を維持) として AI-17 で追加実装
- `cond_layers` の channel schedule は `decoder_type` 別に dict で保持し、 ONNX export 時に `decoder_type` ごとに別 graph を生成 (companion ONNX で別ファイル化される A-2 と同方式)

## 関連ドキュメント

- 親マイルストーン: [../milestones/M2-istftnet2-mb-backbone.md](../milestones/M2-istftnet2-mb-backbone.md)
- 親計画 §6 Action Items: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 親計画 §4.2 A-1 PoC 設計: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 親計画 §3 Conflict Map (`mb_istft.py` HIGH vs PR #222): [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 親計画 §7 Risk Register R1 / R6 / R7: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- Decoder Upgrade deep-dive §2 A-1: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 改善調査統合 §A-1: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- 関連 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — Multi-scale FiLM HIGH conflict、 AI-17 で rebase
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04](https://github.com/ayutaz/piper-plus/pull/537) — 数値ドリフトを AI-16 で再 baseline
- 関連 spec:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — `[mb_istft_1d]` 編集禁止、 `[istftnet2_mb_1d2d]` は AI-14 で追加
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — EP / opset 規約、 Conv2d 検証ポイント
- 論文: [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023, NTT)
- 既存実装: `src/python/piper_train/vits/mb_istft.py` (296 行、 L133 MBiSTFTGenerator, L218 forward)

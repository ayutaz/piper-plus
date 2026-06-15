# AI-06: FLY-TTS ConvNeXt6 decoder 実装 (fly_decoder.py 新規)

## メタ情報

- ID: AI-06
- 親マイルストーン: [M3](../milestones/M3-fly-tts-parallel-harness.md)
- 工数見積: 2 日
- 依存チケット: AI-01 (CSS10 JA データセット整備)
- 後続チケット: AI-07 (FLY-TTS PoC 学習 50 epoch)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items (AI-06) / §4.5 FLY-TTS 並走 / §8 Immediate Next Steps #3](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) は Q13 で zero prior art と確定しており、 50 epoch 投資後に MOS 劣化または CPU RTF 退化を起こすリスクが MEDIUM-HIGH (Risk Register R3) と評価されている。 本チケットはその**失敗時の即時切替先**として FLY-TTS (Guo et al., Interspeech 2024、 MOS 4.12 実証済み) の decoder 部分 (ConvNeXt × 6 + single-band iSTFT) を `fly_decoder.py` として新規実装し、 Day 2 までに forward + ONNX export smoke を通すことをゴールとする。

計画 §4.5 が指す通り、 FLY-TTS は MB-iSTFT-VITS / iSTFTNet2-MB と異なり **PQMF / sub-band loss / 2D conv を一切使わない**シンプルな経路で、 既存 `OnnxISTFT` 追加インスタンスを生やすのみで完結する (新規 ~200 LoC)。 計画 §3 Conflict Map では `mb_istft.py` (HIGH conflict with PR #222) と独立した新ファイルとして配置することで、 PR #222 / #537 の merge 状況に関係なく単独完結する設計を取る (§8 Immediate Next Steps #3)。

上流の AI-01 から CSS10 JA single-speaker LJSpeech 形式 + 16dim prosody が引き渡される前提で、 下流の AI-07 (PoC 学習 50 epoch) には decoder module + smoke 済み ONNX export 経路 + `--c-sub-stft 0.0` 学習レシピを引き渡す。

## 実装内容の詳細

### 新規ファイル

- **`src/python/piper_train/vits/fly_decoder.py`** (新規、 概略 200 LoC)
  - `ConvNeXtBlock1d` (~40 LoC): DepthwiseConv1d(k=7, padding=3) → LayerNorm(channels_last 移行) → Linear(channels→4×channels) → GELU → Linear(4×channels→channels) → residual + DropPath (optional)
  - `FlyDecoder` (~120 LoC): `__init__` で `conv_pre` (Conv1d 192→256) + `ConvNeXtBlock1d × 6` + `conv_post` (Conv1d 256→1026 で magnitude/phase 同時出力) + `OnnxISTFT(n_fft=1024, hop_length=256)` 既存 instance を import
  - `forward(x, g=None)`: shape `[B, 192, T]` → `[B, 256, T]` → 6 block 通過 → `conv_post` で `[B, 1026, T]` → split で `(mag[B,513,T], phase[B,513,T])` → `OnnxISTFT` → `[B, 1, T_audio]` 出力
  - g (speaker embedding) は AI-01 の単一話者 PoC では `None` で済むが、 後の multi-speaker FT に備えて Conv1d projection placeholder を残置 (default は no-op)
  - 公開 API: `class FlyDecoder(nn.Module)` のみ、 既存 `MBiSTFTGenerator` 系を import しない (完全独立)

### 既存ファイルへの最小編集

- **`src/python/piper_train/vits/stft_onnx.py`**: 編集**不要**。 既存 `OnnxISTFT(n_fft, hop_length)` を `fly_decoder.py` から import するのみ (n_fft=1024, hop_length=256 の新 instance を `FlyDecoder.__init__` 内で構築)。 計画 §3 Conflict Map 行 `stft_onnx.py | OnnxISTFT 追加 instance | LOW | NONE` 該当
- **`src/python/piper_train/vits/models.py`**: 本チケット範囲では編集**不要**。 `decoder_type='fly_convnext6'` 受領は AI-07 (PoC 学習) で `Generator` 選択 if 分岐に追加する (本チケットでは decoder module 単体実装のみ)
- **`src/python/piper_train/vits/mb_istft.py` / `lightning.py`**: touch しない (G-1.2 baseline 編集禁止 + G-1.9 後方互換 gate)

### 設定 default / 新規 CLI フラグ

- 本チケットでは CLI フラグ追加なし (AI-07 学習チケットで `--c-sub-stft 0.0` 既存フラグの 0 指定および `--decoder-type fly_convnext6` の追加を行う)
- `FlyDecoder.__init__` のハイパーパラメータ default:
  - `in_channels=192` (VITS posterior latent dim)
  - `hidden_channels=256` (ConvNeXt 内部、 4× expand=1024)
  - `num_blocks=6` (論文値)
  - `kernel_size=7` (depthwise、 論文値)
  - `n_fft=1024`, `hop_length=256` (論文値、 既存 MB-iSTFT の n_fft=16/hop=4 とは独立)

### PR #222 / PR #537 との conflict 回避策

計画 §3 Conflict Map より:

- `fly_decoder.py` は新規ファイルのため**衝突 NONE / NONE**。 PR #222 (`mb_istft.py` HIGH conflict) / PR #537 (プラットフォーム層、 コード衝突 NONE) のどちらの merge 状況にも依存しない (§8 Immediate Next Steps #3 で明示)
- `stft_onnx.py` 行 `LOW | NONE | A-1/A-2 先行で OK` の通り、 新 instance 構築のみで既存定義 unchanged
- `models.py` 編集を本チケットから除外することで PR #222 の `spk_proj` 統合点 (HIGH conflict 行) との衝突を完全回避

### 疑似コード (FlyDecoder.forward の骨格)

```python
# fly_decoder.py
import torch
from torch import nn
from torch.nn import Conv1d, functional as F
from .stft_onnx import OnnxISTFT


class ConvNeXtBlock1d(nn.Module):
    def __init__(self, channels: int, kernel_size: int = 7, expand: int = 4):
        super().__init__()
        self.dwconv = Conv1d(channels, channels, kernel_size,
                             padding=kernel_size // 2, groups=channels)
        self.norm = nn.LayerNorm(channels)
        self.pwconv1 = nn.Linear(channels, expand * channels)
        self.pwconv2 = nn.Linear(expand * channels, channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: [B, C, T]
        residual = x
        x = self.dwconv(x)
        x = x.transpose(1, 2)             # [B, T, C] for LayerNorm channels_last
        x = self.norm(x)
        x = self.pwconv1(x)
        x = F.gelu(x)
        x = self.pwconv2(x)
        x = x.transpose(1, 2)             # back to [B, C, T]
        return residual + x


class FlyDecoder(nn.Module):
    def __init__(self, in_channels: int = 192, hidden_channels: int = 256,
                 num_blocks: int = 6, kernel_size: int = 7,
                 n_fft: int = 1024, hop_length: int = 256):
        super().__init__()
        self.conv_pre = Conv1d(in_channels, hidden_channels, 7, padding=3)
        self.blocks = nn.ModuleList([
            ConvNeXtBlock1d(hidden_channels, kernel_size) for _ in range(num_blocks)
        ])
        out_dim = (n_fft // 2 + 1) * 2  # magnitude + phase
        self.conv_post = Conv1d(hidden_channels, out_dim, 7, padding=3)
        self.istft = OnnxISTFT(n_fft=n_fft, hop_length=hop_length)
        self.n_fft = n_fft

    def forward(self, x: torch.Tensor, g: torch.Tensor | None = None) -> torch.Tensor:
        x = self.conv_pre(x)
        for blk in self.blocks:
            x = blk(x)
        x = self.conv_post(x)             # [B, n_fft+2, T]
        cutoff = self.n_fft // 2 + 1
        magnitude = torch.exp(x[:, :cutoff, :].clamp(max=10))
        phase = torch.sin(x[:, cutoff:, :])  # bounded [-1, 1] (論文式)
        audio = self.istft(magnitude, phase)  # [B, 1, T_audio]
        return audio
```

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|----------|---------|
| Lead Implementer (ML Researcher) | 1 | PyTorch / ConvNeXt 実装経験 / iSTFT 理解 | `fly_decoder.py` 本体実装、 論文 (FLY-TTS Interspeech 2024 / ConvNeXt CVPR 2022) の数式・ハイパー値の正確な反映 |
| ONNX Engineer | 1 | torch.onnx.export / ONNX opset 15 / 既存 `stft_onnx.py` 構造理解 | ONNX export round trip smoke、 op coverage が Conv1d + LayerNorm + GELU + Reshape + 既存 Conv 化 iSTFT のみであることを assert、 QNN HTP / NNAPI / CoreML 互換性事前確認 (Phase 4 Risk 1 設計制約と整合) |
| Test Engineer | 1 | pytest / parametrize / 数値テスト | `test_fly_decoder.py` の Unit Test 設計 (TDD で `__init__` より先に書く)、 既存 `test_mb_istft_generator.py` を一切 touch しない (G-1.2 / G-1.9 gate) |

**3 名構成の根拠:** 新規ファイル 1 つの実装でランタイム連携や 7 ランタイム同期 (AI-13) は範囲外、 学習統合 (AI-07) も後続チケット。 ML/ONNX/Test の 3 軸で最小チーム。 Lead + ONNX を兼任することも可能だが、 ONNX op audit (R7 と整合的な対策) は独立判断が望ましい。

## 提供範囲 (Scope)

### 含むもの

- 新規 `src/python/piper_train/vits/fly_decoder.py` (~200 LoC、 `ConvNeXtBlock1d` + `FlyDecoder` クラス)
- 既存 `OnnxISTFT(n_fft=1024, hop_length=256)` を `FlyDecoder.__init__` 内で新 instance として構築
- Unit Test `src/python/tests/test_fly_decoder.py` (新規、 TDD で先行作成)
- ONNX export round trip smoke スクリプト (`scripts/smoke_fly_decoder_onnx.py` 新規 ~30 LoC) で forward → torch.onnx.export → onnxruntime CPUExecutionProvider で再ロード → numerical equivalence (atol=1e-4) を assert
- params count 0.63M ± 0.05M の数値検証

### 含まないもの (Out of Scope)

- `models.py` の `Generator` 選択分岐への `decoder_type='fly_convnext6'` 追加 → AI-07 (PoC 学習) で扱う
- `lightning.py` の `--c-sub-stft 0.0` CLI フラグ既存活用 → AI-07 で確認
- CSS10 JA 50 epoch 学習 → AI-07
- proxy MOS 計測 / CPU RTF benchmark → AI-12 (3 variant benchmark 追加)
- 7 ランタイム smoke (Python/Rust/Go/C#/WASM/C++/C-API) → AI-13
- `audio-parity-contract.toml` への `[fly_convnext6]` section 追加 → AI-14
- ONNX export での FP16 化 / `--simplify` 適用 → AI-13 範囲
- Multi-speaker speaker embedding (g) の本格統合 → 本 PoC 範囲外 (placeholder のみ)

## テスト項目

### Unit Tests

新規 `src/python/tests/test_fly_decoder.py` (TDD、 `fly_decoder.py` 実装より先に書く):

- `test_convnext_block_residual_shape`
  - assert: `block(x).shape == x.shape` for `x = torch.randn(2, 256, 100)`
- `test_convnext_block_residual_finite`
  - assert: `torch.isfinite(block(x)).all()` (NaN / Inf なし)
- `test_fly_decoder_output_shape`
  - x = `torch.randn(1, 192, 50)` → output shape == `(1, 1, 50 * 256)` (hop_length=256 倍)
- `test_fly_decoder_params_count`
  - assert: `0.58e6 <= sum(p.numel() for p in dec.parameters()) <= 0.68e6` (0.63M ± 0.05M、 計画 §4.5)
- `test_fly_decoder_no_2d_op`
  - 全 modules を walk して `isinstance(m, (nn.Conv2d, nn.ConvTranspose2d))` が一つも無いことを assert (Phase 4 Risk 1 / R7 と整合)
- `test_fly_decoder_no_pqmf`
  - assert: `not any('PQMF' in type(m).__name__ for m in dec.modules())` (計画 §4.5 「PQMF 不使用」)
- `test_fly_decoder_forward_deterministic`
  - `torch.manual_seed(0)` 下で 2 回 forward → `torch.allclose(o1, o2)`
- `test_fly_decoder_gradient_flow`
  - `output.sum().backward()` 後、 `conv_pre.weight.grad is not None and torch.isfinite(grad).all()`
- **既存 `src/python/tests/test_mb_istft_generator.py` は touch しない** (G-1.9 後方互換 gate)
- **既存 `src/python/tests/test_istftnet2_generator.py` (AI-04 で AI-03 と並行作成) も touch しない**

### E2E Tests

新規 `scripts/smoke_fly_decoder_onnx.py` (~30 LoC、 本チケットで作成):

- ONNX export round trip
  - `torch.onnx.export(fly_decoder, dummy_x, "out/fly_decoder.onnx", opset_version=15, dynamic_axes={"x": {2: "T"}, "audio": {2: "T_audio"}})`
  - `ort.InferenceSession("out/fly_decoder.onnx", providers=["CPUExecutionProvider"])`
  - `np.allclose(torch_out.numpy(), ort_out, atol=1e-4)` を assert
- ONNX op audit
  - `onnx.load("out/fly_decoder.onnx").graph.node` を走査し op_type set が `{Conv, LayerNormalization, Gelu, Transpose, Reshape, Split, Exp, Sin, Mul, Add, Clip, ...}` のみ (`Conv2d` / `ConvTranspose` 系が出現しないこと) を assert (R7 mitigation の Phase 4 Risk 1 設計制約と整合)

CSS10 JA 50 epoch 学習・proxy MOS は AI-07 / AI-12 で実施 (本チケット範囲外)。

### 受入基準 (Acceptance Criteria)

計画 §4.5 / §4.6 / §5 Milestone 3 から該当数値を引用:

- params: **0.63M ± 0.05M** (計画 §4.5 「ConvNeXt × 6 + Conv1d(256→1026) + OnnxISTFT、 0.63M params」)
- forward 出力 shape: `[B, 1, T_audio]` で `T_audio == T_input * 256` (hop_length=256)
- ONNX export: opset 15 で round trip 成功、 `atol=1e-4`
- ONNX op set: Conv / LayerNormalization / Gelu / Transpose / Reshape / Split / Exp / Sin / Mul / Add / Clip 系のみ (Conv2d / ConvTranspose2d / STFT / DFT 等が出現しない、 計画 §3 Conflict Map で衝突 NONE を保つため)
- Unit Test: 上記 8 関数全 green
- 既存 `[mb_istft_1d]` baseline test 影響なし (Milestone 5 Exit Criteria の前段)
- 注: proxy MOS / CPU RTF × 0.85 以下 / 7 ランタイム smoke は AI-12 / AI-13 で評価 (本チケット範囲外)

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

- **R3 (MEDIUM-HIGH):** A-1 失敗時の即時切替先として **Day 2 までに ONNX export smoke を通す**ことが必須。 本チケットの工数 2 日が遵守されない場合、 計画 §4.5 「Day 5 までに ONNX export + 7 ランタイム smoke 完了」のスケジュールが崩れる
- **R7 関連 (LOW-MEDIUM):** FLY-TTS は ConvNeXt depthwise Conv1d + LayerNorm channels_last のため、 iSTFTNet2-MB の 2D op 互換性懸念とは別軸で **モバイル EP の LayerNorm + GELU op coverage** が問題化する可能性。 Phase 4 で「ConvNeXt は 2D-CNN 不使用で mobile EP 互換性が高い」と評価済みだが、 LayerNorm が ONNX opset 17+ 必須でないことを export 時に確認する必要 (opset 15 互換用に手動 `LayerNormalization` 展開が必要なケースあり)
- **チケット固有 1:** `OnnxISTFT(n_fft=1024, hop_length=256)` は既存 MB-iSTFT (n_fft=16, hop_length=4) より遥かに大きく、 `_build_inverse_basis` の computational cost が増える。 forward は問題ないが ONNX export 時の constant folding でメモリ消費が増加する可能性
- **チケット固有 2:** `conv_post` 出力次元 1026 (= 513 × 2) の magnitude/phase 分離で、 magnitude に `exp(x.clamp(max=10))`、 phase に `sin(x)` を適用する論文式の正確な反映 (Hugging Face や公式 reference 実装が公開されていない場合は arXiv 数式から再構築)
- **チケット固有 3:** ConvNeXt の `LayerNorm(channels_last)` のため `x.transpose(1, 2)` を blockごとに往復する必要があり、 ONNX graph に Transpose op が 12 個出現 (6 block × 2)。 ORT 側で Transpose fusion が効くかは要確認 (効かない場合は AI-12 benchmark で発覚予定だが、 本チケットで先回り audit)

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 `models.py` を本チケットで編集していない)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止、 `mb_istft.py` / `stft_onnx.py` の既存定義を touch していない)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避、 新規 `fly_decoder.onnx` は別ファイルとして export)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (本チケットでは N/A、 AI-14 / AI-16 で反映)
- [ ] `fly_decoder.py` が `mb_istft.py` / `models.py` / `lightning.py` を一切 import していない (完全独立)
- [ ] `OnnxISTFT` の既存 instance を共有していない (新 instance を `__init__` 内で構築、 既存 MB-iSTFT 経路への副作用なし)
- [ ] params 数 0.63M ± 0.05M で計画 §4.5 値と一致
- [ ] ONNX op set に Conv2d / ConvTranspose 系 / STFT / DFT 不在
- [ ] `test_fly_decoder.py` 8 関数全 green、 既存 test を 1 行も touch していない
- [ ] `scripts/smoke_fly_decoder_onnx.py` の round trip atol=1e-4 達成

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「既存 `mb_istft.py` に decoder_type 分岐を増やさず、 独立ファイル `fly_decoder.py` で完全分離する」だが、 別案として **`Generator` 抽象基底クラスを `vits/decoders/base.py` に切り出し、 `mb_istft.py` / `fly_decoder.py` / 将来の `istftnet2_mb.py` を sibling として並べる**選択肢もあった。 抽象化先行はテスト共通化や registry pattern (G2P と同様) が効きやすく、 AI-13 の 7 ランタイム同期で「decoder 種別 → ONNX 経路マッピング」が表として表現できる。 ただし PR #222 が既に `MBiSTFTGenerator` を直接編集している以上、 抽象化リファクタは PR #222 と HIGH conflict を再生産するため、 現実解として「新ファイル独立 + AI-07 で `models.py` 1 行追加」を採用した。 PR #222 merge 後 (M6) に decoder abstraction として後追いリファクタする余地は残しておきたい。

別の代替として **`fly_decoder.py` 内で `OnnxISTFT` を新 instance 化せず、 `stft_onnx.py` に `OnnxISTFT.from_config(n_fft, hop_length)` factory を追加する**案もあった。 これは将来 iSTFTNet2 (hop=4) と FLY-TTS (hop=256) と MS-Wavehax (hop=16) の 3 variant が共存した際の inverse basis cache 共有に有利だが、 本チケットの 2 日工数では `stft_onnx.py` 編集 = 計画 §3 Conflict Map の LOW conflict 行を触るため、 PR #222 rebase コストを最小化する観点で却下。 cache 共有最適化は AI-12 benchmark で必要性が判明した時点で別チケット化する方が健全。

TDD 順序についても、 「Unit Test 先行」 ではなく **「ONNX export smoke を Day 1 朝一で `dummy FlyDecoder(num_blocks=1)` で先に通す」** 順序が真に reasonable な代替案だった。 op coverage の落とし穴 (LayerNorm opset / Transpose 12 個) は Unit Test では発覚しないため、 ONNX round trip を最初の「失敗指標」として Day 1 中盤までに通せていなければ設計やり直しの判断を即座に下せる。 採用案 (TDD Unit Test 先行 + Day 2 で ONNX) はリスクの早期発見が後ろ倒しになる弱点を残しているため、 後続 AI-12 / AI-13 で op coverage 問題が発生した場合は本省察に立ち戻る。

## 後続タスクへの連絡事項

AI-07 (FLY-TTS PoC 学習 50 epoch) に引き渡す具体的成果物:

- **decoder module:** `from piper_train.vits.fly_decoder import FlyDecoder` で import 可能、 default ハイパーパラメータ (hidden=256 / blocks=6 / k=7 / n_fft=1024 / hop=256) は論文値準拠で fix
- **params 数:** 0.63M ± 0.05M (実測値を AI-07 学習開始前に CHANGELOG-unreleased.md または PR body に記載依頼)
- **ONNX export 経路:** `scripts/smoke_fly_decoder_onnx.py` で round trip 動作確認済み、 AI-13 では同スクリプトを 7 ランタイム smoke の reference とする
- **暫定 ONNX 出力パス:** `out/fly_decoder.onnx` (smoke 用、 AI-07 学習後の本番 ckpt → ONNX 経路は AI-07 で `export_onnx.py` に decoder branch 切替を追加)
- **暫定 decoder_type 値:** `'fly_convnext6'` を予約 (AI-07 で `models.py` の Generator 選択 if 分岐に追加予定、 default 値は `'mb_istft_1d'` 不変)
- **学習レシピ提示:** `--c-sub-stft 0.0` (PQMF / sub-band loss 無効、 計画 §4.5)、 `--decoder-type fly_convnext6` (AI-07 新規)、 epoch 50、 batch 4、 base_lr 2e-5、 ema-decay 0.9995 (CLAUDE.md Template B 準拠)
- **6lang base ckpt warm start は不可:** FLY-TTS decoder は MB-iSTFT と layer 構造が完全に異なるため `--resume-from-multispeaker-checkpoint` 経由の重み移行は不能。 AI-07 では `--from-scratch` または `posterior encoder + flow のみ部分 warm start` で初期化することを連絡
- **PR #222 rebase 注意事項:** `models.py` の `Generator` 選択分岐に AI-07 が `decoder_type='fly_convnext6'` を追加する際、 PR #222 の `spk_proj` 統合点 (`models.py:754` 近傍) と並列に追加するため、 rebase 時に if-elif chain の順序確認が必要 (default `mb_istft_1d` → `istftnet2_mb_1d2d` → `fly_convnext6` の順)
- **ONNX op audit 結果:** Conv / LayerNormalization / Gelu / Transpose / Reshape / Split / Exp / Sin / Mul / Add / Clip 系のみ出現を確認済み、 AI-13 の 7 ランタイム smoke で同 op set を expected baseline として使用可能 (`docs/spec/audio-parity-contract.toml` の `[fly_convnext6]` section 起草資料、 AI-14 で追加)

## 関連ドキュメント

- 親マイルストーン: [../milestones/M3-fly-tts-parallel-harness.md](../milestones/M3-fly-tts-parallel-harness.md)
- 親計画 §6 (AI-06) / §4.5 (FLY-TTS 並走) / §8 #3 (即時着手可): [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- Decoder Upgrade deep-dive §2.5 (FLY-TTS Phase 3 詳細): [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 改善調査統合 §A-1 / §H Track 7: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- 既存 spec: [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) (`[fly_convnext6]` section 追加は AI-14)
- 関連既存実装: `src/python/piper_train/vits/stft_onnx.py` (`OnnxISTFT` を import)
- 論文: [FLY-TTS PDF (Guo et al., Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) / [ConvNeXt (Liu et al., CVPR 2022, arXiv 2201.03545)](https://arxiv.org/abs/2201.03545)
- 依存 PR (本チケットは独立、 参考のみ):
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — 衝突 NONE / NONE
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — 衝突 NONE

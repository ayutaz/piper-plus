# AI-08: MS-Wavehax vocoder 実装 + dual vocoder 統合 (wavehax.py 新規)

## メタ情報

- ID: AI-08
- 親マイルストーン: [M4](../milestones/M4-mswavehax-dual-vocoder.md)
- 工数見積: 2.5 日
- 依存チケット: AI-02 (CSS10 JA 1D MB-iSTFT baseline 50 epoch、 vocoder-only FT の acoustic backbone) または AI-05 (iSTFTNet2-MB 50 epoch ckpt、 backbone 採用後に切替)
- 後続チケット: AI-09 (`configure_optimizers` に `_collect_g_params` hook 追加)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-08 / §4.3 A-2 PoC 設計 / §3 Conflict Map](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

MS-Wavehax ([Yoneyama et al., Interspeech 2025, arXiv 2506.03554](https://arxiv.org/html/2506.03554)) を piper-plus に **streaming 専用の独立 vocoder** として実装し、 既存 `MBiSTFTGenerator` を温存したまま **dual vocoder** 構成 (`self.dec` / `self.dec_wavehax` sibling) を `VITS` model に組み込む。 親計画 §4.3 が定義する「**spectral envelope + harmonic-aware shift + complex residual + `OnnxISTFT(n_fft=64, hop=16)`、 0.332M params**」を `src/python/piper_train/vits/wavehax.py` (新規) として実装し、 `models.py:754` 直後で `enable_wavehax` フラグ下で sibling として attach する。 これにより companion deep-dive §3.4 で定義した「acoustic model 部分 (TextEncoder + DP + Flow) は 100% 流用、 通常モード MB-iSTFT は 100% 温存、 streaming モードのみ MS-Wavehax 経路を起動する」 dual vocoder アーキを確立する。

上流の AI-02 から CSS10 JA 1D MB-iSTFT baseline ckpt (`/data/piper/output-css10-ja-poc-1d-baseline/last.ckpt`) を **acoustic model freeze 対象**として受け取り、 後続 AI-09 に `_collect_g_params` の対象パラメータ集合 (`self.dec_wavehax.parameters()` のみを optimizer に渡す制御点) を引き渡す。 AI-09 が optimizer hook を整え、 AI-10 で vocoder-only FT 30 epoch を回す。 dual vocoder 統合の **EMA shadow_params に `dec_wavehax` を追加しても既存 `infer_forward(... model_g.dec(...))` が不変**であることが本チケットの最重要不変条件で、 計画 §3 Conflict Map で `models.py` を vs PR #222 HIGH と評価している最大要因 (PR #222 が `spk_proj` を `dec` に統合しているため sibling 設計で隔離する) に対応する。

ゴールは (a) `wavehax.py` の forward が CPU で 0.332M params ± 0.02M / 出力 `[B, 1, T]` 不変、 (b) `enable_wavehax=True` 時に `VITS.__init__` で sibling vocoder が attach され、 (c) `infer_forward` default 経路は `self.dec` 不変、 (d) ONNX export は **既存 `model_g.dec` と独立した companion ONNX 経由** (本チケットは export skeleton のみ、 本格 export は AI-10 の出力後) という 4 点を満たす状態。

## 実装内容の詳細

### 編集 / 新規ファイル

| 対象 | 種別 | 概略 LoC | 主要関数 / 編集行 |
|------|------|---------|---------------------|
| `src/python/piper_train/vits/wavehax.py` | **新規** | ~280 LoC | `class WavehaxVocoder(nn.Module)`、 `class SpectralEnvelopeBlock`、 `class HarmonicAwareShift`、 `class ComplexResidualBlock`、 `def forward(self, z, g=None) -> Tensor[B,1,T]` |
| `src/python/piper_train/vits/models.py` | 編集 | +~40 / -0 LoC | `class SynthesizerTrn.__init__` (≈L754 直後、 既存 `self.dec = ...` の直後で `if enable_wavehax: self.dec_wavehax = WavehaxVocoder(...)`)、 `def __init__` の引数に `enable_wavehax: bool = False` / `wavehax_hps: Optional[dict] = None` を追加 |
| `src/python/piper_train/vits/stft_onnx.py` | 編集 (最小) | +~5 LoC | `OnnxISTFT(n_fft=64, hop=16)` 用 instance を `wavehax.py` 側でローカルに呼べるよう、 module-level factory `make_wavehax_istft()` を追加 (既存 `OnnxISTFT` クラス本体は不変) |
| `src/python/piper_train/__main__.py` | 編集 (最小) | +~10 LoC | CLI フラグ `--enable-wavehax` (store_true、 default False)、 hparams へ `enable_wavehax` 伝搬。 vocoder-only FT 用の `--freeze-acoustic` と `--wavehax-lr` は AI-09 に委譲 (本チケットでは追加しない) |
| `src/python/tests/test_wavehax_vocoder.py` | **新規** | ~180 LoC | unit test 群 (詳細は「テスト項目」 参照) |

### 後方互換 / 衝突回避制約 (G-1.x gate)

- **G-1.9 (後方互換 gate):** `enable_wavehax` の default は **False**。 既存 6lang ckpt / CSS10 JA 1D baseline ckpt を `load_state_dict(strict=True)` で resume しても unused key で fail させないため、 `dec_wavehax` の attach は `if enable_wavehax:` ブロック配下のみ。 `strict=False` を要求してはならない (silent regression を招くため)。
- **G-1.2 (audio-parity baseline 不変):** 本チケットは `audio-parity-contract.toml` を編集しない。 `[mswavehax]` section の追加は AI-14 で行う (計画 §6 Milestone 5 AI-14)。
- **PR #222 衝突回避 (Conflict Map `models.py` HIGH 行):** PR #222 が `MBiSTFTGenerator.forward` を Multi-scale FiLM 化し `spk_proj` を `dec` に注入する設計のため、 本チケットの `dec_wavehax` は **`self.dec` に絶対 inject せず sibling 専用**で実装する。 計画 §3 表の 4 行目脚注「`models.py` ... `dec_wavehax` sibling 追加、 `decoder_type` 受領 / vs PR #222 HIGH (spk_proj 統合点) / A-1/A-2 先行で隔離」 に明示的に従う。 sibling 隔離により PR #222 rebase 後は `_apply_film` rank-aware 化が `self.dec` のみで完結し、 `self.dec_wavehax` は touch されない。
- **PR #222 衝突回避 (Conflict Map `lightning.py` MEDIUM 行):** `configure_optimizers` は本チケットでは触らず AI-09 が hook 化する。 これにより `_collect_g_params` の差分が 1 PR で完結し PR #222 の WavLM-D + DINO 拡張 (opt_d/opt_g 二重化) と非衝突となる。
- **PR #537 衝突回避:** 本チケットの新規コードは `torch.fft` を直接呼ばず、 既存 `OnnxISTFT` の Conv 実装を再利用する。 これにより PR #537 の bf16-mixed default / NumPy 2.x 移行で torch.fft op の数値ドリフトが起きても `wavehax.py` は影響を受けない (計画 §7 R5 mitigation)。

### `wavehax.py` 疑似コード スケッチ

```python
# src/python/piper_train/vits/wavehax.py
from torch import nn
import torch
from .stft_onnx import make_wavehax_istft  # n_fft=64, hop=16 factory

class SpectralEnvelopeBlock(nn.Module):
    """Mel-derived envelope の amplitude path、 1D Conv stack。"""
    def __init__(self, in_ch=192, hidden=128): ...
    def forward(self, z):  # -> envelope [B, n_fft/2+1, T_chunk]
        ...

class HarmonicAwareShift(nn.Module):
    """harmonic series の phase shift を decoder 入力に注入。"""
    def __init__(self, n_harmonics=8, hop=16): ...
    def forward(self, f0_proxy, T):  # -> phase tensor [B, K, T]
        ...

class ComplexResidualBlock(nn.Module):
    """real + imag 同時 residual。 ConvTranspose 不使用、 PixelShuffle1d 経由で upsample。"""
    def __init__(self, ch, dilations=(1, 2, 4)): ...
    def forward(self, real, imag):  # -> (real', imag')
        ...

class WavehaxVocoder(nn.Module):
    def __init__(self, z_channels=192, n_fft=64, hop=16, n_blocks=4):
        super().__init__()
        self.envelope = SpectralEnvelopeBlock(in_ch=z_channels)
        self.harmonic = HarmonicAwareShift(hop=hop)
        self.residuals = nn.ModuleList(
            [ComplexResidualBlock(ch=(n_fft // 2 + 1)) for _ in range(n_blocks)]
        )
        self.istft = make_wavehax_istft(n_fft=n_fft, hop=hop)  # Conv 実装

    def forward(self, z, g=None):
        # z: [B, z_channels, T_chunk]
        amp = self.envelope(z)            # [B, F, T]
        phase = self.harmonic(z, T=z.size(-1))
        real, imag = amp * torch.cos(phase), amp * torch.sin(phase)
        for blk in self.residuals:
            real, imag = blk(real, imag)
        x = self.istft(real, imag)        # [B, 1, T_out]、 Conv 実装で ONNX safe
        return x
```

### `models.py` への sibling attach (≈L754)

```python
# src/python/piper_train/vits/models.py 抜粋 (SynthesizerTrn.__init__)
self.dec = MBiSTFTGenerator(...)  # 既存 (touch しない)
if enable_wavehax:
    from .wavehax import WavehaxVocoder
    self.dec_wavehax = WavehaxVocoder(
        z_channels=hidden_channels,
        n_fft=64,
        hop=16,
        n_blocks=4,
    )
# infer_forward / forward は本チケットで touch しない (AI-11 が voice.py 側で session 切替)
```

### CLI 追加 (`__main__.py`)

| フラグ | default | 説明 |
|--------|---------|------|
| `--enable-wavehax` | False | sibling `dec_wavehax` を attach。 学習時の vocoder-only FT 起動条件 |

`--freeze-acoustic` / `--wavehax-lr` は AI-09 が `configure_optimizers` hook と同時に追加 (本チケット範囲外)。

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|------|-----------|---------|
| ML Researcher (Vocoder) | 1 | PyTorch / signal processing (STFT, PQMF, harmonic models) / arXiv 2506.03554 読解 | `wavehax.py` の SpectralEnvelope / HarmonicAwareShift / ComplexResidual ブロック設計、 0.332M params 達成、 論文 sub-80ms チャンクで HiFi-GAN/Vocos 凌駕の再現性方針 |
| Python Lead (Integration) | 1 | piper-plus VITS 内部構造 (`models.py` SynthesizerTrn) / EMA shadow_params / OnnxISTFT factory パターン | `models.py:754` 直後の sibling attach、 `enable_wavehax` flag の `__init__` 引数受領、 PR #222 spk_proj 注入点との隔離保証 |
| Test Engineer | 1 | pytest / `torch.no_grad()` shape assertion / ONNX op audit (opset 15+) | `test_wavehax_vocoder.py` の forward shape / params 数 / sibling 隔離 / EMA shadow registration / 既存 `test_mb_istft_generator.py` non-regression を担保 |

3 名構成。 ONNX export 本番 (companion ONNX の生成) と 7 ランタイム同期は AI-13 (M5) に集約するため本チケットでは export Engineer / Runtime Engineer は不要 (skeleton export smoke のみ Test Engineer が担当)。

## 提供範囲 (Scope)

### 含むもの

- `src/python/piper_train/vits/wavehax.py` 新規 (~280 LoC、 0.332M params ± 0.02M)
- `src/python/piper_train/vits/models.py` の sibling attach (`enable_wavehax` flag、 default False)
- `src/python/piper_train/vits/stft_onnx.py` の `make_wavehax_istft(n_fft=64, hop=16)` factory 追加 (既存 `OnnxISTFT` 本体不変)
- `src/python/piper_train/__main__.py` の CLI `--enable-wavehax` フラグ + hparams 伝搬
- `src/python/tests/test_wavehax_vocoder.py` 新規 (unit + skeleton ONNX export smoke)
- 上記すべてが既存 6lang base ckpt / CSS10 JA 1D baseline ckpt の `strict=True` resume を維持

### 含まないもの (Out of Scope)

- `configure_optimizers` への `_collect_g_params` hook 追加 → **AI-09** に委譲 (CLI `--freeze-acoustic` / `--wavehax-lr` も AI-09 で追加)
- vocoder-only FT 30 epoch の学習実行 → **AI-10**
- `voice.py` の `wavehax_model_path` + streaming 閾値切替 → **AI-11**
- companion ONNX (`tsukuyomi.wavehax.onnx`) の export 本番 → AI-10 の出力 ckpt を元に AI-11 で確立
- 7 ランタイム (Rust / Go / C# / WASM / C++ / C-API) への `wavehax_model_path` 引数追加 → **AI-13**
- `audio-parity-contract.toml` への `[mswavehax]` section 追加 → **AI-14**
- regression guard CI gate (default decoder_type assert / ONNX I/O 不変 audit) → **AI-15**
- PR #222 rebase 後の FiLM rank-aware 化 / ONNX I/O 同期 → **AI-17**

## テスト項目

### Unit Tests (`src/python/tests/test_wavehax_vocoder.py`)

- `test_forward_output_shape`
  - input: `z = torch.randn(2, 192, 100)` (B=2, z_ch=192, T_chunk=100)
  - assert: `out.shape == (2, 1, 1600)` (hop=16 × T_chunk = 1600 サンプル)
  - assert: `out.dtype == torch.float32`
- `test_param_count_within_budget`
  - assert: `0.31e6 <= sum(p.numel() for p in WavehaxVocoder().parameters()) <= 0.35e6` (0.332M ± 0.02M)
- `test_no_convtranspose_used`
  - assert: `not any(isinstance(m, (nn.ConvTranspose1d, nn.ConvTranspose2d)) for m in WavehaxVocoder().modules())` (PixelShuffle 採用 / NNAPI fallback 防止、 companion §3.5 / 親計画 §2.5 Risk 1 mitigation)
- `test_sibling_isolation_when_enabled`
  - SynthesizerTrn(enable_wavehax=True) で `model.dec` と `model.dec_wavehax` が **異なる nn.Module instance**
  - assert: `id(model.dec) != id(model.dec_wavehax)`
  - assert: `model.dec.__class__.__name__ == "MBiSTFTGenerator"`
- `test_default_path_unchanged`
  - SynthesizerTrn(enable_wavehax=False) で `hasattr(model, "dec_wavehax") is False`
  - assert: 既存 6lang ckpt を `model.load_state_dict(ckpt, strict=True)` で resume できる
- `test_mb_istft_generator_untouched`
  - `test_mb_istft_generator.py` の既存 fixture を一切 touch していないことを `git diff --name-only` の path 集合で assert (CI gate 側で扱うため、 本テストは marker のみ)
- `test_onnx_export_skeleton`
  - `torch.onnx.export(WavehaxVocoder(), (torch.randn(1,192,100),), "out.onnx", opset_version=15)` が ONNX FileFormatProto を生成
  - assert: 生成 ONNX に `ConvTranspose` op が含まれない (op audit、 親計画 §4.6 ONNX op coverage)

### E2E Tests (本チケットでは skeleton)

- `test_smoke_synth_trn_attach`
  - SynthesizerTrn(enable_wavehax=True) を CSS10 JA hparams で構築し 1 mini-batch forward が CPU で OOM なく完走
  - assert: `model.dec(...)` 出力と `model.dec_wavehax(...)` 出力が**同一 batch でそれぞれ完走** (互いに干渉しない)
- フル E2E (UTMOS proxy MOS / pairwise SNR / Xeon E5-2650 v4 p50) は AI-10 / AI-13 に委譲

### 受入基準 (Acceptance Criteria)

- params: **0.332M ± 0.02M** (計画 §4.6 footprint / companion §3.1 表)
- 出力 shape: `[B, 1, T_out]` で `T_out = T_chunk × hop` (hop=16) かつ `dtype == float32`
- sibling 隔離: `enable_wavehax=False` で既存 6lang / CSS10 JA 1D baseline ckpt が `strict=True` resume 可能 (G-1.9 後方互換 gate)
- ONNX op set: 生成 ONNX に `ConvTranspose1d` / `ConvTranspose2d` が含まれない (mobile EP fallback 最小化、 companion §2.5 Risk 1 設計制約)
- `test_mb_istft_generator.py` 不変 (calling g-status の path 集合で assert / G-1.2 baseline 編集禁止)
- pytest 完走: `uv run --no-sync pytest src/python/tests/test_wavehax_vocoder.py -v --no-cov` が全 green

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

- **計画 §7 R4 (companion ONNX 配布の ABI 誤認):** 本チケットは Python 側 sibling 追加のみだが、 後続 AI-11 / AI-13 で voice.py / 7 ランタイムに `wavehax_model_path` 引数が増える。 本チケットでは `enable_wavehax=False` default を **絶対に変えない**ことで Python 側 ABI 互換を維持し、 R4 mitigation の起点とする。
- **計画 §7 R5 (PR #537 torch.fft 互換性):** `wavehax.py` で `torch.fft.*` を直接呼ばないことで bf16-mixed default / NumPy 2.x 移行の影響を受けないアーキにする。 `OnnxISTFT` Conv 実装パターンの再利用が前提。
- **計画 §7 R6 (audio-parity baseline 誤改変):** 本チケットは `audio-parity-contract.toml` を絶対に編集しない。 編集は AI-14 で `[mswavehax]` section の **追加のみ**、 `[mb_istft_1d]` は AI-14 でも touch 禁止。
- **チケット固有: spectral envelope の値域爆発:** Mel-derived envelope を `amp * cos(phase)` で展開する段で、 学習初期に `amp` が極端値を取ると iSTFT 出力が clip する。 init を **`nn.init.xavier_uniform_(gain=0.5)`** で慎重に絞る。
- **チケット固有: PixelShuffle1d の shape 縛り:** `n_fft=64, hop=16` の組合せで T_chunk × hop が batch によって割り切れない端数が出ると ONNX export で dynamic axes が不安定化。 forward で `assert z.size(-1) % 1 == 0` 程度の最小 guard を入れ、 端数処理は AI-11 (`voice.py` の streaming chunk 分割) に委譲する旨を docstring に明記。
- **チケット固有: EMA shadow_params への dec_wavehax 自動追加:** `lightning.py` の EMA 登録ループが `model_g.parameters()` を total で見るため、 `dec_wavehax` を attach した瞬間に shadow_params が膨らむ。 AI-09 が hook 化する前に AI-10 学習を回すと意図せず EMA 適用される。 docstring に「**AI-09 完了前は `enable_wavehax=True` で学習しない**」 と明記し、 本チケットのテストは unit / skeleton のみで学習しない。

### レビュー項目 (チェックリスト)

- [ ] default `enable_wavehax=False` 不変 (G-1.9 後方互換、 既存 6lang / CSS10 JA 1D baseline ckpt が `strict=True` resume できる)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止、 `audio-parity-contract.toml` を本チケットで touch しない)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避 / 計画 §3 Conflict Map 4 行目)、 companion ONNX 経路は **独立ファイル** で本チケットでは export しない
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (本チケットは contract を touch しないため AI-16 で吸収)
- [ ] `self.dec_wavehax` を `self.dec` に inject していない (PR #222 spk_proj 統合点との sibling 隔離)
- [ ] `ConvTranspose1d` / `ConvTranspose2d` を `wavehax.py` 全体で使っていない (NNAPI / CoreML NN CPU fallback 最小化、 companion §2.5 Risk 1)
- [ ] `wavehax.py` 内で `torch.fft.*` を直接呼んでいない (PR #537 R5 mitigation)
- [ ] `configure_optimizers` を本チケットで touch していない (AI-09 に委譲、 計画 §6 AI-09 blocked by AI-08 を尊重)
- [ ] `voice.py` / 7 ランタイムを本チケットで touch していない (AI-11 / AI-13 に委譲)
- [ ] `test_mb_istft_generator.py` を 1 行も touch していない (G-1.2)
- [ ] pytest を `uv run --no-sync pytest --no-cov` で実行 (CLAUDE.md ローカルテスト規約、 macOS でも fail しない)

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「**sibling 追加 + default off**」 の最小侵襲アプローチで、 既存 `MBiSTFTGenerator` を 1 行も触らないことで G-1.9 後方互換と PR #222 / #537 衝突回避を同時に成立させた。 代替案として「**`decoder_type` enum で `dec` を切替**」 する方式 (A-1 iSTFTNet2-MB と同じ `_forward_1d` / `_forward_1d2d` 分離パターン) を採れば API 表面が 1 個に集約され dual vocoder の保守コストが消えるが、 streaming 時にのみ別 vocoder を使う A-2 の本質 (companion §3.4 dual vocoder ダイアグラム) と相性が悪く、 「通常モードは MB-iSTFT で品質維持 / streaming のみ MS-Wavehax で低レイテンシ」 という streaming-specific advantage (companion §3.2、 sub-80ms チャンクのみ Vocos 凌駕) が表現できなくなるため捨てた。

TDD でなく **integration-test 先行** で組み立てるとしたら、 まず AI-11 (`voice.py` の streaming 閾値切替) と AI-10 (vocoder-only FT 30 epoch) を skeleton 含めて先に書き、 「voice.py から `dec_wavehax` を呼ぶ pseudocode」 を満たすように `wavehax.py` を逆算実装する流れになる。 これは A-2 の本質が **streaming pipeline** 側にあることを前提とする設計で、 本ティケットの位置付け (vocoder 単体実装 + sibling attach) と整合しないが、 もし「A-2 が piper-plus の主力 streaming パスになる」 という戦略判断が先にあれば integration-test 先行が正解になり得る。 採用案はあくまで「PoC 段階で MS-Wavehax の sub-80ms 優位性 (companion §3.2) を**実機で確認する**」 までを目的とし、 採用判断は AI-18 (採否判定レポート) に委譲する保守的線で組んでいる。

別案として **adaptive single vocoder** (chunk 長で 1 つの vocoder が内部で挙動を切替える) も考えたが、 これは A-2 論文 (MS-Wavehax) の「**大きいチャンクでは Vocos が勝つ**」 (companion §3.2 caveat) という所見と本質的に矛盾する。 1 つの vocoder で全 chunk 長を最適化することは設計トレードオフとして不可能で、 dual vocoder の保守負荷 (companion §3.6 リスク 2) を受け入れる方が技術的に正直。 もし「完全 from-scratch」 で MS-Wavehax を実装するなら、 既存 `OnnxISTFT` の Conv 実装を流用せず `torch.fft.*` の直接呼出で書いて学習時 / 評価時の数値ドリフトを最小化する設計が理論的には clean だが、 PR #537 の bf16-mixed default / NumPy 2.x 移行 (計画 §7 R5) で torch.fft op の数値挙動が変わるリスクを背負うため、 PoC 段階では既存 Conv 実装の流用 (companion §3.3「ONNX 化リスクの低さ」) が現実解。

## 後続タスクへの連絡事項

AI-09 (configure_optimizers hook) への引き渡し:

- **新規モジュールパス:** `src/python/piper_train/vits/wavehax.py:WavehaxVocoder`
- **VITS 内 attach 点:** `SynthesizerTrn.__init__` で `enable_wavehax=True` 時に `self.dec_wavehax` (≈ `models.py:754` 直後)
- **対象パラメータ集合 (AI-09 が `_collect_g_params` で扱うべき):** `model.dec_wavehax.parameters()` のみ optimizer に渡し、 `model.dec.parameters()` / `model.enc_p.parameters()` / `model.flow.parameters()` / `model.dp.parameters()` は **freeze 対象** (`requires_grad=False`)
- **CLI フラグ:** 本チケットで `--enable-wavehax` (store_true、 default False) を追加済み。 AI-09 で `--freeze-acoustic` / `--wavehax-lr 2e-4` を追加すること (計画 §6 AI-10 で記載済の LR)
- **EMA 注意点:** `lightning.py` の EMA shadow_params 登録ループが `model_g.parameters()` を total 走査するため、 AI-09 で `_collect_g_params` hook を入れる際に EMA 側も `wavehax_params_only` フィルタを通すよう同時に修正すること。 これを怠ると vocoder-only FT 中に acoustic model 側の EMA shadow が duplicate 更新される
- **暫定設定 default 値:**
  - `enable_wavehax=False` (リリース時に切替判断、 AI-18 採否判定後)
  - `wavehax_hps.n_fft=64`
  - `wavehax_hps.hop=16`
  - `wavehax_hps.n_blocks=4`
- **CKPT パス (AI-10 で生成予定の暫定パス):** `/data/piper/output-css10-ja-poc-wavehax-ft/last.ckpt` (acoustic model は AI-02 baseline `last.ckpt` から freeze、 wavehax のみ FT)
- **ONNX パス (AI-11 で export 予定の暫定パス):** `out/css10-ja-poc.wavehax.onnx` (companion ONNX、 既存 `out/css10-ja-poc.onnx` とは独立ファイル)
- **PR #222 rebase 時の注意:** `models.py` の `SynthesizerTrn.__init__` 引数末尾に `enable_wavehax: bool = False` / `wavehax_hps: Optional[dict] = None` を追加したため、 PR #222 が同 `__init__` で `speaker_embedding_dim=192` 等を追加した場合は **kwargs 順序衝突なし** (本チケット追加分は default 引数で末尾配置)。 ただし `self.dec = ...` 行直後に sibling attach を入れたため、 PR #222 が `self.spk_proj = ...` を同位置に追加すると 3-way merge で行衝突する。 rebase 時は本チケットの sibling attach ブロックを `self.spk_proj` の **下** に移動するだけで解決
- **AI-09 着手前の禁則:** `enable_wavehax=True` で学習を回さないこと (EMA shadow が意図せず適用される)。 学習着手は AI-09 完了後 AI-10 で行う

## 関連ドキュメント

- 親マイルストーン: [../milestones/M4-mswavehax-dual-vocoder.md](../milestones/M4-mswavehax-dual-vocoder.md)
- 親計画 §6 AI-08: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- Decoder Upgrade deep-dive §3 A-2 MS-Wavehax: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 改善調査統合 §A-2: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- 既存 spec (本チケットでは編集しない):
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — `[mswavehax]` 追加は AI-14
  - [`docs/spec/text-splitter-contract.toml`](../../spec/text-splitter-contract.toml) — 編集禁止 (decoder-agnostic 維持、 計画 §3 Conflict Map)
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — companion ONNX の QNN HTP bucket 仕様追記は Phase 4 提言、 本チケット範囲外
- 既存実装の参照点:
  - `src/python/piper_train/vits/mb_istft.py` — `MBiSTFTGenerator` (本チケットで touch しない、 sibling 元)
  - `src/python/piper_train/vits/stft_onnx.py` — `OnnxISTFT` (Conv 実装の流用元)
  - `src/python/piper_train/vits/models.py` — `SynthesizerTrn` (sibling attach 点 ≈L754)
  - `src/python/piper_train/vits/lightning.py` — EMA shadow_params 登録 (AI-09 で hook 化)
- 論文: [arXiv 2506.03554](https://arxiv.org/html/2506.03554) Yoneyama et al. "MS-Wavehax" (Interspeech 2025)
- 影響 PR (本チケットは merge 前提なし):
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222)
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537)

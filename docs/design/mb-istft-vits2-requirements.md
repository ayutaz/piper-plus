# MB-iSTFT-VITS2: Decoder 置換による推論高速化 — 要求定義

> **Issue**: [#268](https://github.com/ayutaz/piper-plus/issues/268)
> **ブランチ**: `feat/mb-istft-vits2`
> **作成日**: 2026-04-05
> **ステータス**: Draft

---

## 1. 目的

VITS の HiFi-GAN Decoder の最終アップサンプリング段を MB-iSTFT (Multi-Band inverse STFT) + PQMF に置換し、ONNX 推論速度を ~1.2 倍高速化する。品質は現行モデルと同等以上を維持する。

### 1.1 スコープ

- Python 学習パイプラインへの MB-iSTFT Generator 追加
- ONNX エクスポート対応 (DFT 行列方式による iSTFT の ONNX 互換実装)
- 6 言語事前学習 + つくよみちゃんファインチューニング
- 品質検証 (定量 + 定性)

### 1.2 スコープ外

- C#/Rust/WASM 推論エンジンの変更 (ONNX 出力形状 `[B, 1, T]` を維持するため不要)
- MS-iSTFT バリアント (学習可能合成フィルタ。MOS は MB より高いが、ONNX 互換性の検証が追加で必要)
- モバイル向け MS-Wavehax 統合 (F0 推定器が必要、別 issue で対応)
- VITS2 固有機能 (Transformer Flow, Duration Discriminator 等。`feat/vits2-upgrade` ブランチで別途対応中)

---

## 2. 背景

### 2.1 現行アーキテクチャの計算量分布

| コンポーネント | パラメータ比 | MACs 比 |
|-------------|-----------|---------|
| Decoder (HiFi-GAN) | 13% | **75.8%** |
| Flow | 64% | 17.8% |
| TextEncoder | 20% | 6.2% |
| DP + emb | 3% | 0.4% |

Decoder が全推論の 75.8% を占め、特に最終アップサンプリング段 (Stage 2) が最高サンプルレートで動作するため計算コストが最大。

### 2.2 論文エビデンス

**論文**: Kawamura et al., "Lightweight and High-Fidelity End-to-End Text-to-Speech with Multi-Band Generation and Inverse Short-Time Fourier Transform", ICASSP 2023 ([arXiv:2210.15975](https://arxiv.org/abs/2210.15975))

| モデル | パラメータ | MOS | RTF (CPU) |
|--------|----------|-----|-----------|
| VITS (ベースライン) | 28.11M | 4.75 +/- 0.06 | 0.27 |
| iSTFT-VITS | 27.44M | 4.65 +/- 0.06 | 0.15 |
| **MB-iSTFT-VITS** | **27.49M** | **4.67 +/- 0.06** | **0.078** |
| MS-iSTFT-VITS | 27.49M | 4.73 +/- 0.06 | 0.066 |

- 評価条件: LJ Speech, 英語単一話者, N=18
- MB-iSTFT vs VITS: MOS 差 0.08 (統計的有意差なし)
- RTF 3.5 倍高速 (Decoder 単体)

### 2.3 未検証事項 (本プロジェクト固有)

論文は LJ Speech (英語単一話者) でのみ評価されている。以下は本プロジェクトで検証が必要:

| 項目 | リスク | 検証方法 |
|------|--------|---------|
| 多言語 (6 言語) | 中 | Per-language MCD/F0-RMSE |
| 多話者 (571 話者) | **高** | Speaker similarity 評価 |
| gin_channels=512 (論文は未使用) | 中 | A/B 比較 |
| prosody_features 統合 | 低 | Duration 比較 |
| FP16 ONNX 変換 | 低 | 数値精度検証 |

---

## 3. 技術要件

### 3.1 MB-iSTFT Generator

#### 3.1.1 アーキテクチャ

現行の HiFi-GAN Generator の最終アップサンプリング段を iSTFT + PQMF に置換する。

```
現行 (medium):
  z → conv_pre → [ups[0](8x) → ResBlocks] → [ups[1](8x) → ResBlocks] → [ups[2](4x) → ResBlocks] → conv_post(→1ch) → tanh → waveform
  合計: 8 x 8 x 4 = 256x アップサンプル

MB-iSTFT (medium):
  z → conv_pre → [ups[0](4x) → ResBlocks] → [ups[1](4x) → ResBlocks] → subband_conv_post(→72ch) → reshape → exp/sin → iSTFT(4x) → PQMF合成(4x) → waveform
  合計: 4 x 4 x 4(iSTFT) x 4(PQMF) = 256x アップサンプル
```

**重要な変更点**:

| 項目 | 現行 HiFi-GAN | MB-iSTFT |
|------|-------------|----------|
| upsample_rates | (8, 8, 4) | **(4, 4)** |
| upsample_kernel_sizes | (16, 16, 8) | **(16, 16)** |
| upsample_initial_channel | 256 | 256 (変更なし) |
| ResBlock 段数 | 3 段 | **2 段** |
| 最終出力 Conv | Conv1d(32, 1, 7) | **Conv1d(64, 72, 7)** |
| 出力チャネル | 1 (waveform) | **72** = 4 subbands x (n_fft/2+1 + n_fft/2+1) = 4 x 18 |
| 後段処理 | tanh | **exp(mag) + sin(phase)*pi → iSTFT → PQMF** |
| 学習パラメータ | ~1.7M | **~1.66M** (-37K) |

**チャネル次元の推移** (medium, upsample_initial_channel=256):

```
現行 HiFi-GAN:
  conv_pre: 192 → 256 → ups[0](8x): 256→128 → ups[1](8x): 128→64 → ups[2](4x): 64→32 → conv_post: 32→1

MB-iSTFT:
  conv_pre: 192 → 256 → ups[0](4x): 256→128 → ups[1](4x): 128→64 → subband_conv_post: 64→72
```

> **注意**: 原著 MB-iSTFT-VITS は `upsample_initial_channel=512` のため最終段 128ch だが、piper-plus は 256 始まりのため **64ch**。subband_conv_post の入力チャネルは `upsample_initial_channel // (2 ** len(upsample_rates))` で計算される。

#### 3.1.2 Speaker Conditioning (最重要)

**既知の問題**: 参考実装 ([MasayaKawamura/MB-iSTFT-VITS](https://github.com/MasayaKawamura/MB-iSTFT-VITS), [FENRlR/MB-iSTFT-VITS2](https://github.com/FENRlR/MB-iSTFT-VITS2)) の全 Generator バリアントは `gin_channels` を受け取るが `self.cond` 層を作成せず、`forward()` で speaker embedding `g` を完全に無視する。これはマルチスピーカーモデルでの品質低下の根本原因 (FENRlR Issue #13)。

**要件**: 現行 HiFi-GAN Generator と同様に speaker conditioning を実装する。

```python
# 現行 Generator の speaker conditioning (models.py:308-387)
class Generator:
    def __init__(self, ..., gin_channels=0):
        if gin_channels != 0:
            self.cond = nn.Conv1d(gin_channels, upsample_initial_channel, 1)

    def forward(self, x, g=None):
        x = self.conv_pre(x)
        if g is not None:
            x = x + self.cond(g)  # ← conv_pre 直後に加算
        # ... アップサンプリング ...
```

MB-iSTFT Generator でも同一のパターンを適用すること。`self.cond = nn.Conv1d(gin_channels, upsample_initial_channel, 1)` を `__init__` で作成し、`forward()` の `conv_pre` 直後で `x = x + self.cond(g)` を適用する。

#### 3.1.3 forward() の戻り値設計

学習時と推論時で必要な出力が異なるため、モード切替を実装する。

**学習時**: sub-band STFT 損失にサブバンド信号が必要 + フルバンド損失 (mel, MPD/MSD) にフルバンド信号が必要。

```python
class MBiSTFTGenerator(nn.Module):
    def forward(self, x, g=None):
        # ... conv_pre + cond + upsampling + ResBlocks ...
        x = self.subband_conv_post(x)           # [B, 72, T_frames]
        x = x.reshape(B, 4, 18, T_frames)       # [B, subbands, n_fft+2, T_frames]
        mag = torch.exp(x[:, :, :9, :])          # magnitude
        phase = torch.sin(x[:, :, 9:, :]) * pi   # phase [-pi, pi]
        subbands = self.istft(mag, phase)         # [B, 4, T_sub] — サブバンド信号
        fullband = self.pqmf.synthesis(subbands)  # [B, 1, T] — フルバンド信号

        if self.onnx_export_mode:
            return fullband                       # ONNX推論: フルバンドのみ
        return fullband, subbands                 # 学習: 両方返す
```

**SynthesizerTrn.forward() への影響**:

```python
# models.py — SynthesizerTrn.forward()
if self.mb_istft:
    o, o_mb = self.dec(z_slice, g=g)  # (fullband, subbands)
else:
    o = self.dec(z_slice, g=g)        # fullband のみ
    o_mb = None
```

戻り値に `o_mb` を追加し、`lightning.py` の `training_step_g` に渡す。`SynthesizerTrn.forward()` の戻り値タプルに追加。

#### 3.1.4 iSTFT パラメータ

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| n_fft | 16 | 論文標準値。サブバンド (5512.5 Hz) 上で動作し 9 ビンで十分 |
| hop_size | 4 | 4x アップサンプル (= subbands 数と一致) |
| win_length | 16 (= n_fft) | |
| 窓関数 | Hann | |

**Magnitude/Phase 予測**:
- Magnitude: `exp(x[:, :, :n_fft//2+1, :])` — 正の値を保証
- Phase: `sin(x[:, :, n_fft//2+1:, :]) * pi` — [-pi, pi] に制約

#### 3.1.4 PQMF パラメータ

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| subbands | 4 | 論文標準値 |
| taps | 62 | プロトタイプフィルタ長 63 (= taps + 1) |
| 窓関数 | Kaiser (beta=9.0) | ~90 dB ストップバンド減衰 |
| cutoff_ratio | 0.15 | omega_c = pi * 0.15 |
| 再構成誤差 | < -90 dB | テストで検証 |

**実装上の注意**:
1. 全テンソル (`analysis_filter`, `synthesis_filter`, `updown_filter`) を `register_buffer()` で登録する (DDP 互換性のため)
2. 原著実装の `.cuda(device)` ハードコードを除去し、デバイス非依存にする
3. アップサンプル時の振幅補正: `* subbands` を適用 (PQMF 理論上 M 倍の補正が必要)
4. パディング: `ConstantPad1d(taps // 2, 0.0)` を analysis/synthesis 両方に適用
5. プロトタイプフィルタ設計に `numpy.kaiser()` を使用する (`scipy.signal.kaiser` は不要)

**PQMF 出力長のアライメント**:

| 操作 | 入力形状 | 出力形状 | 備考 |
|------|---------|---------|------|
| Analysis: pad | (B, 1, T) | (B, 1, T+62) | ConstantPad1d(31, 0.0) |
| Analysis: filter | (B, 1, T+62) | (B, 4, T) | Conv1d(filter=(4,1,63)) |
| Analysis: downsample | (B, 4, T) | (B, 4, T//4) | Conv1d(updown, stride=4) |
| Synthesis: upsample | (B, 4, T//4) | (B, 4, T) | ConvTranspose1d(updown*4, stride=4) |
| Synthesis: pad | (B, 4, T) | (B, 4, T+62) | ConstantPad1d(31, 0.0) |
| Synthesis: filter | (B, 4, T+62) | (B, 1, T) | Conv1d(filter=(1,4,63)) |

T が subbands (4) で割り切れる場合、analysis → synthesis 往復で入力長が保存される。**segment_size=8192 は 4 で割り切れるため問題なし** (8192 / 4 = 2048)。

**iSTFT 出力長とセグメント長の整合**:

```
z_slice: 32 frames
→ ups (4x4 = 16x): 512 time steps
→ subband_conv_post: 512 time steps, 72ch
→ reshape: [B, 4, 18, 512]
→ iSTFT (hop=4): 各サブバンド 512 * 4 = 2048 samples
→ PQMF synthesis (4 subbands): 2048 * 4 = 8192 samples ✓
```

> **注意**: iSTFT で center=True を使用すると n_fft//2 (=8) samples のエッジトリミングが発生し 2044 samples になる。MB-iSTFT Generator では center=False (トリミングなし) で実装し、segment_size との整合を保つ。原著 MB-iSTFT-VITS も同様にトリミングなしで実装している。

#### 3.1.6 weight_norm と remove_weight_norm

- `conv_pre`, 全 `ups` 層に `weight_norm` を適用 (現行と同一)
- `subband_conv_post` には weight_norm を適用しない (原著に準拠)
- `remove_weight_norm()` メソッドを実装し、ONNX エクスポート前に呼び出し可能にする

### 3.2 ONNX 互換 iSTFT 実装

#### 3.2.1 問題

ONNX は opset 17 で STFT 演算子を追加したが、**iSTFT 演算子は未実装** ([onnx/onnx#4777](https://github.com/onnx/onnx/issues/4777))。`torch.istft` は ONNX エクスポート不可。

#### 3.2.2 解決策: DFT 行列方式

DFT 行列を事前計算し `F.conv_transpose1d` で iSTFT を実現する。

**DFT 行列の構築** (n_fft=16):

```python
fourier_basis = np.fft.fft(np.eye(n_fft))        # (16, 16) complex
cutoff = n_fft // 2 + 1                           # = 9
# 実部と虚部を積み重ね
fourier_stacked = np.vstack([
    np.real(fourier_basis[:cutoff, :]),            # (9, 16)
    np.imag(fourier_basis[:cutoff, :]),            # (9, 16)
])                                                 # (18, 16) = (n_fft+2, n_fft)

# 逆変換基底: 疑似逆行列 + Hann窓 + OLA正規化の事前吸収
scale = n_fft / hop_length                         # = 4.0
inverse_basis = np.linalg.pinv(scale * fourier_stacked).T  # (18, 16)
# Hann窓とOLA正規化を吸収 (n_fft=16, hop=4, overlap=75% → wss=1.5 で定数)
window = np.hanning(n_fft)
wss = 1.5  # 定常状態のwindow sum squares
inverse_basis = inverse_basis * window * (scale / wss)
```

**inverse_basis のテンソル形状**: `(n_fft+2, 1, n_fft)` = `(18, 1, 16)`
- `F.conv_transpose1d` の weight は `(in_channels, out_channels/groups, kernel_size)`
- input: `(B, 18, T_frames)`, output: `(B, 1, T_samples)`

```python
class OnnxISTFT(nn.Module):
    def __init__(self, n_fft=16, hop_length=4):
        super().__init__()
        inverse_basis = self._build_inverse_basis(n_fft, hop_length)
        # 形状: (n_fft+2, 1, n_fft) = (18, 1, 16)
        self.register_buffer("inverse_basis", inverse_basis)
        self.hop_length = hop_length

    def forward(self, magnitude, phase):
        # magnitude: (B, n_fft//2+1, T) = (B, 9, T)
        # phase:     (B, n_fft//2+1, T) = (B, 9, T)
        real = magnitude * torch.cos(phase)         # (B, 9, T)
        imag = magnitude * torch.sin(phase)         # (B, 9, T)
        combined = torch.cat([real, imag], dim=1)   # (B, 18, T)
        waveform = F.conv_transpose1d(
            combined, self.inverse_basis, stride=self.hop_length
        )                                           # (B, 1, T_out)
        return waveform
```

**window_sum_squares 正規化の省略**: n_fft=16, hop=4 (overlap 75%) + Hann 窓では wss が定常状態で定数 1.5 になるため、スカラー乗算として inverse_basis に事前吸収可能。動的な per-sample 正規化は不要で、ONNX 互換性を阻害しない。

**要件**:
- 全演算が Conv1d / ConvTranspose1d で表現されること (opset 15 で十分)
- n_fft=16 の場合、DFT 行列は 18x16 でオーバーヘッド無視可能
- `register_buffer` で全定数テンソルを登録
- 新規ファイル `src/python/piper_train/vits/stft_onnx.py` として実装

### 3.3 損失関数

#### 3.3.1 Sub-band Multi-resolution STFT 損失 (新規追加)

MB-iSTFT では、サブバンド信号に対して Multi-resolution STFT 損失を適用する。これは現行の損失関数に**追加**される。

**パラメータ** (論文準拠):

| 解像度 | FFT サイズ | ホップサイズ | 窓サイズ |
|--------|----------|------------|---------|
| 高 | 171 | 10 | 60 |
| 中 | 384 | 30 | 150 |
| 低 | 683 | 60 | 300 |

**構成**:
- Spectral Convergence Loss: `||STFT(y) - STFT(y_hat)||_F / ||STFT(y)||_F`
- Log STFT Magnitude Loss: `L1(log(|STFT(y)|) - log(|STFT(y_hat)|))`
- 各解像度で上記 2 つを計算し、全解像度の平均を取る

**適用方法**:
1. GT 音声を PQMF analysis でサブバンド分解: `y_mb = pqmf.analysis(y)` → `[B, 4, T//4]`
2. Generator 出力の iSTFT 直後のサブバンド信号 `y_hat_mb` と比較
3. サブバンドをバッチ方向に結合: `(B*4, T//4)` の形状で損失計算

**損失重み**: `c_sub_stft` (デフォルト: 1.0、CLI オプションで調整可能)

#### 3.3.2 既存損失との統合

```python
# MB-iSTFT 有効時の Generator 損失
loss_gen_all = (
    loss_gen           # Adversarial (MPD/MSD, フルバンド)
    + loss_fm          # Feature matching (フルバンド)
    + loss_mel         # Mel L1 (フルバンド)
    + loss_dur         # Duration
    + loss_kl          # KL divergence
    + loss_sub_stft    # Sub-band STFT (新規追加)
    + loss_wavlm       # WavLM (オプション)
)
```

**MPD/MSD はフルバンド信号** (PQMF 合成後) に対して適用を維持する。

#### 3.3.3 新規ファイル

- `src/python/piper_train/vits/stft_loss.py` — SpectralConvergenceLoss, LogSTFTMagnitudeLoss, MultiResolutionSTFTLoss

### 3.4 学習パイプライン

#### 3.4.1 CLI オプション

| オプション | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `--mb-istft` | flag | False | MB-iSTFT Generator を使用 |
| `--sub-stft-fft-sizes` | tuple | (171, 384, 683) | Sub-band STFT 損失の FFT サイズ |
| `--sub-stft-hop-sizes` | tuple | (10, 30, 60) | Sub-band STFT 損失のホップサイズ |
| `--sub-stft-win-sizes` | tuple | (60, 150, 300) | Sub-band STFT 損失の窓サイズ |
| `--c-sub-stft` | float | 1.0 | Sub-band STFT 損失の重み |

#### 3.4.2 training_step の変更

```python
def training_step_g(self, batch):
    # ... 既存のフォワードパス ...
    # SynthesizerTrn.forward() が o_mb (サブバンド信号) も返す

    if self.hparams.mb_istft:
        # 1. GT音声をサブバンド分解
        y_mb = self.pqmf.analysis(y)  # [B, 4, T//4]

        # 2. Sub-band STFT損失 (Generator のサブバンド出力 vs GT サブバンド)
        loss_sub_stft = self.sub_stft_loss(o_mb, y_mb) * self.hparams.c_sub_stft

        loss_gen_all = loss_gen_all + loss_sub_stft

    # フルバンド損失 (mel, MPD/MSD) は o (フルバンド信号) に対して適用
    # MB-iSTFT の場合も Generator が PQMF 合成済みのフルバンド信号を返すため
    # 既存のフルバンド損失コードは変更不要
```

**注意**: `self.pqmf` は `VitsModel.__init__` で `--mb-istft` 有効時にインスタンス化する。学習時の PQMF analysis (GT 分解) 用であり、Generator 内部の PQMF synthesis とは別インスタンス。

#### 3.4.3 save_hyperparameters() との整合

`mb_istft` フラグはチェックポイント復元時の一貫性のために `save_hyperparameters()` に含める必要がある。`freeze_dp` と同じパターンで、`__main__.py` で `dict_args["mb_istft"]` を設定してから `VitsModel(**dict_args)` を呼ぶ。

```python
# __main__.py — モデル作成前に設定
if args.mb_istft:
    dict_args["mb_istft"] = True
    # upsample_rates を MB-iSTFT 用に上書き
    dict_args["upsample_rates"] = (4, 4)
    dict_args["upsample_kernel_sizes"] = (16, 16)

model = VitsModel(**dict_args)  # save_hyperparameters() が mb_istft=True を記録
```

`VitsModel.__init__` で `save_hyperparameters()` が呼ばれる前に全パラメータが確定していること。これによりチェックポイントから `load_from_checkpoint()` した際に `mb_istft=True` が復元され、正しい Generator アーキテクチャが選択される。

#### 3.4.3 Quality プリセットとの相互作用

| Quality | 現行 upsample_rates | MB-iSTFT upsample_rates | 合計倍率 |
|---------|-------------------|------------------------|---------|
| medium | (8, 8, 4) | **(4, 4)** + iSTFT(4x) + PQMF(4x) | 256x |
| x-low | (8, 8, 4) | **(4, 4)** + iSTFT(4x) + PQMF(4x) | 256x |
| high | (8, 8, 2, 2) | **(8, 8)** + iSTFT(4x) + PQMF(4x)? | 要検討 |

**high プリセットの扱い**: 初期実装では medium のみ対応。high は後続で検討 (現在 high プリセットの学習実績がないため)。`--mb-istft` と `--quality high` の組み合わせはエラーとする。

### 3.5 ONNX エクスポート

#### 3.5.1 変更内容

`export_onnx.py` への変更:

1. **iSTFT モジュール差替え**: `replace_stft_for_onnx()` 関数で、学習時の `torch.istft` 呼び出しを DFT 行列方式の `OnnxISTFT` に差し替え
2. **PQMF bake**: PQMF 合成フィルタを ONNX グラフに含める (固定係数 Conv1d として)
3. **出力形状**: `[B, 1, T]` を維持 (C#/Rust の変更不要)
4. **remove_weight_norm()**: MB-iSTFT Generator の構造に合わせた実装

#### 3.5.2 EMA 対応

EMA (`ema.py`) は `model.model_g.dec` の `requires_grad=True` パラメータを自動的に対象とする。MB-iSTFT Generator が `SynthesizerTrn.dec` として設定されていれば、`subband_conv_post` 等の新パラメータも**自動的に EMA 対象に含まれる**。

PQMF の固定係数 (`register_buffer`) は `requires_grad=False` のため EMA 対象外。これは正しい動作。

`export_onnx.py` での EMA 適用時は、新しいパラメータ名 (`subband_conv_post.weight` 等) が `ema_generator_state.shadow_params` に含まれることを確認する。

#### 3.5.3 推論フォワード (infer_forward) の変更

```python
# 現行
o = model_g.dec((z * y_mask), g=g)

# MB-iSTFT: onnx_export_mode=True のため fullband のみ返す
# Generator 内部で iSTFT + PQMF 合成を実行し [B, 1, T] を出力
o = model_g.dec((z * y_mask), g=g)  # 変更不要 (dec 内部で処理)
```

`export_onnx.py` で `model_g.dec.onnx_export_mode = True` を設定することで、Generator が `(fullband, subbands)` ではなく `fullband` のみを返すようになる。これにより `infer_forward()` の変更は不要。

### 3.6 チェックポイント互換性

#### 3.6.1 既存チェックポイントからの部分ロード

MB-iSTFT モデルは既存の 6lang チェックポイントの以下のコンポーネントを**再利用できない**:
- `dec.*` (Generator): アーキテクチャが異なるため不可

以下は**再利用可能**:
- `enc_p.*` (TextEncoder)
- `enc_q.*` (PosteriorEncoder)
- `flow.*` (Flow)
- `dp.*` (DurationPredictor)
- `emb_g.*`, `emb_lang.*` (Embedding)

→ 事前学習済みチェックポイントから Decoder 以外を `strict=False` でロードし、Decoder のみスクラッチで学習する戦略を検討する。ただし初期実装ではフルスクラッチ学習とし、部分ロードは後続の最適化として扱う。

---

## 4. Step 0: ORT 最適化 (再学習不要) — 現状確認と訂正

Issue #268 の Step 0 で提案された ORT 最適化について、現在のコードベースの状態を確認した結果を記録する。

### 4.1 C# `ORT_DISABLE_ALL` について

**Issue の記載**: "C# SessionFactory.cs: `ORT_DISABLE_ALL` → `ORT_ENABLE_ALL` に修正"

**現状**: これはバグではなく、意図的なキャッシュ最適化パターン。

```csharp
// SessionFactory.cs — 初回起動時 (最適化を実行して .opt.onnx に保存)
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;  // L328

// キャッシュ読み込み時 (再最適化をスキップ)
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;  // L133
```

Rust 実装も同一パターン (`engine.rs:159-182`)。**修正不要**。

### 4.2 Python `infer_onnx.py` の SessionOptions

**Issue の記載**: "Python infer_onnx.py に `graph_optimization_level=ORT_ENABLE_ALL` 追加"

**現状**: PR #315 で `ort_utils.py` に集約済み。`create_session_options()` で `ORT_ENABLE_ALL` を設定。**対応済み**。

### 4.3 onnxsim 有効化

**Issue の記載**: "onnxsim有効化 (prosodyモデルでも安全、`check_n=3`で検証済み)"

**現状**: `export_onnx.py` に `--simplify` オプションとして実装済み。ただし prosody モデルでは数値精度保全のため**意図的にスキップ**している (`export_onnx.py:415-422`)。

```python
if args.simplify:
    if has_prosody:
        _LOGGER.info("Prosody features enabled - skipping ONNX simplification")
    else:
        simplify_onnx_model(args.output)
```

**判断**: prosody モデルでの onnxsim は数値精度リスクがあるため、現行の条件付きスキップを維持する。Issue の "prosodyモデルでも安全" という主張は検証が必要だが、MB-iSTFT 実装のブロッカーではない。

### 4.4 dynamic_block_base + メモリアリーナ

**現状**: PR #317 で Python/Rust/C#/C++ 全実装に統一済み (`session.dynamic_block_base=4`, `enable_cpu_mem_arena=True`, `enable_mem_pattern=True`)。**対応済み**。

### 4.5 Step 0 の結論

**ORT 最適化は既に全実装で統一済み**。Step 0 として追加で行う作業はない。MB-iSTFT 実装 (Step 1-6) に直接着手する。

---

## 5. 実装ステップ

### Step 1: 新モジュール追加

**対象ファイル**:

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/vits/mb_istft.py` | MBiSTFTGenerator, PQMF (新規) |
| `src/python/piper_train/vits/stft_onnx.py` | OnnxISTFT (新規) |
| `src/python/piper_train/vits/stft_loss.py` | MultiResolutionSTFTLoss (新規) |
| `src/python/tests/test_pqmf.py` | PQMF 往復再構成テスト (新規) |
| `src/python/tests/test_mb_istft_generator.py` | Generator 出力形状・speaker conditioning テスト (新規) |
| `src/python/tests/test_stft_loss.py` | Sub-band STFT 損失テスト (新規) |

**受け入れ基準**:
- [ ] PQMF analysis → synthesis 往復で再構成 SNR > 5 dB (cosine-modulated PQMF with Kaiser 窓の理論限界。NN が残差エイリアシングを補償する設計)
- [ ] PQMF の全テンソルが `register_buffer` で登録されている (`.cuda()` ハードコードなし)
- [ ] MBiSTFTGenerator の学習時出力が `(fullband, subbands)` タプル
- [ ] MBiSTFTGenerator の `onnx_export_mode=True` 時出力が `fullband` のみ
- [ ] MBiSTFTGenerator の出力形状が `[B, 1, T]` (T = segment_size = 8192)
- [ ] MBiSTFTGenerator が `g` (speaker embedding) を `self.cond` 経由で正しく受け取る
- [ ] subband_conv_post の入力チャネルが `upsample_initial_channel // (2 ** len(upsample_rates))` と一致
- [ ] OnnxISTFT が `torch.istft` と同等の出力を生成する (定常領域の絶対誤差 < 1e-4)
- [ ] OnnxISTFT の inverse_basis 形状が `(n_fft+2, 1, n_fft)` = `(18, 1, 16)`
- [ ] MultiResolutionSTFTLoss が 3 解像度で損失を計算する

### Step 2: 学習パイプライン統合

**対象ファイル**:

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/__main__.py` | `--mb-istft` + 関連 CLI オプション追加 |
| `src/python/piper_train/vits/lightning.py` | training_step_g に PQMF analysis + sub-band STFT 損失追加 |
| `src/python/piper_train/vits/models.py` | SynthesizerTrn に MB-iSTFT Generator の選択ロジック追加 |

**受け入れ基準**:
- [ ] `--mb-istft` で MBiSTFTGenerator が選択される
- [ ] `--mb-istft` で `upsample_rates=(4,4)`, `upsample_kernel_sizes=(16,16)` が自動設定される
- [ ] `--mb-istft` と `--quality high` の組み合わせでエラーが出る
- [ ] `save_hyperparameters()` に `mb_istft=True` が記録される
- [ ] training_step_g で sub-band STFT 損失が計算・ログされる
- [ ] PQMF analysis が GT 音声に適用されてサブバンド分解される
- [ ] フルバンド判別器 (MPD/MSD) は PQMF 合成後の信号に適用される
- [ ] WavLM 判別器との共存が正常に動作する

### Step 3: ONNX エクスポート対応

**対象ファイル**:

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/export_onnx.py` | iSTFT → OnnxISTFT 差替え、PQMF bake |
| `src/python/tests/test_export_onnx.py` | MB-iSTFT ONNX エクスポートテスト追加 |

**受け入れ基準**:
- [ ] ONNX エクスポートが成功する (opset 15)
- [ ] FP16 変換が正常に動作する
- [ ] ONNX 出力形状が `[B, 1, T]`
- [ ] PyTorch と ONNX の推論結果が一致する (既存 `test_pytorch_onnx_parity.py` のパターンで検証)
- [ ] EMA が MB-iSTFT Generator に正しく適用される
- [ ] `remove_weight_norm()` が正常に動作する
- [ ] マルチスピーカー + 多言語モデルのエクスポートが成功する

### Step 4: 6 言語事前学習

**学習コマンド**:

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --mb-istft \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 75 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --default_root_dir /data/piper/output-mbistft-6lang \
  > /data/piper/training_mbistft_6lang.log 2>&1 &
```

**パラメータ設計根拠**:

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| `--max_epochs` | 75 | 現行 6lang と同一。公平な比較のため |
| `--batch-size` | 20 | 現行 6lang と同一。MB-iSTFT で Decoder メモリが削減されるが、保守的に同一値を維持 |
| `--no-wavlm` | 有効 | 現行 6lang と同一条件で比較するため |
| その他 | 現行と同一 | Decoder 以外の変数を固定して公平比較 |

**注意**: Issue の Step 4 では `--batch-size 32` を提案していたが、公平な比較のため現行と同一の 20 を使用する。メモリに余裕があれば後続で 32 を試行する。

### Step 5: つくよみちゃんファインチューニング

Template B (シングルスピーカー FT) + `--mb-istft` で実行。Step 4 完了後に着手。

### Step 6: 品質比較 (必須ゲート)

#### 6.1 定量評価

| 指標 | 方法 | ロールバック基準 |
|------|------|---------------|
| RTF | 同一テキスト 100 回の平均 | < 1.15x (高速化不十分) |
| UTMOS | 自動 MOS 推定 | 劣化 > 0.1 |
| Per-language MCD | Mel Cepstral Distortion (言語別) | いずれかの言語で劣化 > 0.5 dB |
| Per-language F0-RMSE | 基本周波数の RMSE (言語別) | ZH 声調/JA ピッチアクセントの劣化 |
| Duration 比較 | 同一テキストの音声長比較 | 異常な短縮/伸長 |

#### 6.2 定性評価

| 項目 | 方法 |
|------|------|
| 聴覚比較 | 6 言語 x 3 テキスト = 18 サンプル |
| スペクトログラム | サブバンドアーティファクト (周波数ノイズ) の目視確認 |
| Speaker similarity | マルチスピーカーモデルでの話者一貫性 |

#### 6.3 ロールバック判定

以下のいずれかに該当する場合はマージしない:
1. いずれかの言語で MCD 劣化 > 0.5 dB
2. 聴覚比較で明確なアーティファクト (金属音、バズ音、周波数ノイズ)
3. UTMOS 劣化 > 0.1
4. 推論速度が 1.15 倍未満
5. マルチスピーカーモデルで話者の声質が混合する

---

## 6. リスクと軽減策

| リスク | 影響度 | 軽減策 |
|--------|--------|--------|
| マルチスピーカーでの品質低下 | 高 | speaker conditioning の正確な実装 (参考実装のバグを修正) |
| ZH/JA の声調・ピッチアクセント劣化 | 中 | Per-language F0-RMSE で早期検出、学習 epoch 調整 |
| PQMF アーティファクト (エイリアシング) | 中 | 再構成 SNR テスト (> 5 dB、NN が残差補償)、スペクトログラム目視確認 |
| iSTFT の ONNX 互換性問題 | 低 | DFT 行列方式で回避済み。n_fft=16 は十分小さい |
| FP16 変換での精度低下 | 低 | PQMF 固定係数の FP16 SNR は ~75 dB (推論に十分)。252 係数中 40 個が subnormal 領域だが Kaiser 窓テール部分のため知覚的影響なし |
| 参考実装 (FENRlR) の不安定性 | 中 | 参考実装を直接使わず自前実装。論文とオリジナル実装を参照 |

---

## 7. テスト計画

### 7.1 ユニットテスト

| テストファイル | 検証内容 |
|--------------|---------|
| `test_pqmf.py` | analysis → synthesis 往復再構成 (SNR > 5 dB)、バッファ登録、バッチ処理 |
| `test_mb_istft_generator.py` | 出力形状 `[B, 1, T]`、speaker conditioning の動作、weight_norm/remove |
| `test_stft_loss.py` | 3 解像度での損失計算、ゼロ入力でのエッジケース |
| `test_stft_onnx.py` | OnnxISTFT vs torch.istft の数値一致 |

### 7.2 統合テスト

| テスト | 検証内容 |
|--------|---------|
| `test_export_onnx.py` (拡張) | MB-iSTFT ONNX エクスポート、FP16 変換、PyTorch/ONNX parity |
| `test_vits.py` (拡張) | `--mb-istft` での学習ループ 1 epoch 動作確認 |

### 7.3 品質テスト (手動)

Step 6 の品質比較を参照。

---

## 8. 依存関係・前提条件

### 8.1 Python パッケージ

| パッケージ | 用途 | ライセンス |
|-----------|------|----------|
| numpy | DFT 行列計算、PQMF フィルタ設計、Kaiser 窓生成 (`numpy.kaiser()`) | BSD | 既存依存 |
| torch | iSTFT, Conv1d | BSD | 既存依存 |

新規依存の追加は不要。Kaiser 窓は `numpy.kaiser()` で生成でき、scipy は不要。

### 8.2 既存ブランチとの関係

| ブランチ | 関係 |
|---------|------|
| `dev` | ベースブランチ。MB-iSTFT は dev から分岐 |
| `feat/vits2-upgrade` | 独立。VITS2 固有機能 (Duration Discriminator 等) は別途。MB-iSTFT と VITS2 の統合は両方マージ後に検討 |

---

## 9. 用語集

| 用語 | 説明 |
|------|------|
| MB-iSTFT | Multi-Band inverse Short-Time Fourier Transform |
| PQMF | Pseudo Quadrature Mirror Filter — サブバンド分割/合成フィルタ |
| MCD | Mel Cepstral Distortion — メルケプストラム歪み |
| RTF | Real-Time Factor — 推論速度指標 (< 1.0 でリアルタイムより高速) |
| MACs | Multiply-Accumulate operations — 計算量指標 |
| DFT | Discrete Fourier Transform |
| MPD | Multi-Period Discriminator |
| MSD | Multi-Scale Discriminator (DiscriminatorS) |

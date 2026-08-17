"""H-2a / H-5: デコーダ合成チェーン (iSTFT head → PQMF synthesis) の単体検証。

docs/design/zero-shot-v10b-quality-plan.md §3.1 H-2 (a) / H-5 の実装。
v10b の帯域解剖 (§1.1 A1 / §1.2 B2) が挙げた 2 つの容疑

  - 容疑 2: PQMF 帯域境界のエイリアス非相殺 (5512.5Hz = SR/4 / 8268.75Hz =
    3SR/8 のピークが 4-band 境界に一致)
  - B2: 750-1000Hz の系統的包絡欠損 (-8.3dB、v9 と同符号 = 世代非依存)

を「学習と独立に」切り分ける。本ファイルが測るのは **decoder の固定合成段のみ**
(OnnxISTFT + PQMF.synthesis) — 学習される upsampler / ResBlock は含まない。
従って結論は「固定合成段がアーティファクトを作っているか否か」に限定される
(upsampler 側の検証は test_decoder_upsample_mode.py の H-1)。

**測定器**: E-4 の ``piper_train.tools.measure_comb_artifacts.comb_metrics`` を
そのまま使う。同一物理量で測ることが plan §3.1 H-2(a) の要求
(「コム/境界エイリアスを E-4 と同じ物理量で測定」)。EVAL-ONLY モジュールだが
scripts/check_zs_metric_isolation.py の scope は学習コード
(``piper_train/vits/**`` + ``piper_train/__main__.py``) とメトリクス本体のみで、
tests/ は ``classify_role`` が None を返す = 対象外。学習コードから import しない
限り契約 (docs/spec/zs-eval-contract.md §2 禁止事項 4) に抵触しない。

**受け入れ基準の出所** — plan §3.1 H-2 の「受け入れ基準は第一原理から導出し
`# threshold-relaxed:` ルールに従う」に沿い、各 assert の根拠を [第一原理] /
[現状実測 pin] で明示する:

  - [第一原理] 55dB / 50dB の再構成 SNR — tests/test_pqmf.py と同一の canonical
    基準 (元要求 -90dB 残留エイリアスを 5dB に緩めてバグを 15 ヶ月制度化した
    PQMF 事故の再発防止。docs/design/zero-shot-noise-root-cause-pqmf.md §4)。
    iSTFT 側は periodic Hann + hop = n_fft/4 が COLA を満たすため理論上は
    完全再構成で、劣化分は PQMF の near-PR 設計に由来する
  - [第一原理] コム < 1.5dB / autocorr < 0.05 — plan §4.3 の事前登録 gate
    そのもの。固定合成段がこれを自力で破っていれば構造的に達成不能になる
  - [現状実測 pin] 帯域応答の平坦性 — 数値は本テスト作成時 (2026-08-17) の
    実測。将来 taps / 設計式を変えた際に「どれだけ動いたか」を見るための固定

実測値 (taps=62 canonical、2026-08-17):
    analysis 由来 round-trip SNR   64.0 dB
    comb_excess / ac@128 / ac@256  0.694 dB / 0.0091 / 0.0063  (GT 0.65-0.76 / 0.01-0.13)
    帯域応答 max|dev| 250-10kHz    0.009 dB   (750-1000Hz は +0.003 dB)
    独立 subband (NN 相当) の comb 0.577 dB
"""

from __future__ import annotations

import math

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import PQMF  # noqa: E402
from piper_train.vits.stft_onnx import OnnxISTFT  # noqa: E402


SR = 22050
N_FFT = 16  # decoder の iSTFT head 設定 (MBiSTFTGenerator default)
HOP = 4
SUBBANDS = 4
# 1.02 秒 / SUBBANDS で割り切れる長さ。comb_metrics は >= 0.5 秒を要求する。
N_FULL = 22528
# 端は OLA / FIR の過渡区間。PQMF の群遅延 (taps) と iSTFT の 1 フレームを
# 十分に上回る 128 サンプルを両端から捨てる。
TRIM = 128
# PQMF 4-band の帯域境界 (fullband)。SR/8 刻み。
BAND_EDGES_HZ = (2756.25, 5512.5, 8268.75)


def _comb_metrics(x: "torch.Tensor") -> dict:
    """E-4 と同一定義のコム物理量。x は [1, 1, T] または [T]。"""
    from piper_train.tools.measure_comb_artifacts import comb_metrics

    y = x.detach().reshape(-1).to(torch.float64).numpy()
    m = comb_metrics(y, SR)
    assert m is not None, "clip too short for comb metrics"
    return m


def _stft_for_onnx_istft(x: "torch.Tensor") -> tuple["torch.Tensor", "torch.Tensor"]:
    """OnnxISTFT が反転する規約で STFT する (periodic Hann / center=False)。

    OnnxISTFT の inverse basis は合成窓と WSS 正規化を吸収済みなので、解析側で
    同じ Hann 窓をかければ hop = n_fft/4 の COLA により完全再構成になる。
    """
    win = torch.hann_window(N_FFT, periodic=True, dtype=x.dtype)
    spec = torch.stft(
        x,
        n_fft=N_FFT,
        hop_length=HOP,
        win_length=N_FFT,
        window=win,
        center=False,
        return_complex=True,
    )
    return spec.abs(), torch.angle(spec)


def _istft_pqmf_synthesis(
    mag: "torch.Tensor", phase: "torch.Tensor", pqmf: PQMF
) -> "torch.Tensor":
    """decoder 後段と同一の合成: OnnxISTFT → reshape → PQMF.synthesis。"""
    istft = OnnxISTFT(n_fft=N_FFT, hop_length=HOP)
    sub = istft(mag, phase)  # [SUBBANDS, 1, T_sub]
    sub = sub.reshape(1, SUBBANDS, -1)
    return pqmf.synthesis(sub)


def _chain_roundtrip(x: "torch.Tensor", pqmf: PQMF) -> "torch.Tensor":
    """fullband → PQMF.analysis → STFT → (iSTFT + PQMF.synthesis) → fullband。

    subband を「解析フィルタバンク由来」にした場合の経路。QMF のエイリアス
    相殺前提が成立する側の対照。
    """
    sub = pqmf.analysis(x)  # [1, SUBBANDS, T/SUBBANDS]
    mag, phase = _stft_for_onnx_istft(sub.reshape(SUBBANDS, -1))
    return _istft_pqmf_synthesis(mag, phase, pqmf)


def _snr_db(ref: "torch.Tensor", est: "torch.Tensor") -> float:
    r = ref[..., TRIM:-TRIM]
    e = r - est[..., TRIM:-TRIM]
    return float(10 * torch.log10(r.pow(2).sum() / e.pow(2).sum()))


def _mean_psd(x: "torch.Tensor", n_fft: int = 2048) -> np.ndarray:
    """[1, T] の時間平均パワースペクトル (linear)。"""
    spec = torch.stft(
        x,
        n_fft=n_fft,
        hop_length=n_fft // 4,
        window=torch.hann_window(n_fft, dtype=x.dtype),
        center=False,
        return_complex=True,
    )
    return (spec.abs() ** 2).mean(dim=-1).reshape(-1).numpy()


def _band_edges(band_hz: float, n_bins: int, n_fft: int) -> list[tuple[float, float, np.ndarray]]:
    bin_hz = SR / n_fft
    out = []
    for i in range(int((SR / 2) // band_hz)):
        lo, hi = i * band_hz, (i + 1) * band_hz
        idx = np.arange(int(np.ceil(lo / bin_hz)), int(hi / bin_hz) + 1)
        idx = idx[(idx >= 0) & (idx < n_bins)]
        if len(idx):
            out.append((lo, hi, idx))
    return out


def _band_gain_db(
    x_in: "torch.Tensor", x_out: "torch.Tensor", band_hz: float = 250.0
) -> dict[tuple[float, float], float]:
    """帯域ごとの出力/入力パワー比 [dB] (帯域応答)。完全に平坦なら全て 0 dB。"""
    n_fft = 2048
    p_in = _mean_psd(x_in, n_fft)
    p_out = _mean_psd(x_out, n_fft)
    return {
        (lo, hi): 10.0
        * float(np.log10((p_out[idx].sum() + 1e-20) / (p_in[idx].sum() + 1e-20)))
        for lo, hi, idx in _band_edges(band_hz, len(p_in), n_fft)
    }


def _band_profile_db(
    x: "torch.Tensor", band_hz: float = 250.0, ref: tuple[float, float] = (1000.0, 3000.0)
) -> dict[tuple[float, float], float]:
    """帯域プロファイル [dB] (ref 帯域の平均パワー密度基準)。白色なら全て 0 dB。"""
    n_fft = 2048
    p = _mean_psd(x, n_fft)
    bin_hz = SR / n_fft
    ref_idx = np.arange(int(ref[0] / bin_hz), int(ref[1] / bin_hz) + 1)
    ref_density = p[ref_idx].mean()
    return {
        (lo, hi): 10.0 * float(np.log10((p[idx].mean() + 1e-20) / (ref_density + 1e-20)))
        for lo, hi, idx in _band_edges(band_hz, len(p), n_fft)
    }


def _white_noise(seed: int, shape: tuple[int, ...]) -> "torch.Tensor":
    gen = torch.Generator().manual_seed(seed)
    return torch.randn(*shape, generator=gen)


# ===========================================================================
# H-2a: 合成チェーンにおけるコム / 境界エイリアス
# ===========================================================================


@pytest.mark.unit
class TestSynthesisChainAnalysisDerived:
    """subband が解析フィルタバンク由来の場合 (エイリアス相殺が成立する側)。"""

    def test_white_noise_roundtrip_is_near_perfect(self):
        """[第一原理] 白色雑音の chain round-trip SNR >= 55 dB。

        tests/test_pqmf.py と同一の canonical 基準。iSTFT 側は periodic Hann +
        hop = n_fft/4 が COLA を満たし理論上完全再構成なので、残差は PQMF の
        near-PR 設計に由来する分のみ。実測 64.0 dB。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        x = _white_noise(0, (1, 1, N_FULL))
        snr = _snr_db(x, _chain_roundtrip(x, pqmf))
        assert snr >= 55, f"iSTFT+PQMF chain round-trip {snr:.1f} dB < 55 dB"

    def test_band_edge_tones_survive_the_chain(self):
        """[第一原理] PQMF 帯域境界のトーンで chain SNR >= 50 dB。

        境界トーンは位相項が壊れたときに鏡像が漏れる最も鋭いプローブ
        (test_pqmf.py と同一基準)。§1.3 容疑 2 が「合成チェーン単体で」
        境界トーンを壊していないことの固定。実測 59.1 dB。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        t = torch.arange(N_FULL, dtype=torch.float32) / SR
        for freq in BAND_EDGES_HZ:
            tone = torch.sin(2 * math.pi * freq * t).reshape(1, 1, -1)
            snr = _snr_db(tone, _chain_roundtrip(tone, pqmf))
            assert snr >= 50, f"band-edge tone {freq:.0f} Hz chain SNR {snr:.1f} dB < 50 dB"

    def test_chain_output_meets_registered_comb_gates(self):
        """[第一原理] 固定合成段の出力が plan §4.3 の事前登録 gate を満たす。

        コム超過 < 1.5dB / >4kHz 残差 autocorr @lag128,256 < 0.05。固定合成段が
        自力でこれを破っていれば、どんな upsampler を載せても gate は達成不能に
        なる (= 対策の探索空間が変わる)。実測 0.694 dB / 0.0091 / 0.0063 で
        GT 帯 (0.65-0.76 dB / 0.01-0.13) に収まる。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        x = _white_noise(0, (1, 1, N_FULL))
        m = _comb_metrics(_chain_roundtrip(x, pqmf)[..., TRIM:-TRIM])
        assert m["comb_excess_db"] < 1.5, f"comb excess {m['comb_excess_db']:.3f} dB"
        assert m["hf_autocorr_lag128"] < 0.05, f"ac@128 {m['hf_autocorr_lag128']:.4f}"
        assert m["hf_autocorr_lag256"] < 0.05, f"ac@256 {m['hf_autocorr_lag256']:.4f}"


@pytest.mark.unit
class TestSynthesisChainIndependentSubbands:
    """subband が互いに独立な場合 (= NN 生成 subband の性質、相殺前提が崩れる側)。

    plan §1.3 容疑 2 の「NN 生成 subband は解析フィルタバンク由来でないため
    QMF のエイリアス相殺前提が崩れる」を直接プローブする。
    """

    def test_independent_subbands_do_not_create_frame_grid_comb(self):
        """[第一原理] 独立 subband を PQMF 合成してもコム gate を満たす。

        固定 PQMF 合成そのものが SR/128 格子コム (A1) を作るか否かの切り分け。
        作らないなら A1 の発生源は upsampler 側 (容疑 1) に絞られる。
        実測 comb 0.577 dB / ac@128 0.0054 — 作らない。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        sub = _white_noise(1, (1, SUBBANDS, N_FULL // SUBBANDS))
        y = pqmf.synthesis(sub)[..., TRIM:-TRIM]
        m = _comb_metrics(y)
        assert m["comb_excess_db"] < 1.5, (
            f"PQMF synthesis of independent subbands shows comb "
            f"{m['comb_excess_db']:.3f} dB — the fixed synthesis stage would then "
            f"be a source of A1"
        )
        assert m["hf_autocorr_lag128"] < 0.05
        assert m["hf_autocorr_lag256"] < 0.05

    def test_independent_subband_output_is_spectrally_flat(self):
        """[現状実測 pin] 独立白色 subband の出力帯域プロファイルの平坦性。

        cosine-modulated PQMF は power-complementary なので、subband が独立でも
        パワースペクトルは平坦になる (境界に山も谷も出ない)。実測 max|dev|
        0.631 dB (6750-7000Hz) @250Hz 刻み / 250-10000Hz。この pin は taps や
        設計式を変えたときの逸脱検出用。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        sub = _white_noise(1, (1, SUBBANDS, N_FULL // SUBBANDS))
        y = pqmf.synthesis(sub)[..., TRIM:-TRIM]
        prof = _band_profile_db(y.reshape(1, -1))
        dev = {b: v for b, v in prof.items() if 250 <= b[0] and b[1] <= 10000}
        worst = max(dev.items(), key=lambda kv: abs(kv[1]))
        assert abs(worst[1]) <= 1.5, (
            f"independent-subband output band profile deviates {worst[1]:+.3f} dB "
            f"at {worst[0][0]:.0f}-{worst[0][1]:.0f} Hz"
        )


# ===========================================================================
# H-5: 750-1000Hz 包絡欠損 (B2) — 固定合成段の帯域応答
# ===========================================================================


@pytest.mark.unit
class TestH5ChainBandResponse:
    """B2 (-8.3dB @750-1000Hz、v9/r2 同符号) が固定合成段起因か否かの切り分け。"""

    def test_chain_band_response_is_flat_including_750_1000hz(self):
        """[現状実測 pin] iSTFT+PQMF チェーンの白色雑音帯域応答は平坦。

        250Hz 刻みで出力/入力パワー比を測る。B2 の -8.3dB が固定合成段の
        帯域応答に起因するなら、ここに同符号の落ち込みが出るはず。
        実測: 750-1000Hz は +0.003 dB、250-10000Hz の max|dev| は 0.009 dB
        = **固定合成段は B2 の発生源ではない** (原因は loss / データ / 学習
        される upsampler 側に絞られる)。

        閾値 0.1 dB は実測 0.009 dB に 10 倍の余裕を持たせた pin で、B2 の
        -8.3dB とは 2 桁離れている (結論の符号が反転しない範囲)。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        x = _white_noise(0, (1, 1, N_FULL))
        y = _chain_roundtrip(x, pqmf)
        gains = _band_gain_db(x[..., TRIM:-TRIM].reshape(1, -1), y[..., TRIM:-TRIM].reshape(1, -1))

        g750 = gains[(750.0, 1000.0)]
        assert abs(g750) <= 0.1, (
            f"chain band response at 750-1000 Hz is {g750:+.3f} dB — the fixed "
            f"synthesis stage would then explain B2 (-8.3 dB)"
        )
        band = {b: v for b, v in gains.items() if 250 <= b[0] and b[1] <= 10000}
        worst = max(band.items(), key=lambda kv: abs(kv[1]))
        assert abs(worst[1]) <= 0.1, (
            f"chain band response deviates {worst[1]:+.3f} dB at "
            f"{worst[0][0]:.0f}-{worst[0][1]:.0f} Hz (expected flat to ~0.01 dB)"
        )

    def test_low_band_neighbourhood_has_no_energy_shift(self):
        """[現状実測 pin] B2 に付随する「500-750Hz +3.6dB / 750-1000Hz -8.3dB」の
        下方シフト構造が固定合成段に存在しないこと。

        隣接 3 帯域 (500-750 / 750-1000 / 1000-1250Hz) の相対差が 0.05 dB 以内。
        実測 0.0054 dB (B2 の 11.9dB 段差とは 3 桁離れている)。
        """
        pqmf = PQMF(subbands=SUBBANDS)
        x = _white_noise(0, (1, 1, N_FULL))
        y = _chain_roundtrip(x, pqmf)
        gains = _band_gain_db(x[..., TRIM:-TRIM].reshape(1, -1), y[..., TRIM:-TRIM].reshape(1, -1))
        trio = [gains[(500.0, 750.0)], gains[(750.0, 1000.0)], gains[(1000.0, 1250.0)]]
        assert max(trio) - min(trio) <= 0.05, (
            f"500-1250 Hz relative tilt {max(trio) - min(trio):.4f} dB in the fixed chain"
        )

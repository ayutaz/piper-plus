"""S-2c: head 格子 harmonic 位相テンプレートの数学を固定する TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §2.3 / §3.4。

**なぜ学習なしで検証できるか**: テンプレートは F0 から解析的に決まる関数
``[cos(2πmΦ), sin(2πmΦ)]`` であり、学習パラメータを一切持たない。従って
「合成 F0 を入れて解析値と一致するか」が完全な正しさの基準になる。

固定する契約は 4 点:

1. **位相の定義**: head 格子 (SR/16 = 1378.125Hz) で ``Φ_t = Σ_{i≤t} f0_i / fr``
   (cycles 単位)。frame 格子ではなく head 格子であることが設計の中核
   (§1: 我々の decoder で位相が消費される格子は head だけ)。
2. **Chebyshev 漸化式 == 直接評価**: 超越関数を 2 個に減らす最適化が
   数値的に無害であること (§3.1 実測: M=8 で 2.9e-06)。
3. **float64 位相累積**: fp32 で累積すると torch/ORT の加算順序差が長さと
   ともに増幅し、10 秒で相対誤差 1.7e-01 に達する (§3.4 実測)。float64 なら
   長さ非依存で 3e-05。ONNX parity テストを長尺で書けるようにするための
   必須条件なので、精度を数値で pin する。
4. **V/UV ゲート**: 無声フレームでは調波チャネルが厳密に 0 (位相参照は
   有声区間にしか意味がない)。
"""

from __future__ import annotations

import math

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import HarmonicPhaseTemplate  # noqa: E402


SR = 22050
MEL_HOP = 256
UPSAMPLE = 16  # prod(upsample_rates) = 4 * 4
HEAD_FRAME_RATE = SR * UPSAMPLE / MEL_HOP  # 1378.125 Hz


def _template(n_harmonics: int = 8) -> HarmonicPhaseTemplate:
    tmpl = HarmonicPhaseTemplate(
        n_harmonics=n_harmonics,
        upsample=UPSAMPLE,
        sample_rate=SR,
        frame_hop=MEL_HOP,
    )
    tmpl.eval()
    return tmpl


def test_head_frame_rate_is_derived_from_the_decoder_grid():
    """head 格子は frame 格子 (SR/256) の upsample 倍 = SR/16。"""
    assert _template().frame_rate == pytest.approx(HEAD_FRAME_RATE)
    assert _template().frame_rate == pytest.approx(1378.125)


def test_channel_layout_and_shape():
    """出力は ``[cos(1..M), sin(1..M), logf0, uv]`` の 2M+2 ch × T*upsample。"""
    tmpl = _template(n_harmonics=8)
    f0 = torch.full((2, 1, 7), 220.0)
    out = tmpl(f0)
    assert out.shape == (2, 2 * 8 + 2, 7 * UPSAMPLE)
    assert out.dtype == f0.dtype


def test_template_matches_analytic_phase_for_constant_f0():
    """定数 F0 に対し、各調波チャネルが解析値 cos/sin(2πm·Φ_t) と一致する。"""
    m_max = 8
    tmpl = _template(n_harmonics=m_max)
    f0_hz = 260.0
    n_frames = 64
    f0 = torch.full((1, 1, n_frames), f0_hz)

    with torch.no_grad():
        out = tmpl(f0)

    t = torch.arange(1, n_frames * UPSAMPLE + 1, dtype=torch.float64)
    phase = t * (f0_hz / HEAD_FRAME_RATE)  # cycles
    for m in range(1, m_max + 1):
        expected_cos = torch.cos(2 * math.pi * m * phase).float()
        expected_sin = torch.sin(2 * math.pi * m * phase).float()
        torch.testing.assert_close(
            out[0, m - 1], expected_cos, atol=2e-4, rtol=0, msg=f"cos m={m}"
        )
        torch.testing.assert_close(
            out[0, m_max + m - 1], expected_sin, atol=2e-4, rtol=0, msg=f"sin m={m}"
        )


def test_float64_accumulation_keeps_long_sequences_accurate():
    """10 秒級 (T=860 frames = 13,760 head sample) でも位相誤差が積み上がらない。

    §3.4 の実測: fp32 累積は T=1000 で相対誤差 7.0e-02、float64 なら 3.0e-05。
    ここでは「解析値との最大絶対誤差 < 1e-3」で float64 経路を pin する
    (fp32 累積に戻すとこの閾値を大幅に超える)。
    """
    tmpl = _template(n_harmonics=8)
    f0_hz = 313.0
    n_frames = 860
    f0 = torch.full((1, 1, n_frames), f0_hz)

    with torch.no_grad():
        out = tmpl(f0)

    t = torch.arange(1, n_frames * UPSAMPLE + 1, dtype=torch.float64)
    phase = t * (f0_hz / HEAD_FRAME_RATE)
    expected = torch.cos(2 * math.pi * 8 * phase).float()
    max_err = float((out[0, 7] - expected).abs().max())
    assert max_err < 1e-3, f"8th harmonic phase drift too large: {max_err}"


def test_chebyshev_recurrence_matches_direct_evaluation():
    """漸化式で作った m 次調波が直接評価 cos(mθ)/sin(mθ) と一致する。

    テンプレート出力の 1 次調波から θ を復元し、m 次を直接評価して比較する。
    """
    m_max = 8
    tmpl = _template(n_harmonics=m_max)
    torch.manual_seed(0)
    f0 = 80.0 + 400.0 * torch.rand(1, 1, 40)

    with torch.no_grad():
        out = tmpl(f0)

    theta = torch.atan2(out[0, m_max], out[0, 0])  # sin(1Φ), cos(1Φ) → Φ の偏角
    worst = 0.0
    for m in range(1, m_max + 1):
        worst = max(
            worst,
            float((out[0, m - 1] - torch.cos(m * theta)).abs().max()),
            float((out[0, m_max + m - 1] - torch.sin(m * theta)).abs().max()),
        )
    assert worst < 1e-4, f"Chebyshev vs direct evaluation mismatch: {worst}"


def test_unvoiced_frames_gate_harmonic_channels_to_zero():
    """f0 <= 0 のフレームでは調波チャネルが厳密に 0、uv チャネルも 0。"""
    tmpl = _template(n_harmonics=4)
    f0 = torch.tensor([[[200.0, 0.0, 0.0, 240.0]]])

    with torch.no_grad():
        out = tmpl(f0)

    harmonics = out[:, : 2 * 4]
    uv = out[:, -1]
    # frame 1,2 (0 始まり) が無声 → head 格子では [16:48)
    assert torch.all(harmonics[..., 16:48] == 0.0)
    assert torch.all(uv[..., 16:48] == 0.0)
    assert torch.any(harmonics[..., :16] != 0.0)
    assert torch.all(uv[..., :16] == 1.0)


def test_logf0_channel_is_finite_on_unvoiced_frames():
    """log(0) = -inf を漏らさない (clamp 済み) — NaN 伝播の予防線。"""
    tmpl = _template(n_harmonics=4)
    f0 = torch.tensor([[[0.0, 0.0, 300.0]]])
    with torch.no_grad():
        out = tmpl(f0)
    assert torch.isfinite(out).all()


def test_train_mode_randomises_initial_phase_and_eval_mode_does_not():
    """学習時のみ一様乱数の初期位相を足す (§4.4: 位相オフセット不変性の獲得)。

    推論時 (eval) は常にオフセット 0 — ONNX graph に RandomUniform を出さない
    ための構造的保証でもある。
    """
    tmpl = _template(n_harmonics=4)
    f0 = torch.full((1, 1, 8), 200.0)

    tmpl.eval()
    with torch.no_grad():
        a, b = tmpl(f0), tmpl(f0)
    torch.testing.assert_close(a, b)

    tmpl.train()
    torch.manual_seed(0)
    with torch.no_grad():
        c = tmpl(f0)
    torch.manual_seed(1)
    with torch.no_grad():
        d = tmpl(f0)
    assert not torch.allclose(c, d), "train mode should randomise the initial phase"
    # オフセットは位相の平行移動なので、uv / logf0 チャネルは不変
    torch.testing.assert_close(c[:, -2:], d[:, -2:])


def test_template_stays_float32_under_bf16_inputs():
    """bf16 入力でもテンプレートは fp32 で計算される (autocast 下の保険)。

    bf16 の cos/sin は絶対誤差 ~4e-3 で、Chebyshev 漸化式はそれを ~m² 倍に
    増幅する (M=8 で 0.25)。テンプレートは head 格子で超越関数 2 個 +
    Mul/Sub だけなので、dtype を入力に追随させる理由がない。
    """
    m_max = 8
    tmpl = _template(n_harmonics=m_max)
    f0_hz = 260.0
    n_frames = 32
    f0_bf16 = torch.full((1, 1, n_frames), f0_hz, dtype=torch.bfloat16)

    with torch.no_grad():
        out = tmpl(f0_bf16)

    assert out.dtype == torch.float32

    t = torch.arange(1, n_frames * UPSAMPLE + 1, dtype=torch.float64)
    phase = t * (f0_hz / HEAD_FRAME_RATE)
    expected = torch.cos(2 * math.pi * m_max * phase).float()
    max_err = float((out[0, m_max - 1] - expected).abs().max())
    assert max_err < 1e-3, f"bf16 input degraded the 8th harmonic: {max_err}"


def test_per_sample_phase_offset_is_independent_across_batch():
    """初期位相はサンプルごとに独立 (バッチ全体で同一だと拡張にならない)。"""
    tmpl = _template(n_harmonics=4)
    tmpl.train()
    f0 = torch.full((4, 1, 8), 200.0)
    torch.manual_seed(0)
    with torch.no_grad():
        out = tmpl(f0)
    first = out[0, 0]
    assert not all(
        torch.allclose(out[i, 0], first) for i in range(1, 4)
    ), "phase offset must vary per batch element"

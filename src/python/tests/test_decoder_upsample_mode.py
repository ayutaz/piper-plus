"""H-1: upsampler の resize+conv 化 (``--upsample-mode``) の TDD テスト。

docs/design/zero-shot-v10b-quality-plan.md §3.1 H-1。v10b 帯域解剖の容疑序列 1 位
= transposed conv の checkerboard / tonal artifact への直撃レバー。

**なぜ学習なしで検証できるか**: Pons ら (arXiv:2010.14356) の中心的主張は
「transposed conv の tonal artifact は**初期化直後から存在**し学習後も残存する」。
従ってランダム初期化の decoder に白色 latent を流してコム物理量 (E-4) を測れば、
学習を一切せずに「格子由来コムが構造的に減ったか」を判定できる。plan §4.4 が
H-1/H-2 を「学習前後で分離可能」に分類している根拠がこれ。

**MACs 設計 (plan §3.1 H-1【算術】/ §4.3 の推論コスト gate)**:
    ConvTranspose1d(C_in, C_out, k, stride=u):  MACs = L_in · k · C_in · C_out
    nearest resize(×u) + Conv1d(C_in, C_out, k'): MACs = u · L_in · k' · C_in · C_out
同一 kernel (k'=k) では **MACs が u 倍** になるため、k' = k / u (= 16/4 = 4) と
縮小して MACs 中立に設計する。この算術は
``test_resize_mode_is_macs_neutral_by_construction`` が機械的に固定する。

default (``upsample_mode="transposed"``) は v10a-r2 と bit 互換 (state_dict /
出力とも)。

実測値 (2026-08-17、初期化直後 / 白色 latent / 3 seed):
    comb_excess_db  transposed 9.063 / 8.391 / 7.653 (mean 8.37)
                    resize     2.196 / 1.910 / 2.146 (mean 2.08)
    hf_autocorr@256 transposed 0.829 / 0.775 / 0.595
                    resize     0.591 / 0.590 / 0.519
参考: 学習済み v10a-r2 ep79 の実測は 4.1-4.7 dB (GT 0.65-0.76 dB) — 学習は
コムを部分的に補償するが除去はしない、という plan §1.1 A1 の観測と整合する。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import MBiSTFTGenerator  # noqa: E402


SR = 22050
# 白色 latent のフレーム数。fullband 長 = 96 * 256 = 24576 サンプル (1.11 秒)
# で comb_metrics の下限 0.5 秒を満たす。
N_LATENT_FRAMES = 96
_UPSAMPLE_RATES = (4, 4)
_UPSAMPLE_KERNELS = (16, 16)


def _make_generator(seed: int, **overrides) -> MBiSTFTGenerator:
    """本走と同一の decoder 構成 (upsample_initial_channel=256, resblock 2)。"""
    torch.manual_seed(seed)
    kwargs = dict(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=_UPSAMPLE_RATES,
        upsample_initial_channel=256,
        upsample_kernel_sizes=_UPSAMPLE_KERNELS,
    )
    kwargs.update(overrides)
    return MBiSTFTGenerator(**kwargs)


def _generate(gen: MBiSTFTGenerator, seed: int, frames: int = N_LATENT_FRAMES):
    gen.eval()
    gen.onnx_export_mode = True
    g = torch.Generator().manual_seed(seed + 7)
    x = torch.randn(1, 192, frames, generator=g)
    with torch.no_grad():
        return gen(x)


def _comb_metrics_of(wav: "torch.Tensor") -> dict:
    """E-4 と同一定義のコム物理量 (tests/ は isolation gate の scope 外)。"""
    from piper_train.tools.measure_comb_artifacts import comb_metrics

    y = wav.detach().reshape(-1).to(torch.float64).numpy()
    y = y / (np.sqrt((y**2).mean()) + 1e-9)
    m = comb_metrics(y, SR)
    assert m is not None
    return m


def _comb_at_init(mode: str, seed: int) -> dict:
    return _comb_metrics_of(_generate(_make_generator(seed, upsample_mode=mode), seed))


def _conv_macs(module: "torch.nn.Module", l_in: int, upsample: int) -> int:
    """ups 1 段の MACs (出力長基準で数える)。"""
    if isinstance(module, torch.nn.ConvTranspose1d):
        k = module.kernel_size[0]
        return l_in * k * module.in_channels * module.out_channels
    # resize + Conv1d: 内部の Conv1d を探す
    conv = next(m for m in module.modules() if isinstance(m, torch.nn.Conv1d))
    k = conv.kernel_size[0]
    return (l_in * upsample) * k * conv.in_channels * conv.out_channels


# ===========================================================================
# (i) 初期化直後のコム — H-1 の中心的主張
# ===========================================================================


@pytest.mark.unit
class TestResizeReducesCombAtInit:
    _SEEDS = (0, 1, 2)

    def test_resize_lowers_comb_excess_for_every_seed(self):
        """[第一原理 (Pons ら) + 現状実測 pin] 初期化直後のコム超過が全 seed で低下。

        transposed の格子由来トーンは初期化時点で存在する (文献) ため、学習を
        伴わない単変量比較でコム源の除去を実証できる。実測は seed ごとに
        5.5-6.9 dB の低下で、mode 間の分布は重ならない。
        """
        for seed in self._SEEDS:
            t = _comb_at_init("transposed", seed)["comb_excess_db"]
            r = _comb_at_init("resize", seed)["comb_excess_db"]
            assert r < t - 3.0, (
                f"seed={seed}: resize comb {r:.3f} dB is not clearly below "
                f"transposed {t:.3f} dB (expected >= 3 dB reduction; measured "
                f"5.5-6.9 dB)"
            )

    def test_resize_mean_comb_is_low_and_transposed_is_high(self):
        """[現状実測 pin] 3 seed 平均: transposed > 6 dB / resize < 4 dB。

        絶対水準の pin。plan §4.3 の事前登録 gate (< 1.5 dB) は学習後の
        目標であり、初期化直後の resize 2.08 dB は「gate の射程に入った」
        ことを意味するだけで達成の証明ではない (§4.4: Phase D smoke で判定)。
        """
        t = float(np.mean([_comb_at_init("transposed", s)["comb_excess_db"] for s in self._SEEDS]))
        r = float(np.mean([_comb_at_init("resize", s)["comb_excess_db"] for s in self._SEEDS]))
        assert t > 6.0, f"transposed mean comb {t:.3f} dB (measured 8.37)"
        assert r < 4.0, f"resize mean comb {r:.3f} dB (measured 2.08)"


# ===========================================================================
# (ii) 形状互換 / MACs / 構造
# ===========================================================================


@pytest.mark.unit
class TestResizeModeStructure:
    def test_output_shape_matches_transposed(self):
        """(ii) resize モードの出力形状は transposed と同一 (256x upsample 不変)。"""
        y_t = _generate(_make_generator(0, upsample_mode="transposed"), 0, frames=32)
        y_r = _generate(_make_generator(0, upsample_mode="resize"), 0, frames=32)
        assert y_t.shape == (1, 1, 32 * 256)
        assert y_r.shape == y_t.shape

    def test_training_mode_returns_fullband_and_subbands(self):
        """resize モードでも (fullband, subbands) の 2-tuple を返す (学習経路)。"""
        gen = _make_generator(0, upsample_mode="resize")
        gen.eval()
        x = torch.randn(2, 192, 32)
        with torch.no_grad():
            fullband, subbands = gen(x)
        assert fullband.shape == (2, 1, 32 * 256)
        assert subbands.shape == (2, 4, 32 * 64)

    def test_resize_mode_is_macs_neutral_by_construction(self):
        """[第一原理] k' = k/u により ups の MACs が transposed と一致する。

        plan §3.1 H-1【算術】の「同一 kernel だと MACs 約 4 倍/段」を構造で
        封じたことの機械的固定。ここが崩れると §4.3 の CPU レイテンシ gate
        (+10% 以内) を設計段階で落とす。
        """
        gen_t = _make_generator(0, upsample_mode="transposed")
        gen_r = _make_generator(0, upsample_mode="resize")
        l_in = 64
        for i, u in enumerate(_UPSAMPLE_RATES):
            macs_t = _conv_macs(gen_t.ups[i], l_in, u)
            macs_r = _conv_macs(gen_r.ups[i], l_in, u)
            assert macs_r == macs_t, (
                f"ups[{i}]: resize MACs {macs_r} != transposed MACs {macs_t}"
            )
            l_in *= u

    def test_resize_conv_kernel_is_shrunk(self):
        """resize の Conv1d kernel は k/u (= 4)、stride なし。"""
        gen = _make_generator(0, upsample_mode="resize")
        for i, (u, k) in enumerate(zip(_UPSAMPLE_RATES, _UPSAMPLE_KERNELS, strict=True)):
            conv = next(m for m in gen.ups[i].modules() if isinstance(m, torch.nn.Conv1d))
            assert conv.kernel_size == (k // u,)
            assert conv.stride == (1,)

    def test_resize_conv_is_lowpass_initialised(self):
        """[第一原理] 初期 kernel の周波数応答が lowpass (interpolation filter)。

        resize+conv の反 checkerboard 性は構造 (stride なし = 位相ごとの重み
        非対称が消える) から来るが、初期値も ×u 補間フィルタにしておくことで
        初期の image 抑圧を確保する。ここでは kernel 軸の応答が Nyquist で
        DC より 6 dB 以上低いことを固定する (箱型 4-tap の理論値は -inf、
        乱数摂動込みの実測で十分なマージンがある)。
        """
        gen = _make_generator(0, upsample_mode="resize")
        for i in range(len(_UPSAMPLE_RATES)):
            conv = next(m for m in gen.ups[i].modules() if isinstance(m, torch.nn.Conv1d))
            w = conv.weight.detach()  # [C_out, C_in, k]
            # チャネルを跨いだ平均応答ではなく、各フィルタの応答の平均パワー
            resp = torch.fft.rfft(w, n=64, dim=-1).abs() ** 2
            dc = float(resp[..., 0].mean())
            nyq = float(resp[..., -1].mean())
            assert dc > 0.0
            assert 10 * np.log10(nyq / dc) < -6.0, (
                f"ups[{i}] initial kernel is not lowpass: Nyquist/DC = "
                f"{10 * np.log10(nyq / dc):.2f} dB"
            )


# ===========================================================================
# (iv) 後方互換 — default は v10a ckpt をロードできる
# ===========================================================================


@pytest.mark.unit
class TestUpsampleModeBackwardCompat:
    def test_default_is_transposed(self):
        gen = _make_generator(0)
        assert gen.upsample_mode == "transposed"
        for up in gen.ups:
            assert isinstance(up, torch.nn.ConvTranspose1d)

    def test_default_state_dict_is_unchanged(self):
        """default 構築の ups は ConvTranspose1d の weight 形状 (C_in, C_out, k)。

        v10a ckpt (transposed) が strict load できる条件そのもの。resize 実装の
        追加で default 側の state_dict が 1 key も変わらないことを固定する。
        """
        gen = _make_generator(0)
        sd = gen.state_dict()
        assert sd["ups.0.weight_v"].shape == (256, 128, 16)
        assert sd["ups.1.weight_v"].shape == (128, 64, 16)
        fresh = _make_generator(1)
        fresh.load_state_dict(sd)  # strict=True
        assert torch.equal(fresh.state_dict()["ups.0.weight_v"], sd["ups.0.weight_v"])

    def test_explicit_transposed_is_bit_identical_to_default(self):
        """upsample_mode="transposed" の明示指定は default と bit 一致。"""
        y_default = _generate(_make_generator(3), 3, frames=32)
        y_explicit = _generate(_make_generator(3, upsample_mode="transposed"), 3, frames=32)
        assert torch.equal(y_default, y_explicit)

    def test_resize_state_dict_mismatch_is_loud(self):
        """transposed ckpt を resize モデルに load すると明示的に失敗する。

        silent な形状ズレでの誤 resume を防ぐ (weight shape が
        (C_in, C_out, 16) vs (C_out, C_in, 4) で必ず衝突する)。
        """
        sd = _make_generator(0).state_dict()
        gen_r = _make_generator(0, upsample_mode="resize")
        with pytest.raises(RuntimeError):
            gen_r.load_state_dict(sd)

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError, match="upsample_mode"):
            _make_generator(0, upsample_mode="bilinear-ish")

    def test_remove_weight_norm_works_in_resize_mode(self):
        """ONNX export 前処理 (remove_weight_norm) が resize でも通る。"""
        gen = _make_generator(0, upsample_mode="resize")
        gen.eval()
        gen.remove_weight_norm()
        gen.onnx_export_mode = True
        with torch.no_grad():
            out = gen(torch.randn(1, 192, 16))
        assert out.shape == (1, 1, 16 * 256)


# ===========================================================================
# (iii) ONNX export
# ===========================================================================


@pytest.mark.unit
def test_resize_mode_onnx_export_and_runtime_parity():
    """(iii) resize decoder が opset 15 で export でき、ORT 出力が torch と一致。

    F.interpolate(nearest) → Resize、ConstantPad1d → Pad、Conv1d → Conv は
    いずれも ONNX 標準 op (plan §3.1 H-1「両方 ONNX 標準 op」)。
    """
    ort = pytest.importorskip("onnxruntime")

    gen = _make_generator(0, upsample_mode="resize")
    gen.eval()
    gen.remove_weight_norm()
    gen.onnx_export_mode = True
    x = torch.randn(1, 192, 16)
    with torch.no_grad():
        expected = gen(x)

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
        onnx_path = Path(f.name)
    try:
        torch.onnx.export(
            gen,
            (x,),
            str(onnx_path),
            opset_version=15,
            input_names=["z"],
            output_names=["audio"],
            dynamic_axes={"z": {0: "batch", 2: "frames"}, "audio": {0: "batch", 2: "time"}},
            dynamo=False,
        )
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        got = sess.run(None, {"z": x.numpy()})[0]
        assert got.shape == tuple(expected.shape)
        np.testing.assert_allclose(got, expected.numpy(), rtol=1e-3, atol=1e-4)
    finally:
        onnx_path.unlink(missing_ok=True)


@pytest.mark.unit
def test_resize_mode_exports_through_production_infer_path():
    """(iii) 本番 export 経路 (``export_onnx.build_infer_forward``) で export 可能。

    decoder 単体 export では通っても、``set_export_mode`` +
    ``SynthesizerTrn.infer`` を通る本番 graph で落ちれば意味がないため、
    production の組み立て関数をそのまま使って固定する。
    """
    pytest.importorskip("onnxruntime")

    from piper_train.export_onnx import build_infer_forward, set_export_mode
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(0)
    model = SynthesizerTrn(
        n_vocab=97,
        spec_channels=513,
        segment_size=32,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=_UPSAMPLE_RATES,
        upsample_initial_channel=256,
        upsample_kernel_sizes=_UPSAMPLE_KERNELS,
        n_speakers=1,
        n_languages=2,
        gin_channels=512,
        use_sdp=True,
        prosody_dim=0,
        upsample_mode="resize",
    )
    model.eval()
    with torch.no_grad():
        model.dec.remove_weight_norm()
    set_export_mode(model, True)
    model.forward = build_infer_forward(model, stochastic=False)

    n_phonemes = 10
    dummy = (
        torch.randint(0, 97, (1, n_phonemes), dtype=torch.long),
        torch.LongTensor([n_phonemes]),
        torch.FloatTensor([0.4, 1.0, 0.5]),
        torch.LongTensor([0]),
        torch.LongTensor([0]),
    )

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
        onnx_path = Path(f.name)
    try:
        torch.onnx.export(
            model,
            dummy,
            str(onnx_path),
            opset_version=15,
            input_names=["input", "input_lengths", "scales", "sid", "lid"],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "sid": {0: "batch_size"},
                "lid": {0: "batch_size"},
                "output": {0: "batch_size", 2: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            dynamo=False,
        )
        assert onnx_path.stat().st_size > 0
    finally:
        onnx_path.unlink(missing_ok=True)

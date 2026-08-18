"""S-2a / S-2c: MBiSTFTGenerator への F0 注入の TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §2.1 (S-2a: frame 格子 concat) /
§2.3 (S-2c: head 格子 harmonic 位相テンプレート) / §6.1 採否表。

固定する契約:

* **default off = v10a-r2 bit 互換**: ``use_f0_path=False`` では F0 関連の
  module が 1 つも作られず、state_dict も forward 出力も従来と同一。
* **zero-init = 学習開始時は F0 非依存**: ``f0_feat`` / ``head_proj`` を
  zero-init するため、初期化直後の出力は F0 の値に依存しない。設計 §6.2 の
  「退避経路: smoke 失敗時にテンプレート経路を切るのが bit レベルで安全」を
  構造的に担保する。
* **zero-init でも学習は進む**: 出力が 0 でも入力側重みの勾配は非ゼロ
  (``dL/dW = dL/dy · x^T``、``dL/dy`` は下流 conv の重み由来で非ゼロ)。
  「zero-init したから死んでいる」という誤解を数値で潰す。
* **trim 順序 (§6.6) が構造に効く**: head_ch / f0_ch / M の縮退が実際に
  パラメータ数を減らす。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import MBiSTFTGenerator  # noqa: E402


BASE_KWARGS = dict(
    initial_channel=192,
    resblock="2",
    resblock_kernel_sizes=(3, 5, 7),
    resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
    upsample_rates=(4, 4),
    upsample_initial_channel=256,
    upsample_kernel_sizes=(16, 16),
    gin_channels=512,
)

N_FRAMES = 24


def _make(seed: int = 0, **overrides) -> MBiSTFTGenerator:
    torch.manual_seed(seed)
    kwargs = dict(BASE_KWARGS)
    kwargs.update(overrides)
    gen = MBiSTFTGenerator(**kwargs)
    gen.eval()
    return gen


def _inputs(batch: int = 2, frames: int = N_FRAMES, seed: int = 3):
    g = torch.Generator().manual_seed(seed)
    z = torch.randn(batch, 192, frames, generator=g)
    spk = torch.randn(batch, 512, 1, generator=g)
    return z, spk


def _f0(batch: int = 2, frames: int = N_FRAMES, hz: float = 220.0):
    f0 = torch.full((batch, 1, frames), hz)
    f0[:, :, : frames // 4] = 0.0  # 無声区間を含める
    return f0


def test_default_off_creates_no_f0_modules_and_keeps_state_dict():
    """default (off) では F0 module が存在せず、state_dict キーも増えない。"""
    off = _make()
    assert off.use_f0_path is False
    assert not hasattr(off, "f0_feat")
    assert not hasattr(off, "head_proj")
    assert not hasattr(off, "phase_template")
    keys = set(off.state_dict())
    assert not any("f0" in k or "head_proj" in k or "template" in k for k in keys)


def test_default_off_forward_is_unchanged_and_ignores_f0():
    """off の forward は f0 引数を受け取っても従来出力を返す (後方互換)。"""
    gen = _make()
    z, spk = _inputs()
    with torch.no_grad():
        a, a_mb = gen(z, spk)
        b, b_mb = gen(z, spk, f0=_f0())
    torch.testing.assert_close(a, b)
    torch.testing.assert_close(a_mb, b_mb)


def test_f0_path_changes_conv_channel_counts_as_designed():
    """S-2a は conv_pre 入力を、S-2c は subband_conv_post 入力を広げる。"""
    off = _make()
    on = _make(use_f0_path=True, f0_feat_channels=8, f0_head_channels=8)

    assert off.conv_pre.in_channels == 192
    assert on.conv_pre.in_channels == 192 + 8
    assert off.subband_conv_post.in_channels == 64
    assert on.subband_conv_post.in_channels == 64 + 8
    # 出力側の契約は不変 (4 subbands × (n_fft + 2))
    assert on.subband_conv_post.out_channels == off.subband_conv_post.out_channels


def test_f0_path_output_length_matches_baseline():
    """注入しても波形長 (256x upsample) は変わらない。"""
    off = _make()
    on = _make(use_f0_path=True)
    z, spk = _inputs()
    with torch.no_grad():
        base, _ = off(z, spk)
        wav, sub = on(z, spk, f0=_f0())
    assert wav.shape == base.shape
    assert sub.shape[1] == 4


def test_zero_init_makes_output_independent_of_f0_at_initialisation():
    """初期化直後は F0 を変えても出力が変わらない (zero-init 互換の本体)。"""
    gen = _make(use_f0_path=True)
    z, spk = _inputs()
    with torch.no_grad():
        low, _ = gen(z, spk, f0=_f0(hz=110.0))
        high, _ = gen(z, spk, f0=_f0(hz=440.0))
        silent, _ = gen(z, spk, f0=torch.zeros(2, 1, N_FRAMES))
    torch.testing.assert_close(low, high)
    torch.testing.assert_close(low, silent)


def test_zero_init_projections_still_receive_gradient():
    """zero-init は「死んだ枝」ではない — 1 step の backward で勾配が立つ。"""
    gen = _make(use_f0_path=True)
    gen.train()
    z, spk = _inputs()
    wav, _ = gen(z, spk, f0=_f0())
    wav.pow(2).mean().backward()

    for name, param in (
        ("f0_feat.weight", gen.f0_feat.weight),
        ("head_proj.weight", gen.head_proj.weight),
    ):
        assert param.grad is not None, f"{name} has no grad"
        assert float(param.grad.abs().max()) > 0.0, f"{name} grad is all zero"


def test_f0_path_requires_f0_and_fails_fast():
    """有効化したのに f0 を渡さない構成ミスは黙って劣化させず即エラーにする。"""
    gen = _make(use_f0_path=True)
    z, spk = _inputs()
    with pytest.raises(ValueError, match="f0"):
        gen(z, spk)


def test_trim_knobs_reduce_parameter_count():
    """§6.6 の trim 順序 (head_ch → f0_ch → M) が実際にパラメータを減らす。"""
    full = _make(use_f0_path=True, f0_feat_channels=8, f0_head_channels=8, f0_harmonics=8)
    trimmed = _make(
        use_f0_path=True, f0_feat_channels=4, f0_head_channels=4, f0_harmonics=4
    )
    n_full = sum(p.numel() for p in full.parameters())
    n_trim = sum(p.numel() for p in trimmed.parameters())
    assert n_trim < n_full
    assert trimmed.head_proj.in_channels == 2 * 4 + 2
    assert full.head_proj.in_channels == 2 * 8 + 2


def test_head_template_runs_on_the_head_grid():
    """テンプレートは frame 格子ではなく head 格子 (×16) の長さを返す。"""
    gen = _make(use_f0_path=True)
    with torch.no_grad():
        tmpl = gen.phase_template(_f0())
    assert tmpl.shape[-1] == N_FRAMES * 16
    assert gen.phase_template.frame_rate == pytest.approx(22050 * 16 / 256)


def test_f0_path_is_deterministic_in_eval_mode():
    """eval では位相オフセット乱数が入らない → 同一入力で bit 一致。"""
    gen = _make(use_f0_path=True)
    # zero-init を外して F0 経路が実際に効く状態にする
    with torch.no_grad():
        gen.head_proj.weight.normal_(0.0, 0.1)
        gen.f0_feat.weight.normal_(0.0, 0.1)
    z, spk = _inputs()
    with torch.no_grad():
        a, _ = gen(z, spk, f0=_f0())
        b, _ = gen(z, spk, f0=_f0())
    torch.testing.assert_close(a, b)


def test_trained_f0_path_actually_changes_the_waveform():
    """zero-init を外せば F0 が出力を動かす (経路が繋がっている証明)。"""
    gen = _make(use_f0_path=True)
    with torch.no_grad():
        gen.head_proj.weight.normal_(0.0, 0.1)
        gen.f0_feat.weight.normal_(0.0, 0.1)
    z, spk = _inputs()
    with torch.no_grad():
        low, _ = gen(z, spk, f0=_f0(hz=110.0))
        high, _ = gen(z, spk, f0=_f0(hz=440.0))
    assert not torch.allclose(low, high)

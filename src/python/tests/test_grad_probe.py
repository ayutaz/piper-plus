"""Tests for piper_train.vits.grad_probe (per-loss gradient-norm probe, A-1c).

コアの ``compute_grad_probe`` は Lightning 非依存の純関数なので、
小さな Linear 群の toy graph で以下を検証する:

- 全 loss 成分 × 全 probe パラメータのノルムが返ること
- probe が ``.grad`` に蓄積せず、probe 後の combined backward が正常に走ること
- requires_grad しないダミー loss が混じっても落ちないこと (ゼロノルム記録)
- probe パラメータに依存しない loss は allow_unused で 0.0 になること
- spk / スペクトル系合計 の ratio が 1 スカラーで返ること
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.grad_probe import (  # noqa: E402
    METRIC_PREFIX,
    collect_probe_params,
    compute_grad_probe,
)


def _toy_graph():
    """front → back の 2 段 Linear で loss 成分を作る。

    - "mel"  : back の出力に依存 → front / back 両方に勾配
    - "spk"  : front の出力 (中間 h) のみに依存 → back の勾配は None (unused)
    """
    torch.manual_seed(1234)
    front = torch.nn.Linear(4, 4)
    back = torch.nn.Linear(4, 4)
    x = torch.randn(3, 4)
    h = front(x)
    y = back(h)
    losses = {
        "mel": (y**2).mean(),
        "spk": h.abs().mean(),
    }
    probe_params = {"front_w": front.weight, "back_w": back.weight}
    return losses, probe_params, (front, back)


@pytest.mark.unit
def test_returns_norms_for_all_components():
    """全 loss 成分 × 全 probe パラメータのノルム + total が返る。"""
    losses, probe_params, _ = _toy_graph()
    results = compute_grad_probe(losses, probe_params)

    for loss_name in losses:
        for param_name in probe_params:
            key = f"{METRIC_PREFIX}/{loss_name}/{param_name}"
            assert key in results
            assert isinstance(results[key], float)
        assert f"{METRIC_PREFIX}/{loss_name}/total" in results

    # mel は front / back 両方に勾配を持つ
    assert results[f"{METRIC_PREFIX}/mel/front_w"] > 0.0
    assert results[f"{METRIC_PREFIX}/mel/back_w"] > 0.0
    # spk は front のみに依存 → back は allow_unused (None) → 0.0
    assert results[f"{METRIC_PREFIX}/spk/front_w"] > 0.0
    assert results[f"{METRIC_PREFIX}/spk/back_w"] == 0.0


@pytest.mark.unit
def test_backward_still_works_after_probe():
    """probe は .grad に蓄積せず、その後の combined backward が正常に走る。"""
    losses, probe_params, (front, back) = _toy_graph()
    compute_grad_probe(losses, probe_params)

    # probe は torch.autograd.grad を使うので .grad は未蓄積のまま
    assert front.weight.grad is None
    assert back.weight.grad is None

    # combined backward (本番では manual_backward(loss_gen_all) に相当)
    loss_all = losses["mel"] + losses["spk"]
    loss_all.backward()

    assert front.weight.grad is not None
    assert torch.isfinite(front.weight.grad).all()
    assert back.weight.grad is not None
    assert torch.isfinite(back.weight.grad).all()


@pytest.mark.unit
def test_no_grad_dummy_loss_does_not_crash():
    """requires_grad しないダミー loss はゼロノルムとして記録され、落ちない。

    実運用の対応物: ONNX no-grad SCL fallback の loss_spk、NaN マスクで
    定数 0 になった dino_loss など。
    """
    losses, probe_params, _ = _toy_graph()
    losses["dummy"] = torch.tensor(1.0)  # requires_grad=False
    assert not losses["dummy"].requires_grad

    results = compute_grad_probe(losses, probe_params)

    for param_name in probe_params:
        assert results[f"{METRIC_PREFIX}/dummy/{param_name}"] == 0.0
    assert results[f"{METRIC_PREFIX}/dummy/total"] == 0.0
    # 他の成分は通常どおり測定される
    assert results[f"{METRIC_PREFIX}/mel/front_w"] > 0.0


@pytest.mark.unit
def test_ratio_spk_to_spectral():
    """spk / スペクトル系合計 の ratio が 1 スカラーで返る。"""
    losses, probe_params, _ = _toy_graph()
    results = compute_grad_probe(losses, probe_params)

    ratio_key = f"{METRIC_PREFIX}/ratio_spk_to_spectral"
    assert ratio_key in results

    spk_total = results[f"{METRIC_PREFIX}/spk/total"]
    # toy graph のスペクトル系は mel のみ (sub_stft / full_stft / mrd 不在)
    spectral_total = results[f"{METRIC_PREFIX}/mel/total"]
    assert results[ratio_key] == pytest.approx(spk_total / spectral_total)


@pytest.mark.unit
def test_ratio_absent_without_spk_loss():
    """spk が losses に無い場合は ratio を出さない。"""
    losses, probe_params, _ = _toy_graph()
    del losses["spk"]
    results = compute_grad_probe(losses, probe_params)
    assert f"{METRIC_PREFIX}/ratio_spk_to_spectral" not in results


@pytest.mark.unit
def test_empty_probe_params_returns_empty():
    """probe パラメータが空なら空 dict (probe 実質無効)。"""
    losses, _, _ = _toy_graph()
    assert compute_grad_probe(losses, {}) == {}


@pytest.mark.unit
def test_bf16_loss_norm_recorded_as_float32():
    """bf16 graph でもノルムは float32 に cast して有限値で記録される。"""
    w = torch.nn.Parameter(torch.randn(4, 4, dtype=torch.bfloat16))
    loss = (w * 2).sum()
    results = compute_grad_probe({"mel": loss}, {"w": w})
    val = results[f"{METRIC_PREFIX}/mel/w"]
    assert isinstance(val, float)
    assert val > 0.0
    import math

    assert math.isfinite(val)


def _tiny_synthesizer(n_speakers=4):
    """probe 対象構造 (spk_proj / dec / enc_p / flow) を持つ最小モデル。"""
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:  # pragma: no cover - env without training deps
        pytest.skip(f"Training dependencies not available: {e}")

    return SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=32,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=1,
        kernel_size=3,
        p_dropout=0.0,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=64,
        upsample_kernel_sizes=(16, 16),
        n_speakers=n_speakers,
        gin_channels=64,
        use_sdp=True,
        prosody_dim=16,
    )


@pytest.mark.unit
def test_collect_probe_params_on_synthesizer():
    """実モデル (SynthesizerTrn) から 4 点の leaf パラメータを解決できる。"""
    model = _tiny_synthesizer()
    params = collect_probe_params(model)

    assert set(params.keys()) == {
        "spk_proj_out",
        "dec_pre",
        "enc_p_proj",
        "flow0_pre",
    }
    for name, p in params.items():
        # autograd.grad の対象にできる leaf Parameter であること
        # (weight_norm 適用層は再計算される非 leaf .weight ではなく
        # weight_v / parametrizations 側の leaf が解決される)
        assert p.is_leaf, name
        assert p.requires_grad, name

    # spk_proj_out は最終 Linear (gin→gin) の weight
    assert params["spk_proj_out"].shape == (64, 64)


@pytest.mark.unit
def test_collect_probe_params_skips_frozen():
    """freeze 済み (requires_grad=False) のパラメータは除外される。

    実運用の対応物: --train-decoder-only / --freeze-dp 等。
    """
    model = _tiny_synthesizer()
    for p in model.enc_p.parameters():
        p.requires_grad_(False)
    params = collect_probe_params(model)
    assert "enc_p_proj" not in params
    assert "dec_pre" in params


@pytest.mark.unit
def test_collect_probe_params_single_speaker_no_spk_proj():
    """single-speaker (spk_proj なし) でも他 3 点は収集できる。"""
    model = _tiny_synthesizer(n_speakers=1)
    params = collect_probe_params(model)
    assert "spk_proj_out" not in params
    assert {"dec_pre", "enc_p_proj", "flow0_pre"} <= set(params.keys())

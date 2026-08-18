"""S-2 の SynthesizerTrn 配線 (predictor → prior 残差 → decoder) の TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §4.1 (置き場所) / §4.2 (話者条件) /
§4.4 (teacher forcing) / §4.5 (prior 残差)。

固定する契約:

* **default off = v10a-r2 bit 互換**: F0 module が作られず forward も従来どおり。
* **予測器の入力は展開済み enc_p hidden** — posterior ``z`` ではない
  (推論時に存在しない情報を学習で使わない = leak 防止)。
* **話者勾配の既定経路**: F0 loss の勾配は ``spk_proj_f0`` に集約され、
  ``spk_proj`` 本体には届かない (``--f0-spk-grad`` で opt-in)。
* **teacher forcing**: p=0 で GT、p=1 で予測。予測は必ず detach されて
  decoder に入る (mel/GAN 勾配が予測器を汚さない)。
* **S-2r prior 残差は zero-init**: 導入直後は m_p が bit 一致。
"""

from __future__ import annotations

import math

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.models import SynthesizerTrn  # noqa: E402


SEGMENT_FRAMES = 32
HOP = 256

BASE = dict(
    n_vocab=40,
    spec_channels=513,
    segment_size=SEGMENT_FRAMES,
    inter_channels=192,
    hidden_channels=192,
    filter_channels=256,
    n_heads=2,
    n_layers=2,
    kernel_size=3,
    p_dropout=0.0,
    resblock="2",
    resblock_kernel_sizes=(3, 5, 7),
    resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
    upsample_rates=(4, 4),
    upsample_initial_channel=256,
    upsample_kernel_sizes=(16, 16),
    n_speakers=4,
    gin_channels=512,
    prosody_dim=0,
)


def _model(seed: int = 0, **overrides) -> SynthesizerTrn:
    torch.manual_seed(seed)
    kwargs = dict(BASE)
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


def _batch(batch: int = 2, phonemes: int = 12, frames: int = 64, seed: int = 1):
    g = torch.Generator().manual_seed(seed)
    x = torch.randint(1, 40, (batch, phonemes), generator=g)
    x_lengths = torch.full((batch,), phonemes, dtype=torch.long)
    spec = torch.randn(batch, 513, frames, generator=g).abs()
    spec_lengths = torch.full((batch,), frames, dtype=torch.long)
    emb = torch.nn.functional.normalize(torch.randn(batch, 192, generator=g), dim=-1)
    return x, x_lengths, spec, spec_lengths, emb


def _f0(batch: int = 2, frames: int = 64, hz: float = 210.0):
    f0 = torch.full((batch, 1, frames), hz)
    f0[:, :, ::5] = 0.0  # 無声フレームを散らす
    return f0


def test_default_off_has_no_f0_modules():
    model = _model()
    assert model.use_f0_path is False
    assert not hasattr(model, "f0_predictor")
    assert not hasattr(model, "spk_proj_f0")
    assert not hasattr(model, "f0_prior_res")
    assert not any("f0" in k for k in model.state_dict())


def test_default_off_forward_ignores_f0_arguments():
    model = _model()
    model.train()
    args = _batch()
    torch.manual_seed(7)
    out_a = model(*args[:4], None, speaker_embeddings=args[4])
    torch.manual_seed(7)
    out_b = model(
        *args[:4], None, speaker_embeddings=args[4], f0=_f0(), f0_pred_prob=1.0
    )
    torch.testing.assert_close(out_a.waveform, out_b.waveform)
    assert out_a.f0_pred is None and out_a.f0_decoder is None


def test_forward_returns_predictions_and_sliced_decoder_f0():
    model = _model(use_f0_path=True)
    model.train()
    x, x_lengths, spec, spec_lengths, emb = _batch()
    out = model(
        x, x_lengths, spec, spec_lengths, None, speaker_embeddings=emb, f0=_f0()
    )
    log_f0, vuv_logit = out.f0_pred
    assert log_f0.shape == (2, 1, 64)
    assert vuv_logit.shape == (2, 1, 64)
    assert out.f0_decoder.shape == (2, 1, SEGMENT_FRAMES)


def test_teacher_forcing_selects_gt_or_prediction():
    model = _model(use_f0_path=True)
    model.train()
    x, x_lengths, spec, spec_lengths, emb = _batch()
    f0_gt = _f0()

    torch.manual_seed(11)
    gt_only = model(
        x, x_lengths, spec, spec_lengths, None,
        speaker_embeddings=emb, f0=f0_gt, f0_pred_prob=0.0,
    )
    torch.manual_seed(11)
    pred_only = model(
        x, x_lengths, spec, spec_lengths, None,
        speaker_embeddings=emb, f0=f0_gt, f0_pred_prob=1.0,
    )

    gt_slice = torch.stack(
        [
            f0_gt[i, :, s : s + SEGMENT_FRAMES]
            for i, s in enumerate(gt_only.ids_slice.tolist())
        ]
    )
    torch.testing.assert_close(gt_only.f0_decoder, gt_slice)
    assert not torch.allclose(pred_only.f0_decoder, gt_slice)


def test_decoder_f0_is_detached_from_the_predictor():
    """予測 F0 は decoder に渡す時点で detach される (§4.3 の FastPitch 標準)。"""
    model = _model(use_f0_path=True)
    model.train()
    x, x_lengths, spec, spec_lengths, emb = _batch()
    out = model(
        x, x_lengths, spec, spec_lengths, None,
        speaker_embeddings=emb, f0=_f0(), f0_pred_prob=1.0,
    )
    assert out.f0_decoder.requires_grad is False


def _grad_sum(module) -> float:
    return sum(
        float(p.grad.abs().sum())
        for p in module.parameters()
        if p.grad is not None
    )


def _backward_f0_head(model):
    x, x_lengths, spec, spec_lengths, emb = _batch()
    out = model(
        x, x_lengths, spec, spec_lengths, None, speaker_embeddings=emb, f0=_f0()
    )
    model.zero_grad(set_to_none=True)
    out.f0_pred[0].pow(2).mean().backward()


def test_f0_loss_gradient_does_not_reach_spk_proj_or_enc_p_by_default():
    """default は spk_proj / enc_p を保護し、勾配は F0 予測器側に集約される。

    ここが緩いと「F0 loss → predictor → x_frame → enc_p → g → spk_proj」の
    裏口から本体に勾配が届き、専用ヘッド (spk_proj_f0) を作った意味が消える。
    """
    model = _model(use_f0_path=True)
    model.train()
    _backward_f0_head(model)

    assert _grad_sum(model.spk_proj) == 0.0
    assert _grad_sum(model.enc_p) == 0.0
    assert _grad_sum(model.spk_proj_f0) > 0.0
    assert _grad_sum(model.f0_predictor) > 0.0


def test_f0_spk_grad_opt_in_routes_gradient_into_spk_proj():
    model = _model(use_f0_path=True, f0_spk_grad=True)
    model.train()
    _backward_f0_head(model)
    assert _grad_sum(model.spk_proj) > 0.0
    # 入力側は依然 detach されているので enc_p は保護されたまま
    assert _grad_sum(model.enc_p) == 0.0


def test_attaching_predictor_input_routes_gradient_into_enc_p():
    model = _model(use_f0_path=True, f0_detach_input=False)
    model.train()
    _backward_f0_head(model)
    assert _grad_sum(model.enc_p) > 0.0


def test_prior_residual_is_zero_init_and_wired_to_kl_latents():
    """S-2r は zero-init なので導入直後の m_p は残差なしと一致する。"""
    with_res = _model(use_f0_path=True, f0_prior_residual=True)
    without = _model(use_f0_path=True, f0_prior_residual=False)
    without.load_state_dict(
        {k: v for k, v in with_res.state_dict().items() if "f0_prior_res" not in k}
    )
    for m in (with_res, without):
        m.train()

    x, x_lengths, spec, spec_lengths, emb = _batch()
    torch.manual_seed(5)
    a = with_res(
        x, x_lengths, spec, spec_lengths, None, speaker_embeddings=emb, f0=_f0()
    )
    torch.manual_seed(5)
    b = without(
        x, x_lengths, spec, spec_lengths, None, speaker_embeddings=emb, f0=_f0()
    )
    torch.testing.assert_close(a.latents[2], b.latents[2])

    # zero-init でも勾配は立つ (経路が死んでいない)
    with_res.zero_grad(set_to_none=True)
    a.latents[2].pow(2).mean().backward()
    assert float(with_res.f0_prior_res.weight.grad.abs().max()) > 0.0


def test_prior_residual_changes_m_p_once_trained():
    model = _model(use_f0_path=True, f0_prior_residual=True)
    model.train()
    with torch.no_grad():
        model.f0_prior_res.weight.normal_(0.0, 0.1)
    x, x_lengths, spec, spec_lengths, emb = _batch()
    torch.manual_seed(5)
    trained = model(
        x, x_lengths, spec, spec_lengths, None, speaker_embeddings=emb, f0=_f0()
    )
    with torch.no_grad():
        model.f0_prior_res.weight.zero_()
    torch.manual_seed(5)
    zeroed = model(
        x, x_lengths, spec, spec_lengths, None, speaker_embeddings=emb, f0=_f0()
    )
    assert not torch.allclose(trained.latents[2], zeroed.latents[2])


def test_infer_runs_without_ground_truth_f0():
    """推論経路は GT F0 を必要としない (単一 graph で完結する条件)。"""
    model = _model(use_f0_path=True)
    model.eval()
    x = torch.randint(1, 40, (1, 10))
    x_lengths = torch.tensor([10])
    emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
    with torch.no_grad():
        out = model.infer(x, x_lengths, speaker_embeddings=emb)
    assert out.audio.dim() == 3
    assert torch.isfinite(out.audio).all()


def test_infer_f0_scale_shifts_the_commanded_pitch():
    """ablation 用 ``f0_scale`` が decoder に渡る F0 を実際に倍率変更する。

    (合成音の実測 F0 がどれだけ追従するかは Phase D の go/no-go。ここでは
    「指令値が確かに変わる」配線だけを固定する。)
    """
    model = _model(use_f0_path=True)
    model.eval()
    log_f0 = torch.full((1, 1, 4), math.log(200.0))
    vuv_logit = torch.full((1, 1, 4), 5.0)
    base = model._predicted_f0_hz(log_f0, vuv_logit)
    up = model._predicted_f0_hz(log_f0, vuv_logit, f0_scale=2.0 ** (2 / 12))
    torch.testing.assert_close(up, base * 2.0 ** (2 / 12))


def test_predicted_f0_is_zero_on_unvoiced_and_clamped_on_outliers():
    model = _model(use_f0_path=True)
    log_f0 = torch.tensor([[[math.log(200.0), 50.0, -50.0]]])
    vuv_logit = torch.tensor([[[5.0, 5.0, -5.0]]])
    f0 = model._predicted_f0_hz(log_f0, vuv_logit)
    assert float(f0[0, 0, 0]) == pytest.approx(200.0, rel=1e-4)
    assert float(f0[0, 0, 1]) == pytest.approx(1100.0, rel=1e-4)  # clamp 上限
    assert float(f0[0, 0, 2]) == 0.0  # 無声


def test_voice_conversion_rejects_f0_models_explicitly():
    model = _model(use_f0_path=True)
    with pytest.raises(NotImplementedError, match="use_f0_path"):
        model.voice_conversion(
            torch.randn(1, 513, 20),
            torch.tensor([20]),
            speaker_embeddings_src=torch.randn(1, 192),
            speaker_embeddings_tgt=torch.randn(1, 192),
        )

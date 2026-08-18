"""S-2 の学習ループ配線 (VitsModel.training_step_g) の統合テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §4.3 (loss) / §4.4 (teacher forcing)。

ここまでの unit テストは部品ごとの契約を固定しているが、「CLI hparam →
VitsModel → SynthesizerTrn → decoder → loss」の 1 本が実際に通るかは
step を 1 回回さないと分からない。特に次の 2 つは配線ミスが起きやすい:

* **F0 キャッシュ欠落時の fail-fast**: 黙って S-2 なしで 1 週間走るほうが、
  起動時に落ちるより遥かに高くつく。
* **teacher forcing 確率が epoch から決まる**こと (hparam が predictor まで
  届いているか)。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.dataset import Batch  # noqa: E402
from piper_train.vits.lightning import VitsModel  # noqa: E402


N_FRAMES = 48
N_PHONEMES = 10
BATCH = 2

_HPARAMS = dict(
    num_symbols=40,
    num_speakers=4,
    num_languages=1,
    dataset=None,
    resblock="2",
    resblock_kernel_sizes=(3, 5, 7),
    resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
    upsample_rates=(4, 4),
    upsample_initial_channel=256,
    upsample_kernel_sizes=(16, 16),
    filter_channels=256,
    n_layers=2,
    segment_size=8192,
    prosody_dim=0,
    gin_channels=512,
    use_wavlm_discriminator=False,
    c_dino=0.0,
    c_spk=0.0,
    batch_size=BATCH,
)


def _model(**overrides) -> VitsModel:
    torch.manual_seed(0)
    kwargs = dict(_HPARAMS)
    kwargs.update(overrides)
    model = VitsModel(**kwargs)
    # Trainer 無しで step を回すため logging を無効化する
    model._log_with_batch_info = lambda *a, **k: None
    model._grad_probe_due = lambda: False
    model.train()
    return model


def _batch(with_f0: bool = True) -> Batch:
    g = torch.Generator().manual_seed(3)
    f0 = vuv = None
    if with_f0:
        f0 = torch.full((BATCH, 1, N_FRAMES), 200.0)
        f0[:, :, ::4] = 0.0
        vuv = (f0 > 0).float()
    emb = torch.nn.functional.normalize(
        torch.randn(BATCH, 192, generator=g), dim=-1
    )
    return Batch(
        phoneme_ids=torch.randint(1, 40, (BATCH, N_PHONEMES), generator=g),
        phoneme_lengths=torch.full((BATCH,), N_PHONEMES, dtype=torch.long),
        spectrograms=torch.randn(BATCH, 513, N_FRAMES, generator=g).abs(),
        spectrogram_lengths=torch.full((BATCH,), N_FRAMES, dtype=torch.long),
        audios=torch.randn(BATCH, 1, N_FRAMES * 256, generator=g) * 0.1,
        audio_lengths=torch.full((BATCH,), N_FRAMES * 256, dtype=torch.long),
        speaker_ids=torch.zeros(BATCH, dtype=torch.long),
        speaker_embeddings=emb,
        f0=f0,
        vuv=vuv,
    )


def test_training_step_runs_with_the_f0_path_and_produces_a_finite_loss():
    model = _model(use_f0_path=True)
    loss = model.training_step_g(_batch())
    assert torch.isfinite(loss), "generator loss must stay finite with S-2 on"
    assert loss.requires_grad


def test_f0_losses_actually_contribute_to_the_generator_loss():
    """c_f0 / c_vuv を変えると loss_gen_all が変わる (項が本当に足されている)。"""
    with_loss = _model(use_f0_path=True, c_f0=1.0, c_vuv=1.0)
    without = _model(use_f0_path=True, c_f0=0.0, c_vuv=0.0)
    without.load_state_dict(with_loss.state_dict())

    torch.manual_seed(11)
    a = float(with_loss.training_step_g(_batch()))
    torch.manual_seed(11)
    b = float(without.training_step_g(_batch()))
    assert a != pytest.approx(b)


def test_missing_f0_cache_fails_fast_with_an_actionable_message():
    """S-2 を有効にしたのに GT F0 が無い構成は起動直後に落とす。"""
    model = _model(use_f0_path=True)
    with pytest.raises(RuntimeError, match="extract_f0"):
        model.training_step_g(_batch(with_f0=False))


def test_f0_path_off_ignores_f0_in_the_batch():
    """default off では batch に F0 が居ても従来どおり (後方互換)。"""
    model = _model(use_f0_path=False)
    torch.manual_seed(21)
    with_f0 = float(model.training_step_g(_batch(with_f0=True)))
    torch.manual_seed(21)
    without = float(model.training_step_g(_batch(with_f0=False)))
    assert with_f0 == pytest.approx(without)


def test_teacher_forcing_probability_follows_the_epoch():
    """epoch が K 未満なら GT のみ、ramp 後は p_max まで上がる。"""
    from piper_train.vits.losses import f0_teacher_forcing_prob

    model = _model(
        use_f0_path=True,
        f0_teacher_forcing_epochs=10,
        f0_teacher_forcing_ramp=10,
        f0_pred_prob_max=0.5,
    )
    hp = model.hparams
    assert (
        f0_teacher_forcing_prob(
            5, hp.f0_teacher_forcing_epochs, hp.f0_teacher_forcing_ramp,
            hp.f0_pred_prob_max,
        )
        == 0.0
    )
    assert f0_teacher_forcing_prob(
        20, hp.f0_teacher_forcing_epochs, hp.f0_teacher_forcing_ramp,
        hp.f0_pred_prob_max,
    ) == pytest.approx(0.5)


def test_hparams_reach_the_generator():
    """CLI → VitsModel → SynthesizerTrn → decoder の hparam 伝播。"""
    model = _model(
        use_f0_path=True,
        f0_predictor_hidden=64,
        f0_feat_channels=4,
        f0_head_channels=4,
        f0_harmonics=4,
        f0_prior_residual=True,
    )
    gen = model.model_g
    assert gen.use_f0_path is True
    assert gen.f0_predictor.hidden_channels == 64
    assert gen.dec.f0_feat.out_channels == 4
    assert gen.dec.head_proj.out_channels == 4
    assert gen.dec.phase_template.n_harmonics == 4
    assert hasattr(gen, "f0_prior_res")


def test_prior_residual_hparam_is_off_by_default():
    model = _model(use_f0_path=True)
    assert not hasattr(model.model_g, "f0_prior_res")


def test_attach_predictor_input_flag_is_inverted_exactly_once():
    """CLI は肯定形 ``--f0-attach-predictor-input``、hparam は ``f0_detach_input``。

    二重反転 / 反転漏れは「保護しているつもりで保護していない」形で静かに
    壊れる (勾配が enc_p に流れても loss は普通に下がるので気づけない)。
    CLI 側の反転 1 箇所と、モデル側の default が保護側であることを固定する。
    """
    import inspect
    import re

    from piper_train.__main__ import main as train_main

    # 改行位置は formatter が決めるので、空白を潰してから構造だけ照合する
    source = inspect.getsource(train_main)
    flat = re.sub(r"\s+", " ", source)
    assert re.search(
        r'dict_args\["f0_detach_input"\]\s*=\s*not\s+getattr\(\s*args,\s*'
        r'"f0_attach_predictor_input"',
        flat,
    ), "the CLI flag inversion for f0_detach_input is missing or was reshaped"
    # 反転は 1 箇所だけ (二重反転を防ぐ)。読み出し側の参照は数えない。
    assignments = re.findall(r'dict_args\["f0_detach_input"\]\s*=', flat)
    assert len(assignments) == 1

    # モデル側 default は保護側 (detach する)
    assert _model(use_f0_path=True).model_g.f0_detach_input is True

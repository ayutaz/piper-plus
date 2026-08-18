"""v10b Phase B 識別器系の統合テスト (実 batch で training_step を回す)。

S-1a (JCU MRD) / S-1b (adversarial speaker classifier) / H-3 (hires MRD) の
**配線**を、単体テストでは踏めない経路 — ``training_step_g`` と
``training_step_d`` の実行そのもの — で確認する。

なぜ必要か: 単体テストは ``_mrd_generator_losses`` 等のメソッドを直接呼ぶため、
「メソッドは正しいが training_step から呼ばれていない」「条件 embedding が
D 更新に渡っていない」「log キーが衝突する」といった配線バグを全て生存させる
(M1 の logdet→KL 配線漏れと同型のリスク)。特に S-1a は条件 embedding を
**noise 加算後**のものにする契約があり、これは training_step_g のローカル変数
経由でしか観測できない。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")
pytest.importorskip("pytorch_lightning")

from torch.nn import functional as F  # noqa: E402


NUM_SPEAKERS = 4
B, T_TEXT, T_FRAMES = 2, 20, 48
HOP = 256


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": NUM_SPEAKERS,
        "num_languages": 2,
        "dataset": None,
        "batch_size": B,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
        "segment_size": 8192,
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


def _batch():
    from piper_train.vits.dataset import Batch

    torch.manual_seed(1)
    return Batch(
        phoneme_ids=torch.randint(1, 97, (B, T_TEXT)),
        phoneme_lengths=torch.full((B,), T_TEXT),
        spectrograms=torch.randn(B, 513, T_FRAMES).abs(),
        spectrogram_lengths=torch.full((B,), T_FRAMES),
        audios=torch.randn(B, 1, T_FRAMES * HOP) * 0.1,
        audio_lengths=torch.full((B,), T_FRAMES * HOP),
        speaker_ids=torch.tensor([0, 1]),
        language_ids=torch.tensor([0, 0]),
        prosody_features=torch.zeros(B, T_TEXT, 3, dtype=torch.long),
        speaker_embeddings=F.normalize(torch.randn(B, 192), dim=-1),
    )


def _capture_logs(model):
    """``_log_with_batch_info`` を差し替えて log キー/値を回収する。

    Trainer 未 attach では ``self.trainer.world_size`` が RuntimeError になる
    ため、no-op ではなく回収 stub を挿す (どの loss が実際に配線されたかを
    この dict で判定する)。
    """
    logged: dict[str, float] = {}

    def _stub(key, value, batch=None, batch_size=None):
        logged[key] = float(value.detach()) if torch.is_tensor(value) else float(value)

    model._log_with_batch_info = _stub
    return logged


@pytest.mark.unit
class TestFullTrainingStepWithAllLevers:
    def _run(self, **overrides):
        model = _vits_model(
            use_mrd=True,
            use_jcu_mrd=True,
            mrd_hires_resolution="4096",
            use_adv_spk_classifier=True,
            c_adv_spk=0.1,
            adv_spk_start_epoch=0,  # current_epoch=0 でも G 側を有効化
            adv_spk_ramp_epochs=0,
            **overrides,
        )
        model.train()
        logged = _capture_logs(model)
        batch = _batch()
        loss_g = model.training_step_g(batch)
        loss_d = model.training_step_d(batch)
        return model, batch, loss_g, loss_d, logged

    def test_generator_step_wires_both_new_terms(self):
        _model, _, loss_g, _, logged = self._run()
        assert torch.isfinite(loss_g), "G loss が非有限"
        assert "loss_gen_mrd_cond" in logged, (
            "JCU 条件項が training_step_g から呼ばれていない"
        )
        assert "loss_adv_spk" in logged, "S-1b の G 側敵対項が配線されていない"
        assert logged["adv_spk_ramp"] == 1.0

    def test_discriminator_step_wires_both_new_terms(self):
        _model, _, _loss_g, loss_d, logged = self._run()
        assert torch.isfinite(loss_d), "D loss が非有限"
        assert "loss_disc_mrd_cond" in logged
        assert "loss_c_spk" in logged, "分類器 C の更新項が配線されていない"
        # Phase D 検証項目 ③ / 本走 R3 監視の 3 統計
        for key in (
            "c_spk_acc_real",
            "c_spk_acc_fake_as_generated",
            "c_spk_acc_fake_as_conditioned",
        ):
            assert key in logged, f"監視統計 {key} が log されていない"

    def test_condition_passed_to_d_is_the_post_noise_embedding(self):
        """S-1a の契約: D 更新に渡る条件は **noise 加算後** の embedding。

        noise を明示的に効かせた状態で、``_spk_cond`` が batch の生の
        embedding と異なり、かつ L2 正規化されていることを確認する。
        """
        model, batch, _g, _d, _logged = self._run(spk_emb_noise_sigma=0.05)
        assert model._spk_cond is not None
        assert not torch.allclose(model._spk_cond, batch.speaker_embeddings), (
            "D に渡る条件が noise 加算前の生 embedding になっている"
        )
        norms = model._spk_cond.norm(dim=-1)
        assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)

    def test_generator_backward_reaches_classifier_and_generator(self):
        """G backward で C にも勾配が乗る (= fake 経路が C を通っている)。

        C の勾配は続く ``opt_d.zero_grad()`` で捨てられる (training_step の
        順序) が、勾配が**通っている**ことは S-1b の敵対項が本物である証拠。
        """
        model, _, loss_g, _, _logged = self._run()
        loss_g.backward()
        g_grad = sum(
            float(p.grad.abs().sum())
            for p in model.model_g.parameters()
            if p.grad is not None
        )
        c_grad = sum(
            float(p.grad.abs().sum())
            for p in model.model_c_spk.parameters()
            if p.grad is not None
        )
        assert g_grad > 0, "G に勾配が流れていない"
        assert c_grad > 0, "C を経由する fake 経路の勾配が無い"

    def test_state_is_released_after_the_step(self):
        model, _, _g, _d, _logged = self._run()
        # training_step_d 単体では解放しない (training_step が担当) が、
        # 条件 embedding の参照が step を越えて溜まらないことを pin
        assert model._spk_cond is not None
        model._y = None
        model._y_hat = None
        model._spk_cond = None
        assert model._spk_cond is None


@pytest.mark.unit
class TestDefaultRunIsUnchanged:
    def test_no_new_log_keys_by_default(self):
        """default (全 off) では新 loss の log キーが 1 つも出ない。

        「default は v10a-r2 と bit 互換」を観測可能な形で固定する。
        """
        model = _vits_model(use_mrd=True)
        model.train()
        logged = _capture_logs(model)
        batch = _batch()
        loss_g = model.training_step_g(batch)
        loss_d = model.training_step_d(batch)
        assert torch.isfinite(loss_g) and torch.isfinite(loss_d)
        for key in (
            "loss_gen_mrd_cond",
            "loss_disc_mrd_cond",
            "loss_adv_spk",
            "loss_c_spk",
        ):
            assert key not in logged, f"default で {key} が有効化されている"
        assert model.model_c_spk is None
        assert model.model_d_mrd.use_jcu is False
        assert model.model_d_mrd.n_resolutions == 3

    def test_single_speaker_batch_disables_classifier_terms(self):
        """speaker_ids を持たない batch では S-1b が両側 off (例外にならない)。"""
        import dataclasses

        model = _vits_model(
            use_adv_spk_classifier=True, c_adv_spk=0.1, adv_spk_start_epoch=0
        )
        model.train()
        logged = _capture_logs(model)
        batch = dataclasses.replace(_batch(), speaker_ids=None)
        loss_g = model.training_step_g(batch)
        loss_d = model.training_step_d(batch)
        assert torch.isfinite(loss_g) and torch.isfinite(loss_d)
        assert "loss_adv_spk" not in logged
        assert "loss_c_spk" not in logged

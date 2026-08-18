"""v10b Phase B — S-1b: 共進化 adversarial speaker classifier。

背景 (docs/design/zero-shot-v10b-quality-plan.md §3.2 S-1 / §2.2):
話者監督を frozen encoder の cosine で与えると、モデルは似せる代わりに encoder を
騙す方向に逸れる (v10a §10 で prior 経路崩壊、通算 3 例目)。plan §2.2 は
「識別器/分類器が**生成分布上でも更新される場合のみ**可」と条件付けており、
**実音声のみで学習する classifier は禁止** — 生成分布上の決定境界が静的なままで、
frozen encoder と同型の gaming 面が残るため。

本ファイルの中心は `TestClassifierIsUpdatedOnFakes` — **fake 入力に対して C の
パラメータに勾配が流れることの機械固定**。これが v10a 型崩壊の再発防止テストの
本体であり、将来「real だけで C を学習する」形に退行したら赤くなる。

翻案の明示 (StarGANv2-VC arXiv:2107.10394 との差):
原典の adversarial source classifier は変換後サンプルを**source ドメイン**に
分類するよう C を更新するが、TTS の recon 経路には source 話者が存在しない
(条件話者 = 元話者)。そこで「生成音声」クラス K を 1 つ増やし、C は fake を
クラス K に、G は fake を条件話者 (< K) に分類させる min-max とする
(Salimans らの K+1 GAN 形式)。plan が要求する本質 — **C が生成分布上で
敵対的に更新される** — は保たれる。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from torch.nn import functional as F  # noqa: E402


NUM_SPEAKERS = 8


def _classifier(**kwargs):
    from piper_train.vits import models

    cls = getattr(models, "AdversarialSpeakerClassifier", None)
    if cls is None:
        pytest.fail(
            "piper_train.vits.models.AdversarialSpeakerClassifier が未実装 (S-1b)"
        )
    kwargs.setdefault("num_speakers", NUM_SPEAKERS)
    kwargs.setdefault("resolution", (512, 128, 512))
    return cls(**kwargs)


def _loss_fn(name: str):
    from piper_train.vits import losses

    fn = getattr(losses, name, None)
    if fn is None:
        pytest.fail(f"piper_train.vits.losses.{name} が未実装 (S-1b)")
    return fn


def _grad_sum(module) -> float:
    return sum(
        float(p.grad.abs().sum()) for p in module.parameters() if p.grad is not None
    )


@pytest.fixture
def waveforms():
    torch.manual_seed(0)
    return torch.randn(4, 1, 8192), torch.randn(4, 1, 8192)


@pytest.fixture
def sids():
    return torch.tensor([0, 1, 2, 3])


# ===========================================================================
# 1. 構造
# ===========================================================================


@pytest.mark.unit
class TestClassifierStructure:
    def test_output_has_k_plus_one_classes(self, waveforms):
        c = _classifier()
        real, _ = waveforms
        with torch.no_grad():
            logits = c(real)
        assert logits.shape == (4, NUM_SPEAKERS + 1), (
            "出力は num_speakers + 1 (最後のクラスが「生成音声」)"
        )
        assert c.fake_class_index == NUM_SPEAKERS

    def test_spectrogram_is_fp32_under_autocast(self):
        """bf16 cuFFT 事故 (3dcabd57) 対策 — DiscriminatorR と同じ契約。"""
        c = _classifier()
        x = torch.randn(1, 1, 4096)
        with torch.autocast("cpu", dtype=torch.bfloat16):
            spec = c.spectrogram(x)
        assert spec.dtype == torch.float32

    def test_forward_is_finite_for_short_input(self):
        c = _classifier()
        with torch.no_grad():
            logits = c(torch.randn(2, 1, 4096))
        assert torch.isfinite(logits).all()


# ===========================================================================
# 2. ★ C が fake でも更新される (v10a 型崩壊の再発防止テスト本体)
# ===========================================================================


@pytest.mark.unit
class TestClassifierIsUpdatedOnFakes:
    def test_fake_term_produces_nonzero_gradient_on_classifier(self, waveforms, sids):
        """fake 入力だけに由来する勾配が C のパラメータに乗る。

        plan §2.2 の「可」判定の条件そのもの。real のみで学習する形 (禁止形) に
        退行すると、この勾配は恒等的にゼロになり赤くなる。
        """
        c = _classifier()
        _real, fake = waveforms
        loss_fake = F.cross_entropy(
            c(fake),
            torch.full((fake.shape[0],), c.fake_class_index, dtype=torch.long),
        )
        loss_fake.backward()
        assert _grad_sum(c) > 0, "fake 入力に対する C の勾配がゼロ"

    def test_loss_d_includes_the_fake_term(self, waveforms, sids):
        """`adv_speaker_classifier_loss_d` の勾配 ≠ real のみ CE の勾配。

        「fake 項を持つ」ことを loss 関数の外から観測可能な形で固定する
        (実装が real-only に差し替わったら勾配が一致して赤くなる)。
        """
        loss_d = _loss_fn("adv_speaker_classifier_loss_d")
        real, fake = waveforms

        c_full = _classifier()
        torch.manual_seed(5)
        c_real_only = _classifier()
        c_real_only.load_state_dict(c_full.state_dict())

        loss_d(c_full(real), c_full(fake), sids, c_full.fake_class_index).backward()
        F.cross_entropy(c_real_only(real), sids).backward()

        grads_full = torch.cat(
            [p.grad.flatten() for p in c_full.parameters() if p.grad is not None]
        )
        grads_real = torch.cat(
            [p.grad.flatten() for p in c_real_only.parameters() if p.grad is not None]
        )
        assert not torch.allclose(grads_full, grads_real, atol=1e-8), (
            "D 側 loss が real のみ CE と同一勾配 = fake 項が無い (禁止形)"
        )

    def test_loss_d_targets_the_generated_class_for_fakes(self, waveforms, sids):
        """fake の正解ラベルは「生成音声」クラス K (G が避けたいラベル)。"""
        loss_d = _loss_fn("adv_speaker_classifier_loss_d")
        c = _classifier()
        real, fake = waveforms
        n = fake.shape[0]
        real_logits = c(real).detach()
        # fake を K に強く寄せた logits → D 側 loss は小さい
        confident_fake = torch.full((n, NUM_SPEAKERS + 1), -5.0)
        confident_fake[:, c.fake_class_index] = 5.0
        # fake を条件話者に寄せた logits → D 側 loss は大きい (G が勝っている状態)
        fooled_fake = torch.full((n, NUM_SPEAKERS + 1), -5.0)
        fooled_fake[torch.arange(n), sids] = 5.0
        low = loss_d(real_logits, confident_fake, sids, c.fake_class_index)
        high = loss_d(real_logits, fooled_fake, sids, c.fake_class_index)
        assert float(low) < float(high)

    def test_fake_input_gradient_does_not_require_generator(self, waveforms, sids):
        """D 側は detach された fake を受ける想定 — 波形に勾配を返さない。

        呼び出し側 (training_step_d) が ``y_hat.detach()`` を渡す契約の pin。
        """
        loss_d = _loss_fn("adv_speaker_classifier_loss_d")
        c = _classifier()
        real, fake = waveforms
        fake = fake.detach().requires_grad_(False)
        loss_d(c(real), c(fake), sids, c.fake_class_index).backward()
        assert fake.grad is None


# ===========================================================================
# 3. G 側 (条件話者 CE)
# ===========================================================================


@pytest.mark.unit
class TestGeneratorSideObjective:
    def test_gradient_flows_to_generated_waveform(self, sids):
        loss_g = _loss_fn("adv_speaker_classifier_loss_g")
        c = _classifier()
        fake = torch.randn(4, 1, 8192, requires_grad=True)
        loss_g(c(fake), sids).backward()
        assert fake.grad is not None
        assert float(fake.grad.abs().sum()) > 0

    def test_loss_is_lower_when_classified_as_the_conditioned_speaker(self, sids):
        loss_g = _loss_fn("adv_speaker_classifier_loss_g")
        n = sids.shape[0]
        correct = torch.full((n, NUM_SPEAKERS + 1), -5.0)
        correct[torch.arange(n), sids] = 5.0
        as_generated = torch.full((n, NUM_SPEAKERS + 1), -5.0)
        as_generated[:, NUM_SPEAKERS] = 5.0
        assert float(loss_g(correct, sids)) < float(loss_g(as_generated, sids))

    def test_generated_class_is_never_the_generator_target(self, sids):
        """G の目標ラベルは条件話者のみ — K を目標にできない (符号ミス防止)。"""
        loss_g = _loss_fn("adv_speaker_classifier_loss_g")
        n = sids.shape[0]
        logits = torch.zeros(n, NUM_SPEAKERS + 1)
        logits[:, NUM_SPEAKERS] = 10.0  # 完全に「生成音声」と判定された状態
        assert float(loss_g(logits, sids)) > 1.0

    def test_out_of_range_speaker_id_is_rejected(self):
        """speaker_id が num_speakers を超えたら黙って壊れず例外にする。"""
        loss_g = _loss_fn("adv_speaker_classifier_loss_g")
        logits = torch.zeros(2, NUM_SPEAKERS + 1)
        with pytest.raises(ValueError, match="speaker_id"):
            loss_g(logits, torch.tensor([0, NUM_SPEAKERS]))


# ===========================================================================
# 4. ramp スケジュール + DDP 安全性
# ===========================================================================


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
        "batch_size": 4,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


@pytest.mark.unit
class TestRampSchedule:
    def test_ramp_uses_the_swap_style_schedule(self):
        from piper_train.vits.losses import swap_spk_ramp_weight

        assert swap_spk_ramp_weight(9, 10, 5) == 0.0
        assert swap_spk_ramp_weight(10, 10, 5) == pytest.approx(0.0)
        assert swap_spk_ramp_weight(12, 10, 5) == pytest.approx(0.4)
        assert swap_spk_ramp_weight(20, 10, 5) == 1.0

    def test_model_exposes_ramp_for_current_epoch(self):
        model = _vits_model(
            use_adv_spk_classifier=True, adv_spk_start_epoch=10, adv_spk_ramp_epochs=5
        )
        assert model._adv_spk_ramp(0) == 0.0
        assert model._adv_spk_ramp(12) == pytest.approx(0.4)
        assert model._adv_spk_ramp(30) == 1.0

    def test_classifier_trains_before_the_generator_term_ramps_in(self):
        """C 自身の学習は step 0 から、G 側の敵対項だけ ramp する (非対称)。

        C が未学習のまま G に「C を騙せ」と要求するとゴミ勾配を与えるため、
        C は最初から学習させる。この非対称性は意図的な設計判断であり、
        テストで固定する。
        """
        model = _vits_model(use_adv_spk_classifier=True)
        assert model._adv_spk_classifier_active(epoch=0) is True
        assert model._adv_spk_generator_active(epoch=0) is False
        assert model._adv_spk_generator_active(epoch=20) is True

    def test_disabled_when_flag_off(self):
        model = _vits_model()
        assert model.model_c_spk is None
        assert model._adv_spk_classifier_active(epoch=50) is False
        assert model._adv_spk_generator_active(epoch=50) is False


@pytest.mark.unit
class TestDdpSafety:
    def test_gating_is_a_pure_function_of_epoch(self):
        """分岐が epoch と hparams のみで決まる = 全 rank で一致する。

        batch 内容や RNG に依存すると rank 間で分岐が食い違い、NCCL
        all_reduce mismatch → 30 分 timeout (「CUDA illegal access」の偽装
        症状) になる。
        """
        model = _vits_model(use_adv_spk_classifier=True)
        before = torch.get_rng_state()
        results = [
            (
                model._adv_spk_classifier_active(epoch=e),
                model._adv_spk_generator_active(epoch=e),
                model._adv_spk_ramp(e),
            )
            for e in (0, 9, 10, 13, 40)
        ]
        assert torch.equal(torch.get_rng_state(), before), (
            "gating が global RNG を消費している (rank 間で分岐が食い違う)"
        )
        # 2 回目の呼び出しで同一結果 (内部状態に依存しない)
        again = [
            (
                model._adv_spk_classifier_active(epoch=e),
                model._adv_spk_generator_active(epoch=e),
                model._adv_spk_ramp(e),
            )
            for e in (0, 9, 10, 13, 40)
        ]
        assert results == again

    def test_speaker_ids_absence_disables_both_sides(self):
        """speaker_ids を持たないデータセット (single-speaker FT) では両側 off。"""
        model = _vits_model(use_adv_spk_classifier=True)
        assert (
            model._adv_spk_classifier_active(epoch=20, has_speaker_ids=False) is False
        )
        assert model._adv_spk_generator_active(epoch=20, has_speaker_ids=False) is False


# ===========================================================================
# 5. lightning 配線 / off 時 bit 互換 / optimizer
# ===========================================================================


@pytest.mark.unit
class TestLightningWiring:
    def test_off_by_default_and_state_dict_unchanged(self):
        baseline = set(_vits_model().state_dict().keys())
        with_c = set(_vits_model(use_adv_spk_classifier=True).state_dict().keys())
        assert baseline < with_c
        assert all(k.startswith("model_c_spk.") for k in with_c - baseline), (
            "分類器の追加が既存 state_dict キーを動かしている"
        )

    def test_classifier_built_when_enabled(self):
        model = _vits_model(use_adv_spk_classifier=True)
        assert model.model_c_spk is not None
        assert model.model_c_spk.fake_class_index == NUM_SPEAKERS

    def test_single_speaker_disables_classifier(self):
        model = _vits_model(num_speakers=1, use_adv_spk_classifier=True)
        assert model.model_c_spk is None

    def test_classifier_params_go_to_the_discriminator_optimizer(self):
        model = _vits_model(use_adv_spk_classifier=True)
        optimizers, _ = model.configure_optimizers()
        d_param_ids = {
            id(p) for group in optimizers[1].param_groups for p in group["params"]
        }
        g_param_ids = {
            id(p) for group in optimizers[0].param_groups for p in group["params"]
        }
        c_ids = {id(p) for p in model.model_c_spk.parameters()}
        assert c_ids <= d_param_ids, "C が D optimizer に入っていない"
        assert not (c_ids & g_param_ids), "C が G optimizer に混入している"

    def test_model_methods_compute_both_sides(self, sids):
        model = _vits_model(use_adv_spk_classifier=True)
        model.eval()
        torch.manual_seed(2)
        y = torch.randn(4, 1, 8192)
        y_hat = torch.randn(4, 1, 8192)
        loss_d, stats = model._adv_spk_classifier_loss_d(y, y_hat, sids)
        assert torch.isfinite(loss_d)
        # Phase D / 本走 R3 監視項目: fake に対する C の分類の推移
        assert "acc_real" in stats and "acc_fake_as_generated" in stats
        assert "acc_fake_as_conditioned" in stats
        loss_g = model._adv_spk_classifier_loss_g(y_hat, sids)
        assert torch.isfinite(loss_g)

    def test_c_adv_spk_zero_with_flag_on_warns(self, caplog):
        """flag on / 係数 0 は黙って no-op にせず警告する。"""
        import logging

        with caplog.at_level(logging.WARNING, logger="piper_train.vits.lightning"):
            model = _vits_model(use_adv_spk_classifier=True, c_adv_spk=0.0)
        assert model._adv_spk_classifier_active(epoch=20) is False
        assert any("c_adv_spk" in r.message for r in caplog.records)


# ===========================================================================
# 6. CLI
# ===========================================================================


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestAdvSpkCli:
    def test_defaults(self):
        args = _parse_train_args()
        assert args.use_adv_spk_classifier is False
        assert args.adv_spk_start_epoch == 10
        assert args.adv_spk_ramp_epochs == 5

    def test_flags_parse(self):
        args = _parse_train_args(
            (
                "--use-adv-spk-classifier",
                "--c-adv-spk",
                "0.3",
                "--adv-spk-start-epoch",
                "8",
                "--adv-spk-ramp-epochs",
                "3",
            )
        )
        assert args.use_adv_spk_classifier is True
        assert args.c_adv_spk == 0.3
        assert args.adv_spk_start_epoch == 8
        assert args.adv_spk_ramp_epochs == 3

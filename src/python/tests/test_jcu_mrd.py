"""v10b Phase B — S-1a: MRD への JCU (Joint Conditional & Unconditional) 分岐。

背景 (docs/design/zero-shot-v10b-quality-plan.md §3.2 S-1):
話者監督を「frozen encoder の cosine」で与えると、モデルは似せる代わりに
encoder を騙す方向に逸れる (v10a §10 で prior 経路が ~6ep で崩壊、3 例目)。
対策は**共進化する識別器**に話者条件を持たせること — GANSpeech
(arXiv:2106.15153) の JCU 判別器形式。speaker embedding を FC → 時間展開 →
中間層 concat し、無条件分岐と条件分岐が body を共有する。

本ファイルが固定する契約:

1. 分岐の出力形状 + **body 共有** (パラメータ数の検算で「条件分岐が body を
   複製していない」ことを機械固定)
2. **off 時の bit 互換** (state_dict キー / 構築時 RNG 消費 / 出力値)
3. **条件シャッフルで条件項の loss が上がる** — 条件分岐が実際に条件を見て
   いる構造検証 (short training で「学習できる」ことまで確認する。ランダム
   初期化のままでは「条件を読んでいるが無意味」と区別できない)
4. 勾配が G (y_hat) に流れる + 条件経路 (cond_proj) が D 更新で学習される
5. 無条件項と条件項を 1/2 ずつにする配線 (c_mrd の較正値を保つ)

MPD/MSD は無条件のまま (plan §3.2: timbre が住む spectrogram 域に条件を集中)。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from torch.nn import functional as F  # noqa: E402

from piper_train.vits.losses import (  # noqa: E402
    discriminator_loss,
    feature_loss,
    generator_loss,
)


SPK_DIM = 192


def _mrd(**kwargs):
    from piper_train.vits.models import MultiResolutionSpectrogramDiscriminator

    return MultiResolutionSpectrogramDiscriminator(**kwargs)


def _disc_r(resolution=(512, 50, 240), **kwargs):
    from piper_train.vits.models import DiscriminatorR

    return DiscriminatorR(resolution, **kwargs)


def _jcu_split():
    from piper_train.vits import losses

    fn = getattr(losses, "jcu_split", None)
    if fn is None:
        pytest.fail(
            "piper_train.vits.losses.jcu_split が未実装 "
            "(S-1a: JCU 出力リストを無条件/条件に分ける純関数)"
        )
    return fn


@pytest.fixture
def audio_pair():
    torch.manual_seed(0)
    return torch.randn(2, 1, 16384), torch.randn(2, 1, 16384)


@pytest.fixture
def spk_cond():
    torch.manual_seed(1)
    return F.normalize(torch.randn(2, SPK_DIM), dim=-1)


# ===========================================================================
# 1. 分岐の出力形状と body 共有
# ===========================================================================


@pytest.mark.unit
class TestJcuBranchStructure:
    def test_discriminator_r_returns_three_tuple(self, spk_cond):
        """DiscriminatorR は (uncond, fmap, cond) の 3-tuple を返す (arity 固定)。

        cond は条件無効時 None。arity を常に 3 にしておくことで、呼び出し側の
        分岐が「タプル長を数える」形にならない。
        """
        d = _disc_r(spk_cond_dim=SPK_DIM)
        x = torch.randn(2, 1, 8192)
        with torch.no_grad():
            out = d(x, spk_cond)
        assert len(out) == 3
        uncond, fmap, cond = out
        assert cond is not None
        assert cond.shape == uncond.shape, (
            "条件項は無条件項と同形状 (LSGAN で対称に扱う)"
        )
        assert len(fmap) == 6, "fmap は共有 body 5 conv + 無条件 conv_post のみ"

    def test_cond_is_none_without_conditioning(self):
        d = _disc_r(spk_cond_dim=SPK_DIM)
        with torch.no_grad():
            uncond, _fmap, cond = d(torch.randn(2, 1, 8192), None)
        assert cond is None
        assert uncond.dim() == 2

    def test_body_is_shared_not_duplicated(self, spk_cond):
        """パラメータ数の検算: JCU の増分 = cond_proj + conv_post_cond のみ。

        body (convs 5 本 + conv_post) を複製する実装だと増分がこの値を大きく
        超える。「条件分岐が body を共有する」(GANSpeech 形式) の機械固定。
        """
        plain = _disc_r()
        jcu = _disc_r(spk_cond_dim=SPK_DIM)

        def n_params(module):
            return sum(p.numel() for p in module.parameters())

        added = n_params(jcu) - n_params(plain)
        expected = n_params(jcu.cond_proj) + n_params(jcu.conv_post_cond)
        assert added == expected, (
            f"JCU の増分 {added} が cond_proj + conv_post_cond {expected} と "
            "一致しない — body が複製されている可能性"
        )
        # 共有 body のパラメータ名 / 形状は plain と完全一致
        plain_body = {n: tuple(p.shape) for n, p in plain.named_parameters()}
        jcu_body = {
            n: tuple(p.shape)
            for n, p in jcu.named_parameters()
            if not n.startswith(("cond_proj", "conv_post_cond"))
        }
        assert jcu_body == plain_body

    def test_mrd_appends_conditional_outputs(self, audio_pair, spk_cond):
        """MRD は 4-tuple 契約を維持し、条件項は各リストの後半に追加される。"""
        mrd = _mrd(spk_cond_dim=SPK_DIM)
        n = mrd.n_resolutions
        with torch.no_grad():
            y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(
                *audio_pair, speaker_embeddings=spk_cond
            )
        assert len(y_d_rs) == len(y_d_gs) == 2 * n
        assert len(fmap_rs) == len(fmap_gs) == n, (
            "FM loss は共有 body のみを対象にする (条件ヘッドの fmap は含めない)"
        )
        split = _jcu_split()
        uncond, cond = split(y_d_rs, n)
        assert len(uncond) == len(cond) == n
        # 前半 = 無条件項。条件を渡さない forward と bit 一致する
        with torch.no_grad():
            plain_rs, _, _, _ = mrd(*audio_pair, speaker_embeddings=None)
        for a, b in zip(uncond, plain_rs, strict=True):
            assert torch.equal(a, b), "無条件分岐は条件の有無で変化しない"

    def test_jcu_split_pure_function(self):
        split = _jcu_split()
        outputs = ["u0", "u1", "u2", "c0", "c1", "c2"]
        uncond, cond = split(outputs, 3)
        assert uncond == ["u0", "u1", "u2"]
        assert cond == ["c0", "c1", "c2"]
        # 条件項が無い (JCU off) 場合は cond が空リスト
        uncond, cond = split(["u0", "u1", "u2"], 3)
        assert cond == []


# ===========================================================================
# 2. off 時の bit 互換
# ===========================================================================


@pytest.mark.unit
class TestJcuOffBitCompatibility:
    def test_state_dict_keys_unchanged_when_off(self):
        mrd = _mrd()
        keys = list(mrd.state_dict().keys())
        assert not any("cond_proj" in k or "conv_post_cond" in k for k in keys), (
            "default (JCU off) で条件分岐のパラメータが生えている"
        )

    def test_construction_consumes_no_extra_rng_when_off(self):
        """spk_cond_dim=0 は default と bit 一致 (構築時 RNG 消費も同一)。"""
        torch.manual_seed(7)
        a = _mrd()
        torch.manual_seed(7)
        b = _mrd(spk_cond_dim=0)
        for (na, pa), (nb, pb) in zip(
            a.named_parameters(), b.named_parameters(), strict=True
        ):
            assert na == nb
            assert torch.equal(pa, pb)

    def test_speaker_embeddings_ignored_when_off(self, audio_pair, spk_cond):
        """JCU off の MRD に条件を渡しても 4-tuple の中身は変わらない。"""
        mrd = _mrd()
        with torch.no_grad():
            with_cond = mrd(*audio_pair, speaker_embeddings=spk_cond)
            without = mrd(*audio_pair)
        assert len(with_cond[0]) == len(without[0]) == mrd.n_resolutions
        for a, b in zip(with_cond[0], without[0], strict=True):
            assert torch.equal(a, b)

    def test_legacy_positional_forward_still_works(self, audio_pair):
        """既存呼び出し (y, y_hat) の 4-tuple 契約は不変。"""
        mrd = _mrd()
        with torch.no_grad():
            y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(*audio_pair)
        loss_d, _, _ = discriminator_loss(y_d_rs, [g.detach() for g in y_d_gs])
        loss_g, _ = generator_loss(y_d_gs)
        loss_fm = feature_loss(fmap_rs, fmap_gs)
        for v in (loss_d, loss_g, loss_fm):
            assert torch.isfinite(v)


# ===========================================================================
# 3. 条件を実際に見ているか (シャッフル検証)
# ===========================================================================


@pytest.mark.unit
class TestConditionIsActuallyUsed:
    def test_cond_output_depends_on_condition(self, spk_cond):
        """条件を差し替えると条件項だけが変化する (無条件項は不変)。"""
        d = _disc_r(spk_cond_dim=SPK_DIM)
        x = torch.randn(2, 1, 8192)
        torch.manual_seed(2)
        other = F.normalize(torch.randn(2, SPK_DIM), dim=-1)
        with torch.no_grad():
            u1, _, c1 = d(x, spk_cond)
            u2, _, c2 = d(x, other)
        assert torch.equal(u1, u2), "無条件項は条件に依存しない"
        assert not torch.allclose(c1, c2), "条件項が条件を読んでいない (定数出力)"

    def test_shuffled_condition_raises_conditional_loss_after_training(self):
        """正しいペアで学習した条件分岐は、シャッフル条件で LSGAN real loss が上がる。

        ランダム初期化のままでは「条件に依存する」ことしか言えない。
        短時間学習して「正しいペアを real、誤ったペアを fake と学習できる」
        ことまで確認して初めて、条件分岐が話者ペアの整合性を判別する構造だと
        言える (S-1 の狙いそのもの)。
        """
        torch.manual_seed(0)
        d = _disc_r((256, 64, 256), spk_cond_dim=8)
        sr = 22050
        t = torch.arange(4096, dtype=torch.float32) / sr
        # 2 種類の「話者」= 別周波数のトーン、と対応する条件ベクトル
        x = torch.stack(
            [
                torch.sin(2 * torch.pi * 400 * t),
                torch.sin(2 * torch.pi * 3000 * t),
            ]
        ).unsqueeze(1)
        cond = torch.eye(2, 8)
        wrong = cond.flip(0)

        opt = torch.optim.Adam(d.parameters(), lr=5e-3)
        for _ in range(80):
            opt.zero_grad()
            _, _, c_ok = d(x, cond)
            _, _, c_bad = d(x, wrong)
            # LSGAN: 正しいペア → 1、誤ったペア → 0
            loss = ((1 - c_ok) ** 2).mean() + (c_bad**2).mean()
            loss.backward()
            opt.step()

        with torch.no_grad():
            _, _, c_ok = d(x, cond)
            _, _, c_bad = d(x, wrong)
            real_loss_matched = float(((1 - c_ok) ** 2).mean())
            real_loss_shuffled = float(((1 - c_bad) ** 2).mean())
        assert real_loss_shuffled > real_loss_matched, (
            f"条件シャッフルで real loss が上がらない "
            f"(matched={real_loss_matched:.4f} shuffled={real_loss_shuffled:.4f})"
        )


# ===========================================================================
# 4. 勾配経路
# ===========================================================================


@pytest.mark.unit
class TestJcuGradients:
    def test_conditional_term_gradient_reaches_generated_waveform(self, spk_cond):
        """条件項のみの G loss で y_hat に勾配が届く (G が条件項で学習される)。"""
        mrd = _mrd(spk_cond_dim=SPK_DIM)
        y = torch.randn(2, 1, 8192)
        y_hat = torch.randn(2, 1, 8192, requires_grad=True)
        _, y_d_gs, _, _ = mrd(y, y_hat, speaker_embeddings=spk_cond)
        _, cond_g = _jcu_split()(y_d_gs, mrd.n_resolutions)
        loss, _ = generator_loss(cond_g)
        loss.backward()
        assert y_hat.grad is not None
        assert float(y_hat.grad.abs().sum()) > 0

    def test_cond_proj_receives_gradient_in_d_update(self, audio_pair, spk_cond):
        """D 更新で条件経路 (cond_proj) が学習される。"""
        mrd = _mrd(spk_cond_dim=SPK_DIM)
        y, y_hat = audio_pair
        y_d_rs, y_d_gs, _, _ = mrd(y, y_hat, speaker_embeddings=spk_cond)
        uncond_r, cond_r = _jcu_split()(y_d_rs, mrd.n_resolutions)
        uncond_g, cond_g = _jcu_split()(y_d_gs, mrd.n_resolutions)
        loss_uncond, _, _ = discriminator_loss(uncond_r, uncond_g)
        loss_cond, _, _ = discriminator_loss(cond_r, cond_g)
        (0.5 * (loss_uncond + loss_cond)).backward()
        grads = [
            float(p.grad.abs().sum())
            for d in mrd.discriminators
            for p in d.cond_proj.parameters()
            if p.grad is not None
        ]
        assert grads and sum(grads) > 0, "cond_proj に勾配が流れていない"


# ===========================================================================
# 5. lightning 配線 (無条件 + 条件を 1/2 ずつ)
# ===========================================================================


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": 4,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 2,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


@pytest.mark.unit
class TestJcuLightningWiring:
    def test_default_mrd_has_no_jcu(self):
        model = _vits_model(use_mrd=True)
        assert model.model_d_mrd is not None
        assert model.model_d_mrd.use_jcu is False

    def test_use_jcu_mrd_builds_conditional_branch(self):
        model = _vits_model(use_mrd=True, use_jcu_mrd=True)
        assert model.model_d_mrd.use_jcu is True
        names = [n for n, _ in model.model_d_mrd.named_parameters()]
        assert any("cond_proj" in n for n in names)

    def test_jcu_requires_mrd(self):
        """MRD 本体なしで JCU を要求したら黙って無視せず警告して off にする。"""
        model = _vits_model(use_mrd=False, use_jcu_mrd=True)
        assert model.model_d_mrd is None

    def test_generator_losses_average_the_two_branches(self):
        """G 側 MRD loss = 1/2 * (無条件 + 条件)。c_mrd 較正値を保つ配線。"""
        model = _vits_model(use_mrd=True, use_jcu_mrd=True)
        model.eval()
        torch.manual_seed(3)
        y = torch.randn(2, 1, 8192)
        y_hat = torch.randn(2, 1, 8192)
        cond = F.normalize(torch.randn(2, SPK_DIM), dim=-1)
        with torch.no_grad():
            adv, _fm, adv_cond = model._mrd_generator_losses(y, y_hat, cond)
            # 手計算: 無条件項と条件項を別々に取って平均
            _, y_d_gs, _, _ = model.model_d_mrd(y, y_hat, speaker_embeddings=cond)
            uncond_g, cond_g = _jcu_split()(y_d_gs, model.model_d_mrd.n_resolutions)
            loss_u, _ = generator_loss(uncond_g)
            loss_c, _ = generator_loss(cond_g)
        assert adv_cond is not None
        assert float(adv) == pytest.approx(float(0.5 * (loss_u + loss_c)), rel=1e-6)
        assert float(adv_cond) == pytest.approx(float(loss_c), rel=1e-6)

    def test_generator_losses_unscaled_without_jcu(self):
        """JCU off では従来どおり無条件項そのまま (1/2 スケールしない)。"""
        model = _vits_model(use_mrd=True)
        model.eval()
        torch.manual_seed(3)
        y = torch.randn(2, 1, 8192)
        y_hat = torch.randn(2, 1, 8192)
        with torch.no_grad():
            adv, _fm, adv_cond = model._mrd_generator_losses(y, y_hat, None)
            _, y_d_gs, _, _ = model.model_d_mrd(y, y_hat)
            loss_u, _ = generator_loss(y_d_gs)
        assert adv_cond is None
        assert float(adv) == pytest.approx(float(loss_u), rel=1e-6)

    def test_discriminator_loss_averages_the_two_branches(self):
        model = _vits_model(use_mrd=True, use_jcu_mrd=True)
        model.eval()
        torch.manual_seed(4)
        y = torch.randn(2, 1, 8192)
        y_hat = torch.randn(2, 1, 8192)
        cond = F.normalize(torch.randn(2, SPK_DIM), dim=-1)
        with torch.no_grad():
            loss, loss_cond = model._mrd_discriminator_loss(y, y_hat, cond)
            y_d_rs, y_d_gs, _, _ = model.model_d_mrd(y, y_hat, speaker_embeddings=cond)
            n = model.model_d_mrd.n_resolutions
            uncond_r, cond_r = _jcu_split()(y_d_rs, n)
            uncond_g, cond_g = _jcu_split()(y_d_gs, n)
            loss_u, _, _ = discriminator_loss(uncond_r, uncond_g)
            loss_c, _, _ = discriminator_loss(cond_r, cond_g)
        assert loss_cond is not None
        assert float(loss) == pytest.approx(float(0.5 * (loss_u + loss_c)), rel=1e-6)


# ===========================================================================
# 6. CLI
# ===========================================================================


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestJcuCli:
    def test_default_off(self):
        assert _parse_train_args().use_jcu_mrd is False

    def test_flag_parses(self):
        args = _parse_train_args(("--use-mrd", "--use-jcu-mrd"))
        assert args.use_jcu_mrd is True

    def test_dependency_check_rejects_jcu_without_mrd(self):
        from piper_train.__main__ import check_discriminator_arg_consistency

        args = _parse_train_args(("--use-jcu-mrd",))
        msg = check_discriminator_arg_consistency(args)
        assert msg is not None and "--use-mrd" in msg

    def test_dependency_check_passes_with_mrd(self):
        from piper_train.__main__ import check_discriminator_arg_consistency

        args = _parse_train_args(("--use-mrd", "--use-jcu-mrd"))
        assert check_discriminator_arg_consistency(args) is None

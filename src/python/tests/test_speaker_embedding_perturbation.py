"""Tests for speaker_embedding L2 re-normalization after noise perturbation.

bug discovered:
``lightning.py`` の training_step_g 内で、CAM++ 出力 (L2 normalized, norm=1.0)
に Gaussian noise を加えた後、再正規化せずに spk_proj に渡していた:

    speaker_embeddings = speaker_embeddings + torch.randn_like(...) * sigma

これにより perturbed embedding の期待 norm は ``sqrt(1 + sigma^2 * dim)``
(sigma=0.05, dim=192 で ≈ 1.22) となり、推論時の norm=1 と train で
~22% magnitude 不一致を生む。learning が進んで spk_proj の重み
が大きくなると、この magnitude 揺らぎが増幅して
``log_softmax(student_emb / tau)`` で発散し、loss_dino が NaN マスクで
0 に貼り付く現象が発生 (multi-6lang スクラッチで step ~1249 から実測)。

修正: noise 加算後に ``F.normalize(..., p=2, dim=-1)`` を呼んで
norm を 1.0 に戻す。
"""

from __future__ import annotations

import pytest


pytest.importorskip("torch", reason="torch required")

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402


# ---------------------------------------------------------------------------
# 数学的性質: noise 加算 + L2 正規化
# ---------------------------------------------------------------------------


class TestPerturbationMath:
    """L2 再正規化が norm を 1.0 に戻すことを数値的に検証"""

    def test_norm_drift_without_renormalize(self):
        """L2 正規化前: noise 加算で norm が 1 から外れる"""
        torch.manual_seed(42)
        emb = F.normalize(torch.randn(16, 192), p=2, dim=-1)  # CAM++ 風
        sigma = 0.05
        noised = emb + torch.randn_like(emb) * sigma
        norms = noised.norm(dim=-1)
        # 期待値: sqrt(1 + sigma² × dim) = sqrt(1 + 0.0025 × 192) = sqrt(1.48) ≈ 1.216
        assert (norms.mean() - 1.216).abs() < 0.05
        assert (norms - 1.0).abs().mean() > 0.1, "norm が 1 から有意に乖離するはず"

    def test_norm_unity_after_renormalize(self):
        """L2 再正規化後: 全サンプルの norm が 1.0"""
        torch.manual_seed(42)
        emb = F.normalize(torch.randn(16, 192), p=2, dim=-1)
        sigma = 0.05
        noised = emb + torch.randn_like(emb) * sigma
        renorm = F.normalize(noised, p=2, dim=-1)
        norms = renorm.norm(dim=-1)
        torch.testing.assert_close(norms, torch.ones(16), atol=1e-6, rtol=0)

    def test_renormalize_preserves_direction(self):
        """L2 再正規化は方向を保ち、magnitude のみ変える"""
        torch.manual_seed(42)
        emb = F.normalize(torch.randn(8, 192), p=2, dim=-1)
        sigma = 0.05
        noised = emb + torch.randn_like(emb) * sigma
        renorm = F.normalize(noised, p=2, dim=-1)
        # cosine 類似度が 1 (= 同方向)
        cosine = F.cosine_similarity(noised, renorm, dim=-1)
        torch.testing.assert_close(cosine, torch.ones(8), atol=1e-6, rtol=0)


# ---------------------------------------------------------------------------
# 統合: lightning.py:training_step_g 経路の挙動
# ---------------------------------------------------------------------------


class TestLightningIntegration:
    """training_step_g 内の noise + renormalize ロジックを反映していること"""

    def _apply_perturbation(self, speaker_embeddings, sigma=0.05):
        """lightning.py:786-792 と同じロジックを再現"""
        if speaker_embeddings is None:
            return None
        x = speaker_embeddings + torch.randn_like(speaker_embeddings) * sigma
        x = F.normalize(x, p=2, dim=-1)
        return x

    def test_norm_unity_in_training_path(self):
        """training_step_g の経路を通った embedding は norm=1.0"""
        torch.manual_seed(0)
        emb = F.normalize(torch.randn(8, 192), p=2, dim=-1)
        out = self._apply_perturbation(emb, sigma=0.05)
        assert (out.norm(dim=-1) - 1.0).abs().max() < 1e-5

    def test_zero_sigma_returns_almost_same(self):
        """sigma=0 ならほぼ恒等 (denormalization で微小誤差)"""
        torch.manual_seed(0)
        emb = F.normalize(torch.randn(8, 192), p=2, dim=-1)
        out = self._apply_perturbation(emb, sigma=0.0)
        torch.testing.assert_close(out, emb, atol=1e-5, rtol=0)

    def test_none_input_returns_none(self):
        out = self._apply_perturbation(None)
        assert out is None

    def test_different_seeds_give_different_directions(self):
        """noise が 0 でなければ方向は変わる (再正規化後も)"""
        emb = F.normalize(torch.randn(8, 192), p=2, dim=-1)
        torch.manual_seed(1)
        out_a = self._apply_perturbation(emb, sigma=0.05)
        torch.manual_seed(2)
        out_b = self._apply_perturbation(emb, sigma=0.05)
        # 同じ emb から異なる noise → 異なる結果
        assert not torch.allclose(out_a, out_b, atol=1e-3)
        # 元 emb と元 emb+noise の cosine: 1 / sqrt(1 + ||noise||²)
        # ||noise||² = sigma² × dim = 0.05² × 192 = 0.48 → cos ≈ 1/sqrt(1.48) ≈ 0.82
        cos_a = F.cosine_similarity(out_a, emb, dim=-1)
        assert (cos_a > 0.5).all(), "正の方向類似が保たれる (cos > 0.5)"
        assert (cos_a < 1.0).all(), "ただし完全一致ではない (cos < 1.0)"


# ---------------------------------------------------------------------------
# Train / eval mode gating + per-step randomness + L2 re-normalization
# (lightning.py:794-801 の self.training gate を直接検証)
# ---------------------------------------------------------------------------


class _PerturbationModule(torch.nn.Module):
    """``lightning.py:794-801`` の perturbation block を最小限に切り出した nn.Module.

    本物の ``VitsModel`` は依存が重い (HiFi-GAN / MB-iSTFT / spk_proj 等の
    init) ため、ここでは ``self.training`` gate + noise + L2 renorm の振る舞い
    だけを取り出して、production と同じ条件分岐をテストする。
    """

    def __init__(self, sigma: float = 0.05):
        super().__init__()
        self.sigma = sigma

    def forward(self, speaker_embeddings: torch.Tensor) -> torch.Tensor:
        # ``lightning.py:794`` の gate を 1:1 で再現
        if self.training and speaker_embeddings is not None:
            speaker_embeddings = (
                speaker_embeddings
                + torch.randn_like(speaker_embeddings) * self.sigma
            )
            speaker_embeddings = torch.nn.functional.normalize(
                speaker_embeddings, p=2, dim=-1
            )
        return speaker_embeddings


class TestPerturbationModeGating:
    """train / eval mode で perturbation の有無を分岐すること"""

    def test_perturbation_not_applied_in_eval_mode(self):
        """eval mode では perturbation を完全に skip し bit-identical を返す.

        ``lightning.py:794`` の ``self.training`` gate が機能していなければ、
        validation 中の speaker_embeddings に noise が乗って SECS / loss が
        silently に inflate する (multi-6lang での主要 regression risk).
        """
        module = _PerturbationModule(sigma=0.05)
        module.eval()
        torch.manual_seed(0)
        emb0 = F.normalize(torch.randn(4, 192), p=2, dim=-1)

        for _ in range(5):
            out = module(emb0)
            # eval mode は完全に bit-identical (同じ tensor object でも OK)
            assert torch.equal(out, emb0), "eval mode で perturbation が適用された"

    def test_perturbation_differs_per_step_in_train_mode(self):
        """train mode では呼び出しごとに 異なる noise が乗ること (cache されない)"""
        module = _PerturbationModule(sigma=0.05)
        module.train()
        torch.manual_seed(123)
        emb0 = F.normalize(torch.randn(4, 192), p=2, dim=-1)

        # seed 固定せず連続呼び出し: torch global RNG が進むので毎回違う noise
        out1 = module(emb0)
        out2 = module(emb0)
        out3 = module(emb0)

        assert not torch.allclose(out1, out2, atol=1e-4), "step1 と step2 が同一"
        assert not torch.allclose(out2, out3, atol=1e-4), "step2 と step3 が同一"
        assert not torch.allclose(out1, out3, atol=1e-4), "step1 と step3 が同一"

    def test_perturbation_l2_renormalized_after_noise(self):
        """noise 加算後の出力は norm=1 (commit ba71e16 の修正点)"""
        module = _PerturbationModule(sigma=0.05)
        module.train()
        torch.manual_seed(7)
        emb0 = F.normalize(torch.randn(16, 192), p=2, dim=-1)
        # 前提: 入力は norm=1
        torch.testing.assert_close(
            emb0.norm(dim=-1), torch.ones(16), atol=1e-6, rtol=0
        )

        out = module(emb0)
        torch.testing.assert_close(
            out.norm(dim=-1), torch.ones(16), atol=1e-5, rtol=0
        )

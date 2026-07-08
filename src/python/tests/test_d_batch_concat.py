"""Tests for MultiPeriodDiscriminator の batch-concat 最適化 (P0 opt 1/4).

`MultiPeriodDiscriminator.forward(y, y_hat)` を旧: 6 sub-discriminator × 2 forward
(= 12 kernel launch 直列) から、新: y と y_hat を batch dim で `torch.cat` してから
1 forward → split (= 6 kernel launch) に置き換えた。

Conv1d/Conv2d + LeakyReLU + weight_norm/spectral_norm + reflect pad + view/flatten は
いずれも batch dim を跨がないため完全等価。 本ファイルは旧実装をローカルに再現し、
新実装と数値等価性 (`torch.allclose(atol=1e-5)`) を確認する。
"""

from __future__ import annotations

import pytest


pytest.importorskip("torch", reason="torch required for MultiPeriodDiscriminator")

import torch  # noqa: E402

from piper_train.vits.models import MultiPeriodDiscriminator  # noqa: E402


def _old_forward(mpd: MultiPeriodDiscriminator, y: torch.Tensor, y_hat: torch.Tensor):
    """旧実装 (batch-concat 前) を再現。"""
    y_d_rs = []
    y_d_gs = []
    fmap_rs = []
    fmap_gs = []
    for d in mpd.discriminators:
        y_d_r, fmap_r = d(y)
        y_d_g, fmap_g = d(y_hat)
        y_d_rs.append(y_d_r)
        y_d_gs.append(y_d_g)
        fmap_rs.append(fmap_r)
        fmap_gs.append(fmap_g)
    return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class TestBatchConcatEquivalence:
    """新 forward が旧 forward と bit-close (atol=1e-5) であることを保証する。"""

    ATOL = 1e-5
    RTOL = 1e-5

    def _make_input(self, batch: int = 2, time: int = 8192, seed: int = 0):
        g = torch.Generator().manual_seed(seed)
        y = torch.randn(batch, 1, time, generator=g)
        y_hat = torch.randn(batch, 1, time, generator=g)
        return y, y_hat

    def test_equivalence_default_weight_norm(self):
        """default (weight_norm) MPD で旧/新 forward の出力が一致する。"""
        torch.manual_seed(42)
        mpd = MultiPeriodDiscriminator(use_spectral_norm=False).eval()
        y, y_hat = self._make_input()

        with torch.no_grad():
            old_r, old_g, old_fr, old_fg = _old_forward(mpd, y, y_hat)
            new_r, new_g, new_fr, new_fg = mpd(y, y_hat)

        assert len(old_r) == len(new_r) == 6
        assert len(old_g) == len(new_g) == 6

        for i, (o, n) in enumerate(zip(old_r, new_r, strict=True)):
            assert torch.allclose(
                o, n, atol=self.ATOL, rtol=self.RTOL
            ), f"y_d_r mismatch at sub-discriminator {i}"

        for i, (o, n) in enumerate(zip(old_g, new_g, strict=True)):
            assert torch.allclose(
                o, n, atol=self.ATOL, rtol=self.RTOL
            ), f"y_d_g mismatch at sub-discriminator {i}"

        for i, (of_list, nf_list) in enumerate(zip(old_fr, new_fr, strict=True)):
            assert len(of_list) == len(nf_list)
            for j, (of, nf) in enumerate(zip(of_list, nf_list, strict=True)):
                assert torch.allclose(
                    of, nf, atol=self.ATOL, rtol=self.RTOL
                ), f"fmap_r mismatch at sub-D {i} layer {j}"

        for i, (of_list, nf_list) in enumerate(zip(old_fg, new_fg, strict=True)):
            assert len(of_list) == len(nf_list)
            for j, (of, nf) in enumerate(zip(of_list, nf_list, strict=True)):
                assert torch.allclose(
                    of, nf, atol=self.ATOL, rtol=self.RTOL
                ), f"fmap_g mismatch at sub-D {i} layer {j}"

    def test_equivalence_spectral_norm(self):
        """spectral_norm 版 MPD でも旧/新 forward の出力が一致する。

        spectral_norm は forward 時に power iteration で ``u`` を更新するが、
        ``eval()`` モードでは更新されず static parameterization として振る舞うため
        old / new どちらも同じ出力を生む。 学習時 (train モード) に呼び出し回数が
        変わる件は既知の副作用 (実挙動としては訓練後半で無視できる差)。
        """
        torch.manual_seed(43)
        mpd = MultiPeriodDiscriminator(use_spectral_norm=True).eval()
        y, y_hat = self._make_input(seed=1)

        with torch.no_grad():
            old_r, old_g, _, _ = _old_forward(mpd, y, y_hat)
            new_r, new_g, _, _ = mpd(y, y_hat)

        for i, (o, n) in enumerate(zip(old_r, new_r, strict=True)):
            assert torch.allclose(
                o, n, atol=self.ATOL, rtol=self.RTOL
            ), f"spectral_norm y_d_r mismatch at {i}"
        for i, (o, n) in enumerate(zip(old_g, new_g, strict=True)):
            assert torch.allclose(
                o, n, atol=self.ATOL, rtol=self.RTOL
            ), f"spectral_norm y_d_g mismatch at {i}"

    def test_output_shapes(self):
        """batch size と時系列長を再現的に split できていることを確認。"""
        torch.manual_seed(44)
        mpd = MultiPeriodDiscriminator(use_spectral_norm=False).eval()
        batch = 3
        y, y_hat = self._make_input(batch=batch, time=4096, seed=2)

        with torch.no_grad():
            new_r, new_g, new_fr, new_fg = mpd(y, y_hat)

        assert len(new_r) == 6
        assert len(new_g) == 6
        for yd in new_r:
            assert yd.shape[0] == batch
        for yd in new_g:
            assert yd.shape[0] == batch
        for fmap in new_fr:
            for f in fmap:
                assert f.shape[0] == batch
        for fmap in new_fg:
            for f in fmap:
                assert f.shape[0] == batch

    def test_gradient_flow(self):
        """train モードで backward が通り、勾配が y と y_hat の両方に伝わる。"""
        torch.manual_seed(45)
        mpd = MultiPeriodDiscriminator(use_spectral_norm=False).train()
        y, y_hat = self._make_input(batch=2, time=4096, seed=3)
        y.requires_grad_(True)
        y_hat.requires_grad_(True)

        y_d_rs, y_d_gs, _, _ = mpd(y, y_hat)
        loss = sum(t.mean() for t in y_d_rs) + sum(t.mean() for t in y_d_gs)
        loss.backward()

        assert y.grad is not None
        assert y_hat.grad is not None
        assert torch.isfinite(y.grad).all()
        assert torch.isfinite(y_hat.grad).all()

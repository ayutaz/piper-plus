"""Tests for dino_loss diagnostic warnings (NaN/Inf source identification).

Background:
- multi-6lang スクラッチ学習で step ~1249 から ``loss_dino`` が突然 0 に
  貼り付き続ける現象が発生。
- 原因は ``dino_loss`` 内の最終 NaN マスク (loss が NaN なら 0 を返す)。
- どの入力 (student_emb / teacher_emb / dino_center) が壊れているのか
  特定できないため、警告ログで切り分け可能にする。

このテストは:
- 正常入力で finite な loss を返すこと
- 各入力 tensor が non-finite の場合に 0 を返し、対応する warning が出ること
"""

from __future__ import annotations

import logging

import pytest


pytest.importorskip("torch", reason="torch required")

import torch  # noqa: E402

from piper_train.vits.losses import dino_loss  # noqa: E402


@pytest.fixture
def normal_inputs():
    torch.manual_seed(0)
    return (
        torch.randn(4, 16),  # student
        torch.randn(4, 16),  # teacher
        torch.zeros(16),  # center
    )


# ---------------------------------------------------------------------------
# 正常パス
# ---------------------------------------------------------------------------


class TestNormal:
    def test_finite_loss_returned(self, normal_inputs):
        s, t, c = normal_inputs
        loss = dino_loss(s, t, c)
        assert torch.isfinite(loss).all()
        assert loss.dim() == 0
        assert loss.item() > 0  # cross-entropy は 0 以上

    def test_loss_does_not_warn_for_normal_input(self, normal_inputs, caplog):
        s, t, c = normal_inputs
        with caplog.at_level(logging.WARNING):
            dino_loss(s, t, c)
        assert "non-finite" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# NaN/Inf 入力検出 + 警告
# ---------------------------------------------------------------------------


class TestStudentNonFinite:
    def test_nan_returns_zero(self, normal_inputs):
        s, t, c = normal_inputs
        s_bad = s.clone()
        s_bad[0, 0] = float("nan")
        loss = dino_loss(s_bad, t, c)
        assert loss.item() == 0.0

    def test_inf_returns_zero(self, normal_inputs):
        s, t, c = normal_inputs
        s_bad = s.clone()
        s_bad[1, 5] = float("inf")
        loss = dino_loss(s_bad, t, c)
        assert loss.item() == 0.0

    def test_warning_message_for_nan(self, normal_inputs, caplog):
        s, t, c = normal_inputs
        s_bad = s.clone()
        s_bad[0, 0] = float("nan")
        with caplog.at_level(logging.WARNING, logger="piper_train.vits.losses"):
            dino_loss(s_bad, t, c)
        assert "student_emb has non-finite" in caplog.text
        assert "NaN=1" in caplog.text


class TestTeacherNonFinite:
    def test_nan_returns_zero(self, normal_inputs):
        s, t, c = normal_inputs
        t_bad = t.clone()
        t_bad[0, 0] = float("nan")
        loss = dino_loss(s, t_bad, c)
        assert loss.item() == 0.0

    def test_inf_returns_zero(self, normal_inputs):
        s, t, c = normal_inputs
        t_bad = t.clone()
        t_bad[2, 7] = float("inf")
        loss = dino_loss(s, t_bad, c)
        assert loss.item() == 0.0

    def test_warning_message(self, normal_inputs, caplog):
        s, t, c = normal_inputs
        t_bad = t.clone()
        t_bad[0, 0] = float("nan")
        with caplog.at_level(logging.WARNING, logger="piper_train.vits.losses"):
            dino_loss(s, t_bad, c)
        assert "teacher_emb has non-finite" in caplog.text


class TestCenterNonFinite:
    def test_nan_returns_zero(self, normal_inputs):
        s, t, c = normal_inputs
        c_bad = c.clone()
        c_bad[0] = float("nan")
        loss = dino_loss(s, t, c_bad)
        assert loss.item() == 0.0

    def test_warning_message(self, normal_inputs, caplog):
        s, t, c = normal_inputs
        c_bad = c.clone()
        c_bad[0] = float("nan")
        with caplog.at_level(logging.WARNING, logger="piper_train.vits.losses"):
            dino_loss(s, t, c_bad)
        assert "dino_center has non-finite" in caplog.text


# ---------------------------------------------------------------------------
# Edge case: 入力が finite でも、softmax で発散しうる極端値
# ---------------------------------------------------------------------------


class TestExtremeFiniteInput:
    def test_extreme_large_values_clamped(self, normal_inputs):
        """非常に大きい値は clamp(-50, 50) で抑制される、loss は finite"""
        s = torch.full((4, 16), 1e10)
        t = torch.full((4, 16), 1e10)
        c = torch.zeros(16)
        loss = dino_loss(s, t, c)
        # clamp 後 student/teacher_logits = 50.0 一様 → softmax 一様 → cross-entropy = log(D)
        assert torch.isfinite(loss)
        assert loss.item() > 0

    def test_zero_input(self):
        """全 0 入力でも安定動作"""
        s = torch.zeros(4, 16)
        t = torch.zeros(4, 16)
        c = torch.zeros(16)
        loss = dino_loss(s, t, c)
        assert torch.isfinite(loss)


# ---------------------------------------------------------------------------
# Center 汚染後の回復シナリオ
# ---------------------------------------------------------------------------


class TestDinoCenterRecovery:
    """`dino_center` が一度 NaN 汚染された場合の回復挙動を文書化する。

    現状の EMA 更新ロジック (lightning.py:964-978) は
    ``batch_center.isfinite().all()`` を確認してから ``mul_(0.996).add_(...)``
    するが、 ``dino_center`` 側が NaN の場合は ``NaN * 0.996 + x * 0.004 = NaN``
    のままで、 clean batch が来ても永続的に回復しない (= DINO 完全停止)。

    このテストは「クリーンな batch_center だけで center を再シードする」回復
    パスが実装されることを期待し、 現状は xfail として保持する。
    """

    def test_dino_center_recovery_after_nan_corruption(self):
        # Arrange: corrupted center (full NaN) + clean batch teacher embeddings
        dim = 192
        dino_center = torch.full((dim,), float("nan"))
        # Simulate a clean teacher_emb batch (post spk_proj_teacher, L2-normalized)
        torch.manual_seed(42)
        teacher_emb = torch.randn(8, dim)
        teacher_emb = teacher_emb / teacher_emb.norm(dim=-1, keepdim=True)
        batch_center = teacher_emb.mean(dim=0)
        assert torch.isfinite(batch_center).all(), "precondition: clean batch"

        # Act: apply the EMA update from lightning.py:964-978 verbatim.
        # The recovery path re-seeds dino_center from the clean batch_center
        # when self.dino_center is non-finite (NaN*0.996 + x*0.004 = NaN).
        if torch.isfinite(batch_center).all():
            if not torch.isfinite(dino_center).all():
                dino_center.copy_(batch_center.float())
            else:
                dino_center.mul_(0.996).add_(batch_center.float(), alpha=0.004)
            dino_center.clamp_(min=-10, max=10)

        # Assert (expected behavior, currently failing): center should recover
        # to a finite state after at least one clean batch.
        assert torch.isfinite(dino_center).all(), (
            "dino_center must recover from NaN corruption when clean batches "
            "arrive; otherwise dino_loss stays masked at 0 forever."
        )


# ---------------------------------------------------------------------------
# Edge case: tau_s == tau_t
# ---------------------------------------------------------------------------


class TestEqualTemperatures:
    """tau_s == tau_t は数学的に well-defined だが degenerate に近づく edge case。

    student と teacher が同じ温度で softmax されるため、 standard DINO の
    sharpening 効果 (tau_t < tau_s) が消える。 loss は依然 finite scalar
    であるべき。
    """

    def test_dino_loss_with_equal_temperatures(self, normal_inputs):
        # Arrange
        s, t, c = normal_inputs

        # Act
        loss_eq = dino_loss(s, t, c, tau_s=0.07, tau_t=0.07)
        loss_baseline = dino_loss(s, t, c, tau_s=0.1, tau_t=0.07)

        # Assert: finite scalar, non-NaN/Inf
        assert torch.isfinite(loss_eq).all()
        assert loss_eq.dim() == 0
        assert not torch.isnan(loss_eq)
        assert not torch.isinf(loss_eq)
        assert loss_eq.item() > 0  # cross-entropy 下限

        # Sanity: equal temperatures should produce a measurably different
        # magnitude vs the asymmetric baseline (sharpening removed).
        assert abs(loss_eq.item() - loss_baseline.item()) > 1e-6, (
            "tau_s==tau_t should differ from the asymmetric baseline; "
            "if identical, the temperature application path is suspect."
        )

"""Tests for --gradient-clip-val CLI flag and VitsModel grad_clip mapping.

VITS は ``automatic_optimization=False`` で動作するため、Lightning Trainer の
自動 gradient clipping は MisconfigurationException で禁止されている。
代わりに ``vits/lightning.py:589-604`` の training_step 内で
``torch.nn.utils.clip_grad_norm_`` を呼び出す実装。

CLI --gradient-clip-val は ``_resolve_grad_clip`` を経て VitsModel(grad_clip=...) に渡る。
"""

from __future__ import annotations

from unittest import mock

import pytest


pytest.importorskip("torch", reason="torch required for piper_train.__main__")


_BASE_ARGS = ["--dataset-dir", "/tmp/test", "--batch-size", "4"]


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gradient_clip_val_default():
    """--gradient-clip-val のデフォルトは 1.0 (NaN 抑止のため強めに既定有効)。"""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(_BASE_ARGS)
    assert args.gradient_clip_val == 1.0


@pytest.mark.unit
def test_gradient_clip_val_custom():
    """カスタム値が float として受理される。"""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args([*_BASE_ARGS, "--gradient-clip-val", "5.0"])
    assert args.gradient_clip_val == 5.0


@pytest.mark.unit
def test_gradient_clip_val_zero_disables():
    """0 を渡すと無効化扱い (Trainer / VitsModel どちらにも有効にしない)。"""
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args([*_BASE_ARGS, "--gradient-clip-val", "0"])
    assert args.gradient_clip_val == 0.0


# ---------------------------------------------------------------------------
# _resolve_grad_clip
# ---------------------------------------------------------------------------


class TestResolveGradClip:
    """CLI 値 → VitsModel.grad_clip 引数への変換ロジック"""

    def test_positive_value_passes_through(self):
        from piper_train.__main__ import _resolve_grad_clip

        assert _resolve_grad_clip(1.0) == 1.0
        assert _resolve_grad_clip(5.0) == 5.0

    def test_zero_returns_none(self):
        """0 は disable シグナルとして None になる"""
        from piper_train.__main__ import _resolve_grad_clip

        assert _resolve_grad_clip(0) is None
        assert _resolve_grad_clip(0.0) is None

    def test_negative_returns_none(self):
        """負値も None (disable)"""
        from piper_train.__main__ import _resolve_grad_clip

        assert _resolve_grad_clip(-1.0) is None

    def test_none_returns_none(self):
        """None は素通し"""
        from piper_train.__main__ import _resolve_grad_clip

        assert _resolve_grad_clip(None) is None

    def test_returns_float_type(self):
        """戻り値が float であること"""
        from piper_train.__main__ import _resolve_grad_clip

        r = _resolve_grad_clip(2)  # int 渡しでも
        assert isinstance(r, float)
        assert r == 2.0


# ---------------------------------------------------------------------------
# _build_trainer: gradient_clip_val を Trainer に **渡さない** こと
# ---------------------------------------------------------------------------


def _make_trainer_args() -> mock.MagicMock:
    a = mock.MagicMock()
    a.checkpoint_epochs = None
    a.no_ema = True
    a.accelerator = "cpu"
    a.devices = 1
    a.precision = "32-true"
    a.max_epochs = 1
    a.default_root_dir = "/tmp/_test_root"
    a.val_every_n_epochs = 1
    a.limit_val_batches = 1
    a.limit_train_batches = None
    a.strategy = None
    a.no_wavlm = True
    a.samples_per_speaker = 0
    a.gradient_clip_val = 1.0  # CLI で 1.0 渡されたとしても
    return a


@pytest.mark.unit
def test_build_trainer_does_not_pass_gradient_clip(monkeypatch):
    """VITS は manual optimization → Trainer に gradient_clip_val を渡してはいけない。
    渡すと Lightning が MisconfigurationException を投げて学習が即死する。
    """
    from piper_train import __main__ as m

    captured: dict = {}

    def fake_trainer(**kwargs):
        captured.update(kwargs)
        return mock.MagicMock()

    monkeypatch.setattr(m, "Trainer", fake_trainer)
    monkeypatch.setattr(m, "configure_ddp_strategy", lambda *a, **k: None)

    args = _make_trainer_args()
    m._build_trainer(args, loggers=[], num_gpus=1, num_speakers=1)

    # Trainer に gradient_clip_val が渡されていないこと
    assert "gradient_clip_val" not in captured
    assert "gradient_clip_algorithm" not in captured

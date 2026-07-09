"""Regression test: training_step must NOT call ``torch.cuda.empty_cache()``.

Historically the training loop invoked
``torch.cuda.synchronize()`` + ``torch.cuda.empty_cache()`` every 500 batches
as a fragmentation workaround for T4/V100 (16GB) era GPUs. On A100 SXM4 80GB /
H100 with ``PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`` this flush
merely stalls the GPU (a few hundred ms to several seconds) and yields no
measurable memory benefit — see 2026-07-09 lightning.py cleanup.

This test pins the current behaviour so nobody re-introduces the flush by
accident (e.g. copy-pasting the old block). We drive ``training_step`` for a
range of ``batch_idx`` values (including 0 and multiples of 500 — the old
trigger points) via the same fake-self harness used by
``tests/test_ddp_synced_finite.py`` and assert that neither
``torch.cuda.empty_cache`` nor ``torch.cuda.synchronize`` fires.
"""

from __future__ import annotations

from unittest import mock

import pytest


pytest.importorskip("torch", reason="torch required for VitsModel")

import torch  # noqa: E402

from piper_train.vits.lightning import VitsModel  # noqa: E402


# ---------------------------------------------------------------------------
# Fake-self harness (mirrors test_ddp_synced_finite._make_fake_model)
# ---------------------------------------------------------------------------


class _FakeHparams:
    def __init__(self, d_update_interval: int = 1):
        self.d_update_interval = d_update_interval
        self.grad_clip = None


class _FakeOpt:
    def __init__(self):
        self.zero_grad_calls = 0
        self.step_calls = 0

    def zero_grad(self, set_to_none: bool = False):
        self.zero_grad_calls += 1

    def step(self):
        self.step_calls += 1


class _FakeBatch:
    def __init__(self):
        self.phoneme_ids = torch.zeros(2, 4, dtype=torch.long)
        self.phoneme_lengths = torch.tensor([4, 4])
        self.audio_lengths = torch.tensor([100, 100])
        self.spectrogram_lengths = torch.tensor([20, 20])


def _make_fake_model(loss_g: float = 1.0, loss_d: float = 0.5):
    fake = mock.MagicMock()
    fake.hparams = _FakeHparams(d_update_interval=1)
    fake.global_step = 0
    fake._y = None
    fake._y_hat = None

    opt_g = _FakeOpt()
    opt_d = _FakeOpt()
    fake.optimizers = mock.MagicMock(return_value=(opt_g, opt_d))
    fake._opt_g = opt_g
    fake._opt_d = opt_d

    # Static method → bind as plain callable.
    fake._ddp_synced_is_finite = VitsModel._ddp_synced_is_finite

    def fake_training_step_g(batch):
        fake._y_hat = torch.zeros(1, 1, 8)
        fake._y = torch.zeros(1, 1, 8)
        return torch.tensor(loss_g)

    def fake_training_step_d(batch):
        return torch.tensor(loss_d)

    fake.training_step_g = fake_training_step_g
    fake.training_step_d = fake_training_step_d
    fake.manual_backward = mock.MagicMock()
    fake._log_with_batch_info = mock.MagicMock()
    fake.model_g = mock.MagicMock()
    fake.model_d = mock.MagicMock()
    fake.model_d_wavlm = None
    return fake


# ---------------------------------------------------------------------------
# Regression assertions
# ---------------------------------------------------------------------------


class TestNoEmptyCacheFlush:
    """The 500-batch flush must stay gone."""

    @pytest.mark.parametrize(
        "batch_idx",
        [
            0,       # old trigger: batch_idx % 500 == 0 at batch 0
            500,     # old trigger: exact period boundary
            1000,    # old trigger: second period boundary
            499,     # not on old boundary (control)
            1234,    # arbitrary mid-period (control)
        ],
    )
    def test_no_flush_across_500_boundary(self, monkeypatch, batch_idx):
        """training_step must never invoke empty_cache / synchronize, even at
        batch indices that previously triggered the periodic flush."""
        empty_cache_calls = []
        synchronize_calls = []

        # Pretend CUDA is available so the old ``if torch.cuda.is_available():``
        # guard would have entered.
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        monkeypatch.setattr(
            torch.cuda,
            "empty_cache",
            lambda: empty_cache_calls.append(True),
        )
        monkeypatch.setattr(
            torch.cuda,
            "synchronize",
            lambda *a, **kw: synchronize_calls.append((a, kw)),
        )

        fake = _make_fake_model()
        batch = _FakeBatch()
        fake.global_step = batch_idx
        VitsModel.training_step(fake, batch, batch_idx=batch_idx)

        assert empty_cache_calls == [], (
            f"training_step invoked torch.cuda.empty_cache() at "
            f"batch_idx={batch_idx}; the 500-batch periodic flush must "
            "stay removed (2026-07-09 perf cleanup)."
        )
        assert synchronize_calls == [], (
            f"training_step invoked torch.cuda.synchronize() at "
            f"batch_idx={batch_idx}; the 500-batch periodic flush must "
            "stay removed (2026-07-09 perf cleanup)."
        )

    def test_no_flush_across_many_steps(self, monkeypatch):
        """Drive a small run that crosses two 500-batch boundaries and assert
        zero flushes for the entire range."""
        empty_cache_calls = []
        synchronize_calls = []

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        monkeypatch.setattr(
            torch.cuda,
            "empty_cache",
            lambda: empty_cache_calls.append(True),
        )
        monkeypatch.setattr(
            torch.cuda,
            "synchronize",
            lambda *a, **kw: synchronize_calls.append((a, kw)),
        )

        fake = _make_fake_model()
        batch = _FakeBatch()

        # Simulate batches that used to include two flush triggers (0, 500)
        # plus a control batch in the middle.
        for step in (0, 1, 499, 500, 501, 999, 1000):
            fake.global_step = step
            VitsModel.training_step(fake, batch, batch_idx=step)

        assert empty_cache_calls == [], (
            "empty_cache must not fire across the simulated 0..1000 batch run"
        )
        assert synchronize_calls == [], (
            "synchronize must not fire across the simulated 0..1000 batch run"
        )

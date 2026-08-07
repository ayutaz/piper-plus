"""Tests for the KL-cap sticking guard (VitsModel._update_kl_cap_guard).

2026-08 v8 incident: corrupt MAS alignments kept the *raw* KL loss pinned at
the 1e4 safety cap from step ~30 to the end of an 80-epoch run, while every
other health signal (non_finite_skip=0%, decreasing mel) looked normal — the
cap masks divergence from the non-finite skip machinery by design. The guard
watches the raw (pre-clamp, pre-weight) KL value and aborts the run after N
consecutive capped steps, because such a run is unrecoverable garbage and
continuing it only burns GPU hours.

The guard is a plain-attribute method, so it is exercised here through a
SimpleNamespace stand-in without constructing the full LightningModule.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


pytest.importorskip("torch", reason="torch required for lightning import")

from piper_train.vits import lightning as vits_lightning  # noqa: E402
from piper_train.vits.lightning import VitsModel  # noqa: E402


def _make_stub(abort_steps: int = 300, consecutive: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        _kl_cap_consecutive=consecutive,
        _kl_cap_abort_steps=abort_steps,
        global_step=123,
    )


class TestCounter:
    """Consecutive-capped-step counting semantics."""

    def test_below_cap_resets_counter(self):
        stub = _make_stub(consecutive=10)
        VitsModel._update_kl_cap_guard(stub, 5.0)
        assert stub._kl_cap_consecutive == 0

    def test_capped_steps_accumulate(self):
        stub = _make_stub()
        for _ in range(5):
            VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
        assert stub._kl_cap_consecutive == 5

    def test_intermittent_cap_never_accumulates(self):
        """A healthy warmup (occasional cap hits) must not trip the guard."""
        stub = _make_stub(abort_steps=3)
        for _ in range(10):
            VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
            VitsModel._update_kl_cap_guard(stub, 50.0)
        assert stub._kl_cap_consecutive == 0

    def test_nan_does_not_count_as_capped(self):
        """NaN is the non-finite skip machinery's job, not the cap guard's."""
        stub = _make_stub(consecutive=7)
        VitsModel._update_kl_cap_guard(stub, float("nan"))
        assert stub._kl_cap_consecutive == 0

    def test_value_above_cap_counts(self):
        """The clamp means raw values above the cap are equally 'pinned'."""
        stub = _make_stub()
        VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP * 100)
        assert stub._kl_cap_consecutive == 1


class TestAbort:
    """RuntimeError abort at the consecutive threshold."""

    def test_abort_at_threshold(self):
        stub = _make_stub(abort_steps=3)
        VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
        VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
        with pytest.raises(RuntimeError, match="pinned"):
            VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)

    def test_no_abort_below_threshold(self):
        stub = _make_stub(abort_steps=300)
        for _ in range(299):
            VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
        assert stub._kl_cap_consecutive == 299

    def test_zero_disables_abort(self):
        """PIPER_PLUS_KL_CAP_ABORT_STEPS=0 => never raise (logs still fire)."""
        stub = _make_stub(abort_steps=0)
        for _ in range(1000):
            VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
        assert stub._kl_cap_consecutive == 1000

    def test_error_logged_periodically(self, caplog):
        """A loud ERROR fires every 50 consecutive capped steps."""
        stub = _make_stub(abort_steps=0)
        with caplog.at_level("ERROR", logger="vits.lightning"):
            for _ in range(100):
                VitsModel._update_kl_cap_guard(stub, vits_lightning._KL_CAP)
        errors = [r for r in caplog.records if "pinned" in r.getMessage()]
        assert len(errors) == 2, "expected ERROR at steps 50 and 100"


class TestEnvParsing:
    """PIPER_PLUS_KL_CAP_ABORT_STEPS parsing."""

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("PIPER_PLUS_KL_CAP_ABORT_STEPS", raising=False)
        assert (
            vits_lightning._kl_cap_abort_steps_from_env()
            == vits_lightning._KL_CAP_ABORT_DEFAULT
        )

    def test_explicit_value(self, monkeypatch):
        monkeypatch.setenv("PIPER_PLUS_KL_CAP_ABORT_STEPS", "42")
        assert vits_lightning._kl_cap_abort_steps_from_env() == 42

    def test_zero_disables(self, monkeypatch):
        monkeypatch.setenv("PIPER_PLUS_KL_CAP_ABORT_STEPS", "0")
        assert vits_lightning._kl_cap_abort_steps_from_env() == 0

    def test_invalid_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("PIPER_PLUS_KL_CAP_ABORT_STEPS", "not-a-number")
        assert (
            vits_lightning._kl_cap_abort_steps_from_env()
            == vits_lightning._KL_CAP_ABORT_DEFAULT
        )

"""strict resume (--resume_from_checkpoint) は失敗時に weights-only へ黙って
切り替えない。weights-only 読込は --resume-weights-only だけが行う。"""

from __future__ import annotations

from pickle import UnpicklingError

import pytest


pytest.importorskip("torch")

from piper_train.__main__ import run_strict_resume  # noqa: E402


class FakeTrainer:
    def __init__(self, raises=None):
        self.raises = raises
        self.fit_calls = []

    def fit(self, model, ckpt_path=None):
        self.fit_calls.append(ckpt_path)
        if self.raises is not None:
            raise self.raises


class FakeModel:
    def __init__(self):
        self.load_state_dict_calls = []
        self.reset_calls = 0

    def load_state_dict(self, *args, **kwargs):
        self.load_state_dict_calls.append((args, kwargs))

    def _reset_training_progress(self):
        self.reset_calls += 1


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("size mismatch"),
        KeyError("optimizer_states"),
        NotImplementedError("x"),
        UnpicklingError("x"),
    ],
)
def test_strict_resume_failure_does_not_fall_back(tmp_path, exc):
    trainer = FakeTrainer(raises=exc)
    model = FakeModel()
    with pytest.raises(SystemExit, match="--resume-weights-only") as ei:
        run_strict_resume(trainer, model, str(tmp_path / "x.ckpt"))
    assert ei.value.__cause__ is exc
    assert model.load_state_dict_calls == []
    assert model.reset_calls == 0
    assert len(trainer.fit_calls) == 1


def test_strict_resume_success_passes_ckpt_path(tmp_path):
    trainer = FakeTrainer()
    model = FakeModel()
    path = str(tmp_path / "x.ckpt")
    run_strict_resume(trainer, model, path)
    assert trainer.fit_calls == [path]
    assert model.load_state_dict_calls == []

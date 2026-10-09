"""Fixed-reference monitoring through the real Lightning loading/logging hooks."""

import copy
import json
import random
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="inference monitoring requires torch")
pl = pytest.importorskip("pytorch_lightning", reason="tests exercise Lightning hooks")
from piper_train.vits import lightning  # noqa: E402


pytestmark = pytest.mark.unit


class Generator(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.dec = torch.nn.Linear(1, 1)
        self.spk_proj = torch.nn.Linear(192, 1)
        self.register_buffer("dino_center", torch.zeros(1))
        self.calls = []

    def infer(self, text, lengths, **kwargs):
        self.calls.append(
            {"training": self.training, "grad": torch.is_grad_enabled(), **kwargs}
        )
        random.random()
        np.random.random()
        return (torch.randn(1, 1, 32) * self.dec.weight,)


class Monitor(lightning.VitsModel):
    def __init__(self, directory):
        pl.LightningModule.__init__(self)
        self.save_hyperparameters(
            {
                "dataset_dir": directory,
                "num_speakers": 2,
                "use_zero_shot": True,
                "spk_embed_dim": 192,
                "audio_log_epochs": 1,
                "sample_rate": 22050,
                "seed": 42,
            }
        )
        self.model_g = Generator()
        self._trainer = SimpleNamespace(
            is_global_zero=True, world_size=1, current_epoch=0, global_step=5
        )
        self.logger_stub = SimpleNamespace(experiment=MagicMock())
        self.training_batches_seen = 17
        self.generator_updates = 9
        self.discriminator_updates = 17
        self._kl_cap_consecutive = 2

    def _get_wandb_logger(self):
        return self.logger_stub


def write_test_set(tmp_path, extra):
    row = {
        "id": "fixed-1",
        "text": "こんにちは",
        "phoneme_ids": [1, 10, 10, 2],
        "language_id": 0,
        **extra,
    }
    path = tmp_path / "test_utterances.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("inline", [False, True])
def test_fixed_test_loader_keeps_validated_reference(tmp_path, inline):
    vector = np.arange(1, 193, dtype=np.float32)
    np.save(tmp_path / "reference.npy", vector)
    path = write_test_set(
        tmp_path,
        {"speaker_embedding": vector.tolist()}
        if inline
        else {"speaker_embedding_path": "reference.npy"},
    )
    model = Monitor(tmp_path)
    utterance = model._load_test_dataset(path)[0]
    assert utterance.utterance_id == "fixed-1"
    assert utterance.speaker_embedding.shape == (192,)
    assert utterance.speaker_embedding.norm().item() == pytest.approx(1)


@pytest.mark.parametrize("bad", ["missing.npy", "zero.npy", "nan.npy"])
def test_fixed_test_loader_rejects_invalid_explicit_reference(tmp_path, bad):
    if bad != "missing.npy":
        np.save(
            tmp_path / bad, np.zeros(192) if bad == "zero.npy" else np.full(192, np.nan)
        )
    model = Monitor(tmp_path)
    path = write_test_set(tmp_path, {"speaker_embedding_path": bad})
    with pytest.raises(ValueError, match="speaker_embedding"):
        model._load_test_dataset(path)


def test_monitor_uses_reference_predicted_infer_and_restores_state(
    tmp_path, monkeypatch
):
    model = Monitor(tmp_path)
    np.save(tmp_path / "reference.npy", np.ones(192))
    model._test_dataset = model._load_test_dataset(
        write_test_set(tmp_path, {"speaker_embedding_path": "reference.npy"})
    )
    monkeypatch.setattr(lightning, "WANDB_AVAILABLE", True)
    audio_items = []

    def audio(values, **kwargs):
        audio_items.append({"values": values, **kwargs})
        return audio_items[-1]

    monkeypatch.setattr(
        lightning, "wandb", SimpleNamespace(Audio=audio, Table=lambda **kwargs: kwargs)
    )
    model.model_g.train()
    model.model_g.spk_proj.eval()
    before_weights = copy.deepcopy(model.state_dict())
    before_torch = torch.random.get_rng_state().clone()
    before_numpy = np.random.get_state()
    before_random = random.getstate()
    model.on_validation_epoch_end()
    call = model.model_g.calls[0]
    assert not call["training"] and not call["grad"]
    assert call["speaker_embeddings"].norm().item() == pytest.approx(1)
    assert "f0" not in call and "duration" not in call
    assert model.model_g.training and not model.model_g.spk_proj.training
    assert torch.equal(before_torch, torch.random.get_rng_state())
    assert random.getstate() == before_random
    np.testing.assert_array_equal(np.random.get_state()[1], before_numpy[1])
    assert np.random.get_state()[2:] == before_numpy[2:]
    for name, value in model.state_dict().items():
        assert torch.equal(value, before_weights[name]), name
    assert (
        model.training_batches_seen,
        model.generator_updates,
        model.discriminator_updates,
        model._kl_cap_consecutive,
    ) == (17, 9, 17, 2)
    assert "zero-shot" in audio_items[0]["caption"]


def test_monitor_labels_missing_reference_and_display_normalization(
    tmp_path, monkeypatch
):
    model = Monitor(tmp_path)
    model._test_dataset = model._load_test_dataset(write_test_set(tmp_path, {}))
    monkeypatch.setattr(lightning, "WANDB_AVAILABLE", True)
    audio = MagicMock()
    monkeypatch.setattr(
        lightning, "wandb", SimpleNamespace(Audio=audio, Table=lambda **kwargs: kwargs)
    )
    model.on_validation_epoch_end()
    caption = audio.call_args.kwargs["caption"]
    assert "no-reference" in caption and "display-normalized" in caption


def test_fixed_reference_is_not_silently_ignored_when_conditioning_is_disabled(
    tmp_path,
):
    model = Monitor(tmp_path)
    model.hparams.use_zero_shot = False
    path = write_test_set(tmp_path, {"speaker_embedding": np.ones(192).tolist()})
    with pytest.raises(ValueError, match="speaker_embedding"):
        model._load_test_dataset(path)


def test_monitor_passes_fixed_prosody_to_infer(tmp_path, monkeypatch):
    model = Monitor(tmp_path)
    prosody = [{"a1": -1, "a2": 1, "a3": 3}] * 4
    model._test_dataset = model._load_test_dataset(
        write_test_set(
            tmp_path,
            {"speaker_embedding": np.ones(192).tolist(), "prosody_features": prosody},
        )
    )
    monkeypatch.setattr(lightning, "WANDB_AVAILABLE", True)
    monkeypatch.setattr(
        lightning,
        "wandb",
        SimpleNamespace(Audio=MagicMock(), Table=lambda **kwargs: kwargs),
    )
    model.on_validation_epoch_end()
    passed = model.model_g.calls[0]["prosody_features"]
    assert passed.shape == (1, 4, 3) and passed.dtype == torch.int64
    assert passed[0, 0].tolist() == [-1, 1, 3]


def test_monitor_restores_state_when_infer_fails(tmp_path, monkeypatch):
    model = Monitor(tmp_path)
    model._test_dataset = model._load_test_dataset(
        write_test_set(tmp_path, {"speaker_embedding": np.ones(192).tolist()})
    )
    model.model_g.spk_proj.eval()
    modes = [child.training for child in model.model_g.modules()]
    weights = copy.deepcopy(model.state_dict())
    rng, numpy_rng, python_rng = (
        torch.random.get_rng_state().clone(),
        np.random.get_state(),
        random.getstate(),
    )
    original = model.model_g.infer

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("fixture monitoring failure")

    monkeypatch.setattr(model.model_g, "infer", fail)
    monkeypatch.setattr(lightning, "WANDB_AVAILABLE", True)
    monkeypatch.setattr(
        lightning,
        "wandb",
        SimpleNamespace(Audio=MagicMock(), Table=lambda **kwargs: kwargs),
    )
    model.on_validation_epoch_end()
    assert not model.logger_stub.experiment.log.called
    assert modes == [child.training for child in model.model_g.modules()]
    assert (
        torch.equal(rng, torch.random.get_rng_state())
        and python_rng == random.getstate()
    )
    np.testing.assert_array_equal(numpy_rng[1], np.random.get_state()[1])
    assert numpy_rng[2:] == np.random.get_state()[2:]
    for name, value in model.state_dict().items():
        assert torch.equal(value, weights[name]), name
    assert (
        model.training_batches_seen,
        model.generator_updates,
        model.discriminator_updates,
        model._kl_cap_consecutive,
    ) == (17, 9, 17, 2)

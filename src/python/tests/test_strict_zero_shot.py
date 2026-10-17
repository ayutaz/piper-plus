"""Strict research recipes reject silent SCL and same-utterance fallbacks."""

from types import SimpleNamespace

import pytest
import torch


def test_strict_recipe_requires_existing_differentiable_encoder(tmp_path):
    from piper_train.zero_shot_requirements import validate_recipe

    settings = {
        "use_zero_shot": True,
        "c_spk": 1.0,
        "spk_loss_type": "infonce",
        "spk_loss_positives": "cross_utt",
        "speaker_encoder_torch_path": tmp_path / "missing.bin",
    }
    with pytest.raises(ValueError, match="encoder"):
        validate_recipe(**settings)
    settings["speaker_encoder_torch_path"].write_bytes(b"unit-test-weights-placeholder")
    validate_recipe(**settings)
    settings["spk_loss_positives"] = "same_utt"
    with pytest.raises(ValueError, match="cross_utt"):
        validate_recipe(**settings)


@pytest.mark.parametrize(
    "speakers,utterances",
    [
        ([1, 2], ["a", "b"]),
        ([1, 1], ["a", "a"]),
        ([1, 1, 2], ["a", "b", "c"]),
        (None, ["a", "b"]),
        ([1, 1], None),
    ],
)
def test_strict_batch_rejects_missing_cross_utterance_positives(speakers, utterances):
    from piper_train.zero_shot_requirements import validate_training_batch

    batch = SimpleNamespace(
        speaker_ids=None if speakers is None else torch.tensor(speakers),
        utterance_ids=utterances,
        speaker_embeddings=torch.ones(len(utterances or speakers), 192),
    )
    with pytest.raises(ValueError):
        validate_training_batch(batch)


def test_strict_batch_requires_valid_embeddings_and_reports_positive_counts():
    from piper_train.zero_shot_requirements import validate_training_batch

    batch = SimpleNamespace(
        speaker_ids=torch.tensor([1, 1, 2, 2]),
        utterance_ids=["a", "b", "c", "d"],
        speaker_embeddings=torch.ones(4, 192),
    )
    assert validate_training_batch(batch) == {
        "anchors": 4,
        "min_positives": 1,
        "fallbacks": 0,
    }
    batch.speaker_embeddings[0] = 0
    with pytest.raises(ValueError, match="embedding"):
        validate_training_batch(batch)


def test_collation_keeps_utterance_identity_for_strict_batch_checks():
    from piper_train.vits.dataset import UtteranceCollate, UtteranceTensors

    items = [
        UtteranceTensors(
            phoneme_ids=torch.tensor([1, 2]),
            audio_norm=torch.ones(1, 256),
            spectrogram=torch.ones(513, 1),
            speaker_id=torch.tensor([1]),
            speaker_embedding=torch.ones(192),
            utterance_id=name,
        )
        for name in ["a", "b"]
    ]
    batch = UtteranceCollate(segment_size=256, is_multispeaker=True)(items)
    assert set(batch.utterance_ids) == {"a", "b"}


def test_invalid_peer_batch_fails_every_rank_before_optimizer_work(monkeypatch):
    from piper_train.zero_shot_requirements import validate_training_batch

    monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
    monkeypatch.setattr(torch.distributed, "is_initialized", lambda: True)
    monkeypatch.setattr(torch.distributed, "get_world_size", lambda: 2)

    def gather(result, local):
        result[:] = [
            local,
            {
                "speakers": [2],
                "utterances": ["peer-only"],
                "embeddings_valid": True,
                "embedding_count": 1,
            },
        ]

    monkeypatch.setattr(torch.distributed, "all_gather_object", gather)
    batch = SimpleNamespace(
        speaker_ids=torch.tensor([1, 1]),
        utterance_ids=["a", "b"],
        speaker_embeddings=torch.ones(2, 192),
    )
    with pytest.raises(ValueError, match="positive"):
        validate_training_batch(batch, gather=False)

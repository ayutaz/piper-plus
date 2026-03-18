"""Tests for PiperDataset.__getitem__ thread safety and correctness.

Ensures that __getitem__ does not mutate self.utterances (required for num_workers>0).
"""

import numpy as np
import pytest


torch = pytest.importorskip("torch")

from piper_train.vits.dataset import (  # noqa: E402
    PiperDataset,
    Utterance,
    UtteranceCollate,
    UtteranceTensors,
)


def _make_utterance(tmp_path, speaker_id=0, language_id=0, text="test"):
    """Create a valid Utterance with real tensor files on disk."""
    audio_norm = torch.randn(1, 8192)
    spectrogram = torch.randn(80, 32)

    audio_path = tmp_path / f"audio_{speaker_id}_{id(text)}.pt"
    spec_path = tmp_path / f"spec_{speaker_id}_{id(text)}.pt"
    torch.save(audio_norm, audio_path)
    torch.save(spectrogram, spec_path)

    return Utterance(
        phoneme_ids=np.array([1, 8, 5, 39, 25, 0, 15, 22], dtype=np.int16),
        audio_norm_path=audio_path,
        audio_spec_path=spec_path,
        speaker_id=speaker_id,
        language_id=language_id,
        text=text,
    )


def _make_utterance_with_prosody(tmp_path, speaker_id=0):
    """Create a valid Utterance with prosody features."""
    audio_norm = torch.randn(1, 8192)
    spectrogram = torch.randn(80, 32)

    audio_path = tmp_path / f"audio_prosody_{speaker_id}.pt"
    spec_path = tmp_path / f"spec_prosody_{speaker_id}.pt"
    torch.save(audio_norm, audio_path)
    torch.save(spectrogram, spec_path)

    phoneme_ids = np.array([1, 8, 5, 39, 25], dtype=np.int16)
    prosody_features = np.array(
        [
            [-2, 1, 5],
            [-1, 2, 5],
            [0, 3, 5],
            [1, 4, 5],
            [2, 5, 5],
        ],
        dtype=np.int16,
    )

    return Utterance(
        phoneme_ids=phoneme_ids,
        audio_norm_path=audio_path,
        audio_spec_path=spec_path,
        speaker_id=speaker_id,
        prosody_features=prosody_features,
        text="test prosody",
    )


def _make_dataset_with_utterances(utterances):
    """Create a PiperDataset and inject utterances directly (bypass file loading)."""
    dataset = PiperDataset.__new__(PiperDataset)
    dataset.utterances = list(utterances)
    return dataset


@pytest.mark.unit
def test_getitem_returns_utterance_tensors(tmp_path):
    """Normal index returns UtteranceTensors with correct fields."""
    utt = _make_utterance(tmp_path, speaker_id=3, language_id=1, text="hello")
    dataset = _make_dataset_with_utterances([utt])

    result = dataset[0]

    assert isinstance(result, UtteranceTensors)
    assert result.phoneme_ids.tolist() == utt.phoneme_ids.tolist()
    assert result.speaker_id is not None
    assert result.speaker_id.item() == 3
    assert result.language_id is not None
    assert result.language_id.item() == 1
    assert result.text == "hello"
    assert result.spectrogram.shape[0] == 80
    assert result.audio_norm.shape[0] == 1


@pytest.mark.unit
def test_getitem_invalid_file_raises(tmp_path):
    """Invalid file path raises an exception instead of silently mutating the list."""
    utt = Utterance(
        phoneme_ids=np.array([1, 2, 3], dtype=np.int16),
        audio_norm_path=tmp_path / "nonexistent_audio.pt",
        audio_spec_path=tmp_path / "nonexistent_spec.pt",
        speaker_id=0,
    )
    dataset = _make_dataset_with_utterances([utt])

    with pytest.raises(FileNotFoundError):
        dataset[0]


@pytest.mark.unit
def test_getitem_does_not_mutate_utterances_list(tmp_path):
    """__getitem__ must not modify self.utterances (thread safety for num_workers>0)."""
    utt_good = _make_utterance(tmp_path, speaker_id=0, text="good")
    utt_bad = Utterance(
        phoneme_ids=np.array([1, 2], dtype=np.int16),
        audio_norm_path=tmp_path / "bad_audio.pt",
        audio_spec_path=tmp_path / "bad_spec.pt",
        speaker_id=1,
    )
    utt_good2 = _make_utterance(tmp_path, speaker_id=2, text="good2")

    dataset = _make_dataset_with_utterances([utt_good, utt_bad, utt_good2])
    original_len = len(dataset)

    # Access good items
    dataset[0]
    dataset[2]

    # Access bad item should raise, NOT shrink the list
    with pytest.raises(FileNotFoundError):
        dataset[1]

    assert len(dataset) == original_len, (
        f"utterances list was mutated: expected {original_len}, got {len(dataset)}. "
        "__getitem__ must not call self.utterances.pop() for thread safety."
    )


@pytest.mark.unit
def test_getitem_with_prosody_features(tmp_path):
    """Prosody features are correctly converted to tensor."""
    utt = _make_utterance_with_prosody(tmp_path, speaker_id=5)
    dataset = _make_dataset_with_utterances([utt])

    result = dataset[0]

    assert result.prosody_features is not None
    assert result.prosody_features.shape == (
        5,
        3,
    )  # 5 phonemes, 3 features (a1, a2, a3)
    assert result.prosody_features[0].tolist() == [-2, 1, 5]
    assert result.prosody_features[4].tolist() == [2, 5, 5]


@pytest.mark.unit
def test_getitem_without_prosody_features(tmp_path):
    """Utterance without prosody features returns None for prosody_tensor."""
    utt = _make_utterance(tmp_path)
    dataset = _make_dataset_with_utterances([utt])

    result = dataset[0]

    assert result.prosody_features is None


@pytest.mark.unit
def test_getitem_without_speaker_id(tmp_path):
    """Utterance without speaker_id returns None."""
    audio_norm = torch.randn(1, 8192)
    spectrogram = torch.randn(80, 32)
    audio_path = tmp_path / "audio_no_spk.pt"
    spec_path = tmp_path / "spec_no_spk.pt"
    torch.save(audio_norm, audio_path)
    torch.save(spectrogram, spec_path)

    utt = Utterance(
        phoneme_ids=np.array([1, 2, 3], dtype=np.int16),
        audio_norm_path=audio_path,
        audio_spec_path=spec_path,
        speaker_id=None,
    )
    dataset = _make_dataset_with_utterances([utt])

    result = dataset[0]
    assert result.speaker_id is None


@pytest.mark.unit
def test_collate_non_multilanguage_with_language_id(tmp_path):
    """language_id付きデータをis_multilanguage=Falseで処理してもassertで落ちない.

    Regression test: UtteranceCollate(is_multilanguage=False) must not crash
    when utterances carry a non-None language_id.  The collate should simply
    ignore the language_id field rather than raising an AssertionError.
    """
    utt1 = _make_utterance(tmp_path, speaker_id=0, language_id=1, text="a")
    utt2 = _make_utterance(tmp_path, speaker_id=1, language_id=0, text="b")
    dataset = _make_dataset_with_utterances([utt1, utt2])

    tensors = [dataset[0], dataset[1]]

    collate = UtteranceCollate(
        is_multispeaker=True,
        segment_size=8192,
        is_multilanguage=False,
    )

    # Must not raise AssertionError
    batch = collate(tensors)

    # language_ids should be None when is_multilanguage=False
    assert batch.language_ids is None
    # Other fields should still be populated
    assert batch.phoneme_ids.shape[0] == 2
    assert batch.speaker_ids is not None


@pytest.mark.unit
def test_validate_cache_files_method_exists():
    """_validate_cache_files メソッドが定義されていることを確認.

    Regression test: PiperDataset must expose _validate_cache_files so that
    the validate_cache=True code path in __init__ can filter corrupted entries.
    """
    assert hasattr(PiperDataset, "_validate_cache_files")
    assert callable(PiperDataset._validate_cache_files)

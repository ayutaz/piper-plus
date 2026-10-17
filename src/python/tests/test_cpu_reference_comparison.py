"""Control reference duration and keep source utterances out of evaluation."""

import numpy as np
import pytest


def test_crop_matches_active_frames_without_removing_internal_pauses():
    from piper_train.tools.cpu_reference_comparison import crop_active_frames

    # Five active frames separated by silence; preserve the internal silence.
    audio = np.repeat([0, 1, 1, 0, 1, 1, 1, 0], 320).astype(np.float32)
    crop, metadata = crop_active_frames(audio, 16000, 3)
    assert metadata["active_frames"] == 3
    assert metadata["start_frame"] == 1
    assert metadata["end_frame"] == 5
    np.testing.assert_array_equal(crop, audio[320:1600])


def test_activity_crop_rejects_silence_insufficient_and_nonfinite():
    from piper_train.tools.cpu_reference_comparison import crop_active_frames

    for audio in (np.zeros(1600), np.ones(320), np.full(1600, np.nan)):
        with pytest.raises(ValueError):
            crop_active_frames(audio, 16000, 2)


def test_exclusion_covers_source_utterances_and_content_aliases(tmp_path):
    from piper_train.tools.cpu_reference_comparison import independent_reals

    original = tmp_path / "original.wav"
    alias = tmp_path / "alias.wav"
    crop = tmp_path / "crop.wav"
    real = tmp_path / "real.wav"
    original.write_bytes(b"source")
    alias.write_bytes(b"source")
    crop.write_bytes(b"cropped")
    real.write_bytes(b"independent")
    assert independent_reals([original, alias, crop, real], [original, crop]) == [real]


def test_exclusion_never_accepts_empty_source_list(tmp_path):
    from piper_train.tools.cpu_reference_comparison import independent_reals

    with pytest.raises(ValueError, match="sources"):
        independent_reals([tmp_path / "anything.wav"], [])

"""Issue #426 — pin the speaker_embedding feed contract for PiperVoice.

MB-iSTFT-VITS2 + Voice Cloning exports declare `speaker_embedding` /
`speaker_embedding_mask` unconditionally (PR #320 / `export_onnx.py:505-515`).
Mainline runtimes must feed zero embedding + mask=0 so the model falls back
to `emb_g(sid)` (`vits/models.py:1015-1037`); otherwise ORT raises
"Required inputs missing".

This file documents the contract for `src/python_run/piper/voice.py`:
- `PiperVoice.synthesize_audio()` (line ~973) — production path.
- `warmup_session()` (line ~200) — preload path.

If these tests fail, the regression that issue #426 caught in
`docker/python-inference` has crept back into the Python runtime.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from piper.config import PhonemeType, PiperConfig
from piper.voice import PiperVoice


def _make_input_mock(name: str, shape):
    inp = MagicMock()
    inp.name = name
    inp.shape = shape
    return inp


def _make_voice_with_inputs(
    input_specs, *, sample_rate: int = 22050
) -> tuple[PiperVoice, MagicMock]:
    """Build a PiperVoice backed by a MagicMock session declaring the
    given inputs. Returns (voice, session) so tests can inspect the
    last `session.run(...)` feed."""
    config = PiperConfig(
        num_symbols=100,
        num_speakers=1,
        sample_rate=sample_rate,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={
            "_": [0],
            "^": [1],
            "$": [2],
            "a": [10],
        },
        phoneme_type=PhonemeType.MULTILINGUAL,
    )

    session = MagicMock()
    session.get_inputs.return_value = [
        _make_input_mock(name, shape) for name, shape in input_specs
    ]

    output_mock = MagicMock()
    output_mock.name = "output"
    session.get_outputs.return_value = [output_mock]

    audio_samples = np.zeros((1, 1, sample_rate), dtype=np.float32)
    session.run.return_value = [audio_samples]

    voice = PiperVoice(session=session, config=config)
    return voice, session


class TestSynthesizeAudioFeedsSpeakerEmbedding:
    """`PiperVoice.synthesize_audio` must adapt to speaker_embedding."""

    def _run_synth(self, voice):
        # synthesize_ids_to_raw routes through _synthesize_ids_core which
        # is the production path that feeds the ONNX session.
        voice.synthesize_ids_to_raw(
            phoneme_ids=[1, 10, 10, 10, 2],
        )

    def test_no_speaker_embedding_input_not_fed(self):
        voice, session = _make_voice_with_inputs(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
            ]
        )
        self._run_synth(voice)
        feed = session.run.call_args[0][1]
        assert "speaker_embedding" not in feed
        assert "speaker_embedding_mask" not in feed

    def test_speaker_embedding_declared_zero_and_mask_zero(self):
        voice, session = _make_voice_with_inputs(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("sid", ["batch"]),
                ("speaker_embedding", ["batch", 256]),
                ("speaker_embedding_mask", ["batch", 1]),
            ]
        )
        self._run_synth(voice)
        feed = session.run.call_args[0][1]
        assert "speaker_embedding" in feed
        assert "speaker_embedding_mask" in feed

        emb = feed["speaker_embedding"]
        assert emb.dtype == np.float32
        assert emb.shape == (1, 256)
        assert np.all(emb == 0.0)

        mask = feed["speaker_embedding_mask"]
        assert mask.dtype == np.int64
        assert mask.shape == (1, 1)
        # mask=0 → fall back to emb_g(sid) (vits/models.py:1015-1037).
        assert mask[0, 0] == 0

    def test_dynamic_emb_dim_falls_back_to_256(self):
        """If the ONNX graph uses a dynamic axis for emb_dim, the runtime
        must fall back to the ECAPA-TDNN canonical 256."""
        voice, session = _make_voice_with_inputs(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("speaker_embedding", ["batch", "emb_dim"]),  # non-int axis
                ("speaker_embedding_mask", ["batch", 1]),
            ]
        )
        self._run_synth(voice)
        feed = session.run.call_args[0][1]
        assert feed["speaker_embedding"].shape == (1, 256)

    def test_speaker_embedding_with_prosody_and_lid(self):
        """All optional inputs coexist without the speaker_embedding feed
        clobbering them."""
        voice, session = _make_voice_with_inputs(
            [
                ("input", ["batch", "seq"]),
                ("input_lengths", ["batch"]),
                ("scales", [3]),
                ("sid", ["batch"]),
                ("lid", ["batch"]),
                ("prosody_features", ["batch", "seq", 3]),
                ("speaker_embedding", ["batch", 256]),
                ("speaker_embedding_mask", ["batch", 1]),
            ]
        )
        self._run_synth(voice)
        feed = session.run.call_args[0][1]
        # speaker_embedding must coexist with the other dynamic-detection
        # optional inputs (sid is omitted by voice.py when num_speakers=1
        # in the config, which is the single-speaker mock here — not
        # asserted by this test).
        for name in (
            "lid",
            "prosody_features",
            "speaker_embedding",
            "speaker_embedding_mask",
        ):
            assert name in feed, f"{name} missing from feed"


class TestWarmupFeedsSpeakerEmbedding:
    """`_warmup_session()` must obey the same contract as synthesize."""

    def test_warmup_passes_zero_emb_and_mask_zero(self):
        from piper.voice import _warmup_session  # noqa: PLC0415

        session = MagicMock()
        session.get_inputs.return_value = [
            _make_input_mock("input", ["batch", "seq"]),
            _make_input_mock("input_lengths", ["batch"]),
            _make_input_mock("scales", [3]),
            _make_input_mock("speaker_embedding", ["batch", 256]),
            _make_input_mock("speaker_embedding_mask", ["batch", 1]),
        ]
        output_mock = MagicMock()
        output_mock.name = "output"
        session.get_outputs.return_value = [output_mock]
        session.run.return_value = [np.zeros((1, 1, 22050), dtype=np.float32)]

        _warmup_session(session, runs=1)

        feed = session.run.call_args[0][1]
        assert feed["speaker_embedding"].shape == (1, 256)
        assert feed["speaker_embedding"].dtype == np.float32
        assert np.all(feed["speaker_embedding"] == 0.0)
        assert feed["speaker_embedding_mask"].shape == (1, 1)
        assert feed["speaker_embedding_mask"].dtype == np.int64
        assert feed["speaker_embedding_mask"][0, 0] == 0

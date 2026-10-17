"""Tests for the zero-shot (reference audio) path of the HF Space."""

import hashlib
import json
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

import zero_shot
from piper_plus.config import PiperConfig
from piper_plus.phonemize.multilingual import MultilingualPhonemizer
from piper_plus.voice import PiperVoice
from scripts import public_base_runtime as pbr


CONFIG_PATH = Path(zero_shot.__file__).parent / "models" / "zs-v1" / "base.onnx.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeEncoder:
    """Stands in for the CAM++ session; records the feature shape it is fed."""

    def __init__(self):
        self.last_input_shape = None

    def get_inputs(self):
        class _Input:
            name = "input"

        return [_Input()]

    def run(self, _output_names, feeds):
        features = feeds["input"]
        self.last_input_shape = features.shape
        return [np.arange(1, 193, dtype=np.float32).reshape(1, 192)]


@pytest.fixture
def fake_encoder():
    return FakeEncoder()


@pytest.fixture(scope="module")
def base_voice():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return PiperVoice(session=None, config=PiperConfig.from_dict(config))


def _expected_ids(text, language, voice):
    # Independent restatement of scripts/public_base_runtime.py:prepare().
    phonemizer = MultilingualPhonemizer(
        languages=["ja", "en", "zh", "es", "fr", "pt"],
        default_latin_language=language
        if language in {"en", "es", "fr", "pt"}
        else "en",
    )
    phones = [
        p
        for p in phonemizer.phonemize(text)
        if not p.isspace() and p not in ",.;:!¡¿…—–-«»"
    ]
    return voice.phonemes_to_ids(phones)


def test_bundled_config_matches_pinned_sha():
    assert _sha256(CONFIG_PATH) == zero_shot.FILE_SHA256["base.onnx.json"]


def test_pins_match_ci_verifier():
    assert zero_shot.BASE_REPO == pbr.BASE_REPO
    assert zero_shot.BASE_REVISION == pbr.BASE_REVISION
    assert zero_shot.FILE_SHA256 == pbr.FILES


def test_int16_stereo_is_scaled_and_downmixed():
    audio = np.array([[32767, -32768], [16384, 16384]], dtype=np.int16)
    sr, mono = zero_shot.to_mono_float(48000, audio)
    assert sr == 48000
    assert mono.dtype == np.float32
    assert mono.shape == (2,)
    assert np.all(np.abs(mono) <= 1.0)
    assert mono[1] == pytest.approx(0.5, abs=1e-4)


def test_embedding_is_unit_norm_and_uses_16k_fbank(fake_encoder):
    t = np.arange(48000) / 48000
    audio = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    emb = zero_shot.extract_speaker_embedding(48000, audio, fake_encoder)
    assert emb.shape == (192,)
    assert emb.dtype == np.float32
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-5)
    batch, frames, bins = fake_encoder.last_input_shape
    assert (batch, bins) == (1, 80)
    assert 95 <= frames <= 100  # 1 s at 25 ms / 10 ms framing -> 98 frames


def test_rejects_short_reference(fake_encoder):
    audio = np.full(800, 0.1, dtype=np.float32)  # 0.05 s
    with pytest.raises(zero_shot.ZeroShotInputError, match="0.1"):
        zero_shot.extract_speaker_embedding(16000, audio, fake_encoder)


def test_rejects_silent_reference(fake_encoder):
    with pytest.raises(zero_shot.ZeroShotInputError):
        zero_shot.extract_speaker_embedding(
            16000, np.zeros(16000, np.float32), fake_encoder
        )


def test_long_reference_is_truncated(fake_encoder):
    rng = np.random.default_rng(0)
    audio = (0.1 * rng.standard_normal(16000 * 120)).astype(np.float32)
    zero_shot.extract_speaker_embedding(16000, audio, fake_encoder)
    assert fake_encoder.last_input_shape[1] <= 30 * 100


@pytest.mark.parametrize(("key", "language", "text"), pbr.TEXTS)
def test_phoneme_ids_match_ci_recipe(base_voice, key, language, text):
    ids = zero_shot.phoneme_ids_for_base(text, language, base_voice)
    assert ids == _expected_ids(text, language, base_voice), key


def test_untrained_phonemes_raise(base_voice):
    # The current pt G2P emits "ã", which the 173-symbol zs-v1 map lacks.
    with pytest.raises(zero_shot.ZeroShotInputError, match="untrained.*ã"):
        zero_shot.phoneme_ids_for_base("Não sei.", "pt", base_voice)


def test_text_without_phonemes_raises(base_voice):
    # Hangul is outside the six languages, so nothing is phonemized.
    with pytest.raises(zero_shot.ZeroShotInputError, match="no phonemes"):
        zero_shot.phoneme_ids_for_base("안녕하세요", "ja", base_voice)


def test_unknown_language_raises(base_voice):
    with pytest.raises(zero_shot.ZeroShotInputError):
        zero_shot.phoneme_ids_for_base("hej", "sv", base_voice)


def _fake_sessions(monkeypatch):
    monkeypatch.setattr(zero_shot, "_verify", lambda path, expected: None)
    monkeypatch.setattr(
        zero_shot.ZeroShotEngine, "_open_sessions", lambda self, paths: None
    )


def test_assets_loaded_once_under_concurrency(tmp_path, monkeypatch):
    _fake_sessions(monkeypatch)
    calls = []

    def downloader(name):
        calls.append(name)
        path = tmp_path / name
        path.write_bytes(b"x")
        return path

    engine = zero_shot.ZeroShotEngine(cache_dir=tmp_path, downloader=downloader)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: engine.load(), range(8)))
    assert sorted(calls) == ["base.onnx", "campplus.onnx"]


def test_sha_mismatch_is_rejected(tmp_path):
    def downloader(name):
        path = tmp_path / name
        path.write_bytes(b"not the pinned model")
        return path

    engine = zero_shot.ZeroShotEngine(cache_dir=tmp_path, downloader=downloader)
    with pytest.raises(RuntimeError, match="SHA256"):
        engine.load()


def _read_reference(path):
    with wave.open(str(path), "rb") as stream:
        rate = stream.getframerate()
        frames = stream.readframes(stream.getnframes())
        channels = stream.getnchannels()
    audio = np.frombuffer(frames, dtype=np.int16).reshape(-1, channels)
    return rate, audio


@pytest.mark.integration
def test_real_model_conditioning_changes_audio(tmp_path):
    reference = tmp_path / "reference.wav"
    pbr.download(
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/"
        f"{pbr.REFERENCE_REVISION}/samples/sample_ja.wav",
        reference,
        pbr.REFERENCE_SHA256,
    )
    rate, audio = _read_reference(reference)
    engine = zero_shot.get_engine()
    engine.load()
    _, ja_language, ja_text = pbr.TEXTS[0]

    first = zero_shot.extract_speaker_embedding(rate, audio, engine.encoder)
    second = zero_shot.extract_speaker_embedding(rate, audio, engine.encoder)
    np.testing.assert_allclose(first, second, atol=1e-6)

    sample_rate, speech = engine.synthesize(ja_text, ja_language, (rate, audio))
    assert speech.dtype == np.int16
    assert speech.size > 0.3 * sample_rate
    assert np.abs(speech).max() > 0

    # Functional conditioning check (as in public_base_runtime), not quality.
    ids = zero_shot.phoneme_ids_for_base(ja_text, ja_language, engine.voice)
    lid = engine.voice.config.language_id_map[ja_language]
    raw = engine.voice.synthesize_ids_to_raw(
        ids, language_id=lid, speaker_embedding=first, noise_scale=0.0, noise_w=0.0
    )
    negated = engine.voice.synthesize_ids_to_raw(
        ids, language_id=lid, speaker_embedding=-first, noise_scale=0.0, noise_w=0.0
    )
    assert raw != negated

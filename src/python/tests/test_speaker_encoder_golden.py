"""Golden fixture validation for the runtime speaker encoder mel front end.

``test/fixtures/speaker_encoder_golden.json`` pins the mel front end that the
Rust, Go, C#, JS/WASM and C++ encoders compute (n_fft=400, frame-major,
per-band mean subtraction). Its reference implementation is
``test/generate_speaker_encoder_golden.py`` (manual float32 DFT, periodic
Hann). The tests below check the fixture against that generator, so a fixture
edited by hand, or a generator change that was not regenerated, fails here
instead of only in the runtime mirrors.

``piper_train.speaker_encoder.audio_utils`` is not this front end. It feeds
the ECAPA-TDNN in ``piper_train.speaker_encoder`` (n_fft=512, ``(n_mels, T)``,
no mean subtraction), which is the layout ``ECAPATDNN.forward`` and
``export_encoder`` expect. #579 moved the fixture and the runtimes to the
current front end and left the ECAPA path as it was; #857 records why the two
are kept apart.

Spec: ``docs/reference/speaker-encoder-contract.md``.
"""

from __future__ import annotations

import importlib.util
import json
import platform
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_PATH = _REPO_ROOT / "test" / "fixtures" / "speaker_encoder_golden.json"
_GENERATOR_PATH = _REPO_ROOT / "test" / "generate_speaker_encoder_golden.py"
# Loaded by path: the piper_train.speaker_encoder package imports ecapa_tdnn,
# which needs torch, and the Windows CI job has no torch. audio_utils itself
# needs only numpy.
_AUDIO_UTILS_PATH = (
    _REPO_ROOT / "src" / "python" / "piper_train" / "speaker_encoder" / "audio_utils.py"
)

_MEL_CASES = [
    ("sine_440hz_1s", "sine", 440.0, 1.0),
    ("sine_1000hz_0.5s", "sine", 1000.0, 0.5),
    ("multitone_200_600_2000hz_0.5s", "multitone", [200.0, 600.0, 2000.0], 0.5),
]


@pytest.fixture(scope="module")
def golden() -> dict:
    """Load and parse the golden JSON fixture."""
    if not _FIXTURE_PATH.exists():
        pytest.skip(f"Golden fixture not found at {_FIXTURE_PATH}")
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_by_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    """Import the fixture generator by path (``test/`` is not a package)."""
    if not _GENERATOR_PATH.exists():
        pytest.skip(f"Golden generator not found at {_GENERATOR_PATH}")
    return _load_by_path("speaker_encoder_golden_generator", _GENERATOR_PATH)


def _find_case(g: dict, case_id: str) -> dict:
    for tc in g["test_cases"]:
        if tc["id"] == case_id:
            return tc
    raise AssertionError(f"golden fixture missing test case '{case_id}'")


def _case_audio(gen: ModuleType, kind: str, freq, duration_s: float) -> np.ndarray:
    if kind == "sine":
        return gen.generate_sine(freq, duration_s, gen.SR)
    return gen.generate_multitone(freq, duration_s, gen.SR)


@pytest.mark.unit
class TestFixtureMatchesGenerator:
    """Everything except the mel test cases, which are slow (see below)."""

    def test_load_golden_fixture(self, golden):
        assert "mel_params" in golden
        assert "hann_window" in golden
        assert "mel_filterbank" in golden
        assert isinstance(golden["test_cases"], list)
        assert len(golden["test_cases"]) >= 4

    def test_schema_version_optional_forward_compat(self, golden):
        """``schema_version`` may be added later; if present must be int >= 1."""
        if "schema_version" in golden:
            assert isinstance(golden["schema_version"], int)
            assert golden["schema_version"] >= 1

    def test_mel_params(self, golden, generator):
        assert golden["mel_params"] == {
            "sr": generator.SR,
            "n_fft": generator.N_FFT,
            "hop_length": generator.HOP_LENGTH,
            "n_mels": generator.N_MELS,
            "fmin": generator.FMIN,
            "fmax": generator.FMAX,
        }

    def test_hann_window(self, golden, generator):
        window = generator.hann_window(generator.N_FFT)
        hw = golden["hann_window"]
        assert hw["length"] == generator.N_FFT
        assert hw["checksum"] == generator.checksum_floats(window)
        assert hw["first_5"] == window[:5].tolist()
        assert hw["last_5"] == window[-5:].tolist()
        assert hw["mid_value"] == float(window[generator.N_FFT // 2])

    def test_mel_filterbank(self, golden, generator):
        fb = generator.create_mel_filterbank()
        bins = generator.N_FFT // 2 + 1
        mf = golden["mel_filterbank"]
        assert mf["shape"] == [generator.N_MELS, bins]
        assert mf["checksum"] == generator.checksum_floats(fb)
        assert mf["total_sum"] == float(np.sum(fb))
        assert mf["band_sums"] == [
            float(np.sum(fb[m * bins : (m + 1) * bins]))
            for m in range(generator.N_MELS)
        ]
        # Every band has weight, so no mel bin is a constant log floor.
        assert all(s > 0 for s in mf["band_sums"])

    def test_resample_48k_to_16k(self, golden, generator):
        tc = _find_case(golden, "resample_48k_to_16k")
        p = tc["audio_params"]
        audio = generator.generate_sine(p["freq_hz"], p["duration_s"], p["original_sr"])
        out = generator.resample_linear(audio, p["original_sr"], p["target_sr"])
        assert len(audio) == tc["input_samples_count"]
        assert len(out) == tc["expected_output_count"]
        assert tc["output_checksum"] == generator.checksum_floats(out)
        assert tc["output_first_10"] == out[:10].tolist()
        assert tc["output_last_10"] == out[-10:].tolist()

    @pytest.mark.parametrize(("case_id", "kind", "freq", "duration_s"), _MEL_CASES)
    def test_mel_case_frame_count(self, golden, generator, case_id, kind, freq, duration_s):
        tc = _find_case(golden, case_id)
        audio = _case_audio(generator, kind, freq, duration_s)
        n_frames = (len(audio) - generator.N_FFT) // generator.HOP_LENGTH + 1
        assert tc["audio_samples_count"] == len(audio)
        assert tc["expected_mel_shape"] == [generator.N_MELS, n_frames]
        assert len(tc["mel_sampled_every_10"]) == -(-n_frames * generator.N_MELS // 10)

    def test_every_fixture_case_is_checked(self, golden):
        ids = {tc["id"] for tc in golden["test_cases"]}
        assert ids == {case[0] for case in _MEL_CASES} | {"resample_48k_to_16k"}


@pytest.mark.integration
@pytest.mark.skipif(
    platform.machine().lower() not in {"x86_64", "amd64"},
    reason=(
        "the fixture was generated on x86_64; float32 sin/cos/log are not "
        "correctly rounded, so other CPUs (macOS arm64 in CI) give different "
        "low-energy log-mel values and checksums"
    ),
)
@pytest.mark.parametrize(("case_id", "kind", "freq", "duration_s"), _MEL_CASES)
def test_mel_case_matches_generator(golden, generator, case_id, kind, freq, duration_s):
    """Recompute each mel case with the generator and compare it exactly.

    integration, not unit: the generator's manual DFT is a Python triple loop
    (about 8 s for a 0.5 s case on a desktop CPU). A vectorized DFT is no
    shortcut, because float32 accumulation order moves the low-energy bins by
    up to 0.4 in log mel.

    x86_64 only: float32 + and * are IEEE exact, but numpy leaves the rounding
    of sin/cos/log to the platform, and the log of a low-energy bin magnifies
    that difference past the checksum's 6 decimals. A fixture that drifted
    from the generator fails on every CPU, so x86_64 (Linux in CI) still
    catches it.
    """
    tc = _find_case(golden, case_id)
    mel = generator.compute_mel_spectrogram(_case_audio(generator, kind, freq, duration_s))
    n_mels = generator.N_MELS
    n_frames = len(mel) // n_mels
    assert tc["expected_mel_checksum"] == generator.checksum_floats(mel)
    assert tc["mel_sampled_every_10"] == mel[::10].tolist()
    assert tc["mel_corner_values"] == {
        "top_left": float(mel[0]),
        "top_right": float(mel[(n_frames - 1) * n_mels]),
        "bottom_left": float(mel[n_mels - 1]),
        "bottom_right": float(mel[n_frames * n_mels - 1]),
    }


@pytest.mark.unit
def test_ecapa_front_end_is_not_the_fixture_front_end(golden):
    """audio_utils keeps the ECAPA-TDNN input format; do not align it to the fixture.

    ECAPATDNN.forward takes ``(batch, n_mels, time)`` and the exported ONNX
    declares ``mel`` as ``[B, 80, T]``. Switching audio_utils to the fixture
    front end (n_fft=400, ``(T, n_mels)``, mean subtraction) would feed that
    model a layout it was not built for (#857).
    """
    audio_utils = _load_by_path("speaker_encoder_audio_utils", _AUDIO_UTILS_PATH)
    n_fft = audio_utils.DEFAULT_N_FFT

    assert n_fft == 512
    assert golden["mel_params"]["n_fft"] == 400

    mel = audio_utils.compute_mel_spectrogram(np.zeros(16000, dtype=np.float32))
    assert mel.shape == (
        audio_utils.DEFAULT_N_MELS,
        1 + (16000 - n_fft) // audio_utils.DEFAULT_HOP_LENGTH,
    )

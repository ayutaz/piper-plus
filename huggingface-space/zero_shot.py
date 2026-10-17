"""Zero-shot synthesis from reference audio with the public zs-v1 base.

Speaker embedding extraction and phonemization follow the recipe verified in
CI by ``scripts/public_base_runtime.py`` and shipped as the zs-v1 bundle's
``examples/``: Kaldi fbank -> mean subtraction -> CAM++ -> L2 normalization,
and ``MultilingualPhonemizer`` + ``PiperVoice`` with untrained phonemes
rejected instead of dropped. This module does not import gradio.
"""

import hashlib
import logging
import threading
import unicodedata
from collections.abc import Callable
from pathlib import Path

import numpy as np
import onnxruntime

from piper_plus.phonemize.multilingual import MultilingualPhonemizer
from piper_plus.voice import PiperVoice


_LOGGER = logging.getLogger(__name__)

# Keep in sync with scripts/public_base_runtime.py (a test enforces this).
BASE_REPO = "ayousanz/piper-plus-base"
BASE_REVISION = "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1"
FILE_SHA256 = {
    "base.onnx": "e9860701a941db02149c7cfbe19cfb578c235c5e25020f1f592131d9b3b30f84",
    "base.onnx.json": "d085681edaa5029c54ea8329f3f23ed347ba46ca15cd80e766de9a6a643dafc0",
    "campplus.onnx": "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73",
}
DOWNLOADED_FILES = ("base.onnx", "campplus.onnx")
CONFIG_PATH = Path(__file__).parent / "zs-v1" / "base.onnx.json"

LANGUAGES = ("ja", "en", "zh", "es", "fr", "pt")
LATIN_LANGUAGES = frozenset({"en", "es", "fr", "pt"})
# Default texts for the zero-shot tab, from the CI-verified cases in
# scripts/public_base_runtime.py (TEXTS). Every phoneme is in the zs-v1 map.
SAMPLE_TEXTS = {
    "ja": "こんにちは。今日は良い天気ですね。",
    "en": "Hello, today is a beautiful day.",
    "zh": "你好，今天天气很好。",
    "es": "Hola, hoy hace buen tiempo.",  # codespell:ignore hace
    "fr": "Bonjour, le soleil brille.",
    "pt": "Olá, hoje está um belo dia.",
}
# Letters from any other script are dropped by MultilingualPhonemizer, so
# they are rejected up front (matched against Unicode character names).
SUPPORTED_LETTER_PREFIXES = (
    "LATIN",
    "FULLWIDTH LATIN",
    "HIRAGANA",
    "KATAKANA",
    "HALFWIDTH KATAKANA",
    "CJK UNIFIED IDEOGRAPH",
    "CJK COMPATIBILITY IDEOGRAPH",
    "IDEOGRAPHIC",
)
# Spaces and punctuation are absent from the zs-v1 (173-symbol) phoneme map.
DROPPED_PUNCTUATION = frozenset(",.;:!¡¿…—–-«»")

ENCODER_SAMPLE_RATE = 16000
MIN_REFERENCE_SECONDS = 0.1
MAX_REFERENCE_SECONDS = 30.0
SILENCE_PEAK = 1e-4
EMBEDDING_DIM = 192


class ZeroShotInputError(ValueError):
    """The user's reference audio or text cannot be used as given."""


def to_mono_float(sample_rate: int, audio: np.ndarray) -> tuple[int, np.ndarray]:
    """Convert int or float audio shaped ``[N]`` or ``[N, C]`` to float32 mono."""
    audio = np.asarray(audio)
    if np.issubdtype(audio.dtype, np.integer):
        scale = float(np.iinfo(audio.dtype).max) + 1.0
        audio = audio.astype(np.float32) / scale
    else:
        audio = audio.astype(np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    elif audio.ndim != 1:
        raise ZeroShotInputError(f"Unsupported audio shape: {audio.shape}")
    return sample_rate, audio.astype(np.float32)


def extract_speaker_embedding(
    sample_rate: int,
    audio: np.ndarray,
    encoder: onnxruntime.InferenceSession,
) -> np.ndarray:
    """Return the L2-normalized 192-dim CAM++ embedding of the reference."""
    import torch
    import torchaudio

    # Cut before converting so a long upload is never copied in full.
    audio = np.asarray(audio)[: int(MAX_REFERENCE_SECONDS * sample_rate)]
    sample_rate, audio = to_mono_float(sample_rate, audio)
    if audio.size < MIN_REFERENCE_SECONDS * sample_rate:
        raise ZeroShotInputError(
            f"Reference audio must be at least {MIN_REFERENCE_SECONDS} seconds long."
        )
    if not np.isfinite(audio).all() or np.abs(audio).max() < SILENCE_PEAK:
        raise ZeroShotInputError("Reference audio is silent or invalid.")
    waveform = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))
    if sample_rate != ENCODER_SAMPLE_RATE:
        # Kaiser-windowed sinc ("kaiser_best") instead of the CI recipe's
        # soxr HQ, which is LGPL. Measured CAM++ cosine vs soxr: 0.9992.
        waveform = torchaudio.functional.resample(
            waveform,
            sample_rate,
            ENCODER_SAMPLE_RATE,
            lowpass_filter_width=64,
            rolloff=0.9475937167399596,
            resampling_method="sinc_interp_kaiser",
            beta=14.769656459379492,
        )

    features = torchaudio.compliance.kaldi.fbank(
        waveform.unsqueeze(0),
        sample_frequency=ENCODER_SAMPLE_RATE,
        num_mel_bins=80,
        frame_length=25,
        frame_shift=10,
        dither=0.0,
    )
    features -= features.mean(dim=0, keepdim=True)
    input_name = encoder.get_inputs()[0].name
    embedding = encoder.run(None, {input_name: features.unsqueeze(0).numpy()})[0]
    embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
    if embedding.shape != (EMBEDDING_DIM,) or not np.isfinite(embedding).all():
        raise RuntimeError(f"Invalid CAM++ embedding shape {embedding.shape}")
    norm = float(np.linalg.norm(embedding))
    if norm == 0.0:
        raise RuntimeError("CAM++ returned a zero embedding")
    return (embedding / norm).astype(np.float32)


def unsupported_characters(text: str) -> list[str]:
    """Letters outside the scripts of the six supported languages."""
    return sorted(
        {
            c
            for c in text
            if unicodedata.category(c).startswith("L")
            and not unicodedata.name(c, "").startswith(SUPPORTED_LETTER_PREFIXES)
        }
    )


def phoneme_ids_for_base(text: str, language: str, voice: PiperVoice) -> list[int]:
    """Phonemize ``text`` for the zs-v1 base, rejecting untrained phonemes."""
    if language not in LANGUAGES:
        raise ZeroShotInputError(f"Unsupported language: {language}")
    unsupported = unsupported_characters(text)
    if unsupported:
        raise ZeroShotInputError(
            "Text contains characters outside the supported languages: "
            + " ".join(unsupported)
        )
    phonemizer = MultilingualPhonemizer(
        languages=list(LANGUAGES),
        default_latin_language=language if language in LATIN_LANGUAGES else "en",
    )
    phones = [
        p
        for p in phonemizer.phonemize(text)
        if not p.isspace() and p not in DROPPED_PUNCTUATION
    ]
    missing = set(phones) - set(voice.config.phoneme_id_map)
    if missing:
        raise ZeroShotInputError(
            "Text contains phonemes untrained in the zero-shot model: "
            + " ".join(sorted(missing))
        )
    if not phones:
        raise ZeroShotInputError("Text produced no phonemes.")
    return voice.phonemes_to_ids(phones)


def config_sha256(path: Path) -> str:
    """SHA256 of the config as published upstream (CRLF line endings).

    The repository stores it with LF (.gitattributes ``*.json eol=lf``), so the
    pinned digest is checked against the CRLF form.
    """
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(data).hexdigest()


def _verify(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise RuntimeError(f"SHA256 mismatch for {path.name}")


def _hub_downloader(cache_dir: Path | None) -> Callable[[str], Path]:
    def download(name: str) -> Path:
        from huggingface_hub import hf_hub_download

        return Path(
            hf_hub_download(
                repo_id=BASE_REPO,
                revision=BASE_REVISION,
                filename=f"releases/zs-v1/{name}",
                cache_dir=cache_dir,
            )
        )

    return download


class ZeroShotEngine:
    """Lazily fetches, verifies and opens the pinned zs-v1 model and encoder."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        downloader: Callable[[str], Path] | None = None,
    ):
        self._download = downloader or _hub_downloader(cache_dir)
        self._lock = threading.Lock()
        self._loaded = False
        self.voice: PiperVoice | None = None
        self.encoder: onnxruntime.InferenceSession | None = None

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            if config_sha256(CONFIG_PATH) != FILE_SHA256["base.onnx.json"]:
                raise RuntimeError(f"SHA256 mismatch for {CONFIG_PATH.name}")
            paths = {name: self._download(name) for name in DOWNLOADED_FILES}
            for name, path in paths.items():
                _verify(path, FILE_SHA256[name])
            self._open_sessions(paths)
            self._loaded = True

    def _open_sessions(self, paths: dict[str, Path]) -> None:
        voice = PiperVoice.load(paths["base.onnx"], config_path=CONFIG_PATH)
        names = {item.name for item in voice.session.get_inputs()}
        if "speaker_embedding" not in names or "sid" in names:
            raise RuntimeError(f"Unexpected zs-v1 inputs: {sorted(names)}")
        self.voice = voice
        self.encoder = onnxruntime.InferenceSession(
            str(paths["campplus.onnx"]), providers=["CPUExecutionProvider"]
        )

    def synthesize(
        self,
        text: str,
        language: str,
        reference: tuple[int, np.ndarray],
        length_scale: float = 1.0,
        noise_scale: float = 0.667,
        noise_w: float = 0.8,
    ) -> tuple[int, np.ndarray]:
        """Return ``(sample_rate, int16 audio)`` spoken in the reference voice."""
        self.load()
        sample_rate, audio = reference
        embedding = extract_speaker_embedding(sample_rate, audio, self.encoder)
        ids = phoneme_ids_for_base(text, language, self.voice)
        raw = self.voice.synthesize_ids_to_raw(
            ids,
            language_id=self.voice.config.language_id_map[language],
            speaker_embedding=embedding,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
        )
        return self.voice.config.sample_rate, np.frombuffer(raw, dtype=np.int16)


# Construction does no I/O; downloads happen on the first load().
_ENGINE = ZeroShotEngine()


def get_engine() -> ZeroShotEngine:
    return _ENGINE

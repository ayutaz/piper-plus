import json
import logging
import re
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime


# Try to import piper_phonemize, but make it optional
try:
    from piper_phonemize import phonemize_codepoints, phonemize_espeak, tashkeel_run

    HAS_PIPER_PHONEMIZE = True
except ImportError:
    HAS_PIPER_PHONEMIZE = False

    # Provide fallback implementations
    def phonemize_codepoints(text, lang=None):
        # Simple fallback: return text as list of characters
        return list(text)

    def phonemize_espeak(text, voice=None):
        # Try to use espeak-ng command if available
        try:
            from .espeak_phonemizer import phonemize_espeak_ng

            return phonemize_espeak_ng(text, voice or "en-us")
        except ImportError:
            # Simple fallback: return text as list of characters
            _LOGGER.warning("espeak_phonemizer not available, using character fallback")
            return [list(text)]

    def tashkeel_run(text):
        # Simple fallback: return original text
        return text


# Try to import pyopenjtalk, but make it optional
try:
    import pyopenjtalk

    HAS_PYOPENJTALK = True
except ImportError:
    HAS_PYOPENJTALK = False

from .config import PhonemeType, PiperConfig
from .const import BOS, EOS, PAD
from .util import audio_float_to_int16


_LOGGER = logging.getLogger(__name__)

# Regex patterns for Japanese prosody extraction
_RE_PHONEME = re.compile(r"-([^+]+)\+")
_RE_A1 = re.compile(r"/A:([\d-]+)\+")
_RE_A2 = re.compile(r"\+([0-9]+)\+")
_RE_A3 = re.compile(r"\+([0-9]+)/")

# Multi-character phoneme to PUA character mapping for Japanese
# This must match the C++ side and Python training side
MULTI_CHAR_TO_PUA = {
    "a:": "\ue000",
    "i:": "\ue001",
    "u:": "\ue002",
    "e:": "\ue003",
    "o:": "\ue004",
    "cl": "\ue005",
    "ky": "\ue006",
    "kw": "\ue007",
    "gy": "\ue008",
    "gw": "\ue009",
    "ty": "\ue00a",
    "dy": "\ue00b",
    "py": "\ue00c",
    "by": "\ue00d",
    "ch": "\ue00e",
    "ts": "\ue00f",
    "sh": "\ue010",
    "zy": "\ue011",
    "hy": "\ue012",
    "ny": "\ue013",
    "my": "\ue014",
    "ry": "\ue015",
}


@dataclass
class PiperVoice:
    session: onnxruntime.InferenceSession
    config: PiperConfig

    @staticmethod
    def load(
        model_path: str | Path,
        config_path: str | Path | None = None,
        use_cuda: bool = False,
    ) -> "PiperVoice":
        """Load an ONNX model and config."""
        if config_path is None:
            config_path = f"{model_path}.json"

        with open(config_path, encoding="utf-8") as config_file:
            config_dict = json.load(config_file)

        providers: list[str | tuple[str, dict[str, Any]]]
        if use_cuda:
            providers = [
                (
                    "CUDAExecutionProvider",
                    {"cudnn_conv_algo_search": "HEURISTIC"},
                )
            ]
        else:
            providers = ["CPUExecutionProvider"]

        return PiperVoice(
            config=PiperConfig.from_dict(config_dict),
            session=onnxruntime.InferenceSession(
                str(model_path),
                sess_options=onnxruntime.SessionOptions(),
                providers=providers,
            ),
        )

    def phonemize(self, text: str) -> list[list[str]]:
        """Text to phonemes grouped by sentence."""
        if self.config.phoneme_type == PhonemeType.ESPEAK:
            if self.config.espeak_voice == "ar":
                # Arabic diacritization
                # https://github.com/mush42/libtashkeel/
                text = tashkeel_run(text)

            phonemes = phonemize_espeak(text, self.config.espeak_voice)
            _LOGGER.debug(f"Phonemized '{text}' to: {phonemes}")
            return phonemes

        if self.config.phoneme_type == PhonemeType.TEXT:
            return phonemize_codepoints(text)

        if self.config.phoneme_type == PhonemeType.OPENJTALK:
            # Use the exact same phonemization as training
            try:
                import os
                import sys

                # Try to import from relative path first
                piper_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                sys.path.insert(0, os.path.join(piper_root, "src", "python"))
                from piper_train.phonemize.japanese import phonemize_japanese

                return [phonemize_japanese(text)]
            except ImportError:
                _LOGGER.warning("Failed to import piper_train phonemizer, falling back")
                return [self._phonemize_japanese_with_prosody(text)]

        raise ValueError(f"Unexpected phoneme type: {self.config.phoneme_type}")

    def _phonemize_japanese_with_prosody(self, text: str) -> list[str]:
        """Phonemize Japanese text with prosody marks (same as training)."""
        if not HAS_PYOPENJTALK:
            raise RuntimeError("pyopenjtalk is required for Japanese phonemization")

        labels = pyopenjtalk.extract_fullcontext(text)
        tokens = []

        def _is_question(text: str) -> bool:
            """Return True if text ends with a question mark."""
            return text.strip().endswith("?") or text.strip().endswith("？")

        for idx, label in enumerate(labels):
            m_ph = _RE_PHONEME.search(label)
            if not m_ph:
                continue
            phoneme = m_ph.group(1)

            # Beginning / end silence handling
            if phoneme == "sil":
                if idx == 0:
                    tokens.append("^")
                elif idx == len(labels) - 1:
                    tokens.append("?" if _is_question(text) else "$")
                continue

            # Short pause
            if phoneme == "pau":
                tokens.append("_")
                continue

            # Keep unvoiced vowels as uppercase
            tokens.append(phoneme)

            # Extract prosody marks
            m_a1 = _RE_A1.search(label)
            m_a2 = _RE_A2.search(label)
            m_a3 = _RE_A3.search(label)
            if not (m_a1 and m_a2 and m_a3):
                continue

            a1 = int(m_a1.group(1))
            a2 = int(m_a2.group(1))
            a3 = int(m_a3.group(1))

            # Look-ahead to next label
            if idx < len(labels) - 1:
                m_a2_next = _RE_A2.search(labels[idx + 1])
                a2_next = int(m_a2_next.group(1)) if m_a2_next else -1
            else:
                a2_next = -1

            # Insert accent nucleus mark "]" at descending point
            if (a1 == 0) and (a2_next == a2 + 1):
                tokens.append("]")

            # Insert accent phrase boundary "#" when current mora is last
            if (a2 == a3) and (a2_next == 1):
                tokens.append("#")

            # Insert rising mark "[" at phrase head
            if (a2 == 1) and (a2_next == 2):
                tokens.append("[")

        # Use the same token mapper as training
        try:
            # Try to import from relative path first
            import os
            import sys
            piper_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            sys.path.insert(0, os.path.join(piper_root, "src", "python"))
            from piper_train.phonemize.token_mapper import map_sequence

            return map_sequence(tokens)
        except ImportError:
            # Fallback to local PUA mapping
            converted = []
            for token in tokens:
                if token in MULTI_CHAR_TO_PUA:
                    converted.append(MULTI_CHAR_TO_PUA[token])
                elif len(token) > 1:
                    _LOGGER.warning("Multi-char token not in PUA map: %s", token)
                    converted.append(token)
                else:
                    converted.append(token)
            return converted

    def phonemes_to_ids(self, phonemes: list[str]) -> tuple[list[int], list[int]]:
        """Phonemes to ids with prosody support for Japanese."""
        id_map = self.config.phoneme_id_map
        ids: list[int] = list(id_map[BOS])
        prosody_ids: list[int] = []

        _LOGGER.debug(f"Converting phonemes to IDs: {phonemes}")
        _LOGGER.debug(f"Available phonemes in id_map: {len(id_map)} items")

        # For Japanese, we need to match the training AccentProcessor logic
        if self.config.phoneme_type == PhonemeType.OPENJTALK:
            # Define prosody mark to ID mapping (must match accent_processor.py)
            prosody_marks = {
                "^": 0,  # start
                "$": 1,  # end_declarative
                "?": 2,  # end_question
                "_": 3,  # pause
                "#": 4,  # boundary
                "[": 5,  # rising
                "]": 6,  # falling
            }
            # ID 14 is for regular phonemes (<PAD> in training)

            for phoneme in phonemes:
                if phoneme not in id_map:
                    _LOGGER.warning("Missing phoneme from id map: %s", phoneme)
                    continue

                ids.extend(id_map[phoneme])

                # Assign prosody ID based on training logic
                if phoneme in prosody_marks:
                    prosody_ids.append(prosody_marks[phoneme])
                else:
                    # Regular phoneme - use <PAD> ID (14)
                    prosody_ids.append(14)

        else:
            # Non-Japanese: original logic
            prosody_ids.append(0)  # BOS prosody

            for phoneme in phonemes:
                if phoneme not in id_map:
                    _LOGGER.warning("Missing phoneme from id map: %s", phoneme)
                    continue

                ids.extend(id_map[phoneme])
                prosody_ids.append(14)  # Default prosody

                # 学習データが PAD("_") を各音素ごとに含んでいるのは eSpeak 方式のみ。
                if self.config.phoneme_type == PhonemeType.ESPEAK:
                    ids.extend(id_map[PAD])
                    prosody_ids.append(14)  # Default prosody for PAD

            prosody_ids.append(1)  # EOS prosody

        ids.extend(id_map[EOS])

        return ids, prosody_ids

    def synthesize(
        self,
        text: str,
        wav_file: wave.Wave_write,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        sentence_silence: float = 0.0,
        volume: float = 1.0,
    ):
        """Synthesize WAV audio from text."""
        wav_file.setframerate(self.config.sample_rate)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setnchannels(1)  # mono

        for audio_bytes in self.synthesize_stream_raw(
            text,
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
            sentence_silence=sentence_silence,
            volume=volume,
        ):
            wav_file.writeframes(audio_bytes)

    def synthesize_stream_raw(
        self,
        text: str,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        sentence_silence: float = 0.0,
        volume: float = 1.0,
    ) -> Iterable[bytes]:
        """Synthesize raw audio per sentence from text."""
        sentence_phonemes = self.phonemize(text)

        # 16-bit mono
        num_silence_samples = int(sentence_silence * self.config.sample_rate)
        silence_bytes = bytes(num_silence_samples * 2)

        for phonemes in sentence_phonemes:
            phoneme_ids, prosody_ids = self.phonemes_to_ids(phonemes)
            yield (
                self.synthesize_ids_to_raw(
                    phoneme_ids,
                    prosody_ids,
                    speaker_id=speaker_id,
                    length_scale=length_scale,
                    noise_scale=noise_scale,
                    noise_w=noise_w,
                    volume=volume,
                )
                + silence_bytes
            )

    def synthesize_ids_to_raw(
        self,
        phoneme_ids: list[int],
        prosody_ids: list[int] | None = None,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        volume: float = 1.0,
    ) -> bytes:
        """Synthesize raw audio from phoneme ids."""
        if length_scale is None:
            length_scale = self.config.length_scale

        if noise_scale is None:
            noise_scale = self.config.noise_scale

        if noise_w is None:
            noise_w = self.config.noise_w

        phoneme_ids_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        phoneme_ids_lengths = np.array([phoneme_ids_array.shape[1]], dtype=np.int64)
        scales = np.array(
            [noise_scale, length_scale, noise_w],
            dtype=np.float32,
        )

        args = {
            "input": phoneme_ids_array,
            "input_lengths": phoneme_ids_lengths,
            "scales": scales,
        }

        # Add prosody_ids if provided and model supports it
        if prosody_ids is not None:
            # Check if the ONNX model expects prosody_ids input
            model_inputs = [input.name for input in self.session.get_inputs()]
            if "prosody_ids" in model_inputs:
                prosody_ids_array = np.expand_dims(
                    np.array(prosody_ids, dtype=np.int64), 0
                )
                args["prosody_ids"] = prosody_ids_array

        if self.config.num_speakers <= 1:
            speaker_id = None

        if (self.config.num_speakers > 1) and (speaker_id is None):
            # Default speaker
            speaker_id = 0

        # Include sid only for multi-speaker models
        if self.config.num_speakers > 1:
            if speaker_id is None:
                speaker_id = 0
            sid = np.expand_dims(np.array([speaker_id], dtype=np.int64), 0)
            args["sid"] = sid

        # Synthesize through Onnx
        audio = self.session.run(
            None,
            args,
        )[0].squeeze((0, 1))
        audio = audio_float_to_int16(audio.squeeze(), volume=volume)
        return audio.tobytes()

import json
import logging
import os
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime

from .config import PhonemeType, PiperConfig
from .const import BOS, EOS, PAD
from .phonemize.token_mapper import FIXED_PUA_MAPPING
from .util import audio_float_to_int16


_LOGGER = logging.getLogger(__name__)

# Multi-character phoneme to PUA character mapping — derived from token_mapper
# to guarantee consistency across the codebase.
MULTI_CHAR_TO_PUA = {k: chr(v) for k, v in FIXED_PUA_MAPPING.items()}


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
            candidate = Path(f"{model_path}.json")
            if candidate.exists():
                config_path = candidate
            else:
                config_path = Path(model_path).parent / "config.json"

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

        sess_options = onnxruntime.SessionOptions()
        sess_options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        sess_options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        physical_cores = os.cpu_count() or 2
        sess_options.intra_op_num_threads = min(physical_cores // 2 or 1, 4)
        sess_options.inter_op_num_threads = 1
        sess_options.enable_cpu_mem_arena = True
        sess_options.enable_mem_pattern = True
        sess_options.enable_mem_reuse = True

        return PiperVoice(
            config=PiperConfig.from_dict(config_dict),
            session=onnxruntime.InferenceSession(
                str(model_path),
                sess_options=sess_options,
                providers=providers,
            ),
        )

    def phonemize(self, text: str) -> list[list[str]]:
        """Text to phonemes grouped by sentence."""
        if self.config.phoneme_type in (
            PhonemeType.MULTILINGUAL,
            PhonemeType.BILINGUAL,
        ):
            from .phonemize.multilingual import MultilingualPhonemizer

            languages = (
                ["ja", "en"]
                if self.config.phoneme_type == PhonemeType.BILINGUAL
                else ["ja", "en", "zh", "es", "fr", "pt"]
            )
            mp = MultilingualPhonemizer(languages=languages)
            phonemes = mp.phonemize(text)
            _LOGGER.debug("MultilingualPhonemizer: '%s' -> %s", text, phonemes)
            return [phonemes]

        if self.config.phoneme_type == PhonemeType.OPENJTALK:
            from .phonemize.japanese import (
                get_default_dictionary,
                phonemize_japanese,
            )

            custom_dict = get_default_dictionary()
            result = (
                phonemize_japanese(text, custom_dict=custom_dict)
                if custom_dict
                else phonemize_japanese(text)
            )
            return [result]

        raise ValueError(f"Unsupported phoneme type: {self.config.phoneme_type}")

    def phonemes_to_ids(self, phonemes: list[str]) -> list[int]:
        """Phonemes to ids."""
        id_map = self.config.phoneme_id_map
        ids: list[int] = list(id_map[BOS])

        for phoneme in phonemes:
            if phoneme not in id_map:
                _LOGGER.warning("Missing phoneme from id map: %s", phoneme)
                continue

            ids.extend(id_map[phoneme])

            # Bilingual and multilingual models use intersperse padding (PAD between phonemes).
            if self.config.phoneme_type in (
                PhonemeType.BILINGUAL,
                PhonemeType.MULTILINGUAL,
            ):
                ids.extend(id_map[PAD])

        ids.extend(id_map[EOS])

        return ids

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
        language_id: int | None = None,
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
            language_id=language_id,
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
        language_id: int | None = None,
    ) -> Iterable[bytes]:
        """Synthesize raw audio per sentence from text."""
        sentence_phonemes = self.phonemize(text)

        # 16-bit mono
        num_silence_samples = int(sentence_silence * self.config.sample_rate)
        silence_bytes = bytes(num_silence_samples * 2)

        for phonemes in sentence_phonemes:
            phoneme_ids = self.phonemes_to_ids(phonemes)
            yield (
                self.synthesize_ids_to_raw(
                    phoneme_ids,
                    speaker_id=speaker_id,
                    length_scale=length_scale,
                    noise_scale=noise_scale,
                    noise_w=noise_w,
                    volume=volume,
                    language_id=language_id,
                )
                + silence_bytes
            )

    def synthesize_ids_to_raw(
        self,
        phoneme_ids: list[int],
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        volume: float = 1.0,
        language_id: int | None = None,
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

        # Include lid for multilingual models
        input_names = {inp.name for inp in self.session.get_inputs()}
        if "lid" in input_names:
            lid_value = language_id if language_id is not None else 0
            lid = np.array([lid_value], dtype=np.int64)
            args["lid"] = lid

        # Include prosody_features if model requires them (zeros as default)
        if "prosody_features" in input_names:
            num_phonemes = phoneme_ids_array.shape[1]
            prosody = np.zeros((1, num_phonemes, 3), dtype=np.int64)
            args["prosody_features"] = prosody

        # Synthesize through Onnx
        audio = self.session.run(
            None,
            args,
        )[0].squeeze(0)
        audio = audio_float_to_int16(audio.squeeze(), volume=volume)
        return audio.tobytes()

"""
Multilingual dataset for VITS training.
Extends the original dataset to support language IDs.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data import Dataset

from ..norm_audio import load_audio

_LOGGER = logging.getLogger(__name__)


@dataclass
class MultilingualUtterance:
    """Single multilingual training utterance."""

    phoneme_ids: list[int]
    audio_norm_path: Path
    audio_spec_path: Path
    speaker_id: int = 0
    language_id: int = 0
    language_ids_per_phoneme: list[int] | None = None  # For code-switching


@dataclass
class MultilingualBatch:
    """Batch of multilingual training examples."""

    phoneme_ids: torch.Tensor
    phoneme_lengths: torch.Tensor
    audio: torch.Tensor
    audio_lengths: torch.Tensor
    spectrogram: torch.Tensor
    spectrogram_lengths: torch.Tensor
    speaker_ids: torch.Tensor | None = None
    language_ids: torch.Tensor = None
    language_ids_per_phoneme: torch.Tensor | None = None  # [batch, seq_len]


class MultilingualDataset(Dataset):
    """Dataset for multilingual VITS training."""

    def __init__(
        self,
        dataset_paths: Sequence[str | Path],
        max_phoneme_ids: int | None = None,
        language_map: dict[str, int] | None = None,
    ):
        self.utterances: list[MultilingualUtterance] = []
        self.language_map = language_map or {
            "ja": 0,
            "en": 1,
            "zh": 2,
            "es": 3,
            "fr": 4,
            "de": 5,
            "ko": 6,
            "mixed": 7,
        }

        # Load utterances from dataset files
        for dataset_path in dataset_paths:
            dataset_path = Path(dataset_path)
            _LOGGER.info("Loading dataset from %s", dataset_path)

            with open(dataset_path, encoding="utf-8") as dataset_file:
                for line in dataset_file:
                    if not line.strip():
                        continue

                    utt_data = json.loads(line)

                    # Extract phoneme IDs
                    phoneme_ids = utt_data["phoneme_ids"]
                    if max_phoneme_ids and (len(phoneme_ids) > max_phoneme_ids):
                        continue

                    # Extract language information
                    text_language = utt_data.get("text_language", "en")
                    language_id = self.language_map.get(
                        text_language, 1
                    )  # Default to English

                    # For code-switching: create per-phoneme language IDs
                    language_ids_per_phoneme = None
                    if "segments" in utt_data and text_language == "mixed":
                        language_ids_per_phoneme = (
                            self._create_per_phoneme_language_ids(
                                utt_data["phonemes"], utt_data["segments"]
                            )
                        )

                    # Create utterance
                    utterance = MultilingualUtterance(
                        phoneme_ids=phoneme_ids,
                        audio_norm_path=Path(utt_data["audio_norm_path"]),
                        audio_spec_path=Path(utt_data["audio_spec_path"]),
                        speaker_id=utt_data.get("speaker_id", 0),
                        language_id=language_id,
                        language_ids_per_phoneme=language_ids_per_phoneme,
                    )
                    self.utterances.append(utterance)

        _LOGGER.info("Loaded %s utterance(s)", len(self.utterances))

        # Calculate language statistics
        lang_counts = {}
        for utt in self.utterances:
            lang_id = utt.language_id
            lang_counts[lang_id] = lang_counts.get(lang_id, 0) + 1

        _LOGGER.info("Language distribution: %s", lang_counts)

    def _create_per_phoneme_language_ids(
        self, phonemes: list[str], segments: list[dict]
    ) -> list[int]:
        """Create per-phoneme language IDs for code-switching."""
        language_ids = []
        current_lang = None

        for phoneme in phonemes:
            # Check if it's a language tag
            if phoneme.startswith("<lang:") and phoneme.endswith(">"):
                # Extract language from tag
                lang_code = phoneme[6:-1]
                current_lang = self.language_map.get(lang_code, 1)
                language_ids.append(current_lang)
            elif phoneme.startswith("</lang:"):
                language_ids.append(current_lang)
                current_lang = None
            else:
                # Regular phoneme
                language_ids.append(current_lang if current_lang is not None else 1)

        return language_ids

    def __len__(self) -> int:
        return len(self.utterances)

    def __getitem__(self, idx: int) -> MultilingualUtterance:
        return self.utterances[idx]


class MultilingualCollate:
    """Collate function for multilingual batches."""

    def __call__(self, utterances: list[MultilingualUtterance]) -> MultilingualBatch:
        # Sort by phoneme length (descending)
        utterances = sorted(
            utterances, key=lambda utt: len(utt.phoneme_ids), reverse=True
        )

        # Collect data
        phoneme_ids = []
        phoneme_lengths = []
        audios = []
        audio_lengths = []
        spectrograms = []
        spectrogram_lengths = []
        speaker_ids = []
        language_ids = []
        language_ids_per_phoneme = []
        has_per_phoneme_lang = False

        for utterance in utterances:
            # Phonemes
            phoneme_ids.append(torch.LongTensor(utterance.phoneme_ids))
            phoneme_lengths.append(len(utterance.phoneme_ids))

            # Audio
            audio_norm = load_audio(utterance.audio_norm_path)
            audios.append(torch.FloatTensor(audio_norm))
            audio_lengths.append(audio_norm.shape[-1])

            # Spectrogram
            audio_spec = np.load(utterance.audio_spec_path)
            spectrograms.append(torch.FloatTensor(audio_spec))
            spectrogram_lengths.append(audio_spec.shape[-1])

            # Speaker and language
            speaker_ids.append(utterance.speaker_id)
            language_ids.append(utterance.language_id)

            # Per-phoneme language IDs
            if utterance.language_ids_per_phoneme is not None:
                has_per_phoneme_lang = True
                language_ids_per_phoneme.append(
                    torch.LongTensor(utterance.language_ids_per_phoneme)
                )
            else:
                # Use utterance-level language ID for all phonemes
                language_ids_per_phoneme.append(
                    torch.full(
                        (len(utterance.phoneme_ids),),
                        utterance.language_id,
                        dtype=torch.long,
                    )
                )

        # Pad sequences
        phoneme_ids = pad_sequence(phoneme_ids, batch_first=True, padding_value=0)
        audios = pad_sequence(audios, batch_first=True, padding_value=0)
        spectrograms = pad_sequence(spectrograms, batch_first=True, padding_value=0)

        if has_per_phoneme_lang:
            language_ids_per_phoneme = pad_sequence(
                language_ids_per_phoneme, batch_first=True, padding_value=0
            )
        else:
            language_ids_per_phoneme = None

        # Convert to tensors
        phoneme_lengths = torch.LongTensor(phoneme_lengths)
        audio_lengths = torch.LongTensor(audio_lengths)
        spectrogram_lengths = torch.LongTensor(spectrogram_lengths)
        speaker_ids = (
            torch.LongTensor(speaker_ids)
            if any(sid > 0 for sid in speaker_ids)
            else None
        )
        language_ids = torch.LongTensor(language_ids)

        return MultilingualBatch(
            phoneme_ids=phoneme_ids,
            phoneme_lengths=phoneme_lengths,
            audio=audios,
            audio_lengths=audio_lengths,
            spectrogram=spectrograms.transpose(1, 2),  # [B, C, T]
            spectrogram_lengths=spectrogram_lengths,
            speaker_ids=speaker_ids,
            language_ids=language_ids,
            language_ids_per_phoneme=language_ids_per_phoneme,
        )

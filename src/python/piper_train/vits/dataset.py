import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from torch import FloatTensor, LongTensor
from torch.utils.data import Dataset

_LOGGER = logging.getLogger("vits.dataset")


@dataclass
class Utterance:
    phoneme_ids: list[int]
    audio_norm_path: Path
    audio_spec_path: Path
    speaker_id: int | None = None
    text: str | None = None
    prosody_ids: list[int] | None = None
    f0_path: Path | None = None


@dataclass
class UtteranceTensors:
    phoneme_ids: LongTensor
    spectrogram: FloatTensor
    audio_norm: FloatTensor
    speaker_id: LongTensor | None = None
    text: str | None = None
    prosody_ids: LongTensor | None = None
    f0_values: FloatTensor | None = None
    f0_voiced: FloatTensor | None = None

    @property
    def spec_length(self) -> int:
        return self.spectrogram.size(1)


@dataclass
class Batch:
    phoneme_ids: LongTensor
    phoneme_lengths: LongTensor
    spectrograms: FloatTensor
    spectrogram_lengths: LongTensor
    audios: FloatTensor
    audio_lengths: LongTensor
    speaker_ids: LongTensor | None = None
    prosody_ids: LongTensor | None = None
    prosody_lengths: LongTensor | None = None
    f0_values: FloatTensor | None = None
    f0_voiced: FloatTensor | None = None


class PiperDataset(Dataset):
    """
    Dataset format:

    * phoneme_ids (required)
    * audio_norm_path (required)
    * audio_spec_path (required)
    * text (optional)
    * phonemes (optional)
    * audio_path (optional)
    """

    def __init__(
        self,
        dataset_paths: list[str | Path],
        max_phoneme_ids: int | None = None,
    ):
        self.utterances: list[Utterance] = []

        for dataset_path in dataset_paths:
            dataset_path = Path(dataset_path)
            _LOGGER.debug("Loading dataset: %s", dataset_path)
            self.utterances.extend(
                PiperDataset.load_dataset(dataset_path, max_phoneme_ids=max_phoneme_ids)
            )

    def __len__(self):
        return len(self.utterances)

    def __getitem__(self, idx) -> UtteranceTensors:
        utt = self.utterances[idx]
        # 問題のあるファイルでロードが失敗した場合はスキップして次を試す
        while True:
            try:
                audio_norm = torch.load(utt.audio_norm_path, map_location="cpu")
                spectrogram = torch.load(utt.audio_spec_path, map_location="cpu")

                # Load F0 if available
                f0_values = None
                f0_voiced = None
                if utt.f0_path is not None and utt.f0_path.exists():
                    try:
                        f0_data = torch.load(utt.f0_path)
                        f0_values = f0_data["f0"]
                        f0_voiced = f0_data["voiced"]

                        # Ensure F0 length matches spectrogram length
                        if f0_values.shape[0] != spectrogram.shape[1]:
                            # Simple interpolation to match lengths
                            f0_values = torch.nn.functional.interpolate(
                                f0_values.unsqueeze(0).unsqueeze(0),
                                size=spectrogram.shape[1],
                                mode='linear',
                                align_corners=False
                            ).squeeze()
                            f0_voiced = torch.nn.functional.interpolate(
                                f0_voiced.unsqueeze(0).unsqueeze(0),
                                size=spectrogram.shape[1],
                                mode='nearest'
                            ).squeeze()
                    except Exception as e:
                        _LOGGER.warning(f"Failed to load F0 from {utt.f0_path}: {e}")

                return UtteranceTensors(
                    phoneme_ids=LongTensor(utt.phoneme_ids),
                    audio_norm=audio_norm,
                    spectrogram=spectrogram,
                    speaker_id=(
                        LongTensor([utt.speaker_id])
                        if utt.speaker_id is not None
                        else None
                    ),
                    text=utt.text,
                    prosody_ids=(
                        LongTensor(utt.prosody_ids)
                        if utt.prosody_ids is not None
                        else None
                    ),
                    f0_values=f0_values,
                    f0_voiced=f0_voiced,
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to load tensors for %s (spec: %s): %s",
                    utt.audio_norm_path,
                    utt.audio_spec_path,
                    e,
                )

                # 破損ファイルとみなし、データセットから除外
                self.utterances.pop(idx)

                # データがすべて無効になった場合はエラー
                if len(self.utterances) == 0:
                    raise RuntimeError("All utterances failed to load") from e

                # 同じインデックスで次の要素を再試行
                if idx >= len(self.utterances):
                    idx = len(self.utterances) - 1
                utt = self.utterances[idx]
                # 次のファイルでリトライ（ログは出さない）

    @staticmethod
    def load_dataset(
        dataset_path: Path,
        max_phoneme_ids: int | None = None,
    ) -> Iterable[Utterance]:
        num_skipped = 0

        with open(dataset_path, encoding="utf-8") as dataset_file:
            for line_idx, line in enumerate(dataset_file):
                line = line.strip()
                if not line:
                    continue

                try:
                    utt = PiperDataset.load_utterance(line)
                    if (max_phoneme_ids is None) or (
                        len(utt.phoneme_ids) <= max_phoneme_ids
                    ):
                        yield utt
                    else:
                        num_skipped += 1
                except Exception:
                    _LOGGER.exception(
                        "Error on line %s of %s: %s",
                        line_idx + 1,
                        dataset_path,
                        line,
                    )

        if num_skipped > 0:
            _LOGGER.warning("Skipped %s utterance(s)", num_skipped)

    @staticmethod
    def load_utterance(line: str) -> Utterance:
        utt_dict = json.loads(line)
        return Utterance(
            phoneme_ids=utt_dict["phoneme_ids"],
            audio_norm_path=Path(utt_dict["audio_norm_path"]),
            audio_spec_path=Path(utt_dict["audio_spec_path"]),
            speaker_id=utt_dict.get("speaker_id"),
            text=utt_dict.get("text"),
            prosody_ids=utt_dict.get("prosody_ids"),
            f0_path=Path(utt_dict["f0_path"]) if "f0_path" in utt_dict else None,
        )


class UtteranceCollate:
    def __init__(self, is_multispeaker: bool, segment_size: int):
        self.is_multispeaker = is_multispeaker
        self.segment_size = segment_size

    def __call__(self, utterances: Sequence[UtteranceTensors]) -> Batch:
        num_utterances = len(utterances)
        assert num_utterances > 0, "No utterances"

        max_phonemes_length = 0
        max_spec_length = 0
        max_audio_length = 0
        max_prosody_length = 0

        num_mels = 0
        has_prosody = any(utt.prosody_ids is not None for utt in utterances)
        has_f0 = any(utt.f0_values is not None for utt in utterances)

        # Determine lengths
        for _utt_idx, utt in enumerate(utterances):
            assert utt.spectrogram is not None
            assert utt.audio_norm is not None

            phoneme_length = utt.phoneme_ids.size(0)
            spec_length = utt.spectrogram.size(1)
            audio_length = utt.audio_norm.size(1)

            max_phonemes_length = max(max_phonemes_length, phoneme_length)
            max_spec_length = max(max_spec_length, spec_length)
            max_audio_length = max(max_audio_length, audio_length)

            if utt.prosody_ids is not None:
                prosody_length = utt.prosody_ids.size(0)
                max_prosody_length = max(max_prosody_length, prosody_length)

            num_mels = utt.spectrogram.size(0)
            if self.is_multispeaker:
                assert utt.speaker_id is not None, "Missing speaker id"

        # Audio cannot be smaller than segment size (8192)
        max_audio_length = max(max_audio_length, self.segment_size)

        # Create padded tensors
        phonemes_padded = LongTensor(num_utterances, max_phonemes_length)
        spec_padded = FloatTensor(num_utterances, num_mels, max_spec_length)
        audio_padded = FloatTensor(num_utterances, 1, max_audio_length)

        phonemes_padded.zero_()
        spec_padded.zero_()
        audio_padded.zero_()

        phoneme_lengths = LongTensor(num_utterances)
        spec_lengths = LongTensor(num_utterances)
        audio_lengths = LongTensor(num_utterances)

        speaker_ids: LongTensor | None = None
        if self.is_multispeaker:
            speaker_ids = LongTensor(num_utterances)

        prosody_ids_padded: LongTensor | None = None
        prosody_lengths: LongTensor | None = None
        if has_prosody and max_prosody_length > 0:
            prosody_ids_padded = LongTensor(num_utterances, max_prosody_length)
            prosody_ids_padded.zero_()
            prosody_lengths = LongTensor(num_utterances)

        f0_padded: FloatTensor | None = None
        f0_voiced_padded: FloatTensor | None = None
        if has_f0:
            f0_padded = FloatTensor(num_utterances, max_spec_length)
            f0_voiced_padded = FloatTensor(num_utterances, max_spec_length)
            f0_padded.zero_()
            f0_voiced_padded.zero_()

        # Sort by decreasing spectrogram length
        sorted_utterances = sorted(
            utterances, key=lambda u: u.spectrogram.size(1), reverse=True
        )
        for utt_idx, utt in enumerate(sorted_utterances):
            phoneme_length = utt.phoneme_ids.size(0)
            spec_length = utt.spectrogram.size(1)
            audio_length = utt.audio_norm.size(1)

            phonemes_padded[utt_idx, :phoneme_length] = utt.phoneme_ids
            phoneme_lengths[utt_idx] = phoneme_length

            spec_padded[utt_idx, :, :spec_length] = utt.spectrogram
            spec_lengths[utt_idx] = spec_length

            audio_padded[utt_idx, :, :audio_length] = utt.audio_norm
            audio_lengths[utt_idx] = audio_length

            if utt.speaker_id is not None:
                assert speaker_ids is not None
                speaker_ids[utt_idx] = utt.speaker_id

            if utt.prosody_ids is not None and prosody_ids_padded is not None:
                prosody_length = utt.prosody_ids.size(0)
                prosody_ids_padded[utt_idx, :prosody_length] = utt.prosody_ids
                prosody_lengths[utt_idx] = prosody_length

            if utt.f0_values is not None and f0_padded is not None:
                f0_length = min(utt.f0_values.size(0), spec_length)
                f0_padded[utt_idx, :f0_length] = utt.f0_values[:f0_length]
                if utt.f0_voiced is not None and f0_voiced_padded is not None:
                    f0_voiced_padded[utt_idx, :f0_length] = utt.f0_voiced[:f0_length]

        return Batch(
            phoneme_ids=phonemes_padded,
            phoneme_lengths=phoneme_lengths,
            spectrograms=spec_padded,
            spectrogram_lengths=spec_lengths,
            audios=audio_padded,
            audio_lengths=audio_lengths,
            speaker_ids=speaker_ids,
            prosody_ids=prosody_ids_padded,
            prosody_lengths=prosody_lengths,
            f0_values=f0_padded,
            f0_voiced=f0_voiced_padded,
        )

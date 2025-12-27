import json
import logging
import random
from collections import defaultdict
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
    prosody_features: list[dict | None] | None = None  # A1/A2/A3 per phoneme


@dataclass
class UtteranceTensors:
    phoneme_ids: LongTensor
    spectrogram: FloatTensor
    audio_norm: FloatTensor
    speaker_id: LongTensor | None = None
    text: str | None = None
    prosody_features: LongTensor | None = None  # Shape: (num_phonemes, 3) for A1/A2/A3

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
    prosody_features: LongTensor | None = None  # Shape: (batch, max_phonemes, 3)


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
                audio_norm = torch.load(
                    utt.audio_norm_path, map_location="cpu", weights_only=True
                )
                spectrogram = torch.load(
                    utt.audio_spec_path, map_location="cpu", weights_only=True
                )

                # Convert prosody_features to tensor if available
                prosody_tensor = None
                if utt.prosody_features is not None:
                    prosody_tensor = self._prosody_features_to_tensor(utt.prosody_features)

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
                    prosody_features=prosody_tensor,
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
    def _prosody_features_to_tensor(
        prosody_features: list[dict | None],
    ) -> LongTensor:
        """Convert prosody features (list of dicts) to tensor.

        Args:
            prosody_features: List of {"a1": int, "a2": int, "a3": int} or None

        Returns:
            LongTensor of shape (num_phonemes, 3) where:
            - [:, 0] = A1 values (accent nucleus relative position)
            - [:, 1] = A2 values (mora position in phrase, 1-based)
            - [:, 2] = A3 values (total morae in phrase)
            - Special tokens (None) are encoded as (0, 0, 0)
        """
        result = []
        for feat in prosody_features:
            if feat is not None:
                result.append([feat["a1"], feat["a2"], feat["a3"]])
            else:
                # Special tokens (^, $, ?, _, #, [, ]) have no prosody info
                result.append([0, 0, 0])
        return LongTensor(result)

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
            prosody_features=utt_dict.get("prosody_features"),
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

        num_mels = 0
        has_prosody = False

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

            num_mels = utt.spectrogram.size(0)
            if self.is_multispeaker:
                assert utt.speaker_id is not None, "Missing speaker id"

            if utt.prosody_features is not None:
                has_prosody = True

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

        # Create prosody tensor if any utterance has prosody features
        prosody_padded: LongTensor | None = None
        if has_prosody:
            prosody_padded = LongTensor(num_utterances, max_phonemes_length, 3)
            prosody_padded.zero_()

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

            if prosody_padded is not None and utt.prosody_features is not None:
                prosody_padded[utt_idx, :phoneme_length, :] = utt.prosody_features

        return Batch(
            phoneme_ids=phonemes_padded,
            phoneme_lengths=phoneme_lengths,
            spectrograms=spec_padded,
            spectrogram_lengths=spec_lengths,
            audios=audio_padded,
            audio_lengths=audio_lengths,
            speaker_ids=speaker_ids,
            prosody_features=prosody_padded,
        )


class SpeakerBalancedBatchSampler:
    """
    各バッチに同一話者のサンプルが複数含まれるようにするサンプラー

    20話者モデルでDuration Predictor (SDP) が崩壊する問題の解決策として実装。
    従来のランダムサンプリングでは、バッチ内の同一話者サンプル数が少なく
    (20話者の場合約1.6件/バッチ)、SDPが話者埋め込みを安定して学習できない。

    このサンプラーは各バッチに同一話者からsamples_per_speaker個のサンプルを
    含めることで、SDPの学習を安定化させる。

    DDP (Distributed Data Parallel) 対応:
    - torch.distributedが初期化されている場合、各GPUが異なるバッチを取得
    - 全GPUで同じseedを使用してバッチ生成順序を揃え、
      rank番目のバッチのみを各GPUが取得

    Args:
        dataset: PiperDataset (utterancesリストを持つ) または torch.utils.data.Subset
        batch_size: バッチサイズ
        samples_per_speaker: 各話者からのサンプル数 (デフォルト: 4)
        drop_last: 最後の不完全バッチを捨てるか (デフォルト: True)

    Example:
        batch_size=32, samples_per_speaker=4 の場合:
        → 8話者 × 4サンプル = 32サンプル/バッチ

        バッチ構成例:
        [話者0×4, 話者3×4, 話者7×4, 話者12×4, 話者5×4, 話者18×4, 話者9×4, 話者15×4]
    """

    def __init__(
        self,
        dataset,
        batch_size: int,
        samples_per_speaker: int = 4,
        drop_last: bool = True,
    ):
        # 話者ごとにインデックスをグループ化
        # Subsetの場合は元のデータセットのutterancesを参照
        self.speaker_to_indices: dict[int, list[int]] = defaultdict(list)

        # datasetがSubsetの場合の対応
        if hasattr(dataset, "indices") and hasattr(dataset, "dataset"):
            # torch.utils.data.Subset
            original_dataset = dataset.dataset
            indices = dataset.indices
            for subset_idx, original_idx in enumerate(indices):
                utt = original_dataset.utterances[original_idx]
                speaker_id = utt.speaker_id if utt.speaker_id is not None else 0
                self.speaker_to_indices[speaker_id].append(subset_idx)
        else:
            # PiperDataset または utterances属性を持つデータセット
            for idx, utt in enumerate(dataset.utterances):
                speaker_id = utt.speaker_id if utt.speaker_id is not None else 0
                self.speaker_to_indices[speaker_id].append(idx)

        self.speakers = list(self.speaker_to_indices.keys())
        self.batch_size = batch_size
        self.samples_per_speaker = samples_per_speaker
        self.speakers_per_batch = batch_size // samples_per_speaker
        self.drop_last = drop_last

        # DDP対応: rank と world_size を取得
        if torch.distributed.is_initialized():
            self.rank = torch.distributed.get_rank()
            self.world_size = torch.distributed.get_world_size()
        else:
            self.rank = 0
            self.world_size = 1

        self.epoch = 0  # エポックごとにシャッフルを変えるため

        # バリデーション
        if self.speakers_per_batch <= 0:
            raise ValueError(
                f"batch_size ({batch_size}) must be >= samples_per_speaker ({samples_per_speaker})"
            )

        if len(self.speakers) < self.speakers_per_batch:
            _LOGGER.warning(
                "Number of speakers (%d) is less than speakers_per_batch (%d). "
                "Some batches may have fewer speakers.",
                len(self.speakers),
                self.speakers_per_batch,
            )

    def set_epoch(self, epoch: int):
        """エポック番号を設定（DDP時のシャッフル制御用）"""
        self.epoch = epoch

    def __iter__(self):
        # DDP対応: エポックに基づいた固定シードを使用して全GPUで同じバッチ順序を生成
        # 各GPUは rank 番目のバッチのみを取得
        rng = random.Random(self.epoch)

        # 各話者のインデックスをシャッフル
        speaker_indices = {
            spk: rng.sample(indices, len(indices))
            for spk, indices in self.speaker_to_indices.items()
        }
        speaker_pointers = dict.fromkeys(self.speakers, 0)

        batch_idx = 0
        while True:
            # 十分なサンプルが残っている話者を選択
            available_speakers = [
                spk
                for spk in self.speakers
                if speaker_pointers[spk] + self.samples_per_speaker
                <= len(speaker_indices[spk])
            ]

            if len(available_speakers) < self.speakers_per_batch:
                break

            # ランダムに話者を選択
            batch_speakers = rng.sample(available_speakers, self.speakers_per_batch)
            batch = []

            for spk in batch_speakers:
                start = speaker_pointers[spk]
                end = start + self.samples_per_speaker
                batch.extend(speaker_indices[spk][start:end])
                speaker_pointers[spk] = end

            # DDP: このGPUが担当するバッチのみを返す
            if batch_idx % self.world_size == self.rank:
                yield batch
            batch_idx += 1

    def __len__(self) -> int:
        # より正確な計算: 各話者から取れるバッチ数を計算
        # 話者間でサンプル消費のタイミングがずれるため、最小話者のサンプル数で制限
        min_samples = min(len(indices) for indices in self.speaker_to_indices.values())
        # 各話者から取れるバッチ参加回数
        batches_per_speaker = min_samples // self.samples_per_speaker
        # 全バッチ数 = 話者数 × 各話者の参加回数 ÷ バッチあたり話者数
        # 保守的に見積もるため、切り捨てを使用
        total_batches = (
            len(self.speakers) * batches_per_speaker
        ) // self.speakers_per_batch
        # DDP: 各GPUが担当するバッチ数を返す
        batches_per_gpu = total_batches // self.world_size
        return max(1, batches_per_gpu)

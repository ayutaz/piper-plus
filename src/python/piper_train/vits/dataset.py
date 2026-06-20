import json
import logging
import os
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import FloatTensor, LongTensor
from torch.utils.data import Dataset


_LOGGER = logging.getLogger("vits.dataset")


def _load_tensor(path: Path) -> torch.Tensor:
    """Load a tensor from either numpy (.npy) or torch format."""
    path = Path(path)
    if path.suffix == ".npy":
        return torch.from_numpy(np.load(str(path)))
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except Exception:
        # Fallback: try numpy load for .npy files saved with wrong extension
        return torch.from_numpy(np.load(str(path)))


@dataclass
class Utterance:
    phoneme_ids: np.ndarray  # dtype=int16, shape=(num_phonemes,)
    audio_norm_path: Path
    audio_spec_path: Path
    speaker_id: int | None = None
    language_id: int | None = None
    text: str | None = None
    prosody_features: list[dict | None] | None = None  # A1/A2/A3 per phoneme
    speaker_embedding_path: Path | None = None


@dataclass
class UtteranceTensors:
    phoneme_ids: LongTensor
    spectrogram: FloatTensor
    audio_norm: FloatTensor
    speaker_id: LongTensor | None = None
    language_id: LongTensor | None = None
    text: str | None = None
    prosody_features: LongTensor | None = None  # Shape: (num_phonemes, 3) for A1/A2/A3
    speaker_embedding: FloatTensor | None = None

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
    language_ids: LongTensor | None = None
    prosody_features: LongTensor | None = None  # Shape: (batch, max_phonemes, 3)
    speaker_embeddings: FloatTensor | None = None


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
        max_spec_length: int | None = None,
        filter_length: int = 1024,
        validate_cache: bool = False,
    ):
        self.utterances: list[Utterance] = []

        for dataset_path in dataset_paths:
            dataset_path = Path(dataset_path)
            _LOGGER.debug("Loading dataset: %s", dataset_path)
            self.utterances.extend(
                PiperDataset.load_dataset(
                    dataset_path,
                    max_phoneme_ids=max_phoneme_ids,
                    max_spec_length=max_spec_length,
                    filter_length=filter_length,
                )
            )

        if validate_cache:
            before = len(self.utterances)
            self.utterances = [
                utt for utt in self.utterances if self._validate_cache_files(utt)
            ]
            removed = before - len(self.utterances)
            if removed:
                _LOGGER.warning(
                    "validate_cache: removed %d corrupted/missing cache file(s) "
                    "out of %d utterances.",
                    removed,
                    before,
                )
            else:
                _LOGGER.info("validate_cache: all %d cache files are intact.", before)

    def __len__(self):
        return len(self.utterances)

    def __getitem__(self, idx) -> UtteranceTensors:
        utt = self.utterances[idx]
        audio_norm = _load_tensor(utt.audio_norm_path)
        if audio_norm.dim() == 1:
            audio_norm = audio_norm.unsqueeze(0)

        spectrogram = _load_tensor(utt.audio_spec_path)
        # Convert float16 spec to float32 (new caches are saved as float16 to save disk space)
        if spectrogram.dtype == torch.float16:
            spectrogram = spectrogram.float()

        # Convert prosody_features to tensor if available
        prosody_tensor = None
        if utt.prosody_features is not None:
            prosody_tensor = self._prosody_features_to_tensor(utt.prosody_features)

        # Load speaker embedding from .npy file if available
        speaker_embedding_tensor = None
        if utt.speaker_embedding_path is not None:
            spk_emb = np.load(utt.speaker_embedding_path, allow_pickle=False).astype(
                np.float32
            )
            if spk_emb.ndim != 1:
                raise ValueError(
                    f"speaker_embedding must be 1-D, got shape {spk_emb.shape} "
                    f"from {utt.speaker_embedding_path}"
                )
            expected_dim = getattr(self, "speaker_embedding_dim", 192)
            if spk_emb.shape[0] != expected_dim:
                raise ValueError(
                    f"speaker_embedding dim must be {expected_dim}, got {spk_emb.shape[0]} "
                    f"from {utt.speaker_embedding_path}"
                )
            speaker_embedding_tensor = torch.from_numpy(spk_emb)

        return UtteranceTensors(
            phoneme_ids=LongTensor(utt.phoneme_ids),
            audio_norm=audio_norm,
            spectrogram=spectrogram,
            speaker_id=(
                LongTensor([utt.speaker_id]) if utt.speaker_id is not None else None
            ),
            language_id=(
                LongTensor([utt.language_id]) if utt.language_id is not None else None
            ),
            text=utt.text,
            prosody_features=prosody_tensor,
            speaker_embedding=speaker_embedding_tensor,
        )

    @staticmethod
    def _validate_cache_files(utt: Utterance) -> bool:
        """Check that both cached audio files exist on disk."""
        if not utt.audio_norm_path.exists():
            _LOGGER.debug("Missing audio_norm: %s", utt.audio_norm_path)
            return False
        if not utt.audio_spec_path.exists():
            _LOGGER.debug("Missing audio_spec: %s", utt.audio_spec_path)
            return False
        return True

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
        max_spec_length: int | None = None,
        filter_length: int = 1024,
    ) -> Iterable[Utterance]:
        num_skipped_phoneme = 0
        num_skipped_spec = 0

        # Precompute spec channel count for file-size-based length estimation
        # spec shape: [filter_length // 2 + 1, T], stored as float32 (4 bytes)
        spec_channels = filter_length // 2 + 1
        bytes_per_frame = spec_channels * 4
        # NumPy .npy files have a small header (~128 bytes).
        # PyTorch .pt files have a ~2KB header.
        # Using the smaller value (128) is conservative — it overestimates
        # spec_length, so borderline-long utterances are correctly filtered out.
        spec_header_bytes_npy = 128
        spec_header_bytes_pt = 2048

        dataset_dir = dataset_path.parent

        with open(dataset_path, encoding="utf-8") as dataset_file:
            for line_idx, line in enumerate(dataset_file):
                line = line.strip()
                if not line:
                    continue

                try:
                    utt = PiperDataset.load_utterance(line, dataset_dir)
                    if (max_phoneme_ids is not None) and (
                        len(utt.phoneme_ids) > max_phoneme_ids
                    ):
                        num_skipped_phoneme += 1
                        continue

                    # Filter by spectrogram length using file size estimation.
                    # Uses os.path.getsize() (a single stat syscall) instead of
                    # loading every spec file at init time.
                    if max_spec_length is not None:
                        file_size = os.path.getsize(utt.audio_spec_path)
                        header_bytes = (
                            spec_header_bytes_npy
                            if utt.audio_spec_path.suffix == ".npy"
                            else spec_header_bytes_pt
                        )
                        estimated_spec_length = (
                            file_size - header_bytes
                        ) // bytes_per_frame
                        if estimated_spec_length > max_spec_length:
                            num_skipped_spec += 1
                            continue

                    yield utt
                except Exception:
                    _LOGGER.exception(
                        "Error on line %s of %s: %s",
                        line_idx + 1,
                        dataset_path,
                        line,
                    )

        if num_skipped_phoneme > 0:
            _LOGGER.warning(
                "Skipped %s utterance(s) exceeding max_phoneme_ids", num_skipped_phoneme
            )
        if num_skipped_spec > 0:
            _LOGGER.warning(
                "Filtered %s utterance(s) exceeding max_spec_length=%s",
                num_skipped_spec,
                max_spec_length,
            )

    @staticmethod
    def load_utterance(line: str, dataset_dir: Path | None = None) -> Utterance:
        utt_dict = json.loads(line)

        def _resolve(p: str) -> Path:
            """Resolve a path: if relative and dataset_dir given, prepend it."""
            path = Path(p)
            if not path.is_absolute() and dataset_dir is not None:
                return dataset_dir / path
            return path

        spk_emb_path = utt_dict.get("speaker_embedding_path")
        return Utterance(
            phoneme_ids=utt_dict["phoneme_ids"],
            audio_norm_path=_resolve(utt_dict["audio_norm_path"]),
            audio_spec_path=_resolve(utt_dict["audio_spec_path"]),
            speaker_id=utt_dict.get("speaker_id"),
            language_id=utt_dict.get("language_id"),
            text=utt_dict.get("text"),
            prosody_features=utt_dict.get("prosody_features"),
            speaker_embedding_path=_resolve(spk_emb_path) if spk_emb_path else None,
        )


class UtteranceCollate:
    def __init__(
        self, is_multispeaker: bool, segment_size: int, is_multilanguage: bool = False
    ):
        self.is_multispeaker = is_multispeaker
        self.is_multilanguage = is_multilanguage
        self.segment_size = segment_size

    def __call__(self, utterances: Sequence[UtteranceTensors]) -> Batch:
        num_utterances = len(utterances)
        assert num_utterances > 0, "No utterances"

        max_phonemes_length = 0
        max_spec_length = 0
        max_audio_length = 0

        num_mels = 0
        has_prosody = False
        has_speaker_embedding = False

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

            if utt.speaker_embedding is not None:
                has_speaker_embedding = True

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

        language_ids: LongTensor | None = None
        if self.is_multilanguage:
            language_ids = LongTensor(num_utterances).zero_()

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

            if self.is_multispeaker and utt.speaker_id is not None:
                assert speaker_ids is not None
                speaker_ids[utt_idx] = utt.speaker_id

            if utt.language_id is not None and language_ids is not None:
                language_ids[utt_idx] = utt.language_id

            if prosody_padded is not None and utt.prosody_features is not None:
                # prosody_features の長さが phoneme_length と異なる場合に対応
                prosody_length = min(len(utt.prosody_features), phoneme_length)
                if prosody_length > 0:
                    prosody_padded[utt_idx, :prosody_length, :] = utt.prosody_features[
                        :prosody_length
                    ]

        # Stack speaker embeddings (固定長のためパディング不要)
        speaker_embeddings: FloatTensor | None = None
        if has_speaker_embedding:
            emb_list = []
            for utt in sorted_utterances:
                if utt.speaker_embedding is not None:
                    emb_list.append(utt.speaker_embedding)
                else:
                    # Fallback: zero embedding if some utterances don't have it
                    emb_dim = next(
                        u.speaker_embedding.size(-1)
                        for u in sorted_utterances
                        if u.speaker_embedding is not None
                    )
                    emb_list.append(torch.zeros(emb_dim))
            speaker_embeddings = torch.stack(emb_list)

        return Batch(
            phoneme_ids=phonemes_padded,
            phoneme_lengths=phoneme_lengths,
            spectrograms=spec_padded,
            spectrogram_lengths=spec_lengths,
            audios=audio_padded,
            audio_lengths=audio_lengths,
            speaker_ids=speaker_ids,
            language_ids=language_ids,
            prosody_features=prosody_padded,
            speaker_embeddings=speaker_embeddings,
        )


class SpeakerBalancedBatchSampler:
    """
    各バッチに同一話者のサンプルが複数含まれるようにするサンプラー

    20話者モデルでDuration Predictor (SDP) が崩壊する問題の解決策として実装。
    従来のランダムサンプリングでは、バッチ内の同一話者サンプル数が少なく
    (20話者の場合約1.6件/バッチ)、SDPが話者埋め込みを安定して学習できない。

    このサンプラーは各バッチに同一話者からsamples_per_speaker個のサンプルを
    含めることで、SDPの学習を安定化させる。

    language_group_balance の動作:
        - True: 言語グループ (JA/EN) を 50:50 でバランスする（強制有効化）
        - False: バランスしない（強制無効化）
        - None (デフォルト): 自動判定。言語間の話者数比が 3:1 以上の場合に自動有効化。
        EN 話者数 >> JA 話者数の場合に JA 音質が劣化するのを防ぐ。
        例: 20 JA話者 + 310 EN話者 → 各バッチで JA 5話者 + EN 5話者 を保証

    DDP (Distributed Data Parallel) 対応:
    - torch.distributedが初期化されている場合、各GPUが異なるバッチを取得
    - 全GPUで同じseedを使用してバッチ生成順序を揃え、
      rank番目のバッチのみを各GPUが取得

    Args:
        dataset: PiperDataset (utterancesリストを持つ) または torch.utils.data.Subset
        batch_size: バッチサイズ
        samples_per_speaker: 各話者からのサンプル数 (デフォルト: 4)
        drop_last: 最後の不完全バッチを捨てるか (デフォルト: True)
        language_group_balance: 言語グループ (JA/EN) を 50:50 でバランスするか (デフォルト: None=自動判定)

    Example:
        batch_size=32, samples_per_speaker=4 の場合:
        → 8話者 × 4サンプル = 32サンプル/バッチ

        language_group_balance=True の場合:
        → JA 4話者 × 4サンプル + EN 4話者 × 4サンプル = 32サンプル/バッチ
    """

    def __init__(
        self,
        dataset,
        batch_size: int,
        samples_per_speaker: int = 4,
        drop_last: bool = True,
        language_group_balance: bool | None = None,
    ):
        # 話者ごとにインデックスをグループ化
        # Subsetの場合は元のデータセットのutterancesを参照
        self.speaker_to_indices: dict[int, list[int]] = defaultdict(list)
        speaker_to_language: dict[int, int] = {}

        # datasetがSubsetの場合の対応
        if hasattr(dataset, "indices") and hasattr(dataset, "dataset"):
            # torch.utils.data.Subset
            original_dataset = dataset.dataset
            indices = dataset.indices
            for subset_idx, original_idx in enumerate(indices):
                utt = original_dataset.utterances[original_idx]
                speaker_id = utt.speaker_id if utt.speaker_id is not None else 0
                self.speaker_to_indices[speaker_id].append(subset_idx)
                if speaker_id not in speaker_to_language:
                    speaker_to_language[speaker_id] = (
                        utt.language_id if utt.language_id is not None else 0
                    )
        else:
            # PiperDataset または utterances属性を持つデータセット
            for idx, utt in enumerate(dataset.utterances):
                speaker_id = utt.speaker_id if utt.speaker_id is not None else 0
                self.speaker_to_indices[speaker_id].append(idx)
                if speaker_id not in speaker_to_language:
                    speaker_to_language[speaker_id] = (
                        utt.language_id if utt.language_id is not None else 0
                    )

        self.speakers = list(self.speaker_to_indices.keys())
        self.batch_size = batch_size
        self.samples_per_speaker = samples_per_speaker
        # 話者数が少ない場合は実際の話者数を使用
        calculated_speakers_per_batch = batch_size // samples_per_speaker
        self.speakers_per_batch = min(calculated_speakers_per_batch, len(self.speakers))
        # 実際のバッチサイズを調整
        self.effective_batch_size = self.speakers_per_batch * samples_per_speaker
        self.drop_last = drop_last

        # 自動判定: language_group_balance が None の場合
        if language_group_balance is None:
            lang_speaker_counts = Counter(speaker_to_language.values())
            if len(lang_speaker_counts) >= 2:
                majority = max(lang_speaker_counts.values())
                minority = min(lang_speaker_counts.values())
                ratio = majority / minority if minority > 0 else float("inf")
                if ratio >= 3.0:
                    language_group_balance = True
                    _LOGGER.info(
                        "Auto-enabled language-balanced sampling "
                        "(speaker ratio %.1f:1, threshold 3.0)",
                        ratio,
                    )
                else:
                    language_group_balance = False
            else:
                language_group_balance = False

        self.language_group_balance = language_group_balance

        # 言語グループ均等サンプリングの準備
        self.lang_groups: dict[int, list[int]] = defaultdict(list)
        if language_group_balance:
            for spk_id in self.speakers:
                lang = speaker_to_language.get(spk_id, 0)
                self.lang_groups[lang].append(spk_id)
            # N言語均等スロット配分
            n_lang_groups = len(self.lang_groups)
            base_slots = self.speakers_per_batch // n_lang_groups
            remainder = self.speakers_per_batch % n_lang_groups
            # lang_slots: {lang_id: num_slots}
            # 余りは先頭言語に配分
            self.lang_slots: dict[int, int] = {}
            for i, lang_id in enumerate(sorted(self.lang_groups.keys())):
                self.lang_slots[lang_id] = base_slots + (1 if i < remainder else 0)
            lang_counts = {lang: len(spks) for lang, spks in self.lang_groups.items()}
            _LOGGER.info(
                "Language group balance enabled: %s, lang_slots=%s",
                lang_counts,
                self.lang_slots,
            )

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

        if len(self.speakers) < calculated_speakers_per_batch:
            _LOGGER.warning(
                "Number of speakers (%d) is less than requested speakers_per_batch (%d). "
                "Using %d speakers per batch (effective batch_size=%d).",
                len(self.speakers),
                calculated_speakers_per_batch,
                self.speakers_per_batch,
                self.effective_batch_size,
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

        # 全バッチを先に生成してから world_size の倍数に切り詰める
        # これにより全 DDP rank が同じバッチ数を受け取ることを保証する
        all_batches = []
        while True:
            if self.language_group_balance:
                # N言語グループ均等サンプリング
                lang_available: dict[int, list[int]] = {}
                for lang_id, speakers_in_lang in self.lang_groups.items():
                    lang_available[lang_id] = [
                        spk
                        for spk in speakers_in_lang
                        if speaker_pointers[spk] + self.samples_per_speaker
                        <= len(speaker_indices[spk])
                    ]
                # 全言語グループがスロット数を満たせるか確認
                if any(
                    len(lang_available.get(lang_id, []))
                    < self.lang_slots.get(lang_id, 0)
                    for lang_id in self.lang_slots
                ):
                    break
                batch_speakers = []
                for lang_id in sorted(self.lang_slots.keys()):
                    n_slots = self.lang_slots[lang_id]
                    batch_speakers.extend(rng.sample(lang_available[lang_id], n_slots))
            else:
                # 従来の全話者均等サンプリング
                available_speakers = [
                    spk
                    for spk in self.speakers
                    if speaker_pointers[spk] + self.samples_per_speaker
                    <= len(speaker_indices[spk])
                ]
                if len(available_speakers) < self.speakers_per_batch:
                    break
                batch_speakers = rng.sample(available_speakers, self.speakers_per_batch)

            batch = []
            for spk in batch_speakers:
                start = speaker_pointers[spk]
                end = start + self.samples_per_speaker
                batch.extend(speaker_indices[spk][start:end])
                speaker_pointers[spk] = end

            all_batches.append(batch)

        # DDP: world_size の倍数に切り詰めて全 rank が同じバッチ数を受け取る
        usable = (len(all_batches) // self.world_size) * self.world_size
        for batch_idx in range(usable):
            if batch_idx % self.world_size == self.rank:
                yield all_batches[batch_idx]

    def __len__(self) -> int:
        if self.language_group_balance:
            # N言語グループ均等サンプリング: 各言語の総利用可能バッチ数で推定
            # __iter__ は話者が使い切られても他の話者が残っていれば継続するため、
            # 各言語の「全話者の合計利用可能サンプル数 / slots」で推定する
            lang_batches_list = []
            for lang_id, slots in self.lang_slots.items():
                speakers_in_lang = self.lang_groups.get(lang_id, [])
                if not speakers_in_lang or slots == 0:
                    continue
                total_usable = sum(
                    (len(self.speaker_to_indices[s]) // self.samples_per_speaker)
                    for s in speakers_in_lang
                )
                batches = total_usable // slots
                lang_batches_list.append(batches)
            if lang_batches_list:
                total_batches = min(lang_batches_list)
                return max(1, total_batches // self.world_size)

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

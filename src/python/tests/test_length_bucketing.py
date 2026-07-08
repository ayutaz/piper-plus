"""
Length-based bucketing tests for SpeakerBalancedBatchSampler.

The `length_bucket` opt-in flag pre-sorts each speaker's utterance indices by
phoneme length and groups them into buckets of `samples_per_speaker` before
shuffling bucket order. This is intended to reduce padding overhead in
UtteranceCollate by making the phoneme lengths within a batch more similar.

These tests guarantee:
1. The samples_per_speaker=4 contract is preserved in both modes.
2. Batch size is correct in both modes.
3. length_bucket=True produces significantly lower intra-batch length spread
   than length_bucket=False on a broad length distribution.
4. length_bucket=True still visits every speaker across an epoch (no starvation).
5. Bucket order changes across epochs (diversity preserved).
"""

import random
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean

import pytest


torch = pytest.importorskip(
    "torch", reason="torch is required for SpeakerBalancedBatchSampler tests"
)

from piper_train.vits.dataset import SpeakerBalancedBatchSampler  # noqa: E402


@dataclass
class MockUtterance:
    speaker_id: int
    phoneme_ids: list = field(default_factory=list)
    language_id: int | None = None


class MockLengthDataset:
    """Mock dataset with configurable phoneme_length per utterance."""

    def __init__(
        self,
        num_speakers: int,
        samples_per_speaker: int,
        min_len: int = 20,
        max_len: int = 400,
        seed: int = 12345,
    ):
        """Build num_speakers * samples_per_speaker utterances with
        phoneme_ids of a random length uniformly drawn from [min_len, max_len].
        """
        rng = random.Random(seed)
        self.utterances = []
        for speaker_id in range(num_speakers):
            for _ in range(samples_per_speaker):
                length = rng.randint(min_len, max_len)
                # phoneme_ids as a list of that length (values don't matter for
                # the sampler; only len() is read)
                self.utterances.append(
                    MockUtterance(
                        speaker_id=speaker_id,
                        phoneme_ids=[0] * length,
                    )
                )


def _batch_lengths(batch: list[int], dataset: MockLengthDataset) -> list[int]:
    return [len(dataset.utterances[i].phoneme_ids) for i in batch]


def _batch_length_spread(batch: list[int], dataset: MockLengthDataset) -> int:
    """max - min phoneme length within the batch (padding waste proxy)."""
    lengths = _batch_lengths(batch, dataset)
    return max(lengths) - min(lengths)


def _intra_speaker_spread(batch: list[int], dataset: MockLengthDataset) -> float:
    """Mean (max-min) phoneme length spread within each speaker's sub-batch.

    This is what the sampler directly controls: samples_per_speaker
    consecutive slots from the same speaker. Under length_bucket=True those
    slots are drawn from a length-sorted bucket, so this spread must shrink
    substantially. Under length_bucket=False they are random.
    """
    grouped: dict[int, list[int]] = {}
    for idx in batch:
        spk = dataset.utterances[idx].speaker_id
        grouped.setdefault(spk, []).append(len(dataset.utterances[idx].phoneme_ids))
    per_spk_spreads = [max(v) - min(v) for v in grouped.values() if len(v) > 1]
    if not per_spk_spreads:
        return 0.0
    return sum(per_spk_spreads) / len(per_spk_spreads)


@pytest.mark.training
@pytest.mark.unit
class TestLengthBucketing:
    """Tests for length_bucket=True opt-in path of SpeakerBalancedBatchSampler."""

    def _make_dataset(self):
        # 100 speakers * 20 utterances = 2000 utterances,
        # phoneme_length in [20, 400] uniformly.
        return MockLengthDataset(
            num_speakers=100,
            samples_per_speaker=20,
            min_len=20,
            max_len=400,
        )

    def test_samples_per_speaker_contract_off(self):
        """length_bucket=False: same-speaker count within a batch == samples_per_speaker."""
        dataset = self._make_dataset()
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=False,
        )
        for batch in sampler:
            counts = Counter(dataset.utterances[i].speaker_id for i in batch)
            for spk, cnt in counts.items():
                assert cnt == 4, (
                    f"speaker {spk} has {cnt} samples in batch, expected 4"
                )

    def test_samples_per_speaker_contract_on(self):
        """length_bucket=True must preserve the samples_per_speaker=4 contract."""
        dataset = self._make_dataset()
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=True,
        )
        batch_count = 0
        for batch in sampler:
            batch_count += 1
            counts = Counter(dataset.utterances[i].speaker_id for i in batch)
            for spk, cnt in counts.items():
                assert cnt == 4, (
                    f"length_bucket=True: speaker {spk} has {cnt} samples, expected 4"
                )
        assert batch_count > 0, "length_bucket=True produced no batches"

    def test_batch_size_matches(self):
        """Batch size == effective_batch_size in both modes."""
        dataset = self._make_dataset()
        for length_bucket in (False, True):
            sampler = SpeakerBalancedBatchSampler(
                dataset,
                batch_size=32,
                samples_per_speaker=4,
                length_bucket=length_bucket,
            )
            for batch in sampler:
                assert len(batch) == 32, (
                    f"length_bucket={length_bucket}: batch size "
                    f"{len(batch)} != 32"
                )

    def test_length_bucketing_reduces_padding(self):
        """The core property: length_bucket=True must reduce the intra-speaker
        length spread within each batch (that is what the sampler directly
        controls). The overall batch spread is dominated by cross-speaker
        variance and is only weakly affected.
        """
        dataset = self._make_dataset()

        sampler_off = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=False,
        )
        sampler_on = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=True,
        )

        intra_off = [_intra_speaker_spread(b, dataset) for b in sampler_off]
        intra_on = [_intra_speaker_spread(b, dataset) for b in sampler_on]

        assert intra_off and intra_on, "sampler produced no batches"

        mean_off = mean(intra_off)
        mean_on = mean(intra_on)

        # For a uniform [20, 400] distribution the expected max-min spread of
        # 4 samples drawn without replacement is ~3/5 * 380 = ~228 (off case).
        # With sorted buckets of 4 from 20 sorted samples, each bucket has a
        # spread of ~380/5 = ~76 (on case). The reduction is dramatic —
        # a 50% threshold is very conservative.
        assert mean_on < mean_off * 0.5, (
            f"length_bucket=True did not shrink intra-speaker length spread: "
            f"off={mean_off:.1f}, on={mean_on:.1f} (expected on < off * 0.5)"
        )

    def test_all_speakers_visited(self):
        """length_bucket=True must not starve any speaker in a single epoch."""
        dataset = self._make_dataset()
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=True,
        )
        visited: set[int] = set()
        for batch in sampler:
            for idx in batch:
                visited.add(dataset.utterances[idx].speaker_id)
        # All 100 speakers should appear at least once across the epoch.
        assert len(visited) == 100, (
            f"length_bucket=True visited only {len(visited)}/100 speakers"
        )

    def test_epoch_shuffle_differs(self):
        """Bucket order must change between epochs (diversity preserved)."""
        dataset = self._make_dataset()
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=True,
        )
        sampler.set_epoch(0)
        batches_epoch0 = [tuple(b) for b in sampler]
        sampler.set_epoch(1)
        batches_epoch1 = [tuple(b) for b in sampler]
        # The two epoch sequences must not be byte-identical
        # (buckets themselves are stable within a speaker, but the order
        # in which speakers get chosen + buckets get shuffled must differ).
        assert batches_epoch0 != batches_epoch1, (
            "length_bucket=True produced identical batch sequences across epochs"
        )

    def test_no_duplicate_within_epoch(self):
        """length_bucket=True must not emit the same index twice in one epoch."""
        dataset = self._make_dataset()
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=True,
        )
        seen: set[int] = set()
        for batch in sampler:
            for idx in batch:
                assert idx not in seen, (
                    f"index {idx} emitted twice within one epoch"
                )
                seen.add(idx)

    def test_default_off_is_backward_compatible(self):
        """Constructing without the length_bucket kwarg must behave like False."""
        dataset = self._make_dataset()
        sampler_default = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
        )
        sampler_false = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=32,
            samples_per_speaker=4,
            length_bucket=False,
        )
        # Same epoch seed -> identical batch sequences
        sampler_default.set_epoch(7)
        sampler_false.set_epoch(7)
        assert [tuple(b) for b in sampler_default] == [
            tuple(b) for b in sampler_false
        ], "default kwarg differs from length_bucket=False"

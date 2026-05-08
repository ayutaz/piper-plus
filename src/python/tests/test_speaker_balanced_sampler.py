"""
SpeakerBalancedBatchSampler unit tests

Tests for the speaker-balanced batch sampling feature that ensures
each batch contains multiple samples from the same speaker.
This is critical for stable Duration Predictor training in multi-speaker models.

Test guarantees:
1. Each batch contains exactly batch_size samples
2. Each batch contains samples_per_speaker samples from each speaker (core)
3. Each batch contains batch_size // samples_per_speaker speakers
4. No duplicate samples within an epoch
5. All speakers are sampled across batches
6. Different sampling order between epochs
7. __len__ returns accurate batch count

Note: These tests require torch. They are skipped in CI environments
where torch is not installed.
"""

from collections import Counter
from dataclasses import dataclass

import pytest


# Skip entire module if torch is not available (required by piper_train.vits.dataset)
torch = pytest.importorskip(
    "torch", reason="torch is required for SpeakerBalancedBatchSampler tests"
)

from piper_train.vits.dataset import SpeakerBalancedBatchSampler  # noqa: E402


@dataclass
class MockUtterance:
    """Mock utterance for testing"""

    speaker_id: int
    language_id: int | None = None


class MockDataset:
    """Mock dataset for testing"""

    def __init__(self, num_speakers: int, samples_per_speaker: int):
        """
        Args:
            num_speakers: Number of speakers
            samples_per_speaker: Number of samples per speaker
        """
        self.utterances = []
        for speaker_id in range(num_speakers):
            for _ in range(samples_per_speaker):
                self.utterances.append(MockUtterance(speaker_id=speaker_id))


class MockBilingualDataset:
    """Mock bilingual dataset with language_id support for testing"""

    def __init__(
        self,
        ja_speakers: int,
        en_speakers: int,
        samples_per_speaker: int,
    ):
        self.utterances = []
        # JA speakers: speaker_id 0..ja_speakers-1, language_id=0
        for speaker_id in range(ja_speakers):
            for _ in range(samples_per_speaker):
                self.utterances.append(
                    MockUtterance(speaker_id=speaker_id, language_id=0)
                )
        # EN speakers: speaker_id ja_speakers..ja_speakers+en_speakers-1, language_id=1
        for speaker_id in range(ja_speakers, ja_speakers + en_speakers):
            for _ in range(samples_per_speaker):
                self.utterances.append(
                    MockUtterance(speaker_id=speaker_id, language_id=1)
                )


def count_speakers_in_batch(batch: list[int], dataset: MockDataset) -> Counter:
    """Count samples per speaker in a batch"""
    speaker_ids = [dataset.utterances[idx].speaker_id for idx in batch]
    return Counter(speaker_ids)


@pytest.mark.training
class TestSpeakerBalancedBatchSampler:
    """Tests for SpeakerBalancedBatchSampler"""

    @pytest.fixture
    def mock_dataset_20speakers(self):
        """20 speakers, 100 samples each"""
        return MockDataset(num_speakers=20, samples_per_speaker=100)

    @pytest.fixture
    def mock_dataset_5speakers(self):
        """5 speakers, 50 samples each"""
        return MockDataset(num_speakers=5, samples_per_speaker=50)

    @pytest.mark.unit
    def test_batch_size_correct(self, mock_dataset_20speakers):
        """Verify each batch contains exactly batch_size samples"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        batch_count = 0
        for batch in sampler:
            assert len(batch) == batch_size, (
                f"Batch size is not {batch_size}: {len(batch)}"
            )
            batch_count += 1

        assert batch_count > 0, "No batches were generated"

    @pytest.mark.unit
    def test_samples_per_speaker_in_batch(self, mock_dataset_20speakers):
        """Verify each batch contains samples_per_speaker samples from each speaker

        This is the most important test - core for Duration Predictor training stability.
        """
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        for batch in sampler:
            speaker_counts = count_speakers_in_batch(batch, mock_dataset_20speakers)
            for speaker, count in speaker_counts.items():
                assert count == samples_per_speaker, (
                    f"Speaker {speaker} has {count} samples, expected {samples_per_speaker}"
                )

    @pytest.mark.unit
    def test_speakers_per_batch(self, mock_dataset_20speakers):
        """Verify each batch contains batch_size // samples_per_speaker speakers"""
        batch_size = 32
        samples_per_speaker = 4
        expected_speakers_per_batch = batch_size // samples_per_speaker  # 8

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        for batch in sampler:
            speakers = {
                mock_dataset_20speakers.utterances[idx].speaker_id for idx in batch
            }
            assert len(speakers) == expected_speakers_per_batch, (
                f"Batch has {len(speakers)} speakers, expected {expected_speakers_per_batch}"
            )

    @pytest.mark.unit
    def test_no_duplicate_within_epoch(self, mock_dataset_20speakers):
        """Verify no duplicate samples within an epoch"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        all_indices = []
        for batch in sampler:
            all_indices.extend(batch)

        assert len(all_indices) == len(set(all_indices)), (
            f"Duplicate indices found: {len(all_indices)} != {len(set(all_indices))}"
        )

    @pytest.mark.unit
    def test_all_speakers_sampled(self, mock_dataset_20speakers):
        """Verify all speakers are sampled across batches"""
        batch_size = 32
        samples_per_speaker = 4
        num_speakers = 20

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        all_indices = []
        for batch in sampler:
            all_indices.extend(batch)

        sampled_speakers = {
            mock_dataset_20speakers.utterances[idx].speaker_id for idx in all_indices
        }
        expected_speakers = set(range(num_speakers))

        assert sampled_speakers == expected_speakers, (
            f"Not all speakers sampled: {sampled_speakers} != {expected_speakers}"
        )

    @pytest.mark.unit
    def test_shuffle_between_epochs(self, mock_dataset_20speakers):
        """Verify different sampling order between epochs"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        sampler.set_epoch(0)
        batches_epoch1 = [batch.copy() for batch in sampler]
        sampler.set_epoch(1)
        batches_epoch2 = [batch.copy() for batch in sampler]

        # At least some batches should be different
        # (probability of being identical is extremely low)
        assert batches_epoch1 != batches_epoch2, (
            "Two epochs have identical batches (not shuffled)"
        )

    @pytest.mark.unit
    def test_len_returns_reasonable_count(self, mock_dataset_20speakers):
        """Verify __len__ returns a reasonable batch count"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        expected_len = len(sampler)
        actual_len = sum(1 for _ in sampler)

        # Allow 80%-110% range due to random selection variance
        # DataLoader progress bar can tolerate minor inaccuracies
        assert expected_len >= actual_len * 0.8, (
            f"__len__ too small: {expected_len} < {actual_len * 0.8}"
        )
        assert expected_len <= actual_len * 1.1, (
            f"__len__ too large: {expected_len} > {actual_len * 1.1}"
        )

    @pytest.mark.unit
    def test_different_batch_sizes(self, mock_dataset_20speakers):
        """Verify sampler works with different batch_size and samples_per_speaker combinations"""
        test_cases = [
            (20, 4),  # 5 speakers x 4 samples
            (16, 2),  # 8 speakers x 2 samples
            (40, 8),  # 5 speakers x 8 samples
        ]

        for batch_size, samples_per_speaker in test_cases:
            sampler = SpeakerBalancedBatchSampler(
                mock_dataset_20speakers,
                batch_size=batch_size,
                samples_per_speaker=samples_per_speaker,
            )

            for batch in sampler:
                assert len(batch) == batch_size
                speaker_counts = count_speakers_in_batch(batch, mock_dataset_20speakers)
                for count in speaker_counts.values():
                    assert count == samples_per_speaker

    @pytest.mark.unit
    def test_5speakers_dataset(self, mock_dataset_5speakers):
        """Verify sampler works correctly with 5 speakers"""
        batch_size = 20
        samples_per_speaker = 4
        expected_speakers_per_batch = 5  # 20 // 4 = 5

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_5speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        batch_count = 0
        for batch in sampler:
            assert len(batch) == batch_size
            speakers = {
                mock_dataset_5speakers.utterances[idx].speaker_id for idx in batch
            }
            assert len(speakers) == expected_speakers_per_batch
            batch_count += 1

        assert batch_count > 0

    @pytest.mark.unit
    def test_auto_enable_language_balance_when_imbalanced(self):
        """Auto-enable when speaker ratio >= 3:1 and language_group_balance=None"""
        # 20 JA + 310 EN → ratio 15.5:1 → auto-enable
        dataset = MockBilingualDataset(
            ja_speakers=20, en_speakers=310, samples_per_speaker=50
        )
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=20,
            samples_per_speaker=2,
            language_group_balance=None,
        )
        assert sampler.language_group_balance is True

    @pytest.mark.unit
    def test_no_auto_enable_when_balanced(self):
        """No auto-enable when speaker ratio < 3:1 and language_group_balance=None"""
        # 20 JA + 20 EN → ratio 1:1 → no auto-enable
        dataset = MockBilingualDataset(
            ja_speakers=20, en_speakers=20, samples_per_speaker=50
        )
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=20,
            samples_per_speaker=2,
            language_group_balance=None,
        )
        assert sampler.language_group_balance is False

    @pytest.mark.unit
    def test_explicit_true_overrides_auto(self):
        """Explicit True skips auto-detection"""
        # Even with balanced speakers, explicit True forces it on
        dataset = MockBilingualDataset(
            ja_speakers=20, en_speakers=20, samples_per_speaker=50
        )
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=20,
            samples_per_speaker=2,
            language_group_balance=True,
        )
        assert sampler.language_group_balance is True

    @pytest.mark.unit
    def test_single_language_no_auto_enable(self):
        """No auto-enable with single language and language_group_balance=None"""
        # All speakers same language → no auto-enable
        dataset = MockDataset(num_speakers=20, samples_per_speaker=50)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=20,
            samples_per_speaker=2,
            language_group_balance=None,
        )
        assert sampler.language_group_balance is False


# ---------------------------------------------------------------------------
# Edge case: DDP rank-disjoint batches (audit gap #6)
# ---------------------------------------------------------------------------


@pytest.mark.training
class TestSpeakerBalancedSamplerDDP:
    """Verify DDP rank partitioning is disjoint and consistent across world_size.

    The sampler's ``__iter__`` yields ``all_batches[idx]`` only when
    ``idx % world_size == rank`` (dataset.py L580).  Each rank therefore
    sees a disjoint subset.  We simulate DDP by directly setting the
    ``rank`` / ``world_size`` attributes on already-constructed sampler
    instances — no real ``torch.distributed`` init required.

    Sample indices form natural identity within an epoch (no duplicates
    inside a single iter), so cross-rank disjointness is asserted via
    set intersection over per-rank-collected indices.
    """

    @pytest.fixture
    def big_dataset(self):
        """Large enough dataset to produce many batches across ranks."""
        # 32 speakers * 100 samples each; batch_size=16, samples_per_speaker=4
        # → 4 speakers/batch, ~lots of batches before exhaustion.
        return MockDataset(num_speakers=32, samples_per_speaker=100)

    def _make_rank_sampler(self, dataset, batch_size, samples_per_speaker, world_size, rank):
        """Build a sampler then patch (rank, world_size) post-init.

        The sampler reads ``torch.distributed.is_initialized()`` only
        during ``__init__``. Overwriting the cached attributes afterward
        gives identical behaviour to a real DDP environment.
        """
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )
        sampler.rank = rank
        sampler.world_size = world_size
        return sampler

    @pytest.mark.unit
    def test_rank_disjoint_world_size_2(self, big_dataset):
        """world_size=2: rank=0 and rank=1 produce disjoint batch sets.

        Each rank yields ``len(all_batches) // 2`` batches; together they
        cover every usable batch exactly once.
        """
        batch_size = 16
        samples_per_speaker = 4

        sampler_r0 = self._make_rank_sampler(
            big_dataset, batch_size, samples_per_speaker, world_size=2, rank=0
        )
        sampler_r1 = self._make_rank_sampler(
            big_dataset, batch_size, samples_per_speaker, world_size=2, rank=1
        )
        # Same epoch -> same RNG seed -> same all_batches order.
        sampler_r0.set_epoch(0)
        sampler_r1.set_epoch(0)

        batches_r0 = [tuple(b) for b in sampler_r0]
        batches_r1 = [tuple(b) for b in sampler_r1]

        # Both ranks must produce at least one batch
        assert len(batches_r0) > 0, "rank=0 produced no batches"
        assert len(batches_r1) > 0, "rank=1 produced no batches"

        # Disjoint: no batch tuple appears in both ranks
        set_r0 = set(batches_r0)
        set_r1 = set(batches_r1)
        intersection = set_r0 & set_r1
        assert intersection == set(), (
            f"rank=0 and rank=1 batches overlap: {len(intersection)} shared batches"
        )

        # Stronger: per-sample disjointness within an epoch
        idx_r0 = {idx for batch in batches_r0 for idx in batch}
        idx_r1 = {idx for batch in batches_r1 for idx in batch}
        assert idx_r0 & idx_r1 == set(), (
            f"Sample indices overlap across ranks: "
            f"{len(idx_r0 & idx_r1)} shared indices"
        )

    @pytest.mark.unit
    def test_rank_disjoint_world_size_4(self, big_dataset):
        """world_size=4: all four ranks produce mutually disjoint batches."""
        batch_size = 16
        samples_per_speaker = 4
        world_size = 4

        samplers = [
            self._make_rank_sampler(
                big_dataset, batch_size, samples_per_speaker,
                world_size=world_size, rank=r,
            )
            for r in range(world_size)
        ]
        # Identical epoch on every rank
        for s in samplers:
            s.set_epoch(0)

        per_rank_batches = [[tuple(b) for b in s] for s in samplers]
        # Every rank yields at least one batch
        for r, b in enumerate(per_rank_batches):
            assert len(b) > 0, f"rank={r} produced no batches"

        # Pairwise disjoint check
        for i in range(world_size):
            for j in range(i + 1, world_size):
                shared = set(per_rank_batches[i]) & set(per_rank_batches[j])
                assert shared == set(), (
                    f"rank={i} and rank={j} share {len(shared)} batches"
                )

        # All-rank sample-index disjointness
        all_indices = []
        for r in range(world_size):
            ranked = {idx for batch in per_rank_batches[r] for idx in batch}
            for prior in all_indices:
                assert ranked & prior == set(), (
                    f"rank={r} indices overlap with a prior rank"
                )
            all_indices.append(ranked)

    @pytest.mark.unit
    def test_rank_consistent_count_world_size_2(self, big_dataset):
        """world_size=2: each rank receives the same number of batches.

        The sampler trims ``all_batches`` to a multiple of ``world_size``
        (line 578) so both ranks get exactly ``len(all_batches) // 2``.
        """
        batch_size = 16
        samples_per_speaker = 4

        sampler_r0 = self._make_rank_sampler(
            big_dataset, batch_size, samples_per_speaker, world_size=2, rank=0
        )
        sampler_r1 = self._make_rank_sampler(
            big_dataset, batch_size, samples_per_speaker, world_size=2, rank=1
        )
        sampler_r0.set_epoch(0)
        sampler_r1.set_epoch(0)

        n_r0 = sum(1 for _ in sampler_r0)
        n_r1 = sum(1 for _ in sampler_r1)
        assert n_r0 == n_r1, (
            f"rank=0 yielded {n_r0} batches but rank=1 yielded {n_r1}; "
            "world_size truncation should equalize them"
        )

        # Also verify against single-rank baseline (world_size=1).
        sampler_full = self._make_rank_sampler(
            big_dataset, batch_size, samples_per_speaker, world_size=1, rank=0
        )
        sampler_full.set_epoch(0)
        n_full = sum(1 for _ in sampler_full)
        # Per-rank count is ~ (n_full - n_full % 2) / 2
        expected_per_rank = (n_full // 2) * 2 // 2
        assert n_r0 == expected_per_rank, (
            f"rank=0 batches ({n_r0}) != expected ({expected_per_rank}) "
            f"derived from world_size=1 baseline ({n_full})"
        )

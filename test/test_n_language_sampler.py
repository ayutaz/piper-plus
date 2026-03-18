"""Tests for N-language balanced batch sampling."""

import pytest


class TestNLanguageSampler:
    """Tests for N-language generalized SpeakerBalancedBatchSampler."""

    def _create_mock_dataset(self, speaker_langs):
        """Create a mock dataset with given speaker→language mapping.

        Args:
            speaker_langs: dict mapping speaker_id to language_id
        """
        from dataclasses import dataclass

        @dataclass
        class MockUtterance:
            speaker_id: int
            language_id: int

        class MockDataset:
            def __init__(self, utterances):
                self.utterances = utterances

        utterances = []
        for spk_id, lang_id in speaker_langs.items():
            # Add 20 utterances per speaker
            for _ in range(20):
                utterances.append(MockUtterance(speaker_id=spk_id, language_id=lang_id))

        return MockDataset(utterances)

    def test_two_language_50_50(self):
        """2 languages should produce 50/50 split (backward compat)."""
        try:
            from piper_train.vits.dataset import SpeakerBalancedBatchSampler
        except ImportError:
            pytest.skip("piper_train not available")

        # 4 JA speakers + 4 EN speakers
        speaker_langs = {}
        for i in range(4):
            speaker_langs[i] = 0  # JA
        for i in range(4, 8):
            speaker_langs[i] = 1  # EN

        dataset = self._create_mock_dataset(speaker_langs)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=8,
            samples_per_speaker=2,
            language_group_balance=True,
        )

        # 4 speakers per batch, 50/50 → 2 JA + 2 EN
        assert sampler.lang_slots == {0: 2, 1: 2}

    def test_three_language_equal_split(self):
        """3 languages with 9 speakers per batch → 3+3+3."""
        try:
            from piper_train.vits.dataset import SpeakerBalancedBatchSampler
        except ImportError:
            pytest.skip("piper_train not available")

        speaker_langs = {}
        for i in range(3):
            speaker_langs[i] = 0  # JA
        for i in range(3, 6):
            speaker_langs[i] = 1  # EN
        for i in range(6, 9):
            speaker_langs[i] = 2  # ZH

        dataset = self._create_mock_dataset(speaker_langs)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=18,
            samples_per_speaker=2,
            language_group_balance=True,
        )

        # 9 speakers per batch, 3 groups → 3+3+3
        assert sampler.lang_slots == {0: 3, 1: 3, 2: 3}

    def test_three_language_remainder(self):
        """3 languages with 10 speakers per batch → 4+3+3 (remainder to first)."""
        try:
            from piper_train.vits.dataset import SpeakerBalancedBatchSampler
        except ImportError:
            pytest.skip("piper_train not available")

        speaker_langs = {}
        for i in range(4):
            speaker_langs[i] = 0
        for i in range(4, 8):
            speaker_langs[i] = 1
        for i in range(8, 12):
            speaker_langs[i] = 2

        dataset = self._create_mock_dataset(speaker_langs)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=20,
            samples_per_speaker=2,
            language_group_balance=True,
        )

        # 10 speakers, 3 groups: 10//3=3 base, remainder 1 → first group gets 4
        total_slots = sum(sampler.lang_slots.values())
        assert total_slots == 10
        # Remainder goes to first group
        assert sampler.lang_slots[0] == 4
        assert sampler.lang_slots[1] == 3
        assert sampler.lang_slots[2] == 3

    def test_auto_enable_three_languages(self):
        """Auto-enable should work with 3+ languages too."""
        try:
            from piper_train.vits.dataset import SpeakerBalancedBatchSampler
        except ImportError:
            pytest.skip("piper_train not available")

        speaker_langs = {}
        # 2 JA + 20 EN + 20 ZH → ratio 10:1, should auto-enable
        for i in range(2):
            speaker_langs[i] = 0
        for i in range(2, 22):
            speaker_langs[i] = 1
        for i in range(22, 42):
            speaker_langs[i] = 2

        dataset = self._create_mock_dataset(speaker_langs)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=6,
            samples_per_speaker=2,
            language_group_balance=None,  # auto
        )

        assert sampler.language_group_balance is True

    def test_iter_produces_batches(self):
        """Verify __iter__ produces valid batches with N languages."""
        try:
            from piper_train.vits.dataset import SpeakerBalancedBatchSampler
        except ImportError:
            pytest.skip("piper_train not available")

        speaker_langs = {}
        for i in range(4):
            speaker_langs[i] = 0
        for i in range(4, 8):
            speaker_langs[i] = 1

        dataset = self._create_mock_dataset(speaker_langs)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=8,
            samples_per_speaker=2,
            language_group_balance=True,
        )

        batches = list(sampler)
        assert len(batches) > 0
        for batch in batches:
            assert len(batch) == 8  # 4 speakers * 2 samples

    def test_len_with_three_languages(self):
        """__len__ should work correctly with 3 language groups."""
        try:
            from piper_train.vits.dataset import SpeakerBalancedBatchSampler
        except ImportError:
            pytest.skip("piper_train not available")

        speaker_langs = {}
        for i in range(3):
            speaker_langs[i] = 0
        for i in range(3, 6):
            speaker_langs[i] = 1
        for i in range(6, 9):
            speaker_langs[i] = 2

        dataset = self._create_mock_dataset(speaker_langs)
        sampler = SpeakerBalancedBatchSampler(
            dataset,
            batch_size=6,
            samples_per_speaker=2,
            language_group_balance=True,
        )

        length = len(sampler)
        assert length > 0

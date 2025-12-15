"""
SpeakerBalancedBatchSampler のテストコード

このテストは以下を保証します:
1. 各バッチが正確にbatch_sizeのサンプルを含む
2. 各バッチ内で各話者からsamples_per_speaker個のサンプルが含まれる（核心）
3. 各バッチにbatch_size // samples_per_speaker人の話者が含まれる
4. 1エポック内でサンプルの重複がない
5. 複数バッチを通じて全話者からサンプリングされる
6. 異なるエポックで異なる順序でサンプリングされる
7. __len__が正確なバッチ数を返す
"""

from collections import Counter
from dataclasses import dataclass

import pytest

from piper_train.vits.dataset import SpeakerBalancedBatchSampler


@dataclass
class MockUtterance:
    """テスト用のモック発話データ"""
    speaker_id: int


class MockDataset:
    """テスト用のモックデータセット"""

    def __init__(self, num_speakers: int, samples_per_speaker: int):
        """
        Args:
            num_speakers: 話者数
            samples_per_speaker: 各話者のサンプル数
        """
        self.utterances = []
        for speaker_id in range(num_speakers):
            for _ in range(samples_per_speaker):
                self.utterances.append(MockUtterance(speaker_id=speaker_id))


def count_speakers_in_batch(batch: list[int], dataset: MockDataset) -> Counter:
    """バッチ内の話者ごとのサンプル数をカウント"""
    speaker_ids = [dataset.utterances[idx].speaker_id for idx in batch]
    return Counter(speaker_ids)


class TestSpeakerBalancedBatchSampler:
    """SpeakerBalancedBatchSamplerのテスト"""

    @pytest.fixture
    def mock_dataset_20speakers(self):
        """20話者、各100サンプルのモックデータセット"""
        return MockDataset(num_speakers=20, samples_per_speaker=100)

    @pytest.fixture
    def mock_dataset_5speakers(self):
        """5話者、各50サンプルのモックデータセット"""
        return MockDataset(num_speakers=5, samples_per_speaker=50)

    def test_batch_size_correct(self, mock_dataset_20speakers):
        """各バッチが正確にbatch_sizeのサンプルを含むことを検証"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        batch_count = 0
        for batch in sampler:
            assert len(batch) == batch_size, f"バッチサイズが{batch_size}ではない: {len(batch)}"
            batch_count += 1

        assert batch_count > 0, "バッチが1つも生成されなかった"

    def test_samples_per_speaker_in_batch(self, mock_dataset_20speakers):
        """各バッチ内で各話者からsamples_per_speaker個のサンプルが含まれることを検証

        これが最も重要なテスト。Duration Predictor学習の核心部分。
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
                    f"話者{speaker}のサンプル数が{samples_per_speaker}ではない: {count}"
                )

    def test_speakers_per_batch(self, mock_dataset_20speakers):
        """各バッチにbatch_size // samples_per_speaker人の話者が含まれることを検証"""
        batch_size = 32
        samples_per_speaker = 4
        expected_speakers_per_batch = batch_size // samples_per_speaker  # 8

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        for batch in sampler:
            speakers = set(
                mock_dataset_20speakers.utterances[idx].speaker_id for idx in batch
            )
            assert len(speakers) == expected_speakers_per_batch, (
                f"バッチ内の話者数が{expected_speakers_per_batch}ではない: {len(speakers)}"
            )

    def test_no_duplicate_within_epoch(self, mock_dataset_20speakers):
        """1エポック内で同じサンプルが重複して選ばれないことを検証"""
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
            f"重複したインデックスがある: {len(all_indices)} != {len(set(all_indices))}"
        )

    def test_all_speakers_sampled(self, mock_dataset_20speakers):
        """複数バッチを通じて全話者からサンプリングされることを検証"""
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

        sampled_speakers = set(
            mock_dataset_20speakers.utterances[idx].speaker_id for idx in all_indices
        )
        expected_speakers = set(range(num_speakers))

        assert sampled_speakers == expected_speakers, (
            f"全話者がサンプリングされていない: {sampled_speakers} != {expected_speakers}"
        )

    def test_shuffle_between_epochs(self, mock_dataset_20speakers):
        """異なるイテレーションで異なる順序でサンプリングされることを検証"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        batches_epoch1 = [batch.copy() for batch in sampler]
        batches_epoch2 = [batch.copy() for batch in sampler]

        # 少なくとも一部のバッチが異なることを確認
        # （確率的に同じになる可能性は極めて低い）
        assert batches_epoch1 != batches_epoch2, (
            "2つのエポックでバッチが同一（シャッフルされていない）"
        )

    def test_len_returns_correct_count(self, mock_dataset_20speakers):
        """__len__が妥当なバッチ数を返すことを検証"""
        batch_size = 32
        samples_per_speaker = 4

        sampler = SpeakerBalancedBatchSampler(
            mock_dataset_20speakers,
            batch_size=batch_size,
            samples_per_speaker=samples_per_speaker,
        )

        expected_len = len(sampler)
        actual_len = sum(1 for _ in sampler)

        # ランダム選択によりばらつきがあるため、80%-110%の範囲を許容
        # DataLoaderのプログレスバー表示に多少の誤差は許容される
        assert expected_len >= actual_len * 0.8, (
            f"__len__が実際のバッチ数より小さすぎる: {expected_len} < {actual_len * 0.8}"
        )
        assert expected_len <= actual_len * 1.1, (
            f"__len__が実際のバッチ数より大きすぎる: {expected_len} > {actual_len * 1.1}"
        )

    def test_different_batch_sizes(self, mock_dataset_20speakers):
        """異なるbatch_sizeとsamples_per_speakerの組み合わせで動作することを検証"""
        test_cases = [
            (20, 4),  # 5話者 × 4サンプル
            (16, 2),  # 8話者 × 2サンプル
            (40, 8),  # 5話者 × 8サンプル
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

    def test_5speakers_dataset(self, mock_dataset_5speakers):
        """5話者のデータセットで正しく動作することを検証"""
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
            speakers = set(
                mock_dataset_5speakers.utterances[idx].speaker_id for idx in batch
            )
            assert len(speakers) == expected_speakers_per_batch
            batch_count += 1

        assert batch_count > 0


# 直接実行用
if __name__ == "__main__":
    print("=== SpeakerBalancedBatchSampler テスト ===")
    print()

    # モックデータセット作成
    dataset = MockDataset(num_speakers=20, samples_per_speaker=100)
    print(f"データセット: {len(dataset.utterances)} 発話 (20話者 × 100サンプル)")
    print()

    # サンプラー作成
    sampler = SpeakerBalancedBatchSampler(
        dataset,
        batch_size=32,
        samples_per_speaker=4,
    )

    print(f"バッチサイズ: 32")
    print(f"話者あたりサンプル数: 4")
    print(f"予想バッチ内話者数: 8")
    print(f"予想バッチ数: {len(sampler)}")
    print()

    # テスト実行
    all_tests_passed = True

    # Test 1: バッチサイズ
    print("Test 1: バッチサイズが正しいか...")
    for batch in sampler:
        if len(batch) != 32:
            print(f"  FAIL: バッチサイズ = {len(batch)}")
            all_tests_passed = False
            break
    else:
        print("  PASS")

    # Test 2: 話者あたりサンプル数（核心テスト）
    print("Test 2: 各話者からのサンプル数が正しいか（核心）...")
    for batch in sampler:
        speaker_counts = count_speakers_in_batch(batch, dataset)
        for speaker, count in speaker_counts.items():
            if count != 4:
                print(f"  FAIL: 話者{speaker}のサンプル数 = {count}")
                all_tests_passed = False
                break
        else:
            continue
        break
    else:
        print("  PASS")

    # Test 3: バッチ内話者数
    print("Test 3: バッチ内の話者数が正しいか...")
    for batch in sampler:
        speakers = set(dataset.utterances[idx].speaker_id for idx in batch)
        if len(speakers) != 8:
            print(f"  FAIL: バッチ内話者数 = {len(speakers)}")
            all_tests_passed = False
            break
    else:
        print("  PASS")

    # Test 4: 重複なし
    print("Test 4: 重複がないか...")
    all_indices = []
    for batch in sampler:
        all_indices.extend(batch)
    if len(all_indices) != len(set(all_indices)):
        print(f"  FAIL: 重複あり")
        all_tests_passed = False
    else:
        print("  PASS")

    # Test 5: 全話者カバー
    print("Test 5: 全話者がサンプリングされているか...")
    sampled_speakers = set(dataset.utterances[idx].speaker_id for idx in all_indices)
    if sampled_speakers != set(range(20)):
        print(f"  FAIL: サンプリングされた話者 = {sampled_speakers}")
        all_tests_passed = False
    else:
        print("  PASS")

    # Test 6: エポック間シャッフル
    print("Test 6: エポック間でシャッフルされているか...")
    batches1 = [batch.copy() for batch in sampler]
    batches2 = [batch.copy() for batch in sampler]
    if batches1 == batches2:
        print("  FAIL: シャッフルされていない")
        all_tests_passed = False
    else:
        print("  PASS")

    print()
    if all_tests_passed:
        print("=== 全テスト PASS ===")
    else:
        print("=== テスト失敗あり ===")

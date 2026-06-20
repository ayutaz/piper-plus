"""Tests for piper_train.extract_speaker_embedding (per-utterance extraction)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# conftest.py adds src/python to sys.path so this import works
from piper_train import extract_speaker_embedding as ese


# ---------------------------------------------------------------------------
# _filter_for_shard
# ---------------------------------------------------------------------------


class TestFilterForShard:
    """Validate the modulo-based shard partitioning helper."""

    def test_no_sharding_returns_copy(self):
        items = [1, 2, 3, 4]
        result = ese._filter_for_shard(items, shard=0, num_shards=1)
        assert result == items
        # 元のリストへの破壊がないこと
        assert result is not items

    def test_partition_is_disjoint_and_complete_when_evenly_divisible(self):
        n = 100
        num_shards = 4
        items = list(range(n))
        union: set[int] = set()
        for shard in range(num_shards):
            chunk = ese._filter_for_shard(items, shard=shard, num_shards=num_shards)
            assert len(chunk) == n // num_shards
            assert set(chunk).isdisjoint(union), (
                f"shard {shard} overlaps with previous shards"
            )
            union.update(chunk)
        assert union == set(items)

    def test_partition_is_balanced_when_uneven(self):
        # 101 items / 4 shards -> some shards 26, others 25
        n = 101
        num_shards = 4
        items = list(range(n))
        sizes = [
            len(ese._filter_for_shard(items, shard=s, num_shards=num_shards))
            for s in range(num_shards)
        ]
        assert sum(sizes) == n
        # 大小差は最大1
        assert max(sizes) - min(sizes) <= 1

    def test_each_shard_takes_modulo_indices(self):
        items = ["a", "b", "c", "d", "e", "f"]
        # shard 0 / 3 → indices 0, 3 → "a", "d"
        assert ese._filter_for_shard(items, 0, 3) == ["a", "d"]
        # shard 1 / 3 → indices 1, 4 → "b", "e"
        assert ese._filter_for_shard(items, 1, 3) == ["b", "e"]
        # shard 2 / 3 → indices 2, 5 → "c", "f"
        assert ese._filter_for_shard(items, 2, 3) == ["c", "f"]

    def test_invalid_shard_raises(self):
        items = [1, 2, 3]
        with pytest.raises(ValueError, match="shard must be in"):
            ese._filter_for_shard(items, shard=4, num_shards=4)
        with pytest.raises(ValueError, match="shard must be in"):
            ese._filter_for_shard(items, shard=-1, num_shards=4)

    def test_empty_list_returns_empty(self):
        assert ese._filter_for_shard([], 0, 4) == []

    def test_more_shards_than_items(self):
        items = ["x", "y"]
        # 5 shards で 2 アイテム → shard 0, 1 が 1 件、それ以外 0 件
        sizes = [
            len(ese._filter_for_shard(items, shard=s, num_shards=5))
            for s in range(5)
        ]
        assert sizes == [1, 1, 0, 0, 0]


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestCliArgs:
    """Validate that --shard / --num-shards / --no-update-jsonl are parsed."""

    def _patch_main_dependencies(self, monkeypatch):
        """ONNX session 作成と extract_per_utterance を mock化"""
        fake_session = mock.MagicMock()
        fake_session.get_inputs.return_value = [mock.MagicMock(name="input")]
        monkeypatch.setattr(
            ese.onnxruntime,
            "InferenceSession",
            mock.MagicMock(return_value=fake_session),
        )
        monkeypatch.setattr(
            ese.onnxruntime,
            "get_available_providers",
            lambda: ["CPUExecutionProvider"],
        )

    def test_shard_args_pass_through_to_extract(self, monkeypatch, tmp_path):
        """--shard / --num-shards / --no-update-jsonl が
        extract_per_utterance に正しく渡るか確認"""
        # 仮の dataset directory + dataset.jsonl 作成
        ds = tmp_path / "ds"
        ds.mkdir()
        (ds / "dataset.jsonl").write_text("", encoding="utf-8")

        self._patch_main_dependencies(monkeypatch)

        captured: dict = {}

        def fake_extract(*args, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(ese, "extract_per_utterance", fake_extract)

        argv = [
            "piper_train.extract_speaker_embedding",
            "--encoder",
            "/dev/null",
            "--dataset-dir",
            str(ds),
            "--per-utterance",
            "--shard",
            "2",
            "--num-shards",
            "4",
            "--no-update-jsonl",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        ese.main()

        assert captured["shard"] == 2
        assert captured["num_shards"] == 4
        assert captured["update_jsonl"] is False

    def test_default_shard_args(self, monkeypatch, tmp_path):
        """デフォルトでは shard=0, num_shards=1, update_jsonl=True"""
        ds = tmp_path / "ds"
        ds.mkdir()
        (ds / "dataset.jsonl").write_text("", encoding="utf-8")

        self._patch_main_dependencies(monkeypatch)

        captured: dict = {}

        def fake_extract(*args, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(ese, "extract_per_utterance", fake_extract)

        argv = [
            "piper_train.extract_speaker_embedding",
            "--encoder",
            "/dev/null",
            "--dataset-dir",
            str(ds),
            "--per-utterance",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        ese.main()

        assert captured["shard"] == 0
        assert captured["num_shards"] == 1
        assert captured["update_jsonl"] is True


# ---------------------------------------------------------------------------
# extract_per_utterance: short-circuit branches
# ---------------------------------------------------------------------------


class TestExtractPerUtteranceShortCircuit:
    """音声 I/O やバッチ推論を実行せず、短絡経路だけ確認する"""

    def _build_dataset(self, tmp_path: Path, n: int = 8) -> Path:
        ds = tmp_path / "ds"
        ds.mkdir()
        # 各 entry には audio_norm_path が必要 (実体は不要、existing skip させるため)
        with open(ds / "dataset.jsonl", "w", encoding="utf-8") as f:
            for i in range(n):
                json.dump(
                    {
                        "audio_norm_path": f"cache/22050/utt{i}.pt",
                        "speaker_id": i % 3,
                        "language_id": 0,
                    },
                    f,
                )
                f.write("\n")
        return ds

    def test_all_existing_skips_extraction_and_writes_jsonl(self, tmp_path):
        """全ての embedding が既に存在するときは extraction スキップ + jsonl 更新"""
        ds = self._build_dataset(tmp_path, n=4)
        emb_dir = ds / "speaker_embeddings"
        emb_dir.mkdir()
        # 全発話分の .npy を事前に作成 (内容は空ファイルで OK、glob で stem だけ拾う)
        for i in range(4):
            (emb_dir / f"utt{i}.npy").touch()

        # session は呼び出されない経路
        fake_session = mock.MagicMock()

        ese.extract_per_utterance(
            session=fake_session,
            dataset_dir=ds,
            update_jsonl=True,
        )

        # session.run が呼ばれていない (extraction なし)
        fake_session.run.assert_not_called()

        # dataset.jsonl が更新されている (speaker_embedding_path が追加)
        with open(ds / "dataset.jsonl", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f]
        assert len(entries) == 4
        for i, e in enumerate(entries):
            assert e["speaker_embedding_path"] == f"speaker_embeddings/utt{i}.npy"

        # bak が作成されている
        assert (ds / "dataset.jsonl.bak").exists()

    def test_no_update_jsonl_skips_jsonl_write(self, tmp_path):
        """--no-update-jsonl 相当 (update_jsonl=False) では jsonl が変更されない"""
        ds = self._build_dataset(tmp_path, n=4)
        emb_dir = ds / "speaker_embeddings"
        emb_dir.mkdir()
        for i in range(4):
            (emb_dir / f"utt{i}.npy").touch()

        original_jsonl = (ds / "dataset.jsonl").read_text(encoding="utf-8")

        fake_session = mock.MagicMock()
        ese.extract_per_utterance(
            session=fake_session,
            dataset_dir=ds,
            update_jsonl=False,
        )

        # jsonl が変更されていない
        assert (ds / "dataset.jsonl").read_text(encoding="utf-8") == original_jsonl
        # bak も作られない
        assert not (ds / "dataset.jsonl.bak").exists()

    def test_shard_filter_on_empty_after_skip(self, tmp_path):
        """shard で全件除外されたら extraction なし、update_jsonl=False で jsonl 不変"""
        ds = self._build_dataset(tmp_path, n=4)
        # 何も existing なし
        fake_session = mock.MagicMock()

        # shard=0/num_shards=8 で n=4 entries を絞ると、
        # i=0 の 1件だけが対象になる (4 件中 i%8==0 は i=0 のみ)
        # ただし pt ファイル不在で fail するので extraction なし、jsonl もそのまま
        # ここでは session.run が呼ばれないことだけ確認したい
        ese.extract_per_utterance(
            session=fake_session,
            dataset_dir=ds,
            shard=5,
            num_shards=8,
            update_jsonl=False,
        )
        fake_session.run.assert_not_called()
        # jsonl 不変
        assert not (ds / "dataset.jsonl.bak").exists()

    def test_missing_jsonl_raises(self, tmp_path):
        """dataset.jsonl 不在時は FileNotFoundError"""
        ds = tmp_path / "empty"
        ds.mkdir()
        fake_session = mock.MagicMock()
        with pytest.raises(FileNotFoundError, match="dataset.jsonl"):
            ese.extract_per_utterance(session=fake_session, dataset_dir=ds)

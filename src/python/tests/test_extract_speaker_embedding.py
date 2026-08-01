"""Tests for piper_train.extract_speaker_embedding (per-utterance extraction)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest


# extract_speaker_embedding requires torch + torchaudio + soundfile at import time.
# Skip the whole module (collection-time) on minimal CI envs that don't install them.
pytest.importorskip("torchaudio")
pytest.importorskip("soundfile")

# conftest.py adds src/python to sys.path so this import works
from piper_train import extract_speaker_embedding as ese  # noqa: E402


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
            len(ese._filter_for_shard(items, shard=s, num_shards=5)) for s in range(5)
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

    def test_default_fast_path_args(self, monkeypatch, tmp_path):
        """v2 default: --fixed-frames 400, --chunk-batch 128, batch-infer OFF"""
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

        # v2 fast-path defaults
        assert captured["fixed_frames"] == 400, (
            "default should enable A'' chunked mode (fixed_frames=400)"
        )
        assert captured["chunk_batch"] == 128, (
            "default chunk_batch=128 (A100/A6000 safe)"
        )
        assert captured["use_batch_infer"] is False, (
            "legacy padded batch inference must remain opt-in"
        )
        # None = auto (extract_per_utterance decides based on fixed_frames)
        assert captured["use_length_sort"] is None

    def test_disable_fixed_frames_flag(self, monkeypatch, tmp_path):
        """--disable-fixed-frames は fixed_frames=0 (legacy per-utt) にする"""
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
            "--disable-fixed-frames",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        ese.main()

        assert captured["fixed_frames"] == 0

    def test_explicit_fixed_frames_and_chunk_batch(self, monkeypatch, tmp_path):
        """--fixed-frames / --chunk-batch を明示指定できる"""
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
            "--fixed-frames",
            "300",
            "--chunk-batch",
            "64",
            "--length-sort",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        ese.main()

        assert captured["fixed_frames"] == 300
        assert captured["chunk_batch"] == 64
        assert captured["use_length_sort"] is True

    def test_batch_infer_padded_flag(self, monkeypatch, tmp_path):
        """--batch-infer-padded は use_batch_infer=True"""
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
            "--batch-infer-padded",
            "--disable-fixed-frames",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        ese.main()

        assert captured["use_batch_infer"] is True
        assert captured["fixed_frames"] == 0


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
        with pytest.raises(FileNotFoundError, match=r"dataset\.jsonl"):
            ese.extract_per_utterance(session=fake_session, dataset_dir=ds)


# ---------------------------------------------------------------------------
# extract_per_utterance: default fast-path (fixed_frames=400) smoke test
# ---------------------------------------------------------------------------


class TestDefaultFastPath:
    """default (fixed_frames=400, chunk_batch=128) の chunked 経路を end-to-end で検証"""

    def _make_dataset_with_pt(self, tmp_path: Path, n_utts: int = 3) -> Path:
        """dataset.jsonl + 実際に .pt audio tensor を持つ dataset を作る"""
        import torch as _torch  # local alias

        ds = tmp_path / "ds"
        ds.mkdir()
        cache = ds / "cache" / "22050"
        cache.mkdir(parents=True)

        # 各 utt に対して 22050 Hz の audio tensor (~2-5 秒) を .pt で保存
        source_sr = 22050
        durations = [2.0, 3.5, 5.0][:n_utts]
        entries = []
        for i, dur in enumerate(durations):
            n_samples = int(source_sr * dur)
            audio = _torch.randn(n_samples, dtype=_torch.float32) * 0.1
            pt_path = cache / f"utt{i}.pt"
            _torch.save(audio, pt_path)
            entries.append(
                {
                    "audio_norm_path": str(pt_path),
                    "speaker_id": i % 2,
                    "language_id": 0,
                }
            )

        with open(ds / "dataset.jsonl", "w", encoding="utf-8") as f:
            for e in entries:
                json.dump(e, f)
                f.write("\n")

        return ds

    def _make_fake_session(self, emb_dim: int = 192) -> mock.MagicMock:
        """[B, T, 80] 入力 → [B, emb_dim] 出力 を返す fake session"""
        import numpy as _np  # noqa: PLC0415

        session = mock.MagicMock()
        session.get_providers.return_value = ["CPUExecutionProvider"]
        input_mock = mock.MagicMock()
        input_mock.name = "input"
        session.get_inputs.return_value = [input_mock]
        output_mock = mock.MagicMock()
        output_mock.name = "output"
        session.get_outputs.return_value = [output_mock]

        def _run(_out_names, feed):
            arr = feed["input"]
            # arr shape: [B, T, 80] (chunked) or [1, T, 80] (per-utt)
            batch = arr.shape[0]
            # deterministic embedding: sum over T+mel, tile to emb_dim
            base = arr.reshape(batch, -1).sum(axis=1).astype(_np.float32)
            emb = _np.tile(base[:, None], (1, emb_dim))
            # add a bias so numerically all rows differ from zero (avoid div-by-0 in norm)
            emb = emb + _np.arange(emb_dim, dtype=_np.float32)[None, :] * 0.01
            return [emb]

        session.run.side_effect = _run
        return session

    def test_default_chunked_path_produces_normalized_embeddings(self, tmp_path):
        """default (fixed_frames=400 + chunk_batch=128) 経路で .npy が L2 正規化されて保存される"""
        import numpy as _np  # noqa: PLC0415

        ds = self._make_dataset_with_pt(tmp_path, n_utts=3)
        session = self._make_fake_session()

        ese.extract_per_utterance(
            session=session,
            dataset_dir=ds,
            source_sr=22050,
            batch_size=4,
            num_workers=0,  # in-process for test determinism
            # 全て default: fixed_frames=400, chunk_batch=128
        )

        emb_dir = ds / "speaker_embeddings"
        saved_files = sorted(emb_dir.glob("*.npy"))
        assert len(saved_files) == 3, f"expected 3 embeddings, got {len(saved_files)}"

        for npy_path in saved_files:
            emb = _np.load(npy_path)
            assert emb.shape == (192,), f"{npy_path}: shape {emb.shape} != (192,)"
            norm = _np.linalg.norm(emb)
            assert abs(norm - 1.0) < 1e-5, (
                f"{npy_path}: not L2-normalized (norm={norm})"
            )

        # dataset.jsonl が in-place で更新されている
        with open(ds / "dataset.jsonl", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f]
        for e in entries:
            assert "speaker_embedding_path" in e
            assert e["speaker_embedding_path"].startswith("speaker_embeddings/")

    def test_chunk_batch_argument_is_respected(self, tmp_path):
        """chunk_batch を小さく指定すると session.run が複数回呼ばれる"""
        ds = self._make_dataset_with_pt(tmp_path, n_utts=3)
        session = self._make_fake_session()

        ese.extract_per_utterance(
            session=session,
            dataset_dir=ds,
            source_sr=22050,
            batch_size=8,  # 全 3 発話が 1 DataLoader batch に収まる
            num_workers=0,
            chunk_batch=1,  # 極小: chunk ごとに 1 回 session.run が呼ばれる
        )

        # 各発話は 2 chunk (2-4s は先頭寄せ/末尾寄せの 2 variant)、~5s は 1 chunk (T>target で 1 chunk)
        # 3 発話 → 少なくとも 3 回、chunk_batch=1 なので chunk 数だけ session.run が呼ばれる
        assert session.run.call_count >= 3

    def test_env_var_overrides_cli_default(self, tmp_path, monkeypatch):
        """PIPER_PLUS_EMB_FIXED_FRAMES=0 が CLI default (400) を上書きし legacy per-utt に落ちる"""
        ds = self._make_dataset_with_pt(tmp_path, n_utts=2)
        session = self._make_fake_session()

        monkeypatch.setenv("PIPER_PLUS_EMB_FIXED_FRAMES", "0")

        ese.extract_per_utterance(
            session=session,
            dataset_dir=ds,
            source_sr=22050,
            batch_size=4,
            num_workers=0,
            fixed_frames=400,  # CLI では default だが env が上書き
        )

        # 落ちずに完了することを確認 (legacy per-utt 経路)
        emb_dir = ds / "speaker_embeddings"
        assert len(list(emb_dir.glob("*.npy"))) == 2

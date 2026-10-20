"""学習時の G 参照ペア (参照融合計画 §8 Task 7R) の TDD テスト。

固定する契約:

* ``build_reference_pairs`` は各 target に **同話者・同 split・別音声 hash** の
  参照を 1 つ割り当てる。候補がない target は自己参照に戻さず除外し、理由を
  数える。seed に対して決定論的で、入力順にも依存しない。
* ``validate_reference_pairs`` は参照 = target、別話者、別 split、同一音声 hash の
  どれでも ``ValueError``。``--strict-zero-shot`` は batch ごとに呼ぶ。
* dataset は ``generator_reference="cross_utt"`` のときだけ参照フィールドを読む。
  欠けた発話は **読み込み時に** ``ValueError`` (発話名つき)。``"self"`` (既定)
  では batch が変更前と bit 一致する。
* 参照 spec の切り出しは学習時 = (epoch, 発話) から決まるランダム窓 (global RNG を
  消費しない)、検証時 = 先頭固定。
* G (主 forward / SCL 用 re-forward / validation / audio logging / telemetry /
  JCU 条件) は参照を受け、SCL の正例・swap-SCL・Latent Filling・DINO は従来どおり
  target の ``speaker_embeddings`` を使う。
* CLI: ``--reference-conditioning`` が none 以外なら ``cross_utt`` 必須、
  Latent Filling / swap-SCL との併用は ``SystemExit``。
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import random
import sys

import numpy as np
import pytest


torch = pytest.importorskip(
    "torch",
    reason="Reference-pair training wiring needs the train extra (torch).",
)

import piper_train.vits.dataset as dataset_module  # noqa: E402
import piper_train.zero_shot_requirements as requirements  # noqa: E402
from piper_train.vits.dataset import (  # noqa: E402
    Batch,
    PiperDataset,
    UtteranceCollate,
)


def _tool():
    import piper_train.tools.build_reference_pairs as tool

    return tool


def build_reference_pairs(entries, seed):
    return _tool().build_reference_pairs(entries, seed)


def audio_sha256_of(path):
    return _tool().audio_sha256_of(path)


def pairs_main(argv):
    return _tool().main(argv)


def crop_reference_specs(*args, **kwargs):
    return dataset_module.crop_reference_specs(*args, **kwargs)


def validate_reference_pairs(*args, **kwargs):
    return requirements.validate_reference_pairs(*args, **kwargs)


def validate_reference_training_args(**kwargs):
    return requirements.validate_reference_training_args(**kwargs)


def validate_training_batch(batch, **kwargs):
    return requirements.validate_training_batch(batch, **kwargs)


pytestmark = pytest.mark.unit

SPEC_CHANNELS = 513


# ---------------------------------------------------------------------------
# build_reference_pairs (純関数)
# ---------------------------------------------------------------------------


def _entry(name, speaker, sha=None, split=None, emb=True):
    entry = {
        "phoneme_ids": [1, 2, 3],
        "audio_norm_path": f"cache/{name}.pt",
        "audio_spec_path": f"cache/{name}.spec.pt",
        "speaker_id": speaker,
        "audio_sha256": sha if sha is not None else f"hash-{name}",
    }
    if emb:
        entry["speaker_embedding_path"] = f"emb/{name}.npy"
    if split is not None:
        entry["split"] = split
    return entry


def _by_path(entries):
    return {e["audio_norm_path"]: e for e in entries}


class TestBuildReferencePairs:
    def test_pairs_never_self_reference(self):
        entries = [_entry(f"u{i}", speaker=i % 3) for i in range(30)]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert len(paired) == 30
        assert summary["num_output"] == 30
        for e in paired:
            assert e["reference_utterance_id"] != e["audio_norm_path"]
            assert e["reference_audio_sha256"] != e["audio_sha256"]

    def test_pairs_reject_same_hash_different_path(self):
        # a / b は別 path だが同一音声 (同 hash)。c は別音声。
        entries = [
            _entry("a", 1, sha="same"),
            _entry("b", 1, sha="same"),
            _entry("c", 1, sha="other"),
        ]
        paired, _ = build_reference_pairs(entries, seed=0)
        refs = {e["audio_norm_path"]: e["reference_utterance_id"] for e in paired}
        assert refs["cache/a.pt"] == "cache/c.pt"
        assert refs["cache/b.pt"] == "cache/c.pt"
        assert refs["cache/c.pt"] in {"cache/a.pt", "cache/b.pt"}

    def test_speaker_with_only_identical_audio_is_excluded_with_reason(self):
        entries = [_entry("a", 1, sha="same"), _entry("b", 1, sha="same")]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert paired == []
        assert summary["excluded_by_reason"] == {"only_identical_audio": 2}

    def test_pairs_keep_split(self):
        entries = [
            _entry("tr1", 1, split="train"),
            _entry("tr2", 1, split="train"),
            _entry("te1", 1, split="test"),
            _entry("te2", 1, split="test"),
        ]
        paired, summary = build_reference_pairs(entries, seed=3)
        by = _by_path(entries)
        for e in paired:
            assert by[e["reference_utterance_id"]]["split"] == e["split"]
        assert summary["split_field_present"] is True

    def test_lone_utterance_in_a_split_is_not_paired_across_splits(self):
        entries = [
            _entry("tr1", 1, split="train"),
            _entry("tr2", 1, split="train"),
            _entry("te1", 1, split="test"),
        ]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert {e["audio_norm_path"] for e in paired} == {
            "cache/tr1.pt",
            "cache/tr2.pt",
        }
        assert summary["excluded_by_reason"] == {"no_other_utterance": 1}

    def test_pairs_same_speaker(self):
        entries = [_entry(f"u{i}", speaker=i % 4) for i in range(40)]
        paired, _ = build_reference_pairs(entries, seed=1)
        by = _by_path(entries)
        for e in paired:
            assert by[e["reference_utterance_id"]]["speaker_id"] == e["speaker_id"]

    def test_pairs_deterministic_by_seed(self):
        entries = [_entry(f"u{i}", speaker=i % 2) for i in range(40)]
        first, s1 = build_reference_pairs(copy.deepcopy(entries), seed=7)
        second, s2 = build_reference_pairs(copy.deepcopy(entries), seed=7)
        assert first == second
        assert s1 == s2

    def test_different_seed_changes_the_assignment(self):
        entries = [_entry(f"u{i}", speaker=0) for i in range(40)]
        a, _ = build_reference_pairs(entries, seed=0)
        b, _ = build_reference_pairs(entries, seed=1)
        assert [e["reference_utterance_id"] for e in a] != [
            e["reference_utterance_id"] for e in b
        ]

    def test_assignment_does_not_depend_on_input_order(self):
        entries = [_entry(f"u{i}", speaker=i % 3) for i in range(30)]
        shuffled = list(entries)
        random.Random(5).shuffle(shuffled)
        a, _ = build_reference_pairs(entries, seed=11)
        b, _ = build_reference_pairs(shuffled, seed=11)
        refs_a = {e["audio_norm_path"]: e["reference_utterance_id"] for e in a}
        refs_b = {e["audio_norm_path"]: e["reference_utterance_id"] for e in b}
        assert refs_a == refs_b
        # 出力は入力順を保つ
        assert [e["audio_norm_path"] for e in b] == [
            e["audio_norm_path"] for e in shuffled
        ]

    def test_single_utterance_speaker_excluded_with_reason(self):
        entries = [_entry("a", 1), _entry("b", 1), _entry("lonely", 2)]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert "cache/lonely.pt" not in {e["audio_norm_path"] for e in paired}
        assert summary["excluded_by_reason"] == {"no_other_utterance": 1}
        assert summary["num_input"] == 3
        assert summary["num_output"] == 2
        assert summary["num_excluded"] == 1

    def test_dataset_without_split_field_is_one_split_and_recorded(self):
        entries = [_entry("a", 1), _entry("b", 1)]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert len(paired) == 2
        assert summary["split_field_present"] is False

    def test_entry_missing_split_when_others_have_one_is_excluded(self):
        entries = [
            _entry("a", 1, split="train"),
            _entry("b", 1, split="train"),
            _entry("c", 1),
        ]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert "cache/c.pt" not in {e["audio_norm_path"] for e in paired}
        assert summary["excluded_by_reason"] == {"missing_split": 1}

    def test_entry_without_speaker_id_is_excluded(self):
        entries = [_entry("a", 1), _entry("b", 1), _entry("x", None)]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert len(paired) == 2
        assert summary["excluded_by_reason"] == {"missing_speaker_id": 1}

    def test_entry_without_speaker_embedding_is_neither_target_nor_reference(self):
        entries = [_entry("a", 1), _entry("b", 1), _entry("noemb", 1, emb=False)]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert {e["audio_norm_path"] for e in paired} == {"cache/a.pt", "cache/b.pt"}
        assert all(e["reference_utterance_id"] != "cache/noemb.pt" for e in paired)
        assert summary["excluded_by_reason"] == {"missing_speaker_embedding_path": 1}

    def test_entry_without_audio_hash_is_excluded(self):
        entries = [_entry("a", 1), _entry("b", 1), _entry("c", 1)]
        del entries[2]["audio_sha256"]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert len(paired) == 2
        assert summary["excluded_by_reason"] == {"missing_audio_sha256": 1}

    def test_reference_fields_copy_the_reference_entry(self):
        entries = [_entry("a", 1), _entry("b", 1)]
        paired, _ = build_reference_pairs(entries, seed=0)
        a = _by_path(paired)["cache/a.pt"]
        assert a["reference_utterance_id"] == "cache/b.pt"
        assert a["reference_audio_spec_path"] == "cache/b.spec.pt"
        assert a["reference_speaker_embedding_path"] == "emb/b.npy"
        assert a["reference_audio_sha256"] == "hash-b"

    def test_input_entries_are_not_mutated(self):
        entries = [_entry("a", 1), _entry("b", 1)]
        before = copy.deepcopy(entries)
        build_reference_pairs(entries, seed=0)
        assert entries == before

    def test_empty_input(self):
        paired, summary = build_reference_pairs([], seed=0)
        assert paired == []
        assert summary["num_input"] == 0
        assert summary["num_output"] == 0
        assert summary["excluded_by_reason"] == {}

    @pytest.mark.parametrize("seed", [-1, 1.5, True, "1", None])
    def test_invalid_seed_raises(self, seed):
        with pytest.raises(ValueError, match="seed"):
            build_reference_pairs([_entry("a", 1), _entry("b", 1)], seed=seed)


# ---------------------------------------------------------------------------
# build_reference_pairs CLI (実ファイル)
# ---------------------------------------------------------------------------


def _write_audio(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(torch.as_tensor(samples, dtype=torch.float32).unsqueeze(0), path)


def _write_cli_dataset(tmp_path, specs):
    """specs: list of (name, speaker, samples)。audio_sha256 は CLI が計算する。"""
    rows = []
    for name, speaker, samples in specs:
        _write_audio(tmp_path / "cache" / f"{name}.pt", samples)
        row = _entry(name, speaker)
        row.pop("audio_sha256")
        rows.append(json.dumps(row))
    jsonl = tmp_path / "dataset.jsonl"
    jsonl.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return jsonl


class TestBuildReferencePairsCli:
    def test_audio_hash_is_the_sha256_of_float32_samples(self, tmp_path):
        samples = [0.0, 0.5, -0.25, 1.0]
        path = tmp_path / "a.pt"
        _write_audio(path, samples)
        expected = hashlib.sha256(
            np.asarray(samples, dtype="<f4").tobytes()
        ).hexdigest()
        assert audio_sha256_of(path) == expected

    def test_cli_writes_pairs_and_summary(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path,
            [
                ("a", 1, [0.1, 0.2]),
                ("b", 1, [0.3, 0.4]),
                ("c", 2, [0.5, 0.6]),
            ],
        )
        out = tmp_path / "pairs.jsonl"
        assert pairs_main([str(jsonl), str(out), "--seed", "4"]) == 0
        rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
        assert {r["audio_norm_path"] for r in rows} == {"cache/a.pt", "cache/b.pt"}
        summary = json.loads(
            (tmp_path / "pairs.jsonl.summary.json").read_text(encoding="utf-8")
        )
        assert summary["seed"] == 4
        assert summary["input_sha256"] == hashlib.sha256(jsonl.read_bytes()).hexdigest()
        assert summary["excluded_by_reason"] == {"no_other_utterance": 1}
        assert summary["audio_hash"].startswith("sha256")

    def test_cli_detects_identical_audio_at_different_paths(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path,
            [("a", 1, [0.1, 0.2]), ("b", 1, [0.1, 0.2])],
        )
        out = tmp_path / "pairs.jsonl"
        assert pairs_main([str(jsonl), str(out)]) == 0
        assert out.read_text(encoding="utf-8").strip() == ""
        summary = json.loads(
            (tmp_path / "pairs.jsonl.summary.json").read_text(encoding="utf-8")
        )
        assert summary["excluded_by_reason"] == {"only_identical_audio": 2}

    def test_cli_refuses_to_overwrite_existing_output(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        out = tmp_path / "pairs.jsonl"
        out.write_text("keep\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="exists"):
            pairs_main([str(jsonl), str(out)])
        assert out.read_text(encoding="utf-8") == "keep\n"
        assert pairs_main([str(jsonl), str(out), "--overwrite"]) == 0
        assert out.read_text(encoding="utf-8") != "keep\n"

    def test_cli_never_overwrites_its_input(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        before = jsonl.read_bytes()
        with pytest.raises(SystemExit, match="input"):
            pairs_main([str(jsonl), str(jsonl), "--overwrite"])
        assert jsonl.read_bytes() == before

    def test_cli_refuses_other_directory_with_relative_paths(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        other = tmp_path / "elsewhere"
        other.mkdir()
        with pytest.raises(SystemExit, match="directory"):
            pairs_main([str(jsonl), str(other / "pairs.jsonl")])

    def test_cli_missing_audio_fails_loudly(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        (tmp_path / "cache" / "b.pt").unlink()
        with pytest.raises(SystemExit, match=r"b.pt"):
            pairs_main([str(jsonl), str(tmp_path / "pairs.jsonl")])


# ---------------------------------------------------------------------------
# validate_reference_pairs
# ---------------------------------------------------------------------------


def _valid_pairs():
    return {
        "utterance_ids": ["t1", "t2"],
        "reference_utterance_ids": ["r1", "r2"],
        "speaker_ids": ([1, 2], [1, 2]),
        "splits": (["train", "train"], ["train", "train"]),
        "audio_sha256": (["h1", "h2"], ["hr1", "hr2"]),
    }


class TestValidateReferencePairs:
    def test_valid_pairs_pass(self):
        assert validate_reference_pairs(**_valid_pairs()) is None

    def test_reference_equal_to_target_raises(self):
        kwargs = _valid_pairs()
        kwargs["reference_utterance_ids"] = ["t1", "r2"]
        with pytest.raises(ValueError, match="itself"):
            validate_reference_pairs(**kwargs)

    def test_different_speaker_raises(self):
        kwargs = _valid_pairs()
        kwargs["speaker_ids"] = ([1, 2], [1, 3])
        with pytest.raises(ValueError, match="speaker"):
            validate_reference_pairs(**kwargs)

    def test_different_split_raises(self):
        kwargs = _valid_pairs()
        kwargs["splits"] = (["train", "train"], ["train", "test"])
        with pytest.raises(ValueError, match="split"):
            validate_reference_pairs(**kwargs)

    def test_same_audio_hash_raises(self):
        kwargs = _valid_pairs()
        kwargs["audio_sha256"] = (["h1", "h2"], ["hr1", "h2"])
        with pytest.raises(ValueError, match="audio"):
            validate_reference_pairs(**kwargs)

    def test_none_split_on_both_sides_is_one_split(self):
        kwargs = _valid_pairs()
        kwargs["splits"] = ([None, None], [None, None])
        assert validate_reference_pairs(**kwargs) is None

    @pytest.mark.parametrize(
        "field,value",
        [
            ("reference_utterance_ids", ["r1", None]),
            ("speaker_ids", ([1, 2], [1, None])),
            ("audio_sha256", (["h1", "h2"], ["hr1", None])),
            ("audio_sha256", (["h1", None], ["hr1", "hr2"])),
            ("reference_utterance_ids", None),
        ],
    )
    def test_missing_values_raise(self, field, value):
        kwargs = _valid_pairs()
        kwargs[field] = value
        with pytest.raises(ValueError):
            validate_reference_pairs(**kwargs)

    def test_length_mismatch_raises(self):
        kwargs = _valid_pairs()
        kwargs["reference_utterance_ids"] = ["r1"]
        with pytest.raises(ValueError, match="length"):
            validate_reference_pairs(**kwargs)

    def test_empty_batch_raises(self):
        with pytest.raises(ValueError):
            validate_reference_pairs([], [], ([], []), ([], []), ([], []))


# ---------------------------------------------------------------------------
# dataset / collate
# ---------------------------------------------------------------------------


def _write_dataset_files(tmp_path, name, frames, seed):
    g = torch.Generator().manual_seed(seed)
    cache = tmp_path / "cache"
    cache.mkdir(exist_ok=True)
    torch.save(torch.randn(1, frames * 256, generator=g) * 0.1, cache / f"{name}.pt")
    torch.save(
        torch.randn(SPEC_CHANNELS, frames, generator=g).abs(),
        cache / f"{name}.spec.pt",
    )
    emb = torch.randn(192, generator=g).numpy().astype(np.float32)
    (tmp_path / "emb").mkdir(exist_ok=True)
    np.save(tmp_path / "emb" / f"{name}.npy", emb)


# (name, speaker, frames, reference name)
_ROWS = [
    ("a", 0, 20, "b"),
    ("b", 0, 30, "a"),
    ("c", 1, 25, "d"),
    ("d", 1, 40, "c"),
]


def _write_dataset(tmp_path, rows=_ROWS, with_reference=True, drop=None):
    lines = []
    tmp_path.mkdir(parents=True, exist_ok=True)
    for i, (name, speaker, frames, ref) in enumerate(rows):
        _write_dataset_files(tmp_path, name, frames, seed=i)
        row = {
            "phoneme_ids": [1, 2, 3, 4][: 2 + i % 3],
            "audio_norm_path": f"cache/{name}.pt",
            "audio_spec_path": f"cache/{name}.spec.pt",
            "speaker_id": speaker,
            "speaker_embedding_path": f"emb/{name}.npy",
            "audio_sha256": f"hash-{name}",
        }
        if with_reference:
            row.update(
                {
                    "reference_utterance_id": f"cache/{ref}.pt",
                    "reference_audio_spec_path": f"cache/{ref}.spec.pt",
                    "reference_speaker_embedding_path": f"emb/{ref}.npy",
                    "reference_audio_sha256": f"hash-{ref}",
                }
            )
        if drop is not None and name == drop[0]:
            row.pop(drop[1])
        lines.append(json.dumps(row))
    path = tmp_path / "dataset.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _collate(items):
    return UtteranceCollate(is_multispeaker=True, segment_size=256)(items)


_REFERENCE_BATCH_FIELDS = (
    "reference_embeddings",
    "reference_specs",
    "reference_spec_lengths",
    "reference_utterance_ids",
    "reference_speaker_ids",
    "splits",
    "reference_splits",
    "audio_sha256s",
    "reference_audio_sha256s",
)


def _assert_batches_equal(a: Batch, b: Batch):
    for field in dataclasses.fields(Batch):
        x, y = getattr(a, field.name), getattr(b, field.name)
        if isinstance(x, torch.Tensor):
            assert isinstance(y, torch.Tensor), field.name
            assert x.dtype == y.dtype, field.name
            assert torch.equal(x, y), field.name
        else:
            assert x == y, field.name


class TestDatasetReferenceFields:
    def test_missing_reference_fields_raise(self, tmp_path):
        for field in (
            "reference_utterance_id",
            "reference_audio_spec_path",
            "reference_speaker_embedding_path",
        ):
            path = _write_dataset(tmp_path, drop=("c", field))
            with pytest.raises(ValueError, match=r"c\.pt") as info:
                PiperDataset([path], load_references=True)
            assert field in str(info.value)

    def test_reference_missing_from_dataset_raises_at_load(self, tmp_path):
        rows = [("a", 0, 20, "b"), ("b", 0, 30, "ghost")]
        path = _write_dataset(tmp_path, rows=rows)
        with pytest.raises(ValueError, match="ghost"):
            PiperDataset([path], load_references=True)

    def test_reference_hash_disagreeing_with_dataset_raises(self, tmp_path):
        path = _write_dataset(tmp_path)
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["reference_audio_sha256"] = "not-the-hash-of-b"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", "utf-8")
        with pytest.raises(ValueError, match="sha256"):
            PiperDataset([path], load_references=True)

    def test_items_carry_the_reference_files(self, tmp_path):
        path = _write_dataset(tmp_path)
        ds = PiperDataset([path], load_references=True)
        item = ds[0]  # a -> b
        b_spec = torch.load(tmp_path / "cache" / "b.spec.pt")
        b_emb = np.load(tmp_path / "emb" / "b.npy")
        assert torch.equal(item.reference_spec, b_spec)
        expected = torch.from_numpy(b_emb / np.linalg.norm(b_emb.astype(np.float64)))
        assert torch.allclose(item.reference_embedding, expected.float(), atol=1e-7)
        assert item.reference_utterance_id == str(
            (tmp_path / "cache" / "b.pt").resolve()
        )
        assert item.reference_utterance_id != item.utterance_id
        assert item.reference_speaker_id == 0
        assert item.audio_sha256 == "hash-a"
        assert item.reference_audio_sha256 == "hash-b"

    def test_reference_identity_uses_the_utterance_id_convention(self, tmp_path):
        path = _write_dataset(tmp_path)
        ds = PiperDataset([path], load_references=True)
        ids = {ds[i].utterance_id for i in range(len(ds))}
        refs = {ds[i].reference_utterance_id for i in range(len(ds))}
        assert refs == ids

    def test_reference_survives_when_the_reference_is_length_filtered(self, tmp_path):
        # d (40 frame) は max_spec_length で target から外れるが、c の参照としては有効
        path = _write_dataset(tmp_path)
        ds = PiperDataset([path], load_references=True, max_spec_length=35)
        names = [u.audio_norm_path.name for u in ds.utterances]
        assert "d.pt" not in names
        c = ds[names.index("c.pt")]
        assert c.reference_spec.shape == (SPEC_CHANNELS, 40)

    def test_float16_reference_spec_is_upcast(self, tmp_path):
        path = _write_dataset(tmp_path)
        spec = torch.load(tmp_path / "cache" / "b.spec.pt")
        torch.save(spec.half(), tmp_path / "cache" / "b.spec.pt")
        item = PiperDataset([path], load_references=True)[0]
        assert item.reference_spec.dtype == torch.float32

    @pytest.mark.parametrize(
        "bad,match",
        [
            (torch.full((SPEC_CHANNELS, 5), float("nan")), "finite"),
            (torch.full((SPEC_CHANNELS, 5), float("inf")), "finite"),
            (torch.ones(SPEC_CHANNELS - 1, 5), "channels"),
            (torch.ones(SPEC_CHANNELS, 0), "frame"),
            (torch.ones(1, SPEC_CHANNELS, 5), "2-D"),
        ],
    )
    def test_invalid_reference_spec_raises(self, tmp_path, bad, match):
        path = _write_dataset(tmp_path)
        torch.save(bad, tmp_path / "cache" / "b.spec.pt")
        ds = PiperDataset([path], load_references=True)
        with pytest.raises(ValueError, match=match):
            ds[0]

    def test_invalid_reference_embedding_raises(self, tmp_path):
        path = _write_dataset(tmp_path)
        np.save(tmp_path / "emb" / "b.npy", np.zeros(192, dtype=np.float32))
        ds = PiperDataset([path], load_references=True)
        with pytest.raises(ValueError, match="reference_speaker_embedding"):
            ds[0]

    def test_self_mode_batch_unchanged(self, tmp_path):
        with_ref = _write_dataset(tmp_path / "w", with_reference=True)
        without = _write_dataset(tmp_path / "wo", with_reference=False)
        # 同じ乱数で作った同一ファイル群 (dir だけ違う) を比べる
        a = PiperDataset([with_ref])
        b = PiperDataset([without])
        batch_a = _collate([a[i] for i in range(len(a))])
        batch_b = _collate([b[i] for i in range(len(b))])
        for name in _REFERENCE_BATCH_FIELDS:
            assert getattr(batch_a, name) is None, name
        for batch, sub in ((batch_a, "w"), (batch_b, "wo")):
            prefix = str((tmp_path / sub).resolve())
            batch.utterance_ids = [u.replace(prefix, "") for u in batch.utterance_ids]
        _assert_batches_equal(batch_a, batch_b)

    def test_self_mode_items_match_the_legacy_fields(self, tmp_path):
        path = _write_dataset(tmp_path, with_reference=True)
        item = PiperDataset([path])[1]
        assert item.reference_spec is None
        assert item.reference_embedding is None
        assert torch.equal(
            item.spectrogram, torch.load(tmp_path / "cache" / "b.spec.pt")
        )


class TestCollateReferences:
    def test_collate_pads_reference_specs_with_zeros_and_returns_lengths(
        self, tmp_path
    ):
        ds = PiperDataset([_write_dataset(tmp_path)], load_references=True)
        items = [ds[i] for i in range(len(ds))]
        batch = _collate(items)
        assert batch.reference_specs.shape == (4, SPEC_CHANNELS, 40)
        assert batch.reference_spec_lengths.dtype == torch.int64
        by_target = {item.utterance_id: item for item in items}
        for row, uid in enumerate(batch.utterance_ids):
            item = by_target[uid]
            n = item.reference_spec.shape[1]
            assert int(batch.reference_spec_lengths[row]) == n
            assert torch.equal(batch.reference_specs[row, :, :n], item.reference_spec)
            assert bool((batch.reference_specs[row, :, n:] == 0).all())
            assert torch.equal(
                batch.reference_embeddings[row], item.reference_embedding
            )
            assert batch.reference_utterance_ids[row] == item.reference_utterance_id
            assert batch.reference_speaker_ids[row] == item.reference_speaker_id
            assert batch.audio_sha256s[row] == item.audio_sha256
            assert batch.reference_audio_sha256s[row] == item.reference_audio_sha256

    def test_single_item_batch_has_no_padding(self, tmp_path):
        ds = PiperDataset([_write_dataset(tmp_path)], load_references=True)
        batch = _collate([ds[0]])
        assert batch.reference_specs.shape == (1, SPEC_CHANNELS, 30)
        assert batch.reference_spec_lengths.tolist() == [30]

    def test_mixed_reference_presence_raises(self, tmp_path):
        ds = PiperDataset([_write_dataset(tmp_path)], load_references=True)
        items = [ds[0], ds[1]]
        items[1] = dataclasses.replace(items[1], reference_spec=None)
        with pytest.raises(ValueError, match="reference"):
            _collate(items)

    def test_pin_memory_keeps_reference_fields(self, tmp_path):
        ds = PiperDataset([_write_dataset(tmp_path)], load_references=True)
        batch = _collate([ds[0], ds[1]])
        if not torch.cuda.is_available():
            pytest.skip("pin_memory needs a CUDA host")
        pinned = batch.pin_memory()
        assert pinned.reference_specs.is_pinned()
        assert pinned.reference_spec_lengths.is_pinned()
        assert pinned.reference_embeddings.is_pinned()
        assert pinned.reference_utterance_ids == batch.reference_utterance_ids
        assert pinned.audio_sha256s == batch.audio_sha256s


# ---------------------------------------------------------------------------
# 参照 spec の切り出し
# ---------------------------------------------------------------------------


def _ramp_specs(lengths):
    t_max = max(lengths)
    specs = torch.zeros(len(lengths), 3, t_max)
    for row, n in enumerate(lengths):
        # 値 = frame index + 1 (padding の 0 と区別できる)
        specs[row, :, :n] = torch.arange(1, n + 1, dtype=torch.float32)
    return specs, torch.tensor(lengths, dtype=torch.long)


class TestReferenceCrop:
    def test_reference_crop_bounds(self):
        lengths = [3, 8, 8, 20]
        specs, lens = _ramp_specs(lengths)
        keys = [f"u{i}" for i in range(4)]
        for epoch in range(20):
            out, out_lens = crop_reference_specs(
                specs, lens, 8, mode="random", epoch=epoch, keys=keys
            )
            assert out_lens.tolist() == [3, 8, 8, 8]
            assert out.shape == (4, 3, 8)
            for row, n in enumerate(out_lens.tolist()):
                window = out[row, 0, :n]
                start = int(window[0]) - 1
                # 連続した窓で、元の有効範囲内に収まる
                assert torch.equal(
                    window, torch.arange(start + 1, start + n + 1).float()
                )
                assert start >= 0
                assert start + n <= lengths[row]
                assert bool((out[row, :, n:] == 0).all())

    def test_shorter_than_max_is_kept_whole(self):
        specs, lens = _ramp_specs([5, 2])
        out, out_lens = crop_reference_specs(
            specs, lens, 512, mode="random", epoch=0, keys=["a", "b"]
        )
        assert out_lens.tolist() == [5, 2]
        assert torch.equal(out, specs)

    def test_max_frames_one(self):
        specs, lens = _ramp_specs([7, 1])
        out, out_lens = crop_reference_specs(
            specs, lens, 1, mode="random", epoch=3, keys=["a", "b"]
        )
        assert out.shape == (2, 3, 1)
        assert out_lens.tolist() == [1, 1]
        assert 1 <= float(out[0, 0, 0]) <= 7
        assert float(out[1, 0, 0]) == 1

    def test_validation_crop_deterministic(self):
        specs, lens = _ramp_specs([20, 9, 4])
        first, first_lens = crop_reference_specs(specs, lens, 8, mode="head")
        assert first_lens.tolist() == [8, 8, 4]
        for row, n in enumerate(first_lens.tolist()):
            assert torch.equal(first[row, :, :n], specs[row, :, :n])
        again, _ = crop_reference_specs(specs, lens, 8, mode="head", epoch=9)
        assert torch.equal(first, again)

    def test_random_crop_reproducible_per_epoch_and_utterance(self):
        specs, lens = _ramp_specs([200, 200])
        a, _ = crop_reference_specs(
            specs, lens, 10, mode="random", epoch=4, keys=["x", "y"]
        )
        b, _ = crop_reference_specs(
            specs, lens, 10, mode="random", epoch=4, keys=["x", "y"]
        )
        assert torch.equal(a, b)
        # 同じ発話は batch 内の位置や相手に依存しない
        c, _ = crop_reference_specs(
            specs[[1, 0]], lens[[1, 0]], 10, mode="random", epoch=4, keys=["y", "x"]
        )
        assert torch.equal(a, c[[1, 0]])

    def test_random_crop_changes_across_epochs(self):
        specs, lens = _ramp_specs([400])
        starts = {
            float(
                crop_reference_specs(
                    specs, lens, 10, mode="random", epoch=e, keys=["x"]
                )[0][0, 0, 0]
            )
            for e in range(10)
        }
        # 391 通りの窓から 10 epoch 引いて全部同じ確率は無視できる (1/391^9)
        assert len(starts) > 1

    def test_random_crop_does_not_touch_global_rngs(self):
        specs, lens = _ramp_specs([400, 50])
        torch_state = torch.get_rng_state()
        py_state = random.getstate()
        np_state = np.random.get_state()
        crop_reference_specs(specs, lens, 10, mode="random", epoch=1, keys=["a", "b"])
        assert torch.equal(torch.get_rng_state(), torch_state)
        assert random.getstate() == py_state
        np_after = np.random.get_state()
        assert np_after[0] == np_state[0] and np.array_equal(np_after[1], np_state[1])

    def test_inputs_are_not_mutated(self):
        specs, lens = _ramp_specs([30, 9])
        before = specs.clone()
        crop_reference_specs(specs, lens, 8, mode="random", epoch=0, keys=["a", "b"])
        assert torch.equal(specs, before)

    @pytest.mark.parametrize("max_frames", [0, -1, True, 2.5, None])
    def test_invalid_max_frames_raise(self, max_frames):
        specs, lens = _ramp_specs([5])
        with pytest.raises(ValueError, match="max_frames"):
            crop_reference_specs(specs, lens, max_frames, mode="head")

    def test_random_mode_requires_keys_for_every_row(self):
        specs, lens = _ramp_specs([5, 6])
        with pytest.raises(ValueError, match="keys"):
            crop_reference_specs(specs, lens, 4, mode="random", epoch=0, keys=["a"])
        with pytest.raises(ValueError, match="keys"):
            crop_reference_specs(specs, lens, 4, mode="random", epoch=0, keys=None)

    def test_unknown_mode_raises(self):
        specs, lens = _ramp_specs([5])
        with pytest.raises(ValueError, match="mode"):
            crop_reference_specs(specs, lens, 4, mode="center")

    @pytest.mark.parametrize("bad_len", [0, 6])
    def test_lengths_out_of_range_raise(self, bad_len):
        specs, _ = _ramp_specs([5])
        with pytest.raises(ValueError, match="length"):
            crop_reference_specs(specs, torch.tensor([bad_len]), 4, mode="head")


# ---------------------------------------------------------------------------
# lightning 配線 (tiny model を実際に動かす)
# ---------------------------------------------------------------------------

N_FRAMES = 48
N_PHONEMES = 10
BATCH = 4

_HPARAMS = {
    "num_symbols": 40,
    "num_speakers": 4,
    "num_languages": 1,
    "dataset": None,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 64,
    "upsample_kernel_sizes": (16, 16),
    "hidden_channels": 64,
    "inter_channels": 64,
    "filter_channels": 128,
    "n_layers": 2,
    "segment_size": 8192,
    "prosody_dim": 0,
    "gin_channels": 64,
    "use_wavlm_discriminator": False,
    "c_dino": 0.0,
    "c_spk": 0.0,
    "batch_size": BATCH,
}


class _TinySpeakerEncoder(torch.nn.Module):
    """微分可能 CAM++ の代役 (被テスト対象ではない、決定論的な実 module)。"""

    def forward(self, wav):
        pooled = torch.nn.functional.adaptive_avg_pool1d(wav.unsqueeze(1), 192)
        return torch.nn.functional.normalize(pooled.squeeze(1) + 1e-3, dim=-1)


def _model(**overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    kwargs = dict(_HPARAMS)
    kwargs.update(overrides)
    model = VitsModel(**kwargs)
    model._log_with_batch_info = lambda *a, **k: None
    model._grad_probe_due = lambda: False
    model.train()
    return model


def _unit(x):
    return torch.nn.functional.normalize(x, dim=-1)


def _batch(with_reference=True, ref_frames=(30, 12, 30, 20)):
    g = torch.Generator().manual_seed(3)
    target = _unit(torch.randn(BATCH, 192, generator=g))
    batch = Batch(
        phoneme_ids=torch.randint(1, 40, (BATCH, N_PHONEMES), generator=g),
        phoneme_lengths=torch.full((BATCH,), N_PHONEMES, dtype=torch.long),
        spectrograms=torch.randn(BATCH, SPEC_CHANNELS, N_FRAMES, generator=g).abs(),
        spectrogram_lengths=torch.full((BATCH,), N_FRAMES, dtype=torch.long),
        audios=torch.randn(BATCH, 1, N_FRAMES * 256, generator=g) * 0.1,
        audio_lengths=torch.full((BATCH,), N_FRAMES * 256, dtype=torch.long),
        speaker_ids=torch.tensor([0, 0, 1, 1]),
        speaker_embeddings=target,
        utterance_ids=["t0", "t1", "t2", "t3"],
    )
    if with_reference:
        t_ref = max(ref_frames)
        specs = torch.zeros(BATCH, SPEC_CHANNELS, t_ref)
        for row, n in enumerate(ref_frames):
            specs[row, :, :n] = torch.randn(SPEC_CHANNELS, n, generator=g).abs()
        batch.reference_embeddings = _unit(torch.randn(BATCH, 192, generator=g))
        batch.reference_specs = specs
        batch.reference_spec_lengths = torch.tensor(ref_frames, dtype=torch.long)
        batch.reference_utterance_ids = ["r0", "r1", "r2", "r3"]
        batch.reference_speaker_ids = [0, 0, 1, 1]
        batch.splits = [None] * BATCH
        batch.reference_splits = [None] * BATCH
        batch.audio_sha256s = ["h0", "h1", "h2", "h3"]
        batch.reference_audio_sha256s = ["hr0", "hr1", "hr2", "hr3"]
    return batch


def _capture_forward(model):
    calls = []

    def hook(_module, args, kwargs):
        calls.append({"args": args, "kwargs": dict(kwargs)})

    model.model_g.register_forward_pre_hook(hook, with_kwargs=True)
    return calls


def _spy_method(obj, name, calls):
    original = getattr(obj, name)

    def wrapper(*args, **kwargs):
        calls.append(dict(kwargs))
        return original(*args, **kwargs)

    setattr(obj, name, wrapper)


def _scl_model(**overrides):
    kwargs = {
        "c_spk": 1.0,
        "spk_loss_type": "infonce",
        "spk_loss_positives": "cross_utt",
    }
    kwargs.update(overrides)
    model = _model(**kwargs)
    model.scl_encoder = _TinySpeakerEncoder()
    return model


class TestLightningWiring:
    def test_generator_uses_reference_while_scl_uses_target(self, monkeypatch):
        from piper_train.vits import lightning

        model = _scl_model(generator_reference="cross_utt")
        forward_calls = _capture_forward(model)
        scl_calls = []
        original = lightning.speaker_infonce_loss

        def spy(gen, ref, **kwargs):
            scl_calls.append(ref.detach().clone())
            return original(gen, ref, **kwargs)

        monkeypatch.setattr(lightning, "speaker_infonce_loss", spy)
        batch = _batch()
        loss = model.training_step_g(batch)
        assert torch.isfinite(loss)
        assert len(forward_calls) == 1
        received = forward_calls[0]["kwargs"]["speaker_embeddings"]
        # σ=0 の noise + 再正規化は単位ベクトルを float32 丸め以内で保つ
        assert torch.allclose(received, batch.reference_embeddings, atol=1e-6)
        assert not torch.allclose(received, batch.speaker_embeddings, atol=1e-2)
        assert forward_calls[0]["kwargs"]["reference_spec"] is None
        assert len(scl_calls) == 1
        assert torch.allclose(scl_calls[0], batch.speaker_embeddings, atol=1e-6)

    def test_self_mode_generator_uses_target(self):
        model = _model()
        forward_calls = _capture_forward(model)
        batch = _batch(with_reference=False)
        model.training_step_g(batch)
        received = forward_calls[0]["kwargs"]["speaker_embeddings"]
        assert torch.allclose(received, batch.speaker_embeddings, atol=1e-6)

    def test_self_mode_ignores_reference_fields_bit_for_bit(self):
        model = _model()
        torch.manual_seed(5)
        plain = model.training_step_g(_batch(with_reference=False))
        torch.manual_seed(5)
        with_ref = model.training_step_g(_batch(with_reference=True))
        assert torch.equal(plain, with_ref)

    def test_cross_utt_does_not_change_other_random_draws(self):
        self_model = _model()
        cross_model = _model(generator_reference="cross_utt")
        cross_model.load_state_dict(self_model.state_dict())
        outputs = {}
        for name, model, batch in (
            ("self", self_model, _batch(with_reference=False)),
            ("cross", cross_model, _batch(with_reference=True)),
        ):
            slices = []
            model.model_g.register_forward_hook(
                lambda _m, _a, out, s=slices: s.append(out.ids_slice.clone())
            )
            torch.manual_seed(9)
            model.training_step_g(batch)
            outputs[name] = (slices[0], torch.get_rng_state())
        assert torch.equal(outputs["self"][0], outputs["cross"][0])
        assert torch.equal(outputs["self"][1], outputs["cross"][1])

    def test_cross_utt_reference_noise_uses_a_private_generator(self):
        a = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.05)
        b = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.05)
        received = []
        for model in (a, b):
            calls = _capture_forward(model)
            torch.manual_seed(1)
            model.training_step_g(_batch())
            received.append(calls[0]["kwargs"]["speaker_embeddings"])
        # 同じ batch index → 同じ noise (再現性)、かつ σ>0 で参照から離れる
        assert torch.equal(received[0], received[1])
        assert not torch.allclose(received[0], _batch().reference_embeddings, atol=1e-4)
        assert torch.allclose(received[0].norm(dim=-1), torch.ones(BATCH), atol=1e-6)

    def test_ref_spec_generator_receives_reference_specs(self):
        model = _model(
            reference_conditioning="ref_spec", generator_reference="cross_utt"
        )
        calls = _capture_forward(model)
        batch = _batch()
        model.training_step_g(batch)
        kwargs = calls[0]["kwargs"]
        assert kwargs["reference_spec"] is batch.reference_specs
        assert kwargs["reference_spec_lengths"] is batch.reference_spec_lengths

    def test_cross_utt_without_reference_in_batch_raises(self):
        model = _model(generator_reference="cross_utt")
        with pytest.raises(ValueError, match="reference_embeddings"):
            model.training_step_g(_batch(with_reference=False))

    def test_ref_spec_without_reference_spec_in_batch_raises(self):
        model = _model(
            reference_conditioning="ref_spec", generator_reference="cross_utt"
        )
        batch = _batch()
        batch.reference_specs = None
        with pytest.raises(ValueError, match="reference_specs"):
            model.training_step_g(batch)

    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_reference_conditioning_in_self_mode_raises(self, mode):
        model = _model(reference_conditioning=mode)
        with pytest.raises(ValueError, match="cross_utt"):
            model.training_step_g(_batch())

    def test_scl_detached_reforward_uses_the_generator_reference(self):
        model = _scl_model(
            generator_reference="cross_utt",
            reference_conditioning="ref_spec",
            scl_detach_z=True,
        )
        calls = []
        _spy_method(model.model_g, "scl_waveform_detached_z", calls)
        batch = _batch()
        model.training_step_g(batch)
        assert len(calls) == 1
        assert torch.allclose(
            calls[0]["speaker_embeddings"], batch.reference_embeddings, atol=1e-6
        )
        assert calls[0]["reference_spec"] is batch.reference_specs
        assert calls[0]["reference_spec_lengths"] is batch.reference_spec_lengths

    def test_swap_scl_keeps_target_embeddings(self):
        model = _scl_model(
            generator_reference="cross_utt",
            c_swap_spk=1.0,
            swap_spk_start_epoch=0,
            swap_spk_ramp_epochs=0,
        )
        calls = []
        _spy_method(model.model_g, "swap_scl_waveform", calls)
        batch = _batch()
        model.training_step_g(batch)
        assert len(calls) == 1
        swapped = calls[0]["speaker_embeddings"]
        # 各行は target embedding の並べ替えで、参照 embedding ではない
        for row in swapped:
            assert any(
                torch.allclose(row, t, atol=1e-6) for t in batch.speaker_embeddings
            )
            assert not any(
                torch.allclose(row, r, atol=1e-3) for r in batch.reference_embeddings
            )

    def test_latent_filling_keeps_target_embeddings(self, monkeypatch):
        from piper_train.vits import lightning

        model = _scl_model(generator_reference="cross_utt", latent_filling_tau=1.0)
        captured = []
        original = lightning.build_latent_filling_embeddings

        def spy(embeddings, **kwargs):
            captured.append(embeddings.detach().clone())
            return original(embeddings, **kwargs)

        monkeypatch.setattr(lightning, "build_latent_filling_embeddings", spy)
        batch = _batch()
        model.training_step_g(batch)
        assert model._lf_step_active
        assert len(captured) == 1
        assert torch.allclose(captured[0], batch.speaker_embeddings, atol=1e-6)

    def test_jcu_condition_is_the_generator_reference(self):
        model = _model(generator_reference="cross_utt")
        batch = _batch()
        model.training_step_g(batch)
        assert torch.allclose(model._spk_cond, batch.reference_embeddings, atol=1e-6)

    def test_telemetry_receives_the_generator_reference(self, monkeypatch):
        from piper_train.vits import telemetry

        model = _model(
            generator_reference="cross_utt",
            reference_conditioning="ref_spec",
            telemetry_every=1,
        )
        captured = []
        original = telemetry.collect_modulation_telemetry

        def spy(model_g, speaker_embeddings, **kwargs):
            captured.append((speaker_embeddings, kwargs))
            return original(model_g, speaker_embeddings, **kwargs)

        monkeypatch.setattr(telemetry, "collect_modulation_telemetry", spy)
        model.log = lambda *a, **k: None
        batch = _batch()
        model.training_step_g(batch)
        assert len(captured) == 1
        emb, kwargs = captured[0]
        assert torch.allclose(emb, batch.reference_embeddings, atol=1e-6)
        assert kwargs["reference_spec"] is batch.reference_specs
        assert kwargs["reference_spec_lengths"] is batch.reference_spec_lengths

    def test_validation_forward_uses_the_reference(self):
        model = _model(
            generator_reference="cross_utt", reference_conditioning="ref_spec"
        )
        calls = _capture_forward(model)
        model.eval()
        batch = _batch()
        with torch.no_grad():
            model.validation_step(batch, 0)
        kwargs = calls[0]["kwargs"]
        assert torch.allclose(
            kwargs["speaker_embeddings"], batch.reference_embeddings, atol=1e-6
        )
        assert kwargs["reference_spec"] is batch.reference_specs

    def test_batch_transfer_hook_crops_randomly_in_training(self):
        model = _model(generator_reference="cross_utt", reference_max_frames=8)
        batch = _batch(ref_frames=(30, 12, 30, 5))
        out = model.on_before_batch_transfer(batch, 0)
        expected, expected_lens = crop_reference_specs(
            batch.reference_specs,
            batch.reference_spec_lengths,
            8,
            mode="random",
            epoch=0,
            keys=batch.utterance_ids,
        )
        assert torch.equal(out.reference_specs, expected)
        assert torch.equal(out.reference_spec_lengths, expected_lens)

    def test_batch_transfer_hook_crops_head_in_eval(self):
        model = _model(generator_reference="cross_utt", reference_max_frames=8)
        model.eval()
        batch = _batch(ref_frames=(30, 12, 30, 5))
        out = model.on_before_batch_transfer(batch, 0)
        assert out.reference_spec_lengths.tolist() == [8, 8, 8, 5]
        assert torch.equal(out.reference_specs[0], batch.reference_specs[0, :, :8])

    def test_batch_transfer_hook_is_identity_in_self_mode(self):
        model = _model()
        batch = _batch(with_reference=False)
        assert model.on_before_batch_transfer(batch, 0) is batch

    def test_test_example_condition_loads_the_reference_spec(self, tmp_path):
        from piper_train.vits.dataset import Utterance

        model = _model(
            generator_reference="cross_utt",
            reference_conditioning="ref_spec",
            reference_max_frames=6,
        )
        spec = torch.rand(SPEC_CHANNELS, 10)
        torch.save(spec, tmp_path / "ref.spec.pt")
        emb = _unit(torch.randn(192))
        utt = Utterance(
            phoneme_ids=np.array([1, 2]),
            audio_norm_path=None,
            audio_spec_path=None,
            speaker_embedding=emb,
            reference_audio_spec_path=tmp_path / "ref.spec.pt",
        )
        spk, ref_spec, ref_len = model._test_example_condition(utt)
        assert torch.equal(spk, emb.unsqueeze(0))
        assert torch.equal(ref_spec, spec[:, :6].unsqueeze(0))
        assert ref_len.tolist() == [6]

    def test_test_example_condition_without_reference_is_unchanged(self):
        from piper_train.vits.dataset import Utterance

        model = _model()
        emb = _unit(torch.randn(192))
        utt = Utterance(
            phoneme_ids=np.array([1, 2]),
            audio_norm_path=None,
            audio_spec_path=None,
            speaker_embedding=emb,
        )
        spk, ref_spec, ref_len = model._test_example_condition(utt)
        assert torch.equal(spk, emb.unsqueeze(0))
        assert ref_spec is None and ref_len is None

    def test_test_example_from_the_dataset_uses_its_reference(self, tmp_path):
        model = _model(
            generator_reference="cross_utt",
            reference_conditioning="ref_spec",
            reference_max_frames=16,
        )
        ds = PiperDataset([_write_dataset(tmp_path)], load_references=True)
        item = ds[3]  # d -> c (25 frame)
        spk, ref_spec, ref_len = model._test_example_condition(item)
        assert torch.equal(spk, item.reference_embedding.unsqueeze(0))
        assert torch.equal(ref_spec, item.reference_spec[:, :16].unsqueeze(0))
        assert ref_len.tolist() == [16]

    def test_model_loads_reference_dataset_only_in_cross_utt(self, tmp_path):
        path = _write_dataset(tmp_path)
        common = {"dataset": [path], "dataset_dir": tmp_path, "num_test_examples": 0}
        cross = _model(generator_reference="cross_utt", **common)
        plain = _model(**common)
        assert cross._train_dataset.dataset.load_references is True
        assert cross._train_dataset[0].reference_spec is not None
        assert plain._train_dataset.dataset.load_references is False
        assert plain._train_dataset[0].reference_spec is None

    def test_model_with_missing_reference_fields_fails_at_load(self, tmp_path):
        path = _write_dataset(tmp_path, drop=("b", "reference_audio_spec_path"))
        with pytest.raises(ValueError, match=r"b\.pt"):
            _model(
                generator_reference="cross_utt",
                dataset=[path],
                dataset_dir=tmp_path,
                num_test_examples=0,
            )

    def test_fixed_test_set_requires_reference_spec_for_ref_spec(self, tmp_path):
        model = _model(
            generator_reference="cross_utt", reference_conditioning="ref_spec"
        )
        emb = np.random.default_rng(0).standard_normal(192).astype(np.float32)
        path = tmp_path / "test_utterances.jsonl"
        path.write_text(
            json.dumps(
                {"text": "x", "phoneme_ids": [1, 2], "speaker_embedding": emb.tolist()}
            )
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="reference_audio_spec_path"):
            model._load_test_dataset(path)


class TestVitsModelArguments:
    @pytest.mark.parametrize("value", ["cross", "", None, "SELF"])
    def test_invalid_generator_reference_raises(self, value):
        with pytest.raises(ValueError, match="generator_reference"):
            _model(generator_reference=value)

    @pytest.mark.parametrize("value", [0, -3, True, 1.5])
    def test_invalid_reference_max_frames_raises(self, value):
        with pytest.raises(ValueError, match="reference_max_frames"):
            _model(reference_max_frames=value)

    def test_defaults_are_self_and_512(self):
        model = _model()
        assert model.hparams.generator_reference == "self"
        assert model.hparams.reference_max_frames == 512

    @pytest.mark.parametrize(
        "extra", [{"latent_filling_tau": 0.1}, {"c_swap_spk": 0.5}]
    )
    def test_reference_conditioning_with_lf_or_swap_raises_in_model(self, extra):
        with pytest.raises(ValueError, match=r"Latent Filling|swap"):
            _model(
                reference_conditioning="ref_spec",
                generator_reference="cross_utt",
                **extra,
            )


# ---------------------------------------------------------------------------
# CLI の組み合わせ (SystemExit)
# ---------------------------------------------------------------------------


def _parse(extra=()):
    from piper_train.__main__ import create_parser

    return create_parser().parse_args(
        ["--dataset-dir", "/nonexistent-dataset-dir", "--batch-size", "1", *extra]
    )


def _check(args):
    validate_reference_training_args(
        reference_conditioning=args.reference_conditioning,
        generator_reference=args.generator_reference,
        latent_filling_tau=args.latent_filling_tau,
        c_swap_spk=args.c_swap_spk,
    )


class TestCliCombinations:
    def test_parser_defaults(self):
        args = _parse()
        assert args.generator_reference == "self"
        assert args.reference_max_frames == 512

    def test_parser_rejects_unknown_generator_reference(self):
        with pytest.raises(SystemExit):
            _parse(["--generator-reference", "random"])

    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_reference_conditioning_requires_cross_utt(self, mode):
        with pytest.raises(SystemExit, match="cross_utt"):
            _check(_parse(["--reference-conditioning", mode]))
        _check(
            _parse(
                ["--reference-conditioning", mode, "--generator-reference", "cross_utt"]
            )
        )

    @pytest.mark.parametrize("generator_reference", ["self", "cross_utt"])
    def test_no_reference_conditioning_accepts_either_generator_reference(
        self, generator_reference
    ):
        _check(_parse(["--generator-reference", generator_reference]))

    @pytest.mark.parametrize(
        "extra",
        [["--latent-filling-tau", "0.2"], ["--c-swap-spk", "1.0"]],
    )
    def test_reference_conditioning_with_latent_filling_is_rejected(self, extra):
        with pytest.raises(SystemExit, match=r"Latent Filling|swap"):
            _check(
                _parse(
                    [
                        "--reference-conditioning",
                        "ref_spec",
                        "--generator-reference",
                        "cross_utt",
                        *extra,
                    ]
                )
            )

    @pytest.mark.parametrize(
        "extra",
        [["--latent-filling-tau", "0.2"], ["--c-swap-spk", "1.0"]],
    )
    def test_c0_group_cross_utt_without_conditioning_keeps_lf_and_swap(self, extra):
        _check(_parse(["--generator-reference", "cross_utt", *extra]))

    def test_main_rejects_the_combination_before_reading_the_dataset(self, monkeypatch):
        from piper_train import __main__ as cli

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "piper_train",
                "--dataset-dir",
                "/nonexistent-dataset-dir",
                "--batch-size",
                "1",
                "--reference-conditioning",
                "ref_spec",
            ],
        )
        with pytest.raises(SystemExit, match="cross_utt"):
            cli.main()


# ---------------------------------------------------------------------------
# strict zero-shot
# ---------------------------------------------------------------------------


class TestStrictReferencePairs:
    def test_strict_cross_utt_valid_batch_passes(self):
        stats = validate_training_batch(_batch(), require_reference_pairs=True)
        assert stats["anchors"] == BATCH

    def test_strict_cross_utt_requires_reference_fields(self):
        with pytest.raises(ValueError, match="reference"):
            validate_training_batch(
                _batch(with_reference=False), require_reference_pairs=True
            )

    def test_strict_cross_utt_rejects_self_reference(self):
        batch = _batch()
        batch.reference_utterance_ids = ["t0", "r1", "r2", "r3"]
        with pytest.raises(ValueError, match="itself"):
            validate_training_batch(batch, require_reference_pairs=True)

    def test_strict_cross_utt_rejects_other_speaker_reference(self):
        batch = _batch()
        batch.reference_speaker_ids = [0, 1, 1, 1]
        with pytest.raises(ValueError, match="speaker"):
            validate_training_batch(batch, require_reference_pairs=True)

    def test_strict_cross_utt_rejects_identical_audio(self):
        batch = _batch()
        batch.reference_audio_sha256s = ["h0", "hr1", "hr2", "hr3"]
        with pytest.raises(ValueError, match="audio"):
            validate_training_batch(batch, require_reference_pairs=True)

    def test_strict_cross_utt_rejects_invalid_reference_embeddings(self):
        batch = _batch()
        batch.reference_embeddings[2] = 0
        with pytest.raises(ValueError, match="reference"):
            validate_training_batch(batch, require_reference_pairs=True)

    def test_strict_self_mode_does_not_require_references(self):
        validate_training_batch(_batch(with_reference=False))

    def test_invalid_peer_reference_fails_every_rank(self, monkeypatch):
        monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
        monkeypatch.setattr(torch.distributed, "is_initialized", lambda: True)
        monkeypatch.setattr(torch.distributed, "get_world_size", lambda: 2)

        def gather(result, local):
            peer = dict(local)
            peer["reference_error"] = "peer reference is the target itself"
            result[:] = [local, peer]

        monkeypatch.setattr(torch.distributed, "all_gather_object", gather)
        with pytest.raises(ValueError, match="peer"):
            validate_training_batch(_batch(), require_reference_pairs=True)

    def test_training_step_runs_the_reference_check_in_strict_mode(self):
        model = _model(generator_reference="cross_utt")
        model.hparams.strict_zero_shot = True
        batch = _batch()
        batch.reference_utterance_ids = ["t0", "r1", "r2", "r3"]
        with pytest.raises(ValueError, match="itself"):
            model.training_step(batch, 0)


# ===========================================================================
# Fix round 1 (task-7R-review.md の minor 1-8、controller ruling R13)
# ===========================================================================


def _write_rows(tmp_path, rows, overrides=None):
    """``_write_dataset`` の行に ``{name: {field: value}}`` を上書きして書く。"""
    path = _write_dataset(tmp_path, rows=rows)
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        name = line["audio_norm_path"].split("/")[-1].removesuffix(".pt")
        line.update((overrides or {}).get(name, {}))
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", "utf-8")
    return path


# 4 人目までの話者で循環参照 (a->b->c->d->a, e->f->g->h->e)
_CYCLE_ROWS = [
    ("a", 0, 20, "b"),
    ("b", 0, 21, "c"),
    ("c", 0, 22, "d"),
    ("d", 0, 23, "a"),
    ("e", 1, 24, "f"),
    ("f", 1, 25, "g"),
    ("g", 1, 26, "h"),
    ("h", 1, 27, "e"),
]


def _subset_names(model):
    """発話 identity -> 'train' / 'val' / 'test' (実際の random_split の結果)。"""
    full = model._train_dataset.dataset
    names = {}
    for name in ("train", "val", "test"):
        subset = getattr(model, f"_{name}_dataset", None)
        for index in getattr(subset, "indices", []):
            names[str(full.utterances[index].audio_norm_path.resolve())] = name
    return full, names


class TestReferenceSubsetOverlap:
    """R13: jsonl の split と実行時 random_split は別物。跨ぎを数えて警告する。"""

    def _model(self, tmp_path, **kwargs):
        path = _write_dataset(tmp_path, rows=_CYCLE_ROWS)
        return _model(
            generator_reference="cross_utt",
            dataset=[path],
            dataset_dir=tmp_path,
            num_test_examples=0,
            validation_split=0.5,
            **kwargs,
        )

    def test_cross_subset_references_are_counted_and_warned(self, tmp_path, caplog):
        with caplog.at_level("WARNING"):
            model = self._model(tmp_path)
        full, names = _subset_names(model)
        expected = {}
        for utt in full.utterances:
            target = names[str(utt.audio_norm_path.resolve())]
            reference = names.get(utt.reference_utterance_id, "unloaded")
            if reference != target:
                key = f"{target}->{reference}"
                expected[key] = expected.get(key, 0) + 1
        # 4 + 4 発話の 50% split で循環参照なら必ず跨ぎがある (前提の確認)
        assert sum(expected.values()) > 0
        assert model.hparams["reference_subset_overlap"] == expected
        messages = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        overlap = [m for m in messages if "random_split" in m]
        assert len(overlap) == 1, messages
        for key, count in expected.items():
            assert f"{key}={count}" in overlap[0]

    def test_length_filtered_references_are_counted_as_unloaded(self, tmp_path):
        # phoneme 長は 2,3,4,2,3,4,2,3 → max 3 で c (i=2) と f (i=5) が target から
        # 外れる。それを参照する b と e の 2 件が "->unloaded"
        model = self._model(tmp_path, max_phoneme_ids=3)
        overlap = model.hparams["reference_subset_overlap"]
        unloaded = sum(n for k, n in overlap.items() if k.endswith("->unloaded"))
        assert unloaded == 2

    def test_speaker_split_keeps_every_reference_in_its_subset(self, tmp_path, caplog):
        # 同話者内の循環参照なので、話者単位で分ければ跨ぎは 0 になる
        with caplog.at_level("WARNING"):
            model = self._model(tmp_path, validation_split_by="speaker")
        full, names = _subset_names(model)
        sides = {}
        for utt in full.utterances:
            sides.setdefault(utt.speaker_id, set()).add(
                names[str(utt.audio_norm_path.resolve())]
            )
        assert all(len(s) == 1 for s in sides.values()), sides
        assert {"train", "val"} <= set(names.values())
        assert model.hparams["reference_subset_overlap"] == {}
        assert not any("random_split" in r.getMessage() for r in caplog.records)

    def test_self_mode_records_nothing(self, tmp_path, caplog):
        path = _write_dataset(tmp_path, rows=_CYCLE_ROWS)
        with caplog.at_level("WARNING"):
            model = _model(
                dataset=[path],
                dataset_dir=tmp_path,
                num_test_examples=0,
                validation_split=0.5,
            )
        assert "reference_subset_overlap" not in model.hparams
        assert not any("random_split" in r.getMessage() for r in caplog.records)

    def test_generator_reference_help_states_the_split_scope(self):
        from piper_train.__main__ import create_parser

        text = " ".join(create_parser().format_help().split())
        assert "jsonl split field" in text
        assert "random train/val split" in text

    def test_pairs_summary_states_the_split_scope(self):
        _, summary = build_reference_pairs([_entry("a", 1), _entry("b", 1)], seed=0)
        assert "jsonl" in summary["split_check"]
        assert "random train/val split" in summary["split_check"]

    def test_validate_reference_pairs_docstring_states_the_split_scope(self):
        doc = " ".join(requirements.validate_reference_pairs.__doc__.split())
        assert "jsonl" in doc and "random_split" in doc


class TestReferenceNoiseSeeding:
    """参照埋め込みの noise は (step, target 発話) で決まり、rank 間で独立。"""

    def _condition(self, model, batch, step):
        model._training_batch_index = step
        emb, _, _ = model._generator_condition(batch, batch.speaker_embeddings)
        return emb

    def _same_reference_batch(self, prefix):
        batch = _batch()
        batch.utterance_ids = [f"{prefix}{i}" for i in range(BATCH)]
        batch.reference_embeddings = _unit(torch.ones(BATCH, 192))
        return batch

    def test_ranks_with_different_targets_get_different_noise(self):
        model = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.05)
        # 2 rank を模す: 同じ step・同じ行位置・同じ参照埋め込み、target だけ違う
        rank0 = self._condition(model, self._same_reference_batch("rank0-"), 7)
        rank1 = self._condition(model, self._same_reference_batch("rank1-"), 7)
        for row in range(BATCH):
            assert not torch.allclose(rank0[row], rank1[row], atol=1e-4)

    def test_noise_follows_the_target_not_the_row_position(self):
        model = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.05)
        batch = self._same_reference_batch("t")
        out = self._condition(model, batch, 3)
        flipped = self._same_reference_batch("t")
        flipped.utterance_ids = list(reversed(batch.utterance_ids))
        out_flipped = self._condition(model, flipped, 3)
        assert torch.equal(out_flipped, out.flip(0))

    def test_noise_is_deterministic_per_step_and_changes_between_steps(self):
        model = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.05)
        batch = self._same_reference_batch("t")
        first = self._condition(model, batch, 11)
        assert torch.equal(first, self._condition(model, batch, 11))
        assert not torch.allclose(first, self._condition(model, batch, 12), atol=1e-4)

    def test_zero_sigma_draws_no_noise(self, monkeypatch):
        model = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.0)
        batch = _batch()
        calls = []
        original = torch.randn

        def counting_randn(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(torch, "randn", counting_randn)
        out = self._condition(model, batch, 5)
        monkeypatch.undo()
        assert calls == []
        expected = torch.nn.functional.normalize(batch.reference_embeddings, dim=-1)
        assert torch.equal(out, expected)

    def test_eval_adds_no_noise(self):
        model = _model(generator_reference="cross_utt", spk_emb_noise_sigma=0.05)
        model.eval()
        batch = _batch()
        out = self._condition(model, batch, 5)
        assert out is batch.reference_embeddings


REFERENCE_MODES_FOR_PIN = ("random", "head")


@pytest.mark.skipif(not torch.cuda.is_available(), reason="pinned memory needs CUDA")
class TestReferenceCropPinning:
    def test_crop_of_pinned_inputs_is_pinned(self):
        specs = torch.rand(2, SPEC_CHANNELS, 30).pin_memory()
        lengths = torch.tensor([30, 12]).pin_memory()
        for mode in REFERENCE_MODES_FOR_PIN:
            out, out_lengths = crop_reference_specs(
                specs, lengths, 8, mode=mode, keys=["a", "b"]
            )
            assert out.is_pinned() and out_lengths.is_pinned()

    def test_crop_of_unpinned_inputs_stays_unpinned(self):
        out, out_lengths = crop_reference_specs(
            torch.rand(2, SPEC_CHANNELS, 30), torch.tensor([30, 12]), 8, mode="head"
        )
        assert not out.is_pinned() and not out_lengths.is_pinned()

    def test_batch_transfer_hook_keeps_a_pinned_batch_pinned(self):
        model = _model(generator_reference="cross_utt", reference_max_frames=8)
        batch = _batch(ref_frames=(30, 12, 30, 5)).pin_memory()
        out = model.on_before_batch_transfer(batch, 0)
        assert out.reference_specs.is_pinned()
        assert out.reference_spec_lengths.is_pinned()


# 参照 manifest の誤りは、型の誤りでも読み飛ばさず起動時に落とす (minor 6)
_UNREFERENCED_C_ROWS = [
    ("a", 0, 20, "b"),
    ("b", 0, 30, "a"),
    ("c", 0, 25, "a"),  # c は誰の参照でもない → 読み飛ばすと target が黙って減る
    ("d", 1, 40, "e"),
    ("e", 1, 22, "d"),
]


class TestReferenceManifestTypes:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("split", 1),
            ("audio_sha256", 5),
            ("reference_audio_sha256", ["x"]),
            ("reference_utterance_id", 7),
            ("reference_audio_spec_path", {"p": 1}),
            ("reference_speaker_embedding_path", 3.5),
        ],
    )
    def test_bad_type_fails_at_load_with_the_line(self, tmp_path, field, value):
        path = _write_rows(tmp_path, _UNREFERENCED_C_ROWS, {"c": {field: value}})
        with pytest.raises(ValueError, match=r"c\.pt") as info:
            PiperDataset([path], load_references=True)
        assert field in str(info.value)
        assert "line 3" in str(info.value)

    def test_self_mode_ignores_bad_reference_types(self, tmp_path):
        path = _write_rows(
            tmp_path, _UNREFERENCED_C_ROWS, {"c": {"reference_utterance_id": 7}}
        )
        assert len(PiperDataset([path])) == len(_UNREFERENCED_C_ROWS)


class TestValidateCacheReferenceFiles:
    def test_missing_reference_files_are_warned_separately(self, tmp_path, caplog):
        path = _write_dataset(tmp_path)
        (tmp_path / "emb" / "b.npy").unlink()  # a の参照埋め込み
        with caplog.at_level("WARNING"):
            ds = PiperDataset([path], load_references=True, validate_cache=True)
        assert sorted(u.audio_norm_path.name for u in ds.utterances) == [
            "b.pt",
            "c.pt",
            "d.pt",
        ]
        messages = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        reference = [m for m in messages if "reference file" in m]
        assert len(reference) == 1, messages
        assert "1 target" in reference[0]

    def test_no_reference_warning_when_reference_files_exist(self, tmp_path, caplog):
        path = _write_dataset(tmp_path)
        with caplog.at_level("WARNING"):
            PiperDataset([path], load_references=True, validate_cache=True)
        assert not any("reference file" in r.getMessage() for r in caplog.records)


class TestBuildReferencePairsRobustness:
    @pytest.mark.parametrize("field", ["audio_spec_path", "audio_norm_path"])
    def test_missing_cache_path_is_excluded_with_reason(self, field):
        entries = [_entry("a", 1), _entry("b", 1), _entry("c", 1)]
        del entries[2][field]
        paired, summary = build_reference_pairs(entries, seed=0)
        assert len(paired) == 2
        assert summary["excluded_by_reason"] == {f"missing_{field}": 1}
        for row in paired:
            assert row["reference_utterance_id"] != "cache/c.pt"

    def test_cli_names_the_file_for_any_unreadable_cache(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        # 中身が tensor でない cache (AttributeError 系) でもファイル名付きで止める
        torch.save({"not": "a tensor"}, tmp_path / "cache" / "b.pt")
        with pytest.raises(SystemExit, match=r"b\.pt"):
            pairs_main([str(jsonl), str(tmp_path / "pairs.jsonl")])

    def test_cli_skips_hashing_rows_without_audio_norm_path(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path,
            [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4]), ("c", 1, [0.5, 0.6])],
        )
        rows = [json.loads(x) for x in jsonl.read_text(encoding="utf-8").splitlines()]
        del rows[2]["audio_norm_path"]
        jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", "utf-8")
        out = tmp_path / "pairs.jsonl"
        assert pairs_main([str(jsonl), str(out)]) == 0
        summary = json.loads((tmp_path / "pairs.jsonl.summary.json").read_text("utf-8"))
        assert summary["excluded_by_reason"] == {"missing_audio_norm_path": 1}

    def test_failed_summary_write_leaves_no_output(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        out = tmp_path / "pairs.jsonl"
        summary = tmp_path / "summary-is-a-directory"
        summary.mkdir()
        with pytest.raises((SystemExit, OSError)):
            pairs_main([str(jsonl), str(out), "--summary", str(summary), "--overwrite"])
        assert not out.exists()
        leftovers = sorted(
            p.name for p in tmp_path.iterdir() if p.name not in {"cache", "emb"}
        )
        assert leftovers == ["dataset.jsonl", "summary-is-a-directory"]

    def test_existing_output_survives_a_failed_rewrite(self, tmp_path):
        jsonl = _write_cli_dataset(
            tmp_path, [("a", 1, [0.1, 0.2]), ("b", 1, [0.3, 0.4])]
        )
        out = tmp_path / "pairs.jsonl"
        out.write_text("previous\n", encoding="utf-8")
        summary = tmp_path / "summary-is-a-directory"
        summary.mkdir()
        with pytest.raises((SystemExit, OSError)):
            pairs_main([str(jsonl), str(out), "--summary", str(summary), "--overwrite"])
        assert out.read_text(encoding="utf-8") == "previous\n"


# ---------------------------------------------------------------------------
# self 既定の後方互換: 変更前 commit (6904ef0e) の golden (minor 4)
# ---------------------------------------------------------------------------


def _write_golden_dataset(root):
    """golden 専用の固定データ (他のテスト helper の変更に影響されない)。"""
    (root / "cache").mkdir(parents=True, exist_ok=True)
    (root / "emb").mkdir(exist_ok=True)
    rows = [("a", 0, 48, "b"), ("b", 0, 52, "a"), ("c", 1, 40, "d"), ("d", 1, 60, "c")]
    lines = []
    for i, (name, speaker, frames, ref) in enumerate(rows):
        g = torch.Generator().manual_seed(i)
        torch.save(
            torch.randn(1, frames * 256, generator=g) * 0.1,
            root / "cache" / f"{name}.pt",
        )
        torch.save(
            torch.randn(513, frames, generator=g).abs(),
            root / "cache" / f"{name}.spec.pt",
        )
        np.save(root / "emb" / f"{name}.npy", torch.randn(192, generator=g).numpy())
        lines.append(
            json.dumps(
                {
                    "phoneme_ids": list(range(1, 11)),
                    "audio_norm_path": f"cache/{name}.pt",
                    "audio_spec_path": f"cache/{name}.spec.pt",
                    "speaker_id": speaker,
                    "speaker_embedding_path": f"emb/{name}.npy",
                    # self 既定では読まれない参照フィールド (入っていても不変)
                    "audio_sha256": f"h{name}",
                    "reference_utterance_id": f"cache/{ref}.pt",
                    "reference_audio_spec_path": f"cache/{ref}.spec.pt",
                    "reference_speaker_embedding_path": f"emb/{ref}.npy",
                    "reference_audio_sha256": f"h{ref}",
                }
            )
        )
    path = root / "dataset.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class _GoldenSpeakerEncoder(torch.nn.Module):
    def forward(self, wav):
        pooled = torch.nn.functional.adaptive_avg_pool1d(wav.unsqueeze(1), 192)
        return torch.nn.functional.normalize(pooled.squeeze(1) + 1e-3, dim=-1)


def _golden_model(**overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    hparams = {
        "num_symbols": 40,
        "num_speakers": 4,
        "num_languages": 2,
        "dataset": None,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
        "upsample_initial_channel": 64,
        "hidden_channels": 64,
        "inter_channels": 64,
        "filter_channels": 128,
        "n_layers": 2,
        "prosody_dim": 0,
        "gin_channels": 64,
        "use_wavlm_discriminator": False,
        "c_dino": 0.5,
        "c_spk": 1.0,
        "spk_loss_type": "infonce",
        "spk_loss_positives": "cross_utt",
        "scl_detach_z": True,
        "use_mrd": True,
        "use_jcu_mrd": True,
        "telemetry_every": 1,
        "c_swap_spk": 1.0,
        "swap_spk_start_epoch": 0,
        "swap_spk_ramp_epochs": 0,
        "spk_emb_noise_sigma": 0.05,
        # sub-band STFT loss は計算するが重み 0 にする (勾配は厳密に 0 倍)。
        # LogSTFTMagnitudeLoss の勾配は bin ごとに (X/|X|) / (|X| + 1e-7)
        # (大きさ ~1/|X|、向きは X そのもの)。ランダム初期化の o_mb には
        # |X| ≈ 1e-6 の STFT bin が統計的にほぼ必ず数個ある (center=True の
        # reflect pad で端 frame の bin がほぼ実数になり、|X| の分布が 0 近傍で
        # 線形になる)。fp32 の縮約順序の差 (o_mb で絶対 ~1e-8) がその bin の X を
        # 相対 ~1e-2 動かし、勾配も同じ相対量で動く。実測: thread 数 12→1 で
        # sub_stft 由来の勾配 abs 和が相対 2.5e-2、Windows→Linux で 1.5e-1 動き、
        # 他の全 loss 成分は 6e-7 以下だった。この項の勾配はコードではなく
        # 丸め誤差が決めるため、変更前との一致を見る golden から外す
        # (loss 経路自体は c 倍の前まで毎回通る)。
        "c_sub_stft": 0.0,
        "batch_size": 4,
    }
    hparams.update(overrides)
    model = VitsModel(**hparams)
    model.scl_encoder = _GoldenSpeakerEncoder()
    model._log_with_batch_info = lambda *a, **k: None
    model.log = lambda *a, **k: None
    model._grad_probe_due = lambda: False
    return model


def _grad_summary(model):
    grads = [
        (name, p.grad.double())
        for name, p in sorted(model.named_parameters())
        if p.grad is not None
    ]
    return {
        "count": len(grads),
        "abs_sum": float(sum(g.abs().sum() for _, g in grads)),
        "sq_sum": float(sum((g * g).sum() for _, g in grads)),
    }


def _self_mode_step_summary(root):
    """self 既定の 1 step (主経路 + LF + validation) の要約。

    旧 commit のコードでも同じ関数を実行できるよう、7R 以前からある API だけを使う
    (``PiperDataset`` / ``UtteranceCollate`` / ``training_step_g`` /
    ``validation_step`` / ``on_before_batch_transfer``)。
    """
    path = _write_golden_dataset(root)
    dataset = PiperDataset([path])
    batch = UtteranceCollate(is_multispeaker=True, segment_size=8192)(
        [dataset[i] for i in range(len(dataset))]
    )
    batch.language_ids = torch.tensor([0, 1, 0, 1])
    summary = {}
    for tag, overrides in (
        ("main", {}),
        ("lf", {"latent_filling_tau": 1.0, "c_swap_spk": 0.0}),
    ):
        model = _golden_model(**overrides)
        model.train()
        torch.manual_seed(42)
        loss = model.training_step_g(batch)
        loss.backward()
        summary[f"{tag}_loss"] = float(loss)
        summary[f"{tag}_grads"] = _grad_summary(model)
        summary[f"{tag}_rng_sha256"] = hashlib.sha256(
            torch.get_rng_state().numpy().tobytes()
        ).hexdigest()
        if tag == "main":
            summary["spk_cond_abs_sum"] = float(model._spk_cond.double().abs().sum())
            model.zero_grad()
            model.eval()
            torch.manual_seed(7)
            with torch.no_grad():
                summary["val_loss"] = float(model.validation_step(batch, 0))
            summary["hook_identity"] = model.on_before_batch_transfer(batch, 0) is batch
    return summary


# 変更前 commit 6904ef0e (Task 7R 導入前) の値。生成手順:
# ``git archive 6904ef0e pytest.ini pyproject.toml src test tools`` を scratch に
# 展開し、その ``src/python`` / ``src/python_run`` / ``src/python/g2p`` を sys.path
# 先頭に置いて本ファイルを読み込み、``_self_mode_step_summary(<tmp>)`` を実行した
# 値 (Windows 11, torch 2.11.0+cu128, CPU, 12 thread)。
#
# プラットフォーム非依存性の確認 (golden 再生成時、``c_sub_stft=0`` の構成):
# - 同じ環境・同じ thread 数では、本変更後のコードも同じ値を bit 一致で返す
#   (Windows 12 thread / Linux 2 thread の両方で確認)。
# - Linux (Docker python:3.12-slim, torch 2.11.0+cpu, 1/2/4 thread) と Windows
#   1 thread の値は、変更前・変更後のコードとも上の値から相対 3.5e-7 以内
#   (最大は main_grads.sq_sum)。RNG の hash・勾配 tensor 数・hook は全環境で一致。
# 旧 golden (sub-band STFT 込み) は Linux CI で main_grads.abs_sum が相対 8.7e-4
# ずれて落ちた。原因は ``_golden_model`` の ``c_sub_stft`` の注釈を参照。
_SELF_MODE_GOLDEN = {
    "hook_identity": True,
    "lf_grads": {
        "abs_sum": 745.0750663102907,
        "count": 163,
        "sq_sum": 11.851346881818838,
    },
    "lf_loss": 1.0139615535736084,
    "lf_rng_sha256": (
        "6dd35cc3db12a0f86e837d7ee877137355994dc73a91e5159945b50f9afa7f1e"
    ),
    "main_grads": {
        "abs_sum": 55775.65552449414,
        "count": 794,
        "sq_sum": 66453.83724960452,
    },
    "main_loss": 49.673377990722656,
    "main_rng_sha256": (
        "6dd35cc3db12a0f86e837d7ee877137355994dc73a91e5159945b50f9afa7f1e"
    ),
    "spk_cond_abs_sum": 43.53158425033325,
    "val_loss": 57.876007080078125,
}
# 許容誤差: 縮約順序 (thread 数・ISA・BLAS) の違いによる差は、上の実測で相対
# 3.5e-7 以下。self 経路の退行はそれより桁で大きく動く。実測:
# spk_emb_noise_sigma を 0.05→0.0 にすると main_loss は相対 2.9e-3、global seed
# を 42→43 にすると相対 1.5e-2 動いた (下の確認テストが前者を固定する)。rtol 1e-4
# は縮約順序差の ~290 倍、最小の退行例の 1/29 で両者を分離する。
# 縮約順序差が golden に入り込まないことは、thread 数を変えた再計算との比較
# (``test_golden_quantities_are_insensitive_to_reduction_order``) が毎回確かめる。
# global RNG の状態 (Mersenne Twister の整数状態) と勾配 tensor 数は厳密一致
# (乱数消費の増減は値の近さに関係なく検出する)。
_SELF_MODE_GOLDEN_RTOL = 1e-4
# 縮約順序だけを変えたときに golden の各値が動いてよい幅。golden を別環境で
# 比べる余裕として rtol の 1/10 以下を要求する (実測は thread 12→1 で最大
# 相対 2.5e-7 = この幅の 1/40)。
_REDUCTION_ORDER_RTOL = _SELF_MODE_GOLDEN_RTOL / 10


def _assert_summary_close(got, expected, rtol):
    assert set(got) == set(expected)
    for key, golden in expected.items():
        value = got[key]
        if isinstance(golden, dict):
            assert value["count"] == golden["count"], key
            for sub in ("abs_sum", "sq_sum"):
                assert value[sub] == pytest.approx(golden[sub], rel=rtol), (key, sub)
        elif isinstance(golden, float):
            assert value == pytest.approx(golden, rel=rtol), key
        else:
            assert value == golden, key


class TestSelfModePreChangeGolden:
    @pytest.fixture(scope="class")
    def self_mode_summary(self, tmp_path_factory):
        return _self_mode_step_summary(tmp_path_factory.mktemp("self_mode_golden"))

    def test_self_mode_step_matches_the_pre_change_golden(self, self_mode_summary):
        assert _SELF_MODE_GOLDEN is not None, "golden not generated"
        _assert_summary_close(
            self_mode_summary, _SELF_MODE_GOLDEN, _SELF_MODE_GOLDEN_RTOL
        )

    def test_golden_quantities_are_insensitive_to_reduction_order(
        self, self_mode_summary, tmp_path
    ):
        """golden に比べる値は縮約順序 (環境差の主因) でほぼ動かない。

        intra-op thread 数を変えると CPU kernel の部分和の分け方が変わり、
        プラットフォーム間の ISA / BLAS 差と同種の丸め誤差が入る。golden の
        各値がこれで ``_REDUCTION_ORDER_RTOL`` 以上動くなら、その値は丸め誤差に
        敏感で、別環境では golden と比べられない (旧構成の sub-band STFT 勾配が
        thread 12→1 で相対 2.9e-4 動いて Linux CI で落ちた事例)。
        """
        default_threads = torch.get_num_threads()
        other_threads = 1 if default_threads > 1 else 4
        torch.set_num_threads(other_threads)
        try:
            reordered = _self_mode_step_summary(tmp_path)
        finally:
            torch.set_num_threads(default_threads)
        _assert_summary_close(reordered, self_mode_summary, _REDUCTION_ORDER_RTOL)

    def test_golden_tolerance_separates_a_changed_conditioning(self, tmp_path):
        """許容誤差の根拠: noise σ を変えるだけで main_loss が rtol を超えて動く。"""
        assert _SELF_MODE_GOLDEN is not None, "golden not generated"
        path = _write_golden_dataset(tmp_path)
        dataset = PiperDataset([path])
        batch = UtteranceCollate(is_multispeaker=True, segment_size=8192)(
            [dataset[i] for i in range(len(dataset))]
        )
        batch.language_ids = torch.tensor([0, 1, 0, 1])
        model = _golden_model(spk_emb_noise_sigma=0.0)
        model.train()
        torch.manual_seed(42)
        loss = float(model.training_step_g(batch))
        assert loss != pytest.approx(
            _SELF_MODE_GOLDEN["main_loss"], rel=_SELF_MODE_GOLDEN_RTOL
        )


# ---------------------------------------------------------------------------
# strict の失敗伝播を実 2 rank の CPU Gloo で確かめる (minor 5)
# ---------------------------------------------------------------------------


def _strict_reference_gloo_worker(rank, store_path, output_dir):
    """rank 1 だけ自己参照の batch。両 rank が同じ呼び出しで落ちることを記録する。"""
    from datetime import timedelta
    from pathlib import Path

    torch.set_num_threads(1)
    dist = torch.distributed
    dist.init_process_group(
        "gloo",
        store=dist.FileStore(store_path, 2),
        rank=rank,
        world_size=2,
        timeout=timedelta(seconds=30),
    )
    results = []
    try:
        for phase in ("invalid_peer", "valid"):
            batch = _batch()
            batch.utterance_ids = [f"rank{rank}-t{i}" for i in range(BATCH)]
            batch.reference_utterance_ids = [f"rank{rank}-r{i}" for i in range(BATCH)]
            if phase == "invalid_peer" and rank == 1:
                batch.reference_utterance_ids[0] = batch.utterance_ids[0]
            try:
                validate_training_batch(batch, require_reference_pairs=True)
                results.append([phase, "ok"])
            except ValueError as exc:
                results.append([phase, str(exc)])
        (Path(output_dir) / f"rank-{rank}.json").write_text(
            json.dumps(results), encoding="utf-8"
        )
    finally:
        dist.destroy_process_group()


@pytest.mark.skipif(
    not torch.distributed.is_gloo_available(), reason="CPU Gloo backend unavailable"
)
def test_strict_reference_error_fails_every_gloo_rank(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    # test_training_batch_schedule.py と同じく、Gloo の初期化は単一 thread の
    # 別 process で行う (広い pytest process での Windows access violation 回避)
    code = """
import sys
import torch
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import test_reference_pairs as pairs
if __name__ == '__main__':
    torch.multiprocessing.spawn(pairs._strict_reference_gloo_worker,
        args=(sys.argv[3], sys.argv[4]), nprocs=2, join=True)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(Path(__file__).parents[1]),
            str(Path(__file__).parent),
            str(tmp_path / "store"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            **os.environ,
            "PYTHONFAULTHANDLER": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    results = [
        json.loads((tmp_path / f"rank-{rank}.json").read_text(encoding="utf-8"))
        for rank in range(2)
    ]
    for rank_results in results:
        (phase0, message0), (phase1, message1) = rank_results
        # rank 0 の batch は正しいが、peer (rank 1) の誤りで同じ呼び出しが落ちる
        assert phase0 == "invalid_peer" and "itself" in message0
        assert "rank1-t0" in message0
        # 失敗後も collective はずれず、次の正しい batch は両 rank で通る
        assert phase1 == "valid" and message1 == "ok"

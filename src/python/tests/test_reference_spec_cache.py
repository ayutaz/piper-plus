"""参照専用 spec cache (参照融合計画 §8、Ruling R17) の TDD テスト。

固定する契約:

* ``build_reference_pairs`` は参照発話の元音声 ``audio_path`` を
  ``reference_audio_path`` として書き足す (既存の field は変えない。
  ``audio_path`` の無い dataset では書かない)。
* ``tools.build_reference_spec_cache`` は参照の元音声ごとに 1 回、評価と同じ
  ``reference_spec_from_file`` で spec を作り、学習 cache と同じ形式 (fp16 の
  ``torch.save``) で content-addressed な名前 (spec の sha256) に書く。出力 jsonl は
  ``reference_audio_spec_path`` だけを cache へ向け直し、cache dir に来歴 sidecar を
  置く。再実行は同じ出力になり、失敗した実行は前回の cache を壊さない。
* 学習 (``reference_conditioning="ref_spec"``) は起動時に sidecar を照合し、
  frontend・STFT 設定の食い違い、sidecar の無い参照、sidecar に載っていない参照を
  ``SystemExit`` で拒否する。none / capacity は影響を受けない。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="reference spec cache needs torch")
pytest.importorskip("soxr", reason="reference spec frontend requires soxr")
sf = pytest.importorskip("soundfile", reason="reference WAV fixtures need soundfile")

pytestmark = pytest.mark.unit

MODEL_SR = 22050
WAV_SR = 24000  # モデル sr と違う sr で書き、frontend の resample を必ず通す
STFT = {"filter_length": 1024, "hop_length": 256, "win_length": 1024}
STFT_FLAGS = [
    "--filter-length",
    "1024",
    "--hop-length",
    "256",
    "--win-length",
    "1024",
]
FRONTEND = "no-vad;soxr-mq"
OTHER_FRONTEND = "energy-vad@16k;soxr-hq"
SPEC_CHANNELS = 513

# (name, speaker, 秒, 周波数)。発話ごとに音声が違う (audio_sha256 が全部違う)
_UTTERANCES = [
    ("a", 0, 0.50, 180.0),
    ("b", 0, 0.62, 230.0),
    ("c", 0, 0.45, 300.0),
    ("d", 1, 0.55, 140.0),
    ("e", 1, 0.70, 410.0),
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _pairs_tool():
    import piper_train.tools.build_reference_pairs as tool

    return tool


def _cache_tool():
    import piper_train.tools.build_reference_spec_cache as tool

    return tool


def _contract():
    import piper_train.reference_spec_contract as contract

    return contract


def _validate_cache(paths, **kwargs):
    import piper_train.zero_shot_requirements as requirements

    return requirements.validate_reference_spec_cache(paths, **kwargs)


def _speech_like(seconds: float, freq: float, sr: int, seed: int) -> np.ndarray:
    """有声 (VAD を通る振幅) の調波 + 弱い雑音。前後に短い無音を付ける。"""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    voiced = sum(
        (0.25 / k) * np.sin(2 * np.pi * freq * k * t + k) for k in range(1, 5)
    ) + 0.01 * rng.standard_normal(t.size)
    silence = np.zeros(int(0.1 * sr))
    return np.concatenate([silence, voiced, silence]).astype(np.float32)


def _write_config(root: Path, audio: dict | None = None) -> Path:
    config = {
        "audio": audio if audio is not None else {"sample_rate": MODEL_SR},
        "num_symbols": 40,
        "num_speakers": 2,
    }
    path = root / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _make_dataset(root: Path, *, with_audio_path: bool = True) -> Path:
    """tiny dataset (WAV + audio_norm + 学習 spec + 埋め込み) と jsonl を書く。"""
    for sub in ("wav", "cache", "emb"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    lines = []
    for i, (name, speaker, seconds, freq) in enumerate(_UTTERANCES):
        audio = _speech_like(seconds, freq, WAV_SR, seed=i)
        sf.write(str(root / "wav" / f"{name}.wav"), audio, WAV_SR, subtype="FLOAT")
        np.save(root / "cache" / f"{name}.npy", audio[None, :])
        g = torch.Generator().manual_seed(100 + i)
        # 学習 cache の spec (別 builder 由来の想定。参照 spec としては使わせない)
        torch.save(
            torch.randn(SPEC_CHANNELS, 20, generator=g).abs().half(),
            root / "cache" / f"{name}.spec.pt",
        )
        np.save(
            root / "emb" / f"{name}.npy",
            (torch.randn(192, generator=g).numpy() + 0.1).astype(np.float32),
        )
        row = {
            "phoneme_ids": [1, 5, 6, 7, 2],
            "audio_norm_path": f"cache/{name}.npy",
            "audio_spec_path": f"cache/{name}.spec.pt",
            "speaker_id": speaker,
            "speaker_embedding_path": f"emb/{name}.npy",
        }
        if with_audio_path:
            row["audio_path"] = f"wav/{name}.wav"
        lines.append(json.dumps(row))
    path = root / "dataset.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _make_pairs(root: Path, **kwargs) -> Path:
    dataset = _make_dataset(root, **kwargs)
    pairs = root / "dataset.pairs.jsonl"
    assert _pairs_tool().main([str(dataset), str(pairs), "--seed", "7"]) == 0
    return pairs


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_cache(
    root: Path,
    pairs: Path,
    *,
    frontend: str = FRONTEND,
    output: Path | None = None,
    cache_dir: Path | None = None,
    extra: list[str] | None = None,
    stft_flags: list[str] | None = None,
    config: Path | None = None,
) -> tuple[Path, Path]:
    output = output or root / "dataset.refspec.jsonl"
    cache_dir = cache_dir or root / "refspec"
    config = config or _write_config(root)
    argv = [
        str(pairs),
        str(output),
        "--frontend",
        frontend,
        "--config",
        str(config),
        "--output-dir",
        str(cache_dir),
        *(STFT_FLAGS if stft_flags is None else stft_flags),
        *(extra or []),
    ]
    assert _cache_tool().main(argv) == 0
    return output, cache_dir


def _sidecar(cache_dir: Path) -> dict:
    name = _contract().REFERENCE_SPEC_CACHE_SIDECAR
    return json.loads((cache_dir / name).read_text(encoding="utf-8"))


def _eval_spec(wav: Path, frontend: str = FRONTEND, sample_rate: int = MODEL_SR):
    from piper_train.reference_frontend import reference_spec_from_file

    spec, _ = reference_spec_from_file(
        wav, target_sample_rate=sample_rate, frontend=frontend, **STFT
    )
    return spec


def _snapshot(paths: list[Path]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in paths:
        if path.is_dir():
            for child in sorted(path.iterdir()):
                files[str(child)] = child.read_bytes()
        elif path.exists():
            files[str(path)] = path.read_bytes()
    return files


@pytest.fixture
def built(tmp_path):
    """pairs → 参照専用 cache まで作った tiny dataset。"""
    pairs = _make_pairs(tmp_path)
    output, cache_dir = _run_cache(tmp_path, pairs)
    return tmp_path, pairs, output, cache_dir


# ---------------------------------------------------------------------------
# build_reference_pairs: 参照の元音声を運ぶ
# ---------------------------------------------------------------------------


class TestPairsCarryReferenceAudioPath:
    def test_reference_audio_path_is_the_references_audio_path(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        rows = _read_jsonl(pairs)
        by_norm = {row["audio_norm_path"]: row for row in rows}
        for row in rows:
            reference = by_norm[row["reference_utterance_id"]]
            assert row["reference_audio_path"] == reference["audio_path"]

    def test_existing_reference_fields_are_unchanged(self, tmp_path):
        # audio_path の有無で既存の 4 field と割り当ては変わらない
        with_path = _read_jsonl(_make_pairs(tmp_path / "with"))
        without = _read_jsonl(_make_pairs(tmp_path / "without", with_audio_path=False))
        for a, b in zip(with_path, without, strict=True):
            a = dict(a)
            a.pop("audio_path")
            a.pop("reference_audio_path")
            assert a == b

    def test_no_reference_audio_path_without_audio_path(self, tmp_path):
        rows = _read_jsonl(_make_pairs(tmp_path, with_audio_path=False))
        assert rows
        assert all("reference_audio_path" not in row for row in rows)


# ---------------------------------------------------------------------------
# build_reference_spec_cache: spec の中身と保存形式
# ---------------------------------------------------------------------------


class TestCacheSpecParity:
    @pytest.mark.parametrize(
        "frontend", ["no-vad;soxr-mq", "no-vad;soxr-hq", "energy-vad@16k;soxr-hq"]
    )
    def test_written_spec_equals_eval_spec_after_fp16_roundtrip(
        self, tmp_path, frontend
    ):
        pairs = _make_pairs(tmp_path)
        output, _ = _run_cache(tmp_path, pairs, frontend=frontend)
        for row in _read_jsonl(output):
            stored = torch.load(
                tmp_path / row["reference_audio_spec_path"], weights_only=True
            )
            expected = _eval_spec(tmp_path / row["reference_audio_path"], frontend)
            # 厳密一致: tool と評価は同じ関数で同じ float32 spec を作り、fp16 への
            # 丸め (round-to-nearest-even) は入力が同じなら決定的。許容誤差は要らない
            assert torch.equal(stored, expected.half())

    def test_stored_spec_is_fp16_like_the_training_cache(self, built):
        root, _, output, _ = built
        row = _read_jsonl(output)[0]
        stored = torch.load(root / row["reference_audio_spec_path"], weights_only=True)
        assert stored.dtype == torch.float16
        assert stored.dim() == 2 and stored.size(0) == SPEC_CHANNELS

    def test_file_name_is_the_float32_spec_sha256(self, built):
        from piper_train.reference_frontend import reference_spec_sha256

        root, _, output, _ = built
        for row in _read_jsonl(output):
            spec = _eval_spec(root / row["reference_audio_path"])
            name = Path(row["reference_audio_spec_path"]).name
            assert name == f"{reference_spec_sha256(spec)}.spec.pt"

    def test_sample_rate_comes_from_the_config(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        config = _write_config(tmp_path, {"sample_rate": 16000})
        output, _ = _run_cache(tmp_path, pairs, config=config)
        row = _read_jsonl(output)[0]
        stored = torch.load(
            tmp_path / row["reference_audio_spec_path"], weights_only=True
        )
        expected = _eval_spec(tmp_path / row["reference_audio_path"], sample_rate=16000)
        assert torch.equal(stored, expected.half())

    def test_stft_from_the_config_needs_no_flags(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        config = _write_config(tmp_path, {"sample_rate": MODEL_SR, **STFT})
        _, cache_dir = _run_cache(tmp_path, pairs, config=config, stft_flags=[])
        sidecar = _sidecar(cache_dir)
        assert {k: sidecar[k] for k in STFT} == STFT


# ---------------------------------------------------------------------------
# build_reference_spec_cache: 出力 jsonl と sidecar
# ---------------------------------------------------------------------------


class TestCacheOutputs:
    def test_reference_spec_paths_point_into_the_cache(self, built):
        root, _, output, cache_dir = built
        for row in _read_jsonl(output):
            path = (root / row["reference_audio_spec_path"]).resolve()
            assert path.parent == cache_dir.resolve()
            assert path.is_file()

    def test_only_reference_audio_spec_path_changes(self, built):
        _, pairs, output, _ = built
        for before, after in zip(_read_jsonl(pairs), _read_jsonl(output), strict=True):
            before = dict(before)
            after = dict(after)
            assert before.pop("reference_audio_spec_path") != after.pop(
                "reference_audio_spec_path"
            )
            assert before == after

    def test_each_unique_reference_is_computed_once(self, tmp_path, monkeypatch):
        import piper_train.reference_frontend as frontend_module

        pairs = _make_pairs(tmp_path)
        real = frontend_module.reference_spec_from_file
        calls: list[str] = []

        def counting(path, **kwargs):
            calls.append(str(Path(path).resolve()))
            return real(path, **kwargs)

        monkeypatch.setattr(frontend_module, "reference_spec_from_file", counting)
        _run_cache(tmp_path, pairs)
        unique = {
            str((tmp_path / row["reference_audio_path"]).resolve())
            for row in _read_jsonl(pairs)
        }
        assert sorted(calls) == sorted(unique)

    def test_sidecar_records_the_recipe(self, built):
        _, _, _, cache_dir = built
        sidecar = _sidecar(cache_dir)
        assert sidecar["schema"] == _contract().REFERENCE_SPEC_CACHE_SCHEMA
        assert sidecar["frontend"] == FRONTEND
        assert sidecar["sample_rate"] == MODEL_SR
        assert {k: sidecar[k] for k in STFT} == STFT
        assert sidecar["center"] is False
        assert sidecar["spec_channels"] == SPEC_CHANNELS

    def test_sidecar_lists_every_written_file(self, built):
        _, _, _, cache_dir = built
        sidecar = _sidecar(cache_dir)
        on_disk = {p.name for p in cache_dir.glob("*.spec.pt")}
        assert set(sidecar["files"]) == on_disk
        assert sidecar["count"] == len(on_disk)

    def test_sidecar_per_file_hashes_and_frames(self, built):
        from piper_train.reference_frontend import reference_spec_sha256

        root, _, output, cache_dir = built
        files = _sidecar(cache_dir)["files"]
        for row in _read_jsonl(output):
            wav = root / row["reference_audio_path"]
            spec = _eval_spec(wav)
            entry = files[Path(row["reference_audio_spec_path"]).name]
            assert entry["spec_sha256"] == reference_spec_sha256(spec)
            assert entry["frames"] == spec.size(-1)
            assert {
                "audio_path": str(wav.resolve()),
                "audio_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
            } in entry["sources"]

    def test_rerun_is_idempotent(self, built):
        root, pairs, output, cache_dir = built
        before = _snapshot([output, cache_dir])
        _run_cache(root, pairs, extra=["--overwrite"])
        assert _snapshot([output, cache_dir]) == before

    def test_existing_output_requires_overwrite(self, built):
        root, pairs, _, _ = built
        with pytest.raises(SystemExit, match="--overwrite"):
            _run_cache(root, pairs)

    def test_dataset_loader_returns_the_tool_spec(self, built):
        from piper_train.vits.dataset import PiperDataset

        root, _, output, _ = built
        dataset = PiperDataset([output], load_references=True)
        rows = {
            str((root / row["audio_norm_path"]).resolve()): row
            for row in _read_jsonl(output)
        }
        assert len(dataset) == len(rows)
        for index in range(len(dataset)):
            item = dataset[index]
            row = rows[str(dataset.utterances[index].audio_norm_path.resolve())]
            stored = torch.load(
                root / row["reference_audio_spec_path"], weights_only=True
            )
            assert item.reference_spec.dtype == torch.float32
            assert torch.equal(item.reference_spec, stored.float())


# ---------------------------------------------------------------------------
# build_reference_spec_cache: 拒否
# ---------------------------------------------------------------------------


class TestCacheRefusals:
    def test_unknown_frontend_is_refused(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        with pytest.raises(SystemExit, match="no-vad;soxr-mq"):
            _run_cache(tmp_path, pairs, frontend="no-vad")
        assert not (tmp_path / "dataset.refspec.jsonl").exists()

    def test_frontend_is_required(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        config = _write_config(tmp_path)
        with pytest.raises(SystemExit) as info:
            _cache_tool().main(
                [
                    str(pairs),
                    str(tmp_path / "out.jsonl"),
                    "--config",
                    str(config),
                    "--output-dir",
                    str(tmp_path / "refspec"),
                    *STFT_FLAGS,
                ]
            )
        assert info.value.code == 2  # argparse の必須引数エラー

    @pytest.mark.parametrize("key", ["filter_length", "hop_length", "win_length"])
    def test_stft_flag_disagreeing_with_config_is_refused(self, tmp_path, key):
        pairs = _make_pairs(tmp_path)
        config = _write_config(tmp_path, {"sample_rate": MODEL_SR, **STFT})
        flags = list(STFT_FLAGS)
        index = flags.index("--" + key.replace("_", "-"))
        flags[index + 1] = str(STFT[key] // 2)
        with pytest.raises(SystemExit, match=key):
            _run_cache(tmp_path, pairs, config=config, stft_flags=flags)

    @pytest.mark.parametrize("key", ["filter_length", "hop_length", "win_length"])
    def test_stft_missing_from_config_and_flags_is_refused(self, tmp_path, key):
        # 既定値 (1024/256/1024) で黙って作らない
        pairs = _make_pairs(tmp_path)
        flags = list(STFT_FLAGS)
        index = flags.index("--" + key.replace("_", "-"))
        del flags[index : index + 2]
        with pytest.raises(SystemExit, match=key):
            _run_cache(tmp_path, pairs, stft_flags=flags)

    def test_config_without_sample_rate_is_refused(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        config = _write_config(tmp_path, {"quality": "medium"})
        with pytest.raises(SystemExit, match="sample_rate"):
            _run_cache(tmp_path, pairs, config=config)

    def test_all_bad_rows_are_reported_and_nothing_is_written(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        rows = _read_jsonl(pairs)
        # 話者 0 と話者 1 の参照音声を 1 つずつ壊す (欠落と読めない中身)
        missing = next(r for r in rows if r["speaker_id"] == 0)["reference_audio_path"]
        corrupt = next(r for r in rows if r["speaker_id"] == 1)["reference_audio_path"]
        (tmp_path / missing).unlink()
        (tmp_path / corrupt).write_bytes(b"not a wav file")
        bad = [
            i + 1
            for i, row in enumerate(rows)
            if row["reference_audio_path"] in (missing, corrupt)
        ]
        with pytest.raises(SystemExit) as info:
            _run_cache(tmp_path, pairs)
        message = str(info.value)
        assert message.count("line ") == len(bad)
        for line in bad:
            assert f"line {line}:" in message
        assert missing in message and corrupt in message
        assert not (tmp_path / "dataset.refspec.jsonl").exists()
        assert not (
            tmp_path / "refspec" / _contract().REFERENCE_SPEC_CACHE_SIDECAR
        ).exists()

    def test_row_without_reference_audio_path_is_reported(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        rows = _read_jsonl(pairs)
        rows[1].pop("reference_audio_path")
        pairs.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        with pytest.raises(SystemExit, match=r"line 2.*reference_audio_path"):
            _run_cache(tmp_path, pairs)

    def test_failed_run_leaves_the_previous_cache_intact(self, built):
        root, pairs, output, cache_dir = built
        before = _snapshot([output, cache_dir])
        (root / "wav" / "b.wav").unlink()
        with pytest.raises(SystemExit):
            _run_cache(root, pairs, extra=["--overwrite"])
        assert _snapshot([output, cache_dir]) == before

    def test_cache_dir_of_another_frontend_is_refused(self, built):
        root, pairs, _, cache_dir = built
        with pytest.raises(SystemExit, match=FRONTEND):
            _run_cache(
                root,
                pairs,
                frontend=OTHER_FRONTEND,
                output=root / "other.jsonl",
                cache_dir=cache_dir,
            )

    def test_refusing_to_overwrite_the_input(self, tmp_path):
        pairs = _make_pairs(tmp_path)
        with pytest.raises(SystemExit, match="input"):
            _run_cache(tmp_path, pairs, output=pairs, extra=["--overwrite"])


# ---------------------------------------------------------------------------
# 学習側の照合 (zero_shot_requirements.validate_reference_spec_cache)
# ---------------------------------------------------------------------------


def _reference_paths(root: Path, output: Path) -> list[Path]:
    return [root / row["reference_audio_spec_path"] for row in _read_jsonl(output)]


_MODEL_RECIPE = {"frontend": FRONTEND, "sample_rate": MODEL_SR, **STFT}


class TestTrainingCacheCheck:
    def test_covered_specs_pass(self, built):
        root, _, output, _ = built
        _validate_cache(_reference_paths(root, output), **_MODEL_RECIPE)

    def test_frontend_mismatch_is_refused(self, built):
        root, _, output, _ = built
        recipe = {**_MODEL_RECIPE, "frontend": OTHER_FRONTEND}
        with pytest.raises(SystemExit, match="frontend") as info:
            _validate_cache(_reference_paths(root, output), **recipe)
        assert FRONTEND in str(info.value) and OTHER_FRONTEND in str(info.value)

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("filter_length", 2048),
            ("hop_length", 128),
            ("win_length", 512),
            ("sample_rate", 24000),
        ],
    )
    def test_stft_mismatch_is_refused(self, built, key, value):
        root, _, output, _ = built
        with pytest.raises(SystemExit, match=key):
            _validate_cache(
                _reference_paths(root, output), **{**_MODEL_RECIPE, key: value}
            )

    def test_specs_without_sidecar_are_refused_with_count(self, built):
        # build_reference_pairs が書いた学習 cache の spec (sidecar なし)
        root, pairs, _, _ = built
        paths = _reference_paths(root, pairs)
        with pytest.raises(SystemExit, match=rf"{len(paths)} of {len(paths)}"):
            _validate_cache(paths, **_MODEL_RECIPE)

    def test_specs_not_listed_in_the_sidecar_are_refused_with_count(self, built):
        root, _, output, cache_dir = built
        paths = _reference_paths(root, output)
        stray = cache_dir / ("0" * 64 + ".spec.pt")
        stray.write_bytes(paths[0].read_bytes())
        with pytest.raises(SystemExit, match=rf"1 of {len(paths) + 1}"):
            _validate_cache([*paths, stray], **_MODEL_RECIPE)

    def test_undeclared_frontend_is_refused(self, built):
        root, _, output, _ = built
        with pytest.raises(SystemExit, match="reference_spec_frontend"):
            _validate_cache(
                _reference_paths(root, output), **{**_MODEL_RECIPE, "frontend": None}
            )

    def test_corrupt_sidecar_is_refused(self, built):
        root, _, output, cache_dir = built
        (cache_dir / _contract().REFERENCE_SPEC_CACHE_SIDECAR).write_text(
            "{not json", encoding="utf-8"
        )
        with pytest.raises(SystemExit, match="sidecar"):
            _validate_cache(_reference_paths(root, output), **_MODEL_RECIPE)

    def test_sidecar_of_another_schema_is_refused(self, built):
        root, _, output, cache_dir = built
        path = cache_dir / _contract().REFERENCE_SPEC_CACHE_SIDECAR
        sidecar = json.loads(path.read_text(encoding="utf-8"))
        sidecar["schema"] = "reference_spec_cache_v0"
        path.write_text(json.dumps(sidecar), encoding="utf-8")
        with pytest.raises(SystemExit, match="schema"):
            _validate_cache(_reference_paths(root, output), **_MODEL_RECIPE)


# ---------------------------------------------------------------------------
# 学習の起動 (VitsModel._load_datasets) で照合される
# ---------------------------------------------------------------------------

_HPARAMS = {
    "num_symbols": 40,
    "num_speakers": 2,
    "num_languages": 1,
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
    "batch_size": 2,
    "num_test_examples": 0,
    "validation_split": 0.0,
    "generator_reference": "cross_utt",
}


def _model(root: Path, dataset: Path, **overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    return VitsModel(
        **{**_HPARAMS, "dataset": [dataset], "dataset_dir": root, **overrides}
    )


class TestTrainingStartup:
    def test_ref_spec_model_loads_the_tool_cache(self, built):
        root, _, output, _ = built
        model = _model(
            root,
            output,
            reference_conditioning="ref_spec",
            reference_spec_frontend=FRONTEND,
        )
        assert len(model._train_dataset) == len(_read_jsonl(output))

    def test_ref_spec_model_refuses_training_cache_specs(self, built):
        root, pairs, _, _ = built
        with pytest.raises(SystemExit, match="build_reference_spec_cache"):
            _model(
                root,
                pairs,
                reference_conditioning="ref_spec",
                reference_spec_frontend=FRONTEND,
            )

    def test_ref_spec_model_refuses_a_cache_of_another_frontend(self, built):
        root, _, output, _ = built
        with pytest.raises(SystemExit, match="frontend"):
            _model(
                root,
                output,
                reference_conditioning="ref_spec",
                reference_spec_frontend=OTHER_FRONTEND,
            )

    def test_capacity_model_is_unaffected(self, built):
        root, pairs, _, _ = built
        model = _model(root, pairs, reference_conditioning="capacity")
        assert len(model._train_dataset) == len(_read_jsonl(pairs))

    def test_none_cross_utt_model_is_unaffected(self, built):
        root, pairs, _, _ = built
        model = _model(root, pairs)
        assert len(model._train_dataset) == len(_read_jsonl(pairs))

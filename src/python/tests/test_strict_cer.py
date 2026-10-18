"""Strict CER CLI tests use ASR stubs only to verify the gate protocol."""

import importlib.util
import json
import sys
from types import ModuleType

import numpy as np
import pytest

from piper_train.embedding_cache import file_sha256
from piper_train.evaluation_manifest import (
    conditions_sha256,
    create_manifest,
    text_sha256,
)
from piper_train.tools import eval_cer
from piper_train.vits.wavfile import write


pytestmark = pytest.mark.unit

# strict 経路は生成 WAV を scipy.io.wavfile (train extra) で読み直す。scipy を
# 入れない Windows CI job では、その読み直しに到達するテストだけを skip する。
# skip しないと scipy 欠落の例外で gate が落ち、波形検査を検証せずに通ってしまう。
requires_scipy = pytest.mark.skipif(
    importlib.util.find_spec("scipy") is None,
    reason="scipy not installed (train extra)",
)


def test_whisper_initialization_passes_cuda_without_download(monkeypatch):
    # Replace the module itself: Transformers' lazy imports can bypass an
    # attribute patch and accidentally initialize a real pretrained model.
    transformers = ModuleType("transformers")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    calls = []

    def factory(task, **kwargs):
        calls.append((task, kwargs))
        return lambda path, **options: {"text": "fixture"}

    transformers.pipeline = factory
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    transcribe = eval_cer.build_whisper_transcribe_fn(revision="a" * 40)
    assert transcribe("fixture.wav") == "fixture"
    assert calls[0][1]["device"] == "cuda"


@pytest.fixture
def strict_case(tmp_path, monkeypatch):
    np.save(tmp_path / "reference.npy", np.ones(192))
    (tmp_path / "model.onnx").write_bytes(b"protocol fixture")
    rows = [
        {
            "id": f"t{i}",
            "text": text,
            "phoneme_ids": [1, 10, 2],
            "speaker_embedding_path": "reference.npy",
        }
        for i, text in enumerate(["こんにちは", "ありがとう", "さようなら"])
    ]
    source = tmp_path / "test.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = create_manifest(
        source_path=source,
        output_path=manifest_path,
        models={"onnx": tmp_path / "model.onnx"},
        sample_rate=22050,
        asr_revision="a" * 40,
        source_revision="b" * 40,
        training_epoch=40,
    )
    clips = tmp_path / "clips"
    clips.mkdir()
    for row in rows:
        write(clips / (row["id"] + ".wav"), 22050, np.ones(32, dtype=np.float32))
    generation = {
        "version": 1,
        "backend": "onnx",
        "manifest_sha256": file_sha256(manifest_path),
        "conditions_sha256": manifest["conditions_sha256"],
        "model_sha256": manifest["models"]["onnx"]["sha256"],
        "training_epoch": 40,
        "sample_rate": manifest["sample_rate"],
        "scales": manifest["scales"],
        "seed": manifest["seed"],
        "ground_truth_f0_or_duration": False,
        "audio_encoding": "float32-raw",
        "clips": [
            {
                "id": row["id"],
                "wav_sha256": file_sha256(clips / (row["id"] + ".wav")),
                "text_sha256": row["text_sha256"],
                "speaker_embedding_sha256": row["speaker_embedding_sha256"],
                "reference_audio": row["reference_audio"],
                "seed": manifest["seed"] + i,
            }
            for i, row in enumerate(manifest["clips"])
        ],
    }
    (clips / "generation.json").write_text(json.dumps(generation))
    result_path = tmp_path / "cer.json"
    arguments = [
        "eval_cer",
        "--clips-dir",
        str(clips),
        "--manifest",
        str(manifest_path),
        "--json-out",
        str(result_path),
    ]
    calls = []

    def asr(model, language, revision=None, device="cuda"):
        calls.append((model, language, revision, device))
        return lambda wav: rows[int(wav.stem[1:])]["text"]

    monkeypatch.setattr(eval_cer, "build_whisper_transcribe_fn", asr)
    monkeypatch.setattr(sys, "argv", arguments)
    return clips, manifest_path, result_path, arguments, calls, generation


@requires_scipy
def test_strict_cli_pins_asr_and_passes_complete_three_clip_gate(strict_case):
    _clips, manifest_path, result_path, _args, calls, _generation = strict_case
    assert eval_cer.main() == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["gate_passed"] is True and result["n_clips"] == 3
    assert result["cer_median"] == 0
    assert result["manifest_sha256"] == file_sha256(manifest_path)
    assert calls == [("openai/whisper-small", "ja", "a" * 40, "cuda")]


@requires_scipy
@pytest.mark.parametrize("damage", ["wrong-sample-rate", "int16", "nonfinite"])
def test_strict_cli_checks_actual_waveform_before_asr(strict_case, damage):
    clips, _manifest, result_path, _args, calls, generation = strict_case
    values = np.ones(32, dtype=np.int16 if damage == "int16" else np.float32)
    if damage == "nonfinite":
        values[0] = np.nan
    write(clips / "t0.wav", 16000 if damage == "wrong-sample-rate" else 22050, values)
    generation["clips"][0]["wav_sha256"] = file_sha256(clips / "t0.wav")
    (clips / "generation.json").write_text(json.dumps(generation))
    assert eval_cer.main() == 2
    assert not calls
    assert json.loads(result_path.read_text())["gate_passed"] is False


def test_diagnostic_cli_keeps_single_clip_and_honors_explicit_asr_revision(
    strict_case, monkeypatch
):
    clips, _manifest, result_path, _args, calls, _generation = strict_case
    texts = clips / "texts.tsv"
    texts.write_text("t0\tこんにちは\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_cer",
            "--clips-dir",
            str(clips),
            "--texts",
            str(texts),
            "--asr-revision",
            "c" * 40,
            "--json-out",
            str(result_path),
        ],
    )
    assert eval_cer.main() == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["n_clips"] == 1 and result["cer_median"] == 0
    assert result["mode"] == "diagnostic" and result["gate_passed"] is None
    assert calls == [("openai/whisper-small", "ja", "c" * 40, "cuda")]


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "extra",
        "wav-changed",
        "report-duplicate",
        "report-missing",
        "report-hash",
        "n=1",
        "asr-model",
        "asr-revision",
        "asr-device",
        "language",
        "duplicate-texts",
        "empty-normalized-text",
        "scales-changed",
        "reference-changed",
        "gt-used",
    ],
)
def test_strict_cli_rejects_invalid_sets_before_asr(strict_case, damage):
    clips, manifest_path, result_path, args, calls, generation = strict_case
    if damage == "missing":
        (clips / "t0.wav").unlink()
    elif damage == "extra":
        (clips / "extra.wav").write_bytes(b"extra")
    elif damage == "wav-changed":
        (clips / "t0.wav").write_bytes(b"changed")
    elif damage == "report-duplicate":
        generation["clips"].append(generation["clips"][0])
    elif damage == "report-missing":
        generation["clips"].pop()
    elif damage == "report-hash":
        generation["manifest_sha256"] = "bad"
    elif damage == "n=1":
        (clips / "t1.wav").unlink()
        (clips / "t2.wav").unlink()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["clips"] = manifest["clips"][:1]
        manifest["conditions_sha256"] = conditions_sha256(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        generation["clips"] = generation["clips"][:1]
        generation["manifest_sha256"] = file_sha256(manifest_path)
        generation["conditions_sha256"] = manifest["conditions_sha256"]
    elif damage == "empty-normalized-text":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["clips"][0]["text"] = "。。。"
        manifest["clips"][0]["text_sha256"] = text_sha256("。。。")
        manifest["conditions_sha256"] = conditions_sha256(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        generation["manifest_sha256"] = file_sha256(manifest_path)
        generation["conditions_sha256"] = manifest["conditions_sha256"]
    elif damage == "scales-changed":
        generation["scales"] = [0.1, 2.0, 1.0]
    elif damage == "reference-changed":
        generation["clips"][0]["speaker_embedding_sha256"] = "different"
    elif damage == "gt-used":
        generation["ground_truth_f0_or_duration"] = True
    elif damage == "duplicate-texts":
        texts = clips / "texts.tsv"
        texts.write_text("t0\tこんにちは\nt0\tありがとう\n", encoding="utf-8")
        args += ["--texts", str(texts)]
    elif damage == "asr-device":
        args += ["--asr-device", "cpu"]
    else:
        args += ["--" + damage, "different"]
    (clips / "generation.json").write_text(json.dumps(generation))
    assert eval_cer.main() != 0
    assert not calls
    assert json.loads(result_path.read_text(encoding="utf-8"))["gate_passed"] is False


@requires_scipy
@pytest.mark.parametrize(
    "outcome",
    ["high-cer", "asr-failure", "bad-transcript", "early-epoch", "unknown-epoch"],
)
def test_strict_cli_never_promotes_partial_or_ineligible_results(
    strict_case, monkeypatch, outcome
):
    clips, manifest_path, result_path, _args, _calls, generation = strict_case

    def asr(*_args, **_kwargs):
        def transcribe(wav):
            if outcome == "asr-failure" and wav.stem == "t1":
                raise RuntimeError("ASR backend unavailable")
            if outcome in ("early-epoch", "unknown-epoch"):
                return {"t0": "こんにちは", "t1": "ありがとう", "t2": "さようなら"}[
                    wav.stem
                ]
            return None if outcome == "bad-transcript" else "読めません"

        return transcribe

    monkeypatch.setattr(eval_cer, "build_whisper_transcribe_fn", asr)
    if outcome in ("early-epoch", "unknown-epoch"):
        generation["training_epoch"] = 19 if outcome == "early-epoch" else None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["training_epoch"] = generation["training_epoch"]
        manifest["conditions_sha256"] = conditions_sha256(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        generation["manifest_sha256"] = file_sha256(manifest_path)
        generation["conditions_sha256"] = manifest["conditions_sha256"]
        (clips / "generation.json").write_text(json.dumps(generation))
    assert eval_cer.main() != 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["gate_passed"] is False
    if outcome in ("asr-failure", "bad-transcript"):
        assert result["failed_clips"]
        assert result["cer_median"] is None
    if outcome in ("early-epoch", "unknown-epoch"):
        assert result["cer_median"] == 0 and result["eligible_for_promotion"] is False


@requires_scipy
def test_strict_asr_initialization_failure_records_every_failed_clip(
    strict_case, monkeypatch
):
    _clips, _manifest, result_path, _args, _calls, _generation = strict_case

    def failing_asr(*_args, **_kwargs):
        raise RuntimeError("ASR initialization failed")

    monkeypatch.setattr(eval_cer, "build_whisper_transcribe_fn", failing_asr)
    assert eval_cer.main() != 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(result["failed_clips"]) == 3 and result["gate_passed"] is False

"""The evidence collector must reject missing engines, wrong weights and silence."""

import array
import copy
import json
import wave

import pytest

from scripts import public_base_runtime as runtime


def make_report(engine):
    cases = [
        {"key": key, "sha256": "reference" if key == "ja-1" else key}
        for key, _, _ in runtime.TEXTS
    ]
    cases += [
        {"key": "ja-conditioning-repeat", "sha256": "reference"},
        {"key": "ja-conditioning-negative", "sha256": "negative"},
    ]
    return {
        "runtime": engine,
        "base_revision": runtime.BASE_REVISION,
        "model_sha256": runtime.FILES["base.onnx"],
        "reference_sha256": runtime.REFERENCE_SHA256,
        "embedding_dimension": 192,
        "conditioning_changes_audio": True,
        "provider": "ORT Web WASM" if engine == "wasm" else "native CPU",
        "cases": cases,
    }


def reports(tmp_path, records):
    root = tmp_path / "reports"
    root.mkdir()
    for index, record in enumerate(records):
        folder = root / str(index)
        folder.mkdir()
        (folder / "report.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def test_summary_requires_all_six_engines(tmp_path):
    root = reports(tmp_path, [make_report(engine) for engine in runtime.RUNTIMES[:-1]])
    with pytest.raises(ValueError, match="Missing runtime"):
        runtime.summarize(root, tmp_path / "summary.json")
    assert not (tmp_path / "summary.json").exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("base_revision", "legacy", "Wrong model"),
        ("model_sha256", "different", "Wrong model"),
        ("reference_sha256", "private-ref", "Wrong reference"),
        ("embedding_dimension", 256, "conditioning evidence"),
        ("conditioning_changes_audio", False, "conditioning evidence"),
        ("provider", "onnxruntime-node", "WASM provider"),
    ],
)
def test_summary_rejects_wrong_evidence(tmp_path, field, value, message):
    records = [make_report(engine) for engine in runtime.RUNTIMES]
    records[-1][field] = value
    with pytest.raises(ValueError, match=message):
        runtime.summarize(reports(tmp_path, records), tmp_path / "summary.json")


def test_summary_rejects_skipped_language(tmp_path):
    record = make_report("python")
    record["cases"].pop(5)
    with pytest.raises(ValueError, match="Missing cases"):
        runtime.summarize(reports(tmp_path, [record]), tmp_path / "summary.json")


def test_summary_rejects_stochastic_or_ignored_conditioning(tmp_path):
    records = [make_report(engine) for engine in runtime.RUNTIMES]
    records[-1]["cases"][-2]["sha256"] = "not-repeatable"
    with pytest.raises(ValueError, match="Non-repeatable"):
        runtime.summarize(reports(tmp_path, records), tmp_path / "summary.json")


def test_all_engines_are_required_without_claiming_quality(tmp_path):
    records = [make_report(engine) for engine in runtime.RUNTIMES]
    output = tmp_path / "summary.json"
    runtime.summarize(reports(tmp_path, records), output)
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert set(summary["runtimes"]) == set(runtime.RUNTIMES)
    assert summary["quality_approval"] is False


def test_duplicate_engine_rejected(tmp_path):
    record = make_report("python")
    with pytest.raises(ValueError, match="duplicate"):
        runtime.summarize(
            reports(tmp_path, [record, copy.deepcopy(record)]),
            tmp_path / "summary.json",
        )


def write_wav(path, samples, rate=22050):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(array.array("h", samples).tobytes())


def test_silent_or_short_wav_cannot_count_as_success(tmp_path):
    wav = tmp_path / "silent.wav"
    write_wav(wav, [0] * 3000)
    with pytest.raises(ValueError, match="Silent"):
        runtime.inspect_wav(wav, 22050)
    write_wav(wav, [1000] * 100)
    with pytest.raises(ValueError, match="short"):
        runtime.inspect_wav(wav, 22050)


def test_real_pcm_wav_statistics(tmp_path):
    wav = tmp_path / "audio.wav"
    write_wav(wav, [1000, -1000] * 1500)
    stats = runtime.inspect_wav(wav, 22050)
    assert stats["frames"] == 3000
    assert stats["rms"] == pytest.approx(1000 / 32768)
    assert stats["peak"] == pytest.approx(1000 / 32768)
    with pytest.raises(ValueError, match="sample rate"):
        runtime.inspect_wav(wav, 16000)

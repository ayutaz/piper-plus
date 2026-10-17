"""Multiple conditioning references must all be excluded from cross-utterance scores."""

import json

import numpy as np
import pytest


pytest.importorskip(
    "torch",
    reason="The evaluation frontend needs the train extra; lightweight Windows CI omits it.",
)

from piper_train.tools import eval_zs_secs  # noqa: E402


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    synth = tmp_path / "synth"
    real = tmp_path / "real"
    synth.mkdir()
    real.mkdir()
    (synth / "t0.wav").write_bytes(b"generated")
    for name, content in {
        "ref1.wav": b"reference-one",
        "ref1-copy.wav": b"reference-one",
        "ref2.wav": b"reference-two",
        "cross1.wav": b"cross-one",
        "cross2.wav": b"cross-two",
    }.items():
        (real / name).write_bytes(content)
    monkeypatch.setattr(eval_zs_secs, "_create_session", lambda path: object())
    monkeypatch.setattr(
        eval_zs_secs,
        "_extract_embs",
        lambda session, paths, cache: np.tile([1.0, 0.0], (len(paths), 1)),
    )
    monkeypatch.setattr(eval_zs_secs, "_encoder_manifest", lambda path: {"path": path})
    monkeypatch.setattr(eval_zs_secs, "_print_report", lambda *args: None)
    output = tmp_path / "result.json"
    args = [
        "--synth-dir",
        str(synth),
        "--speaker-utts",
        str(real),
        "--encoder",
        "unit-test-encoder",
        "--skip-acoustics",
        "--json-out",
        str(output),
    ]
    return real, output, args


def test_all_reference_paths_and_content_aliases_are_excluded(inputs):
    real, output, args = inputs
    assert (
        eval_zs_secs.main(
            args
            + [
                "--exclude-ref",
                str(real / "ref1.wav"),
                "--exclude-ref",
                str(real / "ref2.wav"),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    manifest = report["manifest"]
    assert {item["file"] for item in manifest["speaker_utts"]["files"]} == {
        "cross1.wav",
        "cross2.wav",
    }
    assert len(manifest["conditioning_references"]) == 2
    assert all(item["sha256"] for item in manifest["conditioning_references"])
    assert len(manifest["excluded_by_hash"]) == 3
    assert report["encoders"]["campplus"]["same_utt_secs"] == pytest.approx(1)


def test_second_missing_reference_is_rejected(inputs):
    real, output, args = inputs
    with pytest.raises(SystemExit, match="not found"):
        eval_zs_secs.main(
            args
            + [
                "--exclude-ref",
                str(real / "ref1.wav"),
                "--exclude-ref",
                str(real / "missing.wav"),
            ]
        )
    assert not output.exists()


def test_excluding_all_but_one_real_utterance_is_rejected(inputs):
    real, output, args = inputs
    with pytest.raises(SystemExit, match="need >= 2"):
        eval_zs_secs.main(
            args
            + [
                "--exclude-ref",
                str(real / "ref1.wav"),
                "--exclude-ref",
                str(real / "ref2.wav"),
                "--exclude-ref",
                str(real / "cross1.wav"),
            ]
        )
    assert not output.exists()

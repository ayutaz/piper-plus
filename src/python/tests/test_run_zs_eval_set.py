"""Per-group zero-shot evaluation runner over a built evaluation set."""

import hashlib
import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

GROUPS = {"ja_a": ["ra0.wav", "ra1.wav"], "ja_b": ["rb0.wav"], "tsukuyomi": ["rt0.wav"]}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def evaluation(tmp_path):
    """A built set (set.json + test.jsonl) and a matching generation directory."""
    built = tmp_path / "set"
    rows, record = [], {"schema": "zs-eval-set-v1", "name": "fixture", "groups": {}}
    for group, references in GROUPS.items():
        speaker = built / "groups" / group / "speaker"
        speaker.mkdir(parents=True)
        (built / "groups" / group / "floor").mkdir()
        embeddings = []
        for index, reference in enumerate(references):
            (speaker / reference).write_bytes(f"{group}-{reference}".encode())
            embeddings.append({"reference": reference, "sha256": "0" * 64})
            rows.append(
                {
                    "id": f"{group}_r{index}_t0",
                    "speaker_embedding_path": f"groups/{group}/ref{index}.npy",
                    "reference_audio_paths": [f"groups/{group}/speaker/{reference}"],
                }
            )
        record["groups"][group] = {"files": [], "embeddings": embeddings}
    (built / "set.json").write_text(json.dumps(record), encoding="utf-8")
    (built / "test.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    generation = tmp_path / "wav"
    generation.mkdir()
    clips = []
    for row in rows:
        wav = generation / f"{row['id']}.wav"
        wav.write_bytes(row["id"].encode())
        clips.append({"id": row["id"], "wav_sha256": _sha(wav)})
    (generation / "generation.json").write_text(
        json.dumps({"backend": "torch-ema", "seed": 42, "clips": clips}),
        encoding="utf-8",
    )
    return built, generation


def _fake_evaluate(calls, transfer):
    def evaluate(argv):
        def value(flag):
            return argv[argv.index(flag) + 1]

        calls.append(argv)
        assert "--require-encoder2" in argv
        group = Path(value("--synth-dir")).name
        report = {
            "encoders": {
                "campplus": {
                    "normalized_transfer": transfer[group],
                    "cross_utt_secs": 0.6,
                },
                "encoder2": {
                    "normalized_transfer": transfer[group] / 2,
                    "cross_utt_secs": 0.5,
                },
            },
            "goodhart_flag": None,
            "above_ceiling_flag": False,
            "comb": {"synth": {"comb_excess_db_median": 2.0}},
        }
        Path(value("--json-out")).write_text(json.dumps(report), encoding="utf-8")
        return 0

    return evaluate


def test_each_group_is_evaluated_with_its_own_audio_and_references(
    tmp_path, evaluation
):
    from piper_train.tools.run_zs_eval_set import run

    built, generation = evaluation
    calls = []
    transfer = {"ja_a": 0.4, "ja_b": 0.2, "tsukuyomi": 0.1}
    out = tmp_path / "out"
    run(
        built, generation, out, "enc.onnx", "enc2.onnx", _fake_evaluate(calls, transfer)
    )

    assert len(calls) == 3
    by_group = {Path(c[c.index("--synth-dir") + 1]).name: c for c in calls}
    call = by_group["ja_a"]
    assert sorted(p.name for p in (out / "synth" / "ja_a").iterdir()) == [
        "ja_a_r0_t0.wav",
        "ja_a_r1_t0.wav",
    ]
    excluded = [call[i + 1] for i, v in enumerate(call) if v == "--exclude-ref"]
    assert sorted(Path(p).name for p in excluded) == ["ra0.wav", "ra1.wav"]
    assert call[call.index("--speaker-utts") + 1].endswith(str(Path("ja_a/speaker")))
    assert call[call.index("--floor-refs") + 1].endswith(str(Path("ja_a/floor")))
    assert call[call.index("--encoder2") + 1] == "enc2.onnx"


def test_summary_reports_japanese_mean_and_tsukuyomi_separately(tmp_path, evaluation):
    from piper_train.tools.run_zs_eval_set import run

    built, generation = evaluation
    transfer = {"ja_a": 0.4, "ja_b": 0.2, "tsukuyomi": 0.1}
    out = tmp_path / "out"
    summary = run(built, generation, out, "e", "e2", _fake_evaluate([], transfer))

    assert summary["ja_mean"]["campplus_normalized_transfer"] == pytest.approx(0.3)
    assert summary["ja_mean"]["encoder2_normalized_transfer"] == pytest.approx(0.15)
    assert summary["groups"]["tsukuyomi"]["campplus_normalized_transfer"] == 0.1
    assert summary["comb_excess_db_mean_all"] == pytest.approx(2.0)
    assert summary["flags"] == {"goodhart": [], "above_ceiling": []}
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == summary


def test_wav_hash_mismatch_with_generation_record_is_rejected(tmp_path, evaluation):
    from piper_train.tools.run_zs_eval_set import run

    built, generation = evaluation
    (generation / "ja_a_r0_t0.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="sha256"):
        run(built, generation, tmp_path / "out", "e", "e2", _fake_evaluate([], {}))


def test_missing_second_encoder_is_rejected(tmp_path, evaluation):
    from piper_train.tools.run_zs_eval_set import main

    built, generation = evaluation
    with pytest.raises(SystemExit):
        main(
            [
                "--set",
                str(built),
                "--generation",
                str(generation),
                "--encoder",
                "e.onnx",
                "--output",
                str(tmp_path / "out"),
            ]
        )

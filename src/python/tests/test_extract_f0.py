"""S-2 Phase C: GT frame-level F0 抽出 (``tools/extract_f0.py``) の TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §4.6。

固定する契約:

* **フレーム格子が spectrogram と厳密に一致**する。ここがずれると F0 と mel が
  時間的に食い違い、学習ターゲットが黙って壊れる (聴感では気づけない種類の
  事故)。``spec_frames_for`` を実際の ``spectrogram_torch`` 出力と突き合わせる。
* **キャッシュパス規約**が reader (``PiperDataset._f0_path_for``) と一致する。
  片方だけ変わるとキャッシュが黙って無視され S-2 が無効化される。
* **無声 = 0.0** の表現 (V/UV は f0 > 0 から一意に決まる)。
* **オクターブエラー検出**が話者中央値からの外れを率と連続長で拾う。
* **docstring に「学習ターゲット生成であり EVAL-ONLY メトリクスではない」**
  という宣言が残っている (設計 doc §5.4 が要求する明示)。
"""

from __future__ import annotations

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.tools import extract_f0  # noqa: E402


pyworld = pytest.importorskip(
    "pyworld", reason="pyworld required for F0 extraction tests"
)

SR = 22050
HOP = 256


def _sine(freq: float, seconds: float, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    # 単純な正弦より倍音を持つ信号のほうが DIO が安定して基本周波数を拾う
    wave = np.zeros_like(t)
    for h, amp in ((1, 1.0), (2, 0.5), (3, 0.25)):
        wave += amp * np.sin(2 * np.pi * freq * h * t)
    return (0.5 * wave / np.abs(wave).max()).astype(np.float32)


# --------------------------------------------------------------------------
# frame grid contract
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "audio_length", [512, 1000, 22050, 22050 + 137, 44100]
)
def test_spec_frames_for_matches_spectrogram_torch(audio_length):
    """F0 の格子計算が実際の STFT 出力フレーム数と一致する。

    (``spectrogram_torch`` は reflect pad の制約で 384 サンプル以下の入力を
    扱えないため、実発話が取りうる長さのみを対象にする。)
    """
    from piper_train.vits.mel_processing import spectrogram_torch

    audio = torch.zeros(1, audio_length)
    spec = spectrogram_torch(
        y=audio, n_fft=1024, sampling_rate=SR, hop_size=HOP, win_size=1024,
        center=False,
    )
    assert extract_f0.spec_frames_for(audio_length, HOP) == spec.size(-1)


def test_extracted_f0_has_exactly_spec_frames():
    audio = _sine(220.0, 1.3)
    f0 = extract_f0.extract_f0_frames(audio, SR, HOP)
    assert f0.shape == (extract_f0.spec_frames_for(len(audio), HOP),)
    assert f0.dtype == np.float32


def test_extracted_f0_tracks_a_known_pitch():
    audio = _sine(220.0, 1.0)
    f0 = extract_f0.extract_f0_frames(audio, SR, HOP)
    voiced = f0[f0 > 0]
    assert voiced.size > 0.5 * f0.size, "most frames of a tone should be voiced"
    assert float(np.median(voiced)) == pytest.approx(220.0, rel=0.05)


def test_silence_is_marked_unvoiced():
    silence = np.zeros(SR, dtype=np.float32)
    f0 = extract_f0.extract_f0_frames(silence, SR, HOP)
    assert np.all(f0 == 0.0)


def test_out_of_range_pitch_is_zeroed():
    """f0_floor/ceil の外に出た推定値は無声に倒す (ターゲット汚染の防止)。"""
    audio = _sine(220.0, 0.6)
    f0 = extract_f0.extract_f0_frames(audio, SR, HOP, f0_floor=300.0, f0_ceil=800.0)
    assert np.all(f0 == 0.0)


# --------------------------------------------------------------------------
# cache path convention
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec_name",
    ["abc123.spec.pt", "abc123.spec.npy", "abc123.pt", "abc123.npy"],
)
def test_f0_path_convention_strips_cache_suffixes(tmp_path, spec_name):
    path = extract_f0.f0_path_for(tmp_path, tmp_path / spec_name)
    assert path.name == "abc123.f0.npy"


def test_writer_and_reader_agree_on_the_cache_path(tmp_path):
    """writer (extract_f0) と reader (PiperDataset) のパス規約が一致する。"""
    from piper_train.vits.dataset import PiperDataset

    spec_path = tmp_path / "deadbeef.spec.pt"
    assert extract_f0.f0_path_for(tmp_path, spec_path) == PiperDataset._f0_path_for(
        tmp_path, spec_path
    )


# --------------------------------------------------------------------------
# quality stats (octave errors)
# --------------------------------------------------------------------------


def test_quality_stats_reports_voiced_rate_and_percentiles():
    f0 = np.array([0.0, 200.0, 210.0, 0.0, 190.0], dtype=np.float32)
    stats = extract_f0.f0_quality_stats(f0)
    assert stats["n_frames"] == 5
    assert stats["n_voiced"] == 3
    assert stats["voiced_rate"] == pytest.approx(0.6)
    assert stats["f0_median_hz"] == pytest.approx(200.0)


def test_octave_errors_are_detected_by_rate_and_run_length():
    """話者中央値の半分に落ちた連続区間を「オクターブエラー候補」として拾う。"""
    f0 = np.array([200.0] * 6 + [100.0] * 4 + [200.0] * 10, dtype=np.float32)
    stats = extract_f0.f0_quality_stats(f0, reference_median_hz=200.0)
    assert stats["octave_error_rate"] == pytest.approx(4 / 20)
    assert stats["octave_error_max_run"] == 4


def test_normal_intonation_is_not_flagged_as_an_octave_error():
    """通常の抑揚 (±400 cent 程度) を誤検出しない。"""
    f0 = np.array([160.0, 200.0, 250.0, 210.0, 180.0], dtype=np.float32)
    stats = extract_f0.f0_quality_stats(f0, reference_median_hz=200.0)
    assert stats["octave_error_rate"] == 0.0


def test_quality_stats_on_a_fully_unvoiced_utterance():
    stats = extract_f0.f0_quality_stats(np.zeros(10, dtype=np.float32), 200.0)
    assert stats["n_voiced"] == 0
    assert stats["f0_median_hz"] is None
    assert stats["octave_error_rate"] == 0.0


def test_speaker_summary_aggregates_per_speaker():
    rows = [
        {"speaker_id": 0, "f0_median_hz": 200.0, "voiced_rate": 0.7,
         "octave_error_rate": 0.0},
        {"speaker_id": 0, "f0_median_hz": 210.0, "voiced_rate": 0.6,
         "octave_error_rate": 0.10},
        {"speaker_id": 1, "f0_median_hz": 110.0, "voiced_rate": 0.5,
         "octave_error_rate": 0.0},
    ]
    summary = extract_f0.summarize_speakers(rows)
    assert summary["0"]["n_utterances"] == 2
    assert summary["0"]["f0_median_hz"] == pytest.approx(205.0)
    assert summary["0"]["n_utts_octave_error_gt_5pct"] == 1
    assert summary["1"]["f0_median_hz"] == pytest.approx(110.0)


# --------------------------------------------------------------------------
# end-to-end over a tiny dataset.jsonl
# --------------------------------------------------------------------------


def _tiny_dataset(tmp_path, n_utts: int = 3):
    import json

    cache = tmp_path / "cache"
    cache.mkdir()
    lines = []
    for i in range(n_utts):
        audio = _sine(180.0 + 20 * i, 0.6)
        np.save(str(cache / f"utt{i}.npy"), audio)
        norm_path = cache / f"utt{i}.npy"
        spec_path = cache / f"utt{i}.spec.pt"
        spec_path.write_bytes(b"")  # 実体は不要 (パス規約のためだけに存在)
        lines.append(
            json.dumps(
                {
                    "phoneme_ids": [1, 2, 3],
                    "audio_norm_path": str(norm_path),
                    "audio_spec_path": str(spec_path),
                    "speaker_id": i % 2,
                }
            )
        )
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("\n".join(lines), encoding="utf-8")
    return dataset


def test_run_writes_fp16_cache_and_a_quality_report(tmp_path):
    dataset = _tiny_dataset(tmp_path)
    out_dir = tmp_path / "f0"
    report_path = tmp_path / "report.json"

    report = extract_f0.run(
        dataset, out_dir, workers=1, report_path=report_path
    )

    assert report["n_ok"] == 3
    assert report["n_error"] == 0
    assert report_path.exists()
    files = sorted(out_dir.glob("*.f0.npy"))
    assert len(files) == 3
    arr = np.load(files[0])
    assert arr.dtype == np.float16
    assert arr.ndim == 1
    # 話者集計が report に載る (品質ガードの出力先)
    assert set(report["speakers"]) == {"0", "1"}


def test_run_skips_existing_cache_unless_overwrite(tmp_path):
    dataset = _tiny_dataset(tmp_path, n_utts=1)
    out_dir = tmp_path / "f0"
    extract_f0.run(dataset, out_dir, workers=1)
    cached = sorted(out_dir.glob("*.f0.npy"))[0]
    mtime = cached.stat().st_mtime_ns
    extract_f0.run(dataset, out_dir, workers=1)
    assert cached.stat().st_mtime_ns == mtime


def test_run_reports_errors_without_crashing(tmp_path):
    import json

    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "phoneme_ids": [1],
                "audio_norm_path": str(tmp_path / "missing.npy"),
                "audio_spec_path": str(tmp_path / "missing.spec.pt"),
            }
        ),
        encoding="utf-8",
    )
    report = extract_f0.run(dataset, tmp_path / "f0", workers=1)
    assert report["n_ok"] == 0
    assert report["n_error"] == 1


# --------------------------------------------------------------------------
# 契約: 学習ターゲット生成であって評価メトリクスではない (§5.4)
# --------------------------------------------------------------------------


def test_module_declares_it_is_a_training_target_not_an_eval_metric():
    doc = extract_f0.__doc__ or ""
    assert "学習ターゲット" in doc
    assert "EVAL-ONLY" in doc
    # 評価側 (librosa.pyin) との推定器分離を明示していること
    assert "measure_prosody" in doc
    assert "pyin" in doc

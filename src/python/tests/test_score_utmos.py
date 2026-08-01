"""score_utmos.py の契約テスト。

- 出力 tsv が消費側 `export_common_voice_ko.load_utmos` でそのまま読めること
  (path\tutmos、ヘッダ付き)
- resume: 既存 output のスコア済み clip を skip すること
- --cv-dir モード: validated.tsv に載る tar member のみスコアすること

GPU / torch.hub には依存しない — predictor は fake を注入する。
"""

import io
import tarfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import torch

from piper_train.tools import score_utmos as su
from piper_train.tools.export_common_voice_ko import load_utmos


def _wav_bytes(sr: int = 16000, secs: float = 0.2) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.zeros(int(sr * secs), dtype=np.float32), sr, format="WAV")
    return buf.getvalue()


def _fake_predictor(wave, sr):
    assert wave.ndim == 2, "predictor は [1, T] を受ける契約"
    return torch.tensor([3.25])


@pytest.mark.unit
class TestScoreStream:
    def test_output_readable_by_consumer(self, tmp_path: Path):
        """出力 tsv が export_common_voice_ko.load_utmos で読めること。"""
        out = tmp_path / "utmos.tsv"
        audio = [("clip_a.mp3", _wav_bytes()), ("clip_b.mp3", _wav_bytes())]
        scored, failed = su.score_stream(
            iter(audio), _fake_predictor, "cpu", out, done=set()
        )
        assert (scored, failed) == (2, 0)

        parsed = load_utmos(out)
        assert parsed == {"clip_a.mp3": 3.25, "clip_b.mp3": 3.25}

    def test_resume_skips_done(self, tmp_path: Path):
        out = tmp_path / "utmos.tsv"
        su.score_stream(
            iter([("clip_a.mp3", _wav_bytes())]),
            _fake_predictor,
            "cpu",
            out,
            done=set(),
        )
        done = su.load_existing_scores(out)
        assert done == {"clip_a.mp3"}

        scored, failed = su.score_stream(
            iter([("clip_a.mp3", _wav_bytes()), ("clip_c.mp3", _wav_bytes())]),
            _fake_predictor,
            "cpu",
            out,
            done=done,
        )
        assert (scored, failed) == (1, 0)
        assert set(load_utmos(out)) == {"clip_a.mp3", "clip_c.mp3"}

    def test_decode_failure_is_skipped(self, tmp_path: Path):
        out = tmp_path / "utmos.tsv"
        audio = [("bad.mp3", b"not audio"), ("ok.mp3", _wav_bytes())]
        scored, failed = su.score_stream(
            iter(audio), _fake_predictor, "cpu", out, done=set()
        )
        assert (scored, failed) == (1, 1)
        assert set(load_utmos(out)) == {"ok.mp3"}


@pytest.mark.unit
class TestCvDirMode:
    def _make_cv_dir(self, root: Path) -> Path:
        cv = root / "cv22-ko"
        (cv / "transcript" / "ko").mkdir(parents=True)
        (cv / "transcript" / "ko" / "validated.tsv").write_text(
            "client_id\tpath\tsentence\n"
            "spk1\tclip_a.mp3\t안녕하세요\n"
            "spk2\tclip_b.mp3\t감사합니다\n",
            encoding="utf-8",
        )
        tar_dir = cv / "audio" / "ko" / "train"
        tar_dir.mkdir(parents=True)
        with tarfile.open(tar_dir / "ko_train_0.tar", "w") as tf:
            for name in ("clip_a.mp3", "clip_b.mp3", "clip_other.mp3"):
                data = _wav_bytes()
                info = tarfile.TarInfo(name=f"ko_train_0/{name}")
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return cv

    def test_only_validated_members_scored(self, tmp_path: Path):
        """validated.tsv に無い member (clip_other) はスコアされないこと。"""
        cv = self._make_cv_dir(tmp_path)
        wanted = su.load_validated_clips(cv, "ko")
        assert wanted == {"clip_a.mp3", "clip_b.mp3"}

        names = [name for name, _ in su.iter_cv_tar_audio(cv, "ko", wanted)]
        assert sorted(names) == ["clip_a.mp3", "clip_b.mp3"]

    def test_main_end_to_end(self, tmp_path: Path, monkeypatch):
        cv = self._make_cv_dir(tmp_path)
        out = tmp_path / "utmos.tsv"
        monkeypatch.setattr(su, "_load_predictor", lambda device: _fake_predictor)
        monkeypatch.setattr(
            "sys.argv",
            [
                "score_utmos",
                "--cv-dir",
                str(cv),
                "--output",
                str(out),
                "--device",
                "cpu",
            ],
        )
        su.main()
        assert load_utmos(out) == {"clip_a.mp3": 3.25, "clip_b.mp3": 3.25}

"""ProcessPool 並列版 ``prepare_moe_speech_plus`` の parity テスト。

`prepare_moe_speech_plus.py` の per-zip 展開 phase は 473 zip × ~800 utts
の CPU-bound loop (JSON parse + Levenshtein CER) が本命 hotspot。 2026-07-09
に `--parallel` を追加 (P3 で opt-in、 P5 で default ON 化 + chunksize 8)、
`Pool.imap` の input 順序 preserve 契約で serial parity を保つ設計とした。
本テストはその契約 (serial と並列で:

  1. metadata.csv が byte-for-byte 一致
  2. wavs/*.wav の内容が byte-for-byte 一致
  3. 統計 (kept_speakers, selected_utts) が一致

) を mock zip 3 個で pin する。 これが drift すると v8 学習の再現性
(571 → 3,250 話者スケーリング) が壊れる。
"""

from __future__ import annotations

import argparse
import io
import json
import multiprocessing as mp
import os
import sys
import wave
import zipfile
from pathlib import Path

import pytest

from piper_train.tools import prepare_moe_speech_plus as p


# ---------------------------------------------------------------------------
# Fixture: 決定論的な mock zip を組み立てる
# ---------------------------------------------------------------------------


def _make_wav_bytes(seed: int) -> bytes:
    """1 秒 16kHz mono PCM WAV を deterministic に生成 (numpy 依存回避)。"""
    sample_rate = 16000
    n = sample_rate  # 1 秒
    # seed で amplitude を変えて zip 間の wav 差を作る
    amp = 100 + (seed % 50)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        # 単純な整数繰り返し (seed でずらす) — sox/numpy に依存しない
        samples = bytearray()
        for i in range(n):
            v = ((i + seed) % 1024) - 512
            v = int(v * amp / 100)
            samples += int(v & 0xFFFF).to_bytes(2, "little", signed=False)
        wf.writeframes(bytes(samples))
    return buf.getvalue()


def _make_mock_zip(
    zip_path: Path,
    n_utts: int,
    speaker_seed: int,
    *,
    include_bad_cer_pct: float = 0.0,
    include_short_pct: float = 0.0,
) -> None:
    """1 キャラ分の mock zip を生成。

    各 utterance に:
      - `<stem>.wav` (1s, 16kHz mono)
      - `<stem>.json` (duration / speechMOS / anime_whisper_transcription
        / parakeet_jp_transcription)
    を含める。 include_* pct で reject 対象発話を混ぜて filter 動作も検証。
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for i in range(n_utts):
            stem = f"spk{speaker_seed:03d}_utt{i:04d}"
            # 一部を duration 短すぎで reject
            is_short = i < int(n_utts * include_short_pct)
            duration = 0.3 if is_short else (1.5 + (i % 5) * 0.5)
            # 一部を CER 高で reject (parakeet を意図的にズラす)
            is_bad_cer = not is_short and i < int(n_utts * include_short_pct) + int(
                n_utts * include_bad_cer_pct
            )
            text_aw = f"これはテスト発話{i}です"
            text_pk = "全く違う内容ですよ本当に" if is_bad_cer else text_aw
            meta = {
                "duration": duration,
                "speechMOS": 3.0 + (i % 10) * 0.1,
                "anime_whisper_transcription": text_aw,
                "parakeet_jp_transcription": text_pk,
            }
            zf.writestr(f"{stem}.json", json.dumps(meta, ensure_ascii=False))
            zf.writestr(f"{stem}.wav", _make_wav_bytes(speaker_seed * 1000 + i))


@pytest.fixture
def mock_dataset(tmp_path: Path) -> Path:
    """3 zip x 30 utts の mini moe-speech-plus dataset を生成する。"""
    in_dir = tmp_path / "input"
    in_dir.mkdir()
    # 3 キャラ、各 30 発話、5% short + 10% bad-cer で reject 経路も踏む
    for spk_idx in range(3):
        _make_mock_zip(
            in_dir / f"speaker_{spk_idx:03d}.zip",
            n_utts=30,
            speaker_seed=spk_idx,
            include_short_pct=0.05,
            include_bad_cer_pct=0.10,
        )
    return in_dir


def _run_extraction(
    input_dir: Path,
    output_dir: Path,
    *,
    parallel: bool,
    num_processes: int = 2,
) -> None:
    """`main()` を argv 経由で呼び出す。"""
    argv = [
        "prep",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
        "--min-mos",
        "0.0",
        "--max-cer",
        "0.15",
        "--min-dur",
        "1.0",
        "--max-dur",
        "15.0",
        "--min-utts",
        "5",
        "--cap",
        "20",
    ]
    # 2026-07-09 (P5): `--parallel` は default ON になったため、
    # serial 側は `--no-parallel` を明示する。 parallel 側は default に
    # 頼らず `--parallel` を明示することで CLI 契約 (BooleanOptionalAction)
    # 自体も同時に検証する。
    if parallel:
        argv += ["--parallel", "--num-processes", str(num_processes)]
    else:
        argv += ["--no-parallel"]
    old = sys.argv
    sys.argv = argv
    try:
        p.main()
    finally:
        sys.argv = old


# ---------------------------------------------------------------------------
# Parity テスト — serial vs parallel が byte-for-byte 一致すること
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSerialVsParallelParity:
    """`--parallel` opt-in の byte-for-byte 契約を pin する。"""

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason=(
            "Windows CI runner の spawn overhead が遅く flake しやすい"
            " (test_vad_parallel と同じ扱い)。 canonical coverage は"
            " Linux CI (dev-guard.yml) が担う"
        ),
    )
    def test_metadata_csv_identical(self, mock_dataset: Path, tmp_path: Path):
        out_serial = tmp_path / "out_serial"
        out_parallel = tmp_path / "out_parallel"

        _run_extraction(mock_dataset, out_serial, parallel=False)
        _run_extraction(mock_dataset, out_parallel, parallel=True, num_processes=2)

        meta_s = (out_serial / "metadata.csv").read_bytes()
        meta_p = (out_parallel / "metadata.csv").read_bytes()
        # imap(chunksize=1) で input 順序 preserve → byte-for-byte 一致必須
        assert meta_s == meta_p, (
            "metadata.csv drift between serial and parallel:\n"
            f"  serial ({len(meta_s)}B): {meta_s[:200]!r}...\n"
            f"  parallel ({len(meta_p)}B): {meta_p[:200]!r}..."
        )

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason="Same as test_metadata_csv_identical",
    )
    def test_wav_files_identical(self, mock_dataset: Path, tmp_path: Path):
        out_serial = tmp_path / "out_serial"
        out_parallel = tmp_path / "out_parallel"

        _run_extraction(mock_dataset, out_serial, parallel=False)
        _run_extraction(mock_dataset, out_parallel, parallel=True, num_processes=2)

        wavs_s = sorted(p_.name for p_ in (out_serial / "wavs").glob("*.wav"))
        wavs_p = sorted(p_.name for p_ in (out_parallel / "wavs").glob("*.wav"))
        assert wavs_s == wavs_p, f"wav filename set drift: {wavs_s} vs {wavs_p}"
        assert len(wavs_s) > 0, "sanity check: at least one wav should be extracted"

        for name in wavs_s:
            b_serial = (out_serial / "wavs" / name).read_bytes()
            b_parallel = (out_parallel / "wavs" / name).read_bytes()
            assert b_serial == b_parallel, (
                f"wav byte drift in {name}: len {len(b_serial)} vs {len(b_parallel)}"
            )

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason="Same as test_metadata_csv_identical",
    )
    def test_selected_utts_count_matches(self, mock_dataset: Path, tmp_path: Path):
        """metadata.csv の行数 (= selected_utts) が両パスで一致すること。"""
        out_serial = tmp_path / "out_serial"
        out_parallel = tmp_path / "out_parallel"

        _run_extraction(mock_dataset, out_serial, parallel=False)
        _run_extraction(mock_dataset, out_parallel, parallel=True, num_processes=2)

        n_serial = sum(
            1
            for line in (out_serial / "metadata.csv")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        n_parallel = sum(
            1
            for line in (out_parallel / "metadata.csv")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        assert n_serial == n_parallel
        assert n_serial > 0, "sanity check: expect at least one selected utterance"


# ---------------------------------------------------------------------------
# 単体テスト — worker 関数を直接呼んで shape 契約を pin
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessZipWorker:
    """`_process_zip_worker` の返り値 shape が Pool.imap 集約契約を満たすこと。"""

    def test_worker_returns_stem_rows_stats_triple(
        self, mock_dataset: Path, tmp_path: Path
    ):
        wav_dir = tmp_path / "wavs"
        wav_dir.mkdir()
        zip_path = next(mock_dataset.glob("*.zip"))
        filter_kwargs = {
            "min_dur": 1.0,
            "max_dur": 15.0,
            "min_mos": 0.0,
            "max_cer": 0.15,
            "min_utts": 5,
            "cap": 20,
        }
        result = p._process_zip_worker((zip_path, str(wav_dir), filter_kwargs))
        assert isinstance(result, tuple) and len(result) == 3
        zip_stem, rows, stats = result
        assert zip_stem == zip_path.stem
        assert isinstance(rows, list)
        # rows は (stem, speaker, text) triple
        for row in rows:
            assert len(row) == 3
            assert row[1] == zip_stem  # speaker == zip stem
        # 統計は少なくとも "total" を含む
        assert stats["total"] > 0
        # wav が書き出されている
        assert len(list(wav_dir.glob("*.wav"))) == len(rows)

    def test_worker_speaker_below_min_utts_returns_empty(self, tmp_path: Path):
        """min_utts に満たない話者は rows=[] で返る (話者除外契約)。"""
        in_dir = tmp_path / "input"
        in_dir.mkdir()
        # 3 発話しかない zip
        _make_mock_zip(in_dir / "tiny.zip", n_utts=3, speaker_seed=99)

        wav_dir = tmp_path / "wavs"
        wav_dir.mkdir()
        filter_kwargs = {
            "min_dur": 1.0,
            "max_dur": 15.0,
            "min_mos": 0.0,
            "max_cer": 0.15,
            "min_utts": 20,  # 3 発話 < 20 → 除外
            "cap": 120,
        }
        _zip_stem, rows, stats = p._process_zip_worker(
            (in_dir / "tiny.zip", str(wav_dir), filter_kwargs)
        )
        assert rows == []
        assert stats.get("speaker_rejected") == 1
        # wav も書き出されないこと (rows 空なので extract_speaker が呼ばれない)
        assert list(wav_dir.glob("*.wav")) == []


@pytest.mark.unit
class TestFilterKwargsExtraction:
    """`_filter_kwargs_from_args` が worker 用 primitive dict を返すこと。"""

    def test_extracts_only_filter_fields(self):
        args = argparse.Namespace(
            min_dur=1.0,
            max_dur=15.0,
            min_mos=0.0,
            max_cer=0.15,
            min_utts=20,
            cap=120,
            # 以下は worker に送るべきでない属性
            input_dir=Path("/tmp/in"),
            output_dir=Path("/tmp/out"),
            parallel=True,
            num_processes=4,
            stats_only=False,
            limit_speakers=0,
        )
        kwargs = p._filter_kwargs_from_args(args)
        assert set(kwargs.keys()) == {
            "min_dur",
            "max_dur",
            "min_mos",
            "max_cer",
            "min_utts",
            "cap",
        }
        assert kwargs["cap"] == 120


@pytest.mark.unit
class TestDefaultNumProcesses:
    def test_default_bounded_1_to_32(self):
        n = p._default_num_processes()
        assert 1 <= n <= 32


@pytest.mark.unit
class TestParallelDefaultOn:
    """`--parallel` の default が ON、 `--no-parallel` で opt-out できること。

    2026-07-09 (P5) で default OFF → ON に変更。 v8 データ選抜 (30-45min →
    3-5min) の高速化を default で受けられるようにする契約変更のため、
    ここで pin する。 CI / 小さい dataset での opt-out 経路も同時に検証。

    実装: `argparse.ArgumentParser.parse_args` を spy して `--parallel` の
    ns.parallel を捕捉、 main() は `--stats-only` を渡して I/O を最小化。
    """

    def test_default_is_parallel_on(self, tmp_path: Path, monkeypatch):
        """argv に `--parallel` / `--no-parallel` を渡さないときは並列 ON。"""
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        # zip を 1 個作って main() を通す。 --stats-only で終わらせて I/O 最小化。
        _make_mock_zip(input_dir / "spk000.zip", n_utts=3, speaker_seed=0)

        captured: dict = {}

        real_parse = argparse.ArgumentParser.parse_args

        def spy_parse(self, *a, **kw):
            ns = real_parse(self, *a, **kw)
            captured["parallel"] = ns.parallel
            return ns

        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", spy_parse)
        argv = [
            "prep",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--stats-only",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        p.main()
        assert captured["parallel"] is True, (
            "P5 契約: `--parallel` の argparse default は True でなければならない "
            "(v8 dataset prep 高速化の主軸)"
        )

    def test_no_parallel_flag_opts_out(self, tmp_path: Path, monkeypatch):
        """`--no-parallel` を渡すと BooleanOptionalAction で False になる。"""
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        _make_mock_zip(input_dir / "spk000.zip", n_utts=3, speaker_seed=0)

        captured: dict = {}
        real_parse = argparse.ArgumentParser.parse_args

        def spy_parse(self, *a, **kw):
            ns = real_parse(self, *a, **kw)
            captured["parallel"] = ns.parallel
            return ns

        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", spy_parse)
        argv = [
            "prep",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--stats-only",
            "--no-parallel",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        p.main()
        assert captured["parallel"] is False, (
            "`--no-parallel` は BooleanOptionalAction で False にならなければならない"
        )


# ---------------------------------------------------------------------------
# Pool 経由の byte-for-byte 実 dispatch (spawn context)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPoolImapDispatch:
    """実際に Pool.imap で dispatch した結果が serial worker 呼び出しと一致すること。"""

    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("CI") == "true",
        reason=(
            "Windows CI runner spawn overhead が遅く flake しやすい"
            " (test_vad_parallel と同じ扱い)。 Linux CI で cover。"
        ),
    )
    def test_pool_imap_matches_serial_worker(self, mock_dataset: Path, tmp_path: Path):
        wav_serial_dir = tmp_path / "wavs_serial"
        wav_parallel_dir = tmp_path / "wavs_parallel"
        wav_serial_dir.mkdir()
        wav_parallel_dir.mkdir()

        filter_kwargs = {
            "min_dur": 1.0,
            "max_dur": 15.0,
            "min_mos": 0.0,
            "max_cer": 0.15,
            "min_utts": 5,
            "cap": 20,
        }
        zip_paths = sorted(mock_dataset.glob("*.zip"))

        # Serial 経由
        serial_jobs = [(zp, str(wav_serial_dir), filter_kwargs) for zp in zip_paths]
        serial_results = [p._process_zip_worker(j) for j in serial_jobs]

        # Pool.imap 経由 (chunksize=1 で順序 preserve)
        ctx = mp.get_context("spawn")
        parallel_jobs = [(zp, str(wav_parallel_dir), filter_kwargs) for zp in zip_paths]
        with ctx.Pool(processes=2) as pool:
            parallel_results = list(
                pool.imap(p._process_zip_worker, parallel_jobs, chunksize=1)
            )

        assert len(serial_results) == len(parallel_results)
        for (stem_s, rows_s, stats_s), (stem_p, rows_p, stats_p) in zip(
            serial_results, parallel_results, strict=True
        ):
            assert stem_s == stem_p
            assert rows_s == rows_p, (
                f"row drift for {stem_s}: serial={rows_s[:2]} parallel={rows_p[:2]}"
            )
            assert dict(stats_s) == dict(stats_p)

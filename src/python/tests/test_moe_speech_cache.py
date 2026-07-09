"""per-zip scan cache テスト (2026-07-09 追加、 v8 dataset prep 再実行短縮)。

`prepare_moe_speech_plus.py` の 473 zip × ~800 utts 走査は本来 3-4 時間かかる
CPU-bound loop (JSON parse + Levenshtein CER)。 実運用では `--min-mos` /
`--max-cer` / `--cap` 等のしきい値を試行錯誤するため、 stateless 再実行では
毎回 全 zip を再走査していた。

per-zip cache (`{output-dir}/_scan_cache/{zip_stem}.jsonl`) を導入し、
pre-filter 生 metadata を JSONL に落として 2 回目以降を数分に短縮する。
本テストは以下 3 パターンを pin する:

  1. cache miss → JSONL が生成される (verifier + record 列)
  2. cache hit → `scan_zip_records` が呼ばれない (monkeypatch で検出)
  3. cache invalidation → zip の mtime / size 変化で自動再走査

かつ:

  * `--clear-scan-cache` で cache dir が wipe される
  * `--no-scan-cache` で cache が完全に無効
  * cache 経由と cache 無効の main() 実行が同一 metadata.csv を生成する
    (byte-for-byte、 filter パラメータ変更による再実行でも同等)
"""

from __future__ import annotations

import io
import json
import os
import sys
import wave
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from piper_train.tools import prepare_moe_speech_plus as p


# ---------------------------------------------------------------------------
# Fixture: 決定論的な mini mock zip (test_moe_speech_parallel と同型)
# ---------------------------------------------------------------------------


def _make_wav_bytes(seed: int) -> bytes:
    sample_rate = 16000
    n = sample_rate
    amp = 100 + (seed % 50)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        samples = bytearray()
        for i in range(n):
            v = ((i + seed) % 1024) - 512
            v = int(v * amp / 100)
            samples += int(v & 0xFFFF).to_bytes(2, "little", signed=False)
        wf.writeframes(bytes(samples))
    return buf.getvalue()


def _make_mock_zip(zip_path: Path, n_utts: int, speaker_seed: int) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for i in range(n_utts):
            stem = f"spk{speaker_seed:03d}_utt{i:04d}"
            duration = 1.5 + (i % 5) * 0.5
            text_aw = f"これはテスト発話{i}です"
            meta = {
                "duration": duration,
                "speechMOS": 3.0 + (i % 10) * 0.1,
                "anime_whisper_transcription": text_aw,
                "parakeet_jp_transcription": text_aw,  # CER = 0
            }
            zf.writestr(f"{stem}.json", json.dumps(meta, ensure_ascii=False))
            zf.writestr(f"{stem}.wav", _make_wav_bytes(speaker_seed * 1000 + i))


@pytest.fixture
def one_zip(tmp_path: Path) -> Path:
    zp = tmp_path / "speaker_000.zip"
    _make_mock_zip(zp, n_utts=25, speaker_seed=0)
    return zp


@pytest.fixture
def mini_dataset(tmp_path: Path) -> Path:
    in_dir = tmp_path / "input"
    in_dir.mkdir()
    for spk_idx in range(3):
        _make_mock_zip(
            in_dir / f"speaker_{spk_idx:03d}.zip", n_utts=25, speaker_seed=spk_idx
        )
    return in_dir


def _default_args() -> SimpleNamespace:
    return SimpleNamespace(
        min_dur=1.0,
        max_dur=15.0,
        min_mos=0.0,
        max_cer=0.15,
        min_utts=5,
        cap=20,
    )


# ---------------------------------------------------------------------------
# cache miss / hit / invalidation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanCacheMissAndHit:
    """`_load_or_scan_zip` の cache 動作契約を pin する。"""

    def test_cache_miss_writes_jsonl(self, one_zip: Path, tmp_path: Path):
        """1 回目実行で {cache_dir}/{stem}.jsonl が生成されること。"""
        cache_dir = tmp_path / "_scan_cache"
        records = p._load_or_scan_zip(one_zip, cache_dir)

        cache_file = cache_dir / f"{one_zip.stem}.jsonl"
        assert cache_file.exists(), "cache miss で JSONL が生成されていない"
        assert len(records) == 25

        # header line = verifier
        with open(cache_file, encoding="utf-8") as f:
            header = json.loads(f.readline())
        assert header["cache_version"] == p._CACHE_VERSION
        assert header["zip_stem"] == one_zip.stem
        assert header["zip_size"] == one_zip.stat().st_size
        assert header["zip_mtime_ns"] == one_zip.stat().st_mtime_ns

        # データ行数 (header 除く) = record 数
        lines = cache_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1 + 25

    def test_cache_hit_skips_scan(self, one_zip: Path, tmp_path: Path, monkeypatch):
        """cache hit 時に `scan_zip_records` が呼ばれないこと。"""
        cache_dir = tmp_path / "_scan_cache"
        # 1 回目: cache に書き込ませる
        records_first = p._load_or_scan_zip(one_zip, cache_dir)

        # scan_zip_records を trip-wire に置き換え
        def _tripwire(_):
            raise AssertionError("cache hit のはずが scan_zip_records が再度呼ばれた")

        monkeypatch.setattr(p, "scan_zip_records", _tripwire)

        # 2 回目: cache から復元する経路のみ通れば例外は出ない
        records_second = p._load_or_scan_zip(one_zip, cache_dir)

        assert records_second == records_first, "cache 復元で record 内容が drift"
        assert len(records_second) == 25

    def test_cache_hit_produces_identical_filter_result(
        self, one_zip: Path, tmp_path: Path
    ):
        """cache 有効 / 無効 で `select_utterances` が同一 (selected, stats) を返すこと。"""
        cache_dir = tmp_path / "_scan_cache"
        args = _default_args()

        # cold cache (miss + write)
        selected_cold, stats_cold = p.select_utterances(
            one_zip, args, cache_dir=cache_dir
        )
        # warm cache (hit)
        selected_warm, stats_warm = p.select_utterances(
            one_zip, args, cache_dir=cache_dir
        )
        # no cache
        selected_none, stats_none = p.select_utterances(one_zip, args, cache_dir=None)

        assert selected_cold == selected_warm == selected_none
        assert dict(stats_cold) == dict(stats_warm) == dict(stats_none)


@pytest.mark.unit
class TestScanCacheInvalidation:
    """(zip_size, zip_mtime_ns) の差分で cache が自動 invalidate すること。"""

    def test_invalidation_on_zip_size_change(self, one_zip: Path, tmp_path: Path):
        """zip を差し替えて size が変わったら cache が rebuild されること。"""
        cache_dir = tmp_path / "_scan_cache"
        p._load_or_scan_zip(one_zip, cache_dir)
        cache_file = cache_dir / f"{one_zip.stem}.jsonl"
        original_size = cache_file.stat().st_size

        # zip 差し替え: utterance 数を変えて size を変える
        _make_mock_zip(one_zip, n_utts=10, speaker_seed=0)
        assert (
            one_zip.stat().st_size
            != json.loads(cache_file.read_text(encoding="utf-8").splitlines()[0])[
                "zip_size"
            ]
        ), "sanity: zip size が変わったこと"

        records = p._load_or_scan_zip(one_zip, cache_dir)
        assert len(records) == 10, "invalidate 後 rebuild で新 record 数を反映"

        # cache 自体は rebuild されている (utterance 数が減って size も減る想定)
        new_size = cache_file.stat().st_size
        assert new_size < original_size, (
            f"rebuild 後の cache は元より小さいはず: {new_size} vs {original_size}"
        )

        # header verifier が最新 zip と一致するようになった
        with open(cache_file, encoding="utf-8") as f:
            new_header = json.loads(f.readline())
        assert new_header["zip_size"] == one_zip.stat().st_size

    def test_invalidation_on_zip_mtime_change(
        self, one_zip: Path, tmp_path: Path, monkeypatch
    ):
        """zip の size は同じで mtime だけずれても cache が rebuild されること。"""
        cache_dir = tmp_path / "_scan_cache"
        p._load_or_scan_zip(one_zip, cache_dir)
        cache_file = cache_dir / f"{one_zip.stem}.jsonl"

        # mtime を強制的にずらす (size は不変)
        original_size = one_zip.stat().st_size
        new_mtime_ns = one_zip.stat().st_mtime_ns + 1_000_000_000  # +1s
        os.utime(one_zip, ns=(new_mtime_ns, new_mtime_ns))
        assert one_zip.stat().st_size == original_size

        # 監視用 tripwire: scan_zip_records が呼ばれたら記録
        calls = {"n": 0}
        original_scan = p.scan_zip_records

        def _counting_scan(zp):
            calls["n"] += 1
            return original_scan(zp)

        monkeypatch.setattr(p, "scan_zip_records", _counting_scan)

        p._load_or_scan_zip(one_zip, cache_dir)
        assert calls["n"] == 1, "mtime drift で scan_zip_records が再度呼ばれるべき"

        # 新 header に更新 mtime が反映
        with open(cache_file, encoding="utf-8") as f:
            new_header = json.loads(f.readline())
        assert new_header["zip_mtime_ns"] == new_mtime_ns

    def test_force_rescan_bypasses_cache(
        self, one_zip: Path, tmp_path: Path, monkeypatch
    ):
        """force_rescan=True で cache 有効時でも rebuild を強制すること。"""
        cache_dir = tmp_path / "_scan_cache"
        p._load_or_scan_zip(one_zip, cache_dir)  # 初回書込

        calls = {"n": 0}
        original_scan = p.scan_zip_records

        def _counting_scan(zp):
            calls["n"] += 1
            return original_scan(zp)

        monkeypatch.setattr(p, "scan_zip_records", _counting_scan)

        p._load_or_scan_zip(one_zip, cache_dir, force_rescan=True)
        assert calls["n"] == 1, "force_rescan=True で scan_zip_records が呼ばれるべき"

    def test_corrupt_cache_falls_back_to_rescan(self, one_zip: Path, tmp_path: Path):
        """cache JSONL が壊れていたら warning + rescan で正常復帰すること。"""
        cache_dir = tmp_path / "_scan_cache"
        cache_dir.mkdir()
        cache_file = cache_dir / f"{one_zip.stem}.jsonl"
        cache_file.write_text("this is not json\n", encoding="utf-8")

        records = p._load_or_scan_zip(one_zip, cache_dir)
        assert len(records) == 25, "壊れた cache から rescan で正常復帰"
        # cache も rebuild されている
        with open(cache_file, encoding="utf-8") as f:
            header = json.loads(f.readline())
        assert header["cache_version"] == p._CACHE_VERSION


# ---------------------------------------------------------------------------
# main() end-to-end: byte-for-byte parity (cache 経由 vs cache 無効)
# ---------------------------------------------------------------------------


def _run_main(input_dir: Path, output_dir: Path, extra_argv: list[str]) -> None:
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
    ] + extra_argv
    old = sys.argv
    sys.argv = argv
    try:
        p.main()
    finally:
        sys.argv = old


@pytest.mark.unit
class TestMainCacheParity:
    """cache 有効 / 無効 で main() が同一 metadata.csv + wavs を吐くこと。"""

    def test_cached_run_matches_no_cache_run(self, mini_dataset: Path, tmp_path: Path):
        """cache 有効経路 (default) と `--no-scan-cache` が byte-for-byte 一致。"""
        out_cached = tmp_path / "out_cached"
        out_nocache = tmp_path / "out_nocache"

        _run_main(mini_dataset, out_cached, [])
        _run_main(mini_dataset, out_nocache, ["--no-scan-cache"])

        meta_c = (out_cached / "metadata.csv").read_bytes()
        meta_n = (out_nocache / "metadata.csv").read_bytes()
        assert meta_c == meta_n, "cache 経由と cache 無効で metadata.csv が drift"

        # cache 有効経路では _scan_cache/ が生成されている
        assert (out_cached / "_scan_cache").is_dir()
        assert not (out_nocache / "_scan_cache").exists()

        # wav 集合も一致
        wavs_c = sorted(x.name for x in (out_cached / "wavs").glob("*.wav"))
        wavs_n = sorted(x.name for x in (out_nocache / "wavs").glob("*.wav"))
        assert wavs_c == wavs_n
        assert len(wavs_c) > 0

    def test_rerun_uses_cache(self, mini_dataset: Path, tmp_path: Path, monkeypatch):
        """1 回目実行 → cache に書込 → 2 回目実行 で scan_zip_records が呼ばれない。"""
        out_dir = tmp_path / "out"
        _run_main(mini_dataset, out_dir, [])

        # cache が 3 zip 分あること
        cache_files = sorted((out_dir / "_scan_cache").glob("*.jsonl"))
        assert len(cache_files) == 3

        # 2 回目: scan_zip_records は 1 度も呼ばれるべきでない
        original_scan = p.scan_zip_records

        def _tripwire(zp):
            raise AssertionError(
                f"cache hit 期待だが scan_zip_records({zp.name}) が呼ばれた"
            )

        monkeypatch.setattr(p, "scan_zip_records", _tripwire)

        # rerun (output dir は同じ、 cache は既存)
        _run_main(mini_dataset, out_dir, [])
        # trip しなければテスト成功
        monkeypatch.setattr(p, "scan_zip_records", original_scan)

    def test_clear_scan_cache_wipes_and_rebuilds(
        self, mini_dataset: Path, tmp_path: Path, monkeypatch
    ):
        """`--clear-scan-cache` で既存 cache が wipe され、 rescan が走ること。"""
        out_dir = tmp_path / "out"
        _run_main(mini_dataset, out_dir, [])
        cache_dir = out_dir / "_scan_cache"
        assert len(list(cache_dir.glob("*.jsonl"))) == 3

        # scan 呼び出しを数える
        calls = {"n": 0}
        original_scan = p.scan_zip_records

        def _counting_scan(zp):
            calls["n"] += 1
            return original_scan(zp)

        monkeypatch.setattr(p, "scan_zip_records", _counting_scan)

        _run_main(mini_dataset, out_dir, ["--clear-scan-cache"])
        assert calls["n"] == 3, "--clear-scan-cache で 3 zip すべて再走査"
        # cache は rebuild されている
        assert len(list(cache_dir.glob("*.jsonl"))) == 3

    def test_filter_change_reuses_cache(
        self, mini_dataset: Path, tmp_path: Path, monkeypatch
    ):
        """しきい値 (--min-mos / --cap) 変更でも cache が有効利用されること。

        これが本 skill の主目的 — 3-4h → 5min の実運用短縮。 filter は cache
        の record 上で replay するだけなので、 scan_zip_records は呼ばれない。
        """
        out_dir = tmp_path / "out"
        # 1 回目: min-mos 3.0 (default 相当は 0.0)
        _run_main(mini_dataset, out_dir, ["--cap", "15"])

        # 2 回目: --cap を変えて再実行 — cache は再利用可
        original_scan = p.scan_zip_records

        def _tripwire(zp):
            raise AssertionError(
                f"filter パラメータ変更後の rerun で scan_zip_records({zp.name}) が呼ばれた"
            )

        monkeypatch.setattr(p, "scan_zip_records", _tripwire)

        # NOTE: metadata.csv は上書きされる (append ではなく open("w") のため)
        # ここでは filter 変更で main() が正常完了することのみ確認
        _run_main(mini_dataset, out_dir, ["--cap", "10"])
        monkeypatch.setattr(p, "scan_zip_records", original_scan)


# ---------------------------------------------------------------------------
# helper: verifier / cache 書込の primitive 単体
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCacheVerifierPrimitives:
    def test_verifier_contains_required_keys(self, one_zip: Path):
        verifier = p._cache_verifier(one_zip)
        assert set(verifier.keys()) == {
            "cache_version",
            "zip_stem",
            "zip_size",
            "zip_mtime_ns",
        }
        assert verifier["cache_version"] == p._CACHE_VERSION
        assert verifier["zip_stem"] == one_zip.stem
        assert verifier["zip_size"] == one_zip.stat().st_size

    def test_scan_zip_records_shape(self, one_zip: Path):
        records = p.scan_zip_records(one_zip)
        assert len(records) == 25
        for rec in records:
            assert set(rec.keys()) == {
                "stem",
                "wav_name",
                "dur",
                "mos",
                "text_aw",
                "cer",
            }
            assert isinstance(rec["stem"], str)
            assert rec["wav_name"].endswith(".wav")
            assert 1.0 <= rec["dur"] <= 15.0
            assert 0.0 <= rec["mos"] <= 5.0
            assert rec["cer"] == pytest.approx(0.0)  # text_aw == text_pk

    def test_select_from_records_matches_zip_path(self, one_zip: Path):
        """`select_utterances_from_records` と cache 経由 `select_utterances` が一致。"""
        args = _default_args()
        records = p.scan_zip_records(one_zip)
        sel_a, stats_a = p.select_utterances_from_records(records, args)
        sel_b, stats_b = p.select_utterances(one_zip, args, cache_dir=None)
        assert sel_a == sel_b
        assert dict(stats_a) == dict(stats_b)

"""FLAC 直保存 (parquet の audio.bytes を write_bytes() で `.flac` として出力)
経路の regression guard。

v8 前処理 5-11h 目標に対して、 従来の parquet export は:

  1. `sf.read(BytesIO(FLAC bytes))` で decode (encode 済み FLAC → PCM)
  2. `sf.write(<...>.wav, pcm)` で WAV に encode
  3. downstream の norm_audio が再度 `sf.read(<...>.wav)` で decode

と decode/encode を 3 回踏んでいた。 audio.bytes が既に FLAC ならその bytes を
`write_bytes(<...>.flac)` でそのまま書き出せば (1) (2) の 2 段を丸ごと省略
できる。 downstream は soundfile が FLAC/WAV 透過対応なので変更不要。

期待 impact: LibriTTS-R export 30-60min → 5-10min (docs/design/zero-shot-v8-
dataset-scaling-plan.md §2 / handoff)。

本テストは以下 6 契約を pin する:

  1. FLAC magic 判定 (`fLaC` = 0x66 0x4C 0x61 0x43) が bytes[:4] のみで動作
  2. libritts_r export (flac mode): raw FLAC bytes が byte-for-byte 保存される
     (sf.read → sf.write の double roundtrip を経ない)
  3. libritts_r export (flac mode): metadata.csv が `utt_id.flac` を record
  4. libritts_r export (wav mode / backward compat): 既存挙動を保つ
  5. cml_tts export (flac mode): write_audio が FLAC bytes を zero-copy 保存し
     WAV bytes は FLAC に再 encode する
  6. downstream `prepare_bilingual_dataset` の path resolution が `.wav` と
     `.flac` の両拡張子で動く

sf.write の compressed encoding は libsndfile の internal state に依存して
非決定的なので、 flac 直保存経路のみが byte-for-byte 保証を担う (この test
の存在意義)。
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest


pytest.importorskip("soundfile")
pytest.importorskip("pyarrow")

import soundfile as sf  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: build a real (short) FLAC bytes blob without touching HF parquet.
# ---------------------------------------------------------------------------


def _make_flac_bytes(seed: int = 0, seconds: float = 2.0, sr: int = 16000) -> bytes:
    """soundfile で FLAC を in-memory 生成 する。 sr=16kHz mono、 短い正弦波様。

    再現性のため decode → 元 bytes の byte-for-byte 一致は保証しないが、
    magic (`fLaC`) と duration の contract は満たす。
    """
    import numpy as np  # local import to avoid module-level dep

    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    # 小振幅ホワイトノイズ (int16 相当の range)。
    data = (rng.standard_normal(n) * 0.05).astype("float32")
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="FLAC")
    return buf.getvalue()


def _make_wav_bytes(seed: int = 0, seconds: float = 2.0, sr: int = 16000) -> bytes:
    import numpy as np

    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    data = (rng.standard_normal(n) * 0.05).astype("float32")
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="WAV")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. FLAC magic 判定
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlacMagic:
    def test_flac_bytes_start_with_flac_magic(self):
        raw = _make_flac_bytes()
        assert raw[:4] == b"fLaC", (
            f"生成した FLAC bytes の magic が `fLaC` でない: {raw[:4]!r}"
        )

    def test_wav_bytes_do_not_start_with_flac_magic(self):
        raw = _make_wav_bytes()
        assert raw[:4] != b"fLaC"
        assert raw[:4] == b"RIFF", (
            f"生成した WAV bytes の magic が `RIFF` でない: {raw[:4]!r}"
        )


# ---------------------------------------------------------------------------
# 2/3/4. libritts_r export の flac / wav mode 挙動
# ---------------------------------------------------------------------------


def _build_libritts_batch(n_utts: int, spk: str = "1001") -> dict:
    """`ParquetFile.iter_batches(...).to_pydict()` が返す構造を最小限模す。"""
    utts = []
    for i in range(n_utts):
        utts.append(
            {
                "id": f"{spk}_ch{i:03d}",
                "speaker_id": spk,
                "text_normalized": f"sample text {i}",
                "audio_bytes": _make_flac_bytes(seed=i),
            }
        )
    return {
        "id": [u["id"] for u in utts],
        "speaker_id": [u["speaker_id"] for u in utts],
        "text_normalized": [u["text_normalized"] for u in utts],
        "audio": [{"bytes": u["audio_bytes"], "path": f"{u['id']}.flac"} for u in utts],
    }


class _FakeBatch:
    def __init__(self, cols: dict):
        self._cols = cols

    def to_pydict(self) -> dict:
        return self._cols


class _FakeParquetFile:
    def __init__(self, cols: dict):
        self._cols = cols

    def iter_batches(self, batch_size: int = 64, columns=None):  # noqa: D401
        if columns is not None:
            filtered = {k: v for k, v in self._cols.items() if k in columns}
            yield _FakeBatch(filtered)
        else:
            yield _FakeBatch(self._cols)


@pytest.mark.unit
class TestLibrittsRFlacDirect:
    """`export_libritts_r_from_parquet.pass2_export` の flac 直保存経路。"""

    def _call_pass2(
        self,
        tmp_path: Path,
        output_format: str,
        n_utts: int = 5,
    ) -> tuple[Path, list[Path], list[str]]:
        # 遅延 import で torch stack 依存を回避 (この module は pyarrow / soundfile
        # のみに依存する)。
        from piper_train.tools import export_libritts_r_from_parquet as mod

        cols = _build_libritts_batch(n_utts=n_utts)
        fake_pf = _FakeParquetFile(cols)

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        # argparse.Namespace 相当を組み立てる。
        class _Args:
            pass

        args = _Args()
        args.output_dir = output_dir
        args.max_utterances_per_speaker = 10
        args.min_utterances_per_speaker = 1
        args.min_dur = 0.5
        args.max_dur = 30.0
        args.output_format = output_format

        # pass1 は id / speaker のみ触るので実 impl で通す。 `pq.ParquetFile` を
        # モック化するために module 内 API を patch する。
        parquet_files = [tmp_path / "fake.parquet"]
        with patch.object(mod.pq, "ParquetFile", return_value=fake_pf):
            reserved = mod.pass1_reserve(parquet_files, cap=10, min_utts=1)
            n_speakers, n_utts_written = mod.pass2_export(parquet_files, reserved, args)

        wavs_dir = output_dir / "wavs"
        audio_files = sorted(wavs_dir.iterdir())
        with open(output_dir / "metadata.csv", encoding="utf-8") as f:
            meta_rows = [line.rstrip("\n") for line in f if line.strip()]
        assert n_utts_written == len(meta_rows) == len(audio_files) == n_utts
        assert n_speakers == 1
        return output_dir, audio_files, meta_rows

    def test_flac_mode_writes_flac_extension(self, tmp_path: Path):
        _out, audio_files, _meta = self._call_pass2(
            tmp_path, output_format="flac", n_utts=3
        )
        assert all(p.suffix == ".flac" for p in audio_files), (
            f"flac mode 出力の拡張子が .flac でない: {[p.name for p in audio_files]}"
        )

    def test_flac_mode_preserves_raw_bytes(self, tmp_path: Path):
        """FLAC 直保存 = decode/encode を経ずに raw bytes を byte-for-byte 書き出す。"""
        cols = _build_libritts_batch(n_utts=3)
        raw_by_id = {
            utt_id: raw["bytes"]
            for utt_id, raw in zip(cols["id"], cols["audio"], strict=False)
        }

        _out, audio_files, _meta = self._call_pass2(
            tmp_path, output_format="flac", n_utts=3
        )
        for p in audio_files:
            utt_id = p.stem
            assert utt_id in raw_by_id
            assert p.read_bytes() == raw_by_id[utt_id], (
                f"flac 直保存の byte-for-byte 契約破綻: {p.name} "
                f"(raw {len(raw_by_id[utt_id])}B / disk {p.stat().st_size}B)"
            )

    def test_flac_mode_metadata_contains_extension(self, tmp_path: Path):
        _out, _files, meta_rows = self._call_pass2(
            tmp_path, output_format="flac", n_utts=3
        )
        for row in meta_rows:
            filename = row.split("|", 1)[0]
            assert filename.endswith(".flac"), (
                f"metadata.csv の filename 列に .flac 拡張子が入っていない: {row!r}"
            )

    def test_wav_mode_metadata_contains_wav_extension(self, tmp_path: Path):
        """backward compat: wav モードでは .wav 拡張子で record される。"""
        _out, files, meta_rows = self._call_pass2(
            tmp_path, output_format="wav", n_utts=3
        )
        assert all(p.suffix == ".wav" for p in files)
        for row in meta_rows:
            filename = row.split("|", 1)[0]
            assert filename.endswith(".wav"), (
                f"metadata.csv の filename 列に .wav 拡張子が入っていない: {row!r}"
            )

    def test_flac_mode_roundtrip_via_soundfile(self, tmp_path: Path):
        """downstream 想定: 書き出した .flac を soundfile で decode でき、
        sample_rate/frame 数が元と一致する。"""
        _out, audio_files, _meta = self._call_pass2(
            tmp_path, output_format="flac", n_utts=2
        )
        for p in audio_files:
            data, sr = sf.read(str(p))
            assert sr == 16000
            # 生成時に seconds=2.0, sr=16000 で作成 → 32000 frame
            assert len(data) == 32000, (
                f"soundfile decode 後の frame 数が元と一致しない: {len(data)}"
            )


# ---------------------------------------------------------------------------
# 5. cml_tts export の write_audio 関数
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCmlTtsWriteAudio:
    def test_flac_mode_zero_copy_for_flac_bytes(self, tmp_path: Path):
        from piper_train.tools import export_cml_tts_from_parquet as mod

        raw = _make_flac_bytes()
        audio = {"bytes": raw, "path": "sample.flac"}
        written = mod.write_audio(audio, tmp_path, "sample", output_format="flac")
        assert written is not None
        dst_path, dst_size = written
        assert dst_path.suffix == ".flac"
        assert dst_path.read_bytes() == raw, (
            "cml_tts flac zero-copy 経路が byte-for-byte を保っていない"
        )
        assert dst_size == len(raw)

    def test_flac_mode_reencodes_wav_bytes_to_flac(self, tmp_path: Path):
        from piper_train.tools import export_cml_tts_from_parquet as mod

        wav_raw = _make_wav_bytes()
        audio = {"bytes": wav_raw, "path": "sample.wav"}
        written = mod.write_audio(audio, tmp_path, "sample", output_format="flac")
        assert written is not None
        dst_path, _dst_size = written
        assert dst_path.suffix == ".flac"
        # magic が fLaC (書き直された FLAC file)
        assert dst_path.read_bytes()[:4] == b"fLaC"

    def test_wav_mode_zero_copy_for_wav_bytes(self, tmp_path: Path):
        """backward compat: wav mode + WAV bytes は既存挙動と同じ zero-copy。"""
        from piper_train.tools import export_cml_tts_from_parquet as mod

        raw = _make_wav_bytes()
        audio = {"bytes": raw, "path": "sample.wav"}
        written = mod.write_audio(audio, tmp_path, "sample", output_format="wav")
        assert written is not None
        dst_path, dst_size = written
        assert dst_path.suffix == ".wav"
        assert dst_path.read_bytes() == raw
        assert dst_size == len(raw)

    def test_detect_container_priority(self):
        from piper_train.tools import export_cml_tts_from_parquet as mod

        # magic 優先: path が .flac でも先頭 4 byte が RIFF なら wav
        assert mod._detect_container(b"RIFF...WAVE", "sample.flac") == "wav"
        # magic なしで path 拡張子 fallback
        assert mod._detect_container(b"XXXXsomething", "sample.wav") == "wav"
        assert mod._detect_container(b"XXXXsomething", "sample.flac") == "flac"
        # どちらも該当なしなら other
        assert mod._detect_container(b"XXXXsomething", "sample.mp3") == "other"


# ---------------------------------------------------------------------------
# 6. downstream (prepare_bilingual_dataset) の path resolution が .flac を受理する
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBilingualPathResolution:
    """`prepare_bilingual_dataset.process_en_dataset` の wav 経路 resolve だけを
    静的検査する。 実 phonemization は torch/g2p が要るため invoked しない。"""

    def _get_source(self) -> str:
        # 巨大な torch import を避けるため生ソースを検査する。
        path = (
            Path(__file__).resolve().parents[2]
            / "python"
            / "piper_train"
            / "tools"
            / "prepare_bilingual_dataset.py"
        )
        return path.read_text(encoding="utf-8")

    def test_source_accepts_flac_suffix(self):
        src = self._get_source()
        # 拡張子 .flac を明示的に受け入れる分岐が入っていること
        assert '".wav", ".flac"' in src or "'.wav', '.flac'" in src, (
            "process_en_dataset の拡張子 tuple に .flac が入っていない — "
            "flac 直保存 metadata.csv を downstream が resolve できなくなる。"
        )
        # 拡張子なし fallback で `.flac` 候補も見に行くこと
        assert "flac_candidate" in src, (
            "`.flac` fallback candidate が消えている — 既存 metadata.csv "
            "(拡張子なし) と .flac 出力を共存させる backward compat が壊れる。"
        )

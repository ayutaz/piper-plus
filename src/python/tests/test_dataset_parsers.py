"""Unit tests for dataset metadata parsers in prepare_multilingual_dataset.

Each parser takes a directory or file path that points to real corpus
metadata (AISHELL-3 content.txt / CML-TTS train.csv / bilingual JSONL) and
returns structured tuples used by downstream phonemization. Drift in field
order, speaker-id derivation, or filename-mangling silently corrupts the
training corpus, so these tests pin the parsing contract against synthetic
fixtures written to ``tmp_path``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("torch")

from piper_train.tools.prepare_multilingual_dataset import (  # noqa: E402
    load_ja_en_dataset,
    parse_aishell3,
    parse_cml_tts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _make_existing_wav(directory: Path, name: str) -> Path:
    """Touch a placeholder WAV so ``Path.exists()`` returns True."""
    directory.mkdir(parents=True, exist_ok=True)
    wav = directory / name
    wav.write_bytes(b"")
    return wav


def _make_audio_caches(tmp_path: Path, stem: str) -> tuple[Path, Path]:
    """Create dummy norm/spec cache files referenced by JA+EN utterances."""
    norm = tmp_path / f"{stem}.norm.pt"
    spec = tmp_path / f"{stem}.spec.pt"
    norm.write_bytes(b"")
    spec.write_bytes(b"")
    return norm, spec


# ---------------------------------------------------------------------------
# load_ja_en_dataset (JA+EN bilingual JSONL)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadJaEnDataset:
    def test_minimal_record(self, tmp_path: Path) -> None:
        norm, spec = _make_audio_caches(tmp_path, "u1")
        rec = {
            "phoneme_ids": [1, 2, 3],
            "audio_norm_path": str(norm),
            "audio_spec_path": str(spec),
            "speaker": "spk_a",
            "speaker_id": 0,
            "language_id": 0,
        }
        jsonl = tmp_path / "dataset.jsonl"
        _make_jsonl(jsonl, [rec])

        utterances, speaker_id_map, max_id = load_ja_en_dataset(jsonl)

        assert len(utterances) == 1
        assert speaker_id_map == {"spk_a": 0}
        assert max_id == 0

    def test_skips_records_without_phoneme_ids(self, tmp_path: Path) -> None:
        norm, spec = _make_audio_caches(tmp_path, "u1")
        good = {
            "phoneme_ids": [1, 2],
            "audio_norm_path": str(norm),
            "audio_spec_path": str(spec),
            "speaker": "spk",
            "speaker_id": 0,
        }
        bad_empty = {**good, "phoneme_ids": []}
        bad_missing = {k: v for k, v in good.items() if k != "phoneme_ids"}
        jsonl = tmp_path / "dataset.jsonl"
        _make_jsonl(jsonl, [good, bad_empty, bad_missing])

        utterances, _, _ = load_ja_en_dataset(jsonl)

        assert len(utterances) == 1

    def test_skips_records_with_missing_audio_cache(self, tmp_path: Path) -> None:
        norm, _spec = _make_audio_caches(tmp_path, "u1")
        # spec_path points to a file that does not exist.
        rec = {
            "phoneme_ids": [1, 2, 3],
            "audio_norm_path": str(norm),
            "audio_spec_path": str(tmp_path / "ghost.spec.pt"),
            "speaker": "spk",
            "speaker_id": 0,
        }
        jsonl = tmp_path / "dataset.jsonl"
        _make_jsonl(jsonl, [rec])

        utterances, _, _ = load_ja_en_dataset(jsonl)

        assert utterances == []

    def test_skips_invalid_json_lines(self, tmp_path: Path) -> None:
        norm, spec = _make_audio_caches(tmp_path, "u1")
        good = {
            "phoneme_ids": [1, 2],
            "audio_norm_path": str(norm),
            "audio_spec_path": str(spec),
            "speaker": "spk",
            "speaker_id": 0,
        }
        jsonl = tmp_path / "dataset.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(good) + "\n")
            f.write("{ this is not valid json\n")
            f.write("\n")  # blank line

        utterances, _, _ = load_ja_en_dataset(jsonl)

        assert len(utterances) == 1

    def test_max_speaker_id_tracks_highest_value(self, tmp_path: Path) -> None:
        utterances = []
        for speaker_id in [0, 7, 3]:
            norm, spec = _make_audio_caches(tmp_path, f"u_{speaker_id}")
            utterances.append(
                {
                    "phoneme_ids": [1],
                    "audio_norm_path": str(norm),
                    "audio_spec_path": str(spec),
                    "speaker": f"spk_{speaker_id}",
                    "speaker_id": speaker_id,
                }
            )
        jsonl = tmp_path / "dataset.jsonl"
        _make_jsonl(jsonl, utterances)

        loaded, speaker_id_map, max_id = load_ja_en_dataset(jsonl)

        assert len(loaded) == 3
        assert max_id == 7
        assert speaker_id_map == {"spk_0": 0, "spk_7": 7, "spk_3": 3}

    def test_unicode_speaker_and_text_pass_through(self, tmp_path: Path) -> None:
        norm, spec = _make_audio_caches(tmp_path, "u_utf8")
        rec = {
            "phoneme_ids": [9],
            "audio_norm_path": str(norm),
            "audio_spec_path": str(spec),
            "speaker": "つくよみちゃん",
            "speaker_id": 42,
            "text": "こんにちは",
        }
        jsonl = tmp_path / "dataset.jsonl"
        _make_jsonl(jsonl, [rec])

        utterances, speaker_id_map, max_id = load_ja_en_dataset(jsonl)

        assert utterances[0]["speaker"] == "つくよみちゃん"
        assert speaker_id_map == {"つくよみちゃん": 42}
        assert max_id == 42


# ---------------------------------------------------------------------------
# parse_aishell3 (Mandarin AISHELL-3)
# ---------------------------------------------------------------------------


def _write_aishell3_corpus(
    base: Path,
    rows: list[tuple[str, str]],
    *,
    create_wavs: bool = True,
) -> None:
    """Build an AISHELL-3-shaped tree under *base*.

    Each row is (filename, "char1 pinyin1 char2 pinyin2 ...").  When
    ``create_wavs=True`` the wav file is touched so that ``Path.exists()``
    returns True for it.
    """
    train = base / "train"
    train.mkdir(parents=True, exist_ok=True)
    content_lines: list[str] = []
    for filename, body in rows:
        content_lines.append(f"{filename}\t{body}")
        if create_wavs:
            speaker_dir = train / "wav" / filename[:7]
            _make_existing_wav(speaker_dir, filename)
    (train / "content.txt").write_text(
        "\n".join(content_lines) + "\n", encoding="utf-8"
    )


@pytest.mark.unit
class TestParseAishell3:
    def test_minimal_two_speakers(self, tmp_path: Path) -> None:
        _write_aishell3_corpus(
            tmp_path,
            [
                ("SSB00050001.wav", "广 guang3 州 zhou1"),
                ("SSB00050002.wav", "你 ni3 好 hao3"),
                ("SSB00120001.wav", "再 zai4 见 jian4"),
            ],
        )

        entries, speaker_counts = parse_aishell3(tmp_path)

        assert len(entries) == 3
        text, wav_path, speaker, pinyin = entries[0]
        assert text == "广州"
        assert pinyin == ["guang3", "zhou1"]
        assert speaker == "SSB0005"
        assert wav_path.endswith("SSB00050001.wav")  # filename only, no separator
        assert speaker_counts == {"SSB0005": 2, "SSB0012": 1}

    def test_returns_empty_when_content_txt_missing(self, tmp_path: Path) -> None:
        # No train/content.txt at all.
        entries, speaker_counts = parse_aishell3(tmp_path)

        assert entries == []
        assert speaker_counts == {}

    def test_skips_lines_with_missing_pinyin(self, tmp_path: Path) -> None:
        _write_aishell3_corpus(
            tmp_path,
            [
                ("SSB00050001.wav", "广 guang3"),
                # No tab → split returns one part, must be skipped.
                ("SSB00050002.wav", ""),
            ],
        )
        # Make the second line a no-tab oddity.
        with (tmp_path / "train" / "content.txt").open("a", encoding="utf-8") as f:
            f.write("BROKEN_NO_TAB_LINE\n")

        entries, _ = parse_aishell3(tmp_path)

        # First row valid; second row has empty body (no chars/pinyin) → skipped;
        # third row has no tab → skipped.
        assert len(entries) == 1
        assert entries[0][0] == "广"

    def test_skips_when_wav_does_not_exist(self, tmp_path: Path) -> None:
        # create_wavs=False makes every wav reference dangle.
        _write_aishell3_corpus(
            tmp_path,
            [("SSB00050001.wav", "广 guang3")],
            create_wavs=False,
        )

        entries, speaker_counts = parse_aishell3(tmp_path)

        assert entries == []
        assert speaker_counts == {}

    def test_speaker_id_derived_from_filename_prefix(self, tmp_path: Path) -> None:
        _write_aishell3_corpus(
            tmp_path,
            [("SSB99990123.wav", "你 ni3 好 hao3")],
        )

        entries, speaker_counts = parse_aishell3(tmp_path)

        assert entries[0][2] == "SSB9999"
        assert "SSB9999" in speaker_counts

    def test_skips_comment_and_blank_lines(self, tmp_path: Path) -> None:
        _write_aishell3_corpus(
            tmp_path,
            [("SSB00050001.wav", "广 guang3")],
        )
        with (tmp_path / "train" / "content.txt").open("a", encoding="utf-8") as f:
            f.write("\n# this is a comment\n\n")

        entries, _ = parse_aishell3(tmp_path)

        assert len(entries) == 1


# ---------------------------------------------------------------------------
# parse_cml_tts (CML-TTS for ES/FR/PT)
# ---------------------------------------------------------------------------


_CML_HEADER = (
    "wav_filename|wav_filesize|transcript|transcript_wav2vec|"
    "levenshtein|duration|num_words|client_id"
)


def _write_cml_tts_corpus(
    base: Path,
    rows: list[tuple[str, str, str]],
    *,
    create_wavs: bool = True,
) -> None:
    """Build a CML-TTS-shaped train.csv.

    Each row is (wav_filename, transcript, client_id).
    """
    base.mkdir(parents=True, exist_ok=True)
    lines = [_CML_HEADER]
    for wav_filename, transcript, client_id in rows:
        lines.append(
            "|".join(
                [
                    wav_filename,
                    "12345",
                    transcript,
                    transcript,
                    "0.0",
                    "1.5",
                    "3",
                    client_id,
                ]
            )
        )
        if create_wavs:
            wav_path = base / wav_filename
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            wav_path.write_bytes(b"")
    (base / "train.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.unit
class TestParseCmlTts:
    def test_minimal_three_speakers(self, tmp_path: Path) -> None:
        _write_cml_tts_corpus(
            tmp_path,
            [
                ("audio/spk_a/u1.wav", "Hola mundo", "spk_a"),
                ("audio/spk_a/u2.wav", "Buenos dias", "spk_a"),
                ("audio/spk_b/u1.wav", "Adios", "spk_b"),
            ],
        )

        entries, speaker_counts = parse_cml_tts(tmp_path, "es")

        assert len(entries) == 3
        text, wav_path, client_id = entries[0]
        assert text == "Hola mundo"
        assert client_id == "spk_a"
        assert wav_path.endswith(os.path.join("audio", "spk_a", "u1.wav"))
        assert speaker_counts == {"spk_a": 2, "spk_b": 1}

    def test_returns_empty_when_train_csv_missing(self, tmp_path: Path) -> None:
        entries, speaker_counts = parse_cml_tts(tmp_path, "fr")

        assert entries == []
        assert speaker_counts == {}

    def test_skips_rows_with_too_few_columns(self, tmp_path: Path) -> None:
        # Manually write a malformed row alongside a valid one.
        _write_cml_tts_corpus(
            tmp_path,
            [("audio/u1.wav", "Bonjour", "spk")],
        )
        with (tmp_path / "train.csv").open("a", encoding="utf-8") as f:
            f.write("not|enough|columns\n")

        entries, _ = parse_cml_tts(tmp_path, "fr")

        assert len(entries) == 1

    def test_skips_rows_with_empty_transcript(self, tmp_path: Path) -> None:
        _write_cml_tts_corpus(
            tmp_path,
            [
                ("audio/u1.wav", "", "spk_a"),
                ("audio/u2.wav", "Olá", "spk_b"),
            ],
        )

        entries, _ = parse_cml_tts(tmp_path, "pt")

        assert len(entries) == 1
        assert entries[0][0] == "Olá"

    def test_skips_when_wav_does_not_exist(self, tmp_path: Path) -> None:
        _write_cml_tts_corpus(
            tmp_path,
            [("audio/ghost.wav", "Bonjour", "spk")],
            create_wavs=False,
        )

        entries, _ = parse_cml_tts(tmp_path, "fr")

        assert entries == []

    def test_skips_blank_lines_in_csv(self, tmp_path: Path) -> None:
        _write_cml_tts_corpus(
            tmp_path,
            [("audio/u1.wav", "Bonjour", "spk")],
        )
        with (tmp_path / "train.csv").open("a", encoding="utf-8") as f:
            f.write("\n\n\n")

        entries, _ = parse_cml_tts(tmp_path, "fr")

        assert len(entries) == 1

    def test_returns_empty_when_csv_only_has_header(self, tmp_path: Path) -> None:
        (tmp_path / "train.csv").write_text(_CML_HEADER + "\n", encoding="utf-8")

        entries, speaker_counts = parse_cml_tts(tmp_path, "es")

        assert entries == []
        assert speaker_counts == {}

    def test_unicode_transcript_preserved(self, tmp_path: Path) -> None:
        _write_cml_tts_corpus(
            tmp_path,
            [("audio/u1.wav", "Olá, tudo bem? — Pergunta", "spk_pt")],
        )

        entries, _ = parse_cml_tts(tmp_path, "pt")

        assert entries[0][0] == "Olá, tudo bem? — Pergunta"

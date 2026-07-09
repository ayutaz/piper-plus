"""Unit tests for Korean dataset parsers in prepare_multilingual_dataset.

The v8 dataset scaling plan adds Korean (ko=7) via three sources — Zeroth
Korean (CC BY 4.0), KsponSpeech (MIT/ETRI consent), and Common Voice ko (CC0).
Each parser produces the same `(text, wav_path, speaker_id_str)` tuple shape
as the existing `parse_aishell3` / `parse_cml_tts`, but with source-specific
speaker prefixes ("zeroth-", "kspon-", "cv-") so the three streams merge into
a single ko group with globally-unique speaker ids.

Drift in field order, speaker-id derivation, ETRI notation cleaning, or the
UTMOS/≥N-clip filter silently corrupts the training corpus, so these tests
pin each parsing contract against synthetic fixtures written to ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("torch")

from piper_train.tools.prepare_multilingual_dataset import (  # noqa: E402
    _clean_kspon_text,
    parse_common_voice_ko,
    parse_kspon_speech,
    parse_zeroth_korean,
)


# ---------------------------------------------------------------------------
# parse_zeroth_korean (LibriSpeech-style flac tree + *.trans.txt)
# ---------------------------------------------------------------------------


def _write_zeroth_corpus(
    base: Path,
    speaker_utts: dict[str, list[tuple[str, str]]],
    *,
    split: str = "train_data_01",
    create_flac: bool = True,
) -> None:
    """Build a Zeroth-Korean-shaped tree under *base*.

    speaker_utts is {speaker_id: [(utt_id, transcript), ...]}. Each utt gets
    an empty flac file and shares a per-speaker ``{spk}.trans.txt`` that lists
    ``utt_id text`` lines.
    """
    for speaker_id, utts in speaker_utts.items():
        spk_dir = base / split / speaker_id
        spk_dir.mkdir(parents=True, exist_ok=True)
        trans_lines: list[str] = []
        for utt_id, text in utts:
            if create_flac:
                (spk_dir / f"{utt_id}.flac").write_bytes(b"")
            trans_lines.append(f"{utt_id} {text}")
        (spk_dir / f"{speaker_id}.trans.txt").write_text(
            "\n".join(trans_lines) + "\n", encoding="utf-8"
        )


@pytest.mark.unit
class TestParseZerothKorean:
    def test_minimal_two_speakers(self, tmp_path: Path) -> None:
        _write_zeroth_corpus(
            tmp_path,
            {
                "003": [
                    ("003_0033_0001", "안녕하세요"),
                    ("003_0033_0002", "반갑습니다"),
                ],
                "004": [("004_0044_0001", "감사합니다")],
            },
        )

        entries, speaker_counts = parse_zeroth_korean(tmp_path)

        assert len(entries) == 3
        # Speaker id prefix must be "zeroth-" for cross-source uniqueness.
        assert all(spk.startswith("zeroth-") for _, _, spk in entries)
        assert speaker_counts == {"zeroth-003": 2, "zeroth-004": 1}

    def test_speaker_id_derived_from_underscore_prefix(self, tmp_path: Path) -> None:
        _write_zeroth_corpus(tmp_path, {"9999": [("9999_0000_0001", "테스트")]})

        entries, speaker_counts = parse_zeroth_korean(tmp_path)

        assert entries[0][2] == "zeroth-9999"
        assert "zeroth-9999" in speaker_counts

    def test_upsample_to_22050_is_deferred_to_cache_stage(self, tmp_path: Path) -> None:
        """Parser must NOT touch audio — resampling happens later.

        Zeroth ships 16kHz flac; the design routes resample through
        cache_audio_parallel/soxr MQ so the parser only records paths.
        """
        _write_zeroth_corpus(tmp_path, {"003": [("003_0000_0001", "테스트")]})

        entries, _ = parse_zeroth_korean(tmp_path)

        _text, path_str, _spk = entries[0]
        assert path_str.endswith("003_0000_0001.flac")
        assert Path(path_str).exists()

    def test_returns_empty_when_split_missing(self, tmp_path: Path) -> None:
        entries, speaker_counts = parse_zeroth_korean(tmp_path)

        assert entries == []
        assert speaker_counts == {}

    def test_skips_utterances_without_flac(self, tmp_path: Path) -> None:
        _write_zeroth_corpus(
            tmp_path,
            {"003": [("003_0033_0001", "안녕")]},
            create_flac=False,
        )

        entries, speaker_counts = parse_zeroth_korean(tmp_path)

        assert entries == []
        assert speaker_counts == {}

    def test_skips_blank_and_comment_transcript_lines(self, tmp_path: Path) -> None:
        _write_zeroth_corpus(tmp_path, {"003": [("003_0033_0001", "정상")]})
        trans_path = tmp_path / "train_data_01" / "003" / "003.trans.txt"
        with trans_path.open("a", encoding="utf-8") as f:
            f.write("\n# comment\n\n")

        entries, _ = parse_zeroth_korean(tmp_path)

        assert len(entries) == 1

    def test_speaker_ids_are_globally_unique_with_prefix(self, tmp_path: Path) -> None:
        # Two speakers named "003" in KsponSpeech style would collide without
        # the prefix — the "zeroth-" prefix guarantees no cross-source clash.
        _write_zeroth_corpus(tmp_path, {"003": [("003_0000_0001", "말")]})

        entries, _ = parse_zeroth_korean(tmp_path)

        assert entries[0][2] == "zeroth-003"
        assert entries[0][2] != "kspon-003"
        assert entries[0][2] != "cv-003"


# ---------------------------------------------------------------------------
# parse_kspon_speech (PCM/WAV + ETRI notation)
# ---------------------------------------------------------------------------


def _write_kspon_corpus(
    base: Path,
    speaker_utts: dict[str, list[tuple[str, str]]],
    *,
    split: str = "KsponSpeech_01",
    audio_ext: str = ".pcm",
    create_audio: bool = True,
) -> None:
    """speaker_utts = {speaker_id: [(utt_id, raw_text_with_ETRI_markup), ...]}.

    Default extension is ``.pcm`` to mirror the KsponSpeech raw distribution
    (16 kHz mono s16le, headerless) which ``parse_kspon_speech`` now enumerates
    directly since the v8 KO enablement.  Pass ``audio_ext=".wav"`` to test the
    legacy pre-converted layout.
    """
    for speaker_id, utts in speaker_utts.items():
        spk_dir = base / split / speaker_id
        spk_dir.mkdir(parents=True, exist_ok=True)
        for utt_id, text in utts:
            (spk_dir / f"{utt_id}.txt").write_text(text, encoding="utf-8")
            if create_audio:
                (spk_dir / f"{utt_id}{audio_ext}").write_bytes(b"")


@pytest.mark.unit
class TestCleanKsponText:
    def test_dual_form_keeps_pronunciation_side(self) -> None:
        assert _clean_kspon_text("(5)/(오) 시") == "오 시"

    def test_multiple_dual_forms(self) -> None:
        assert _clean_kspon_text("(5)/(오) (10)/(십) 일") == "오 십 일"

    def test_removes_noise_tags(self) -> None:
        assert _clean_kspon_text("안녕 b/ 하세요 l/") == "안녕 하세요"

    def test_removes_repetition_marker(self) -> None:
        assert _clean_kspon_text("아 아+ 안녕") == "아 아 안녕"

    def test_removes_emphasis_star(self) -> None:
        assert _clean_kspon_text("*중요* 정보") == "중요 정보"

    def test_removes_stray_slash(self) -> None:
        assert _clean_kspon_text("먹었어/ 아니") == "먹었어 아니"

    def test_idempotent_on_already_clean(self) -> None:
        assert _clean_kspon_text("반갑습니다") == "반갑습니다"

    def test_collapses_repeated_whitespace(self) -> None:
        assert _clean_kspon_text("안녕   b/   하세요") == "안녕 하세요"


@pytest.mark.unit
class TestParseKsponSpeech:
    def test_minimal_two_speakers_with_etri_cleaning(self, tmp_path: Path) -> None:
        _write_kspon_corpus(
            tmp_path,
            {
                "KsponSpeech_0001": [
                    (f"KsponSpeech_{i:06d}", "(5)/(오) 시") for i in range(20)
                ],
                "KsponSpeech_0002": [
                    (f"KsponSpeech_{i:06d}", "안녕 b/ 하세요") for i in range(20)
                ],
            },
        )

        entries, speaker_counts = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=None
        )

        assert len(entries) == 40
        # Both speakers should be present with the "kspon-" prefix.
        assert set(speaker_counts.keys()) == {
            "kspon-KsponSpeech_0001",
            "kspon-KsponSpeech_0002",
        }
        # ETRI notation must be cleaned in the returned text field.
        spk1_texts = [t for t, _, s in entries if s == "kspon-KsponSpeech_0001"]
        assert all(t == "오 시" for t in spk1_texts)
        spk2_texts = [t for t, _, s in entries if s == "kspon-KsponSpeech_0002"]
        assert all(t == "안녕 하세요" for t in spk2_texts)

    def test_speaker_id_prefix_kspon(self, tmp_path: Path) -> None:
        _write_kspon_corpus(
            tmp_path,
            {"KsponSpeech_0001": [("KsponSpeech_000001", "안녕")]},
        )

        entries, _ = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=None
        )

        assert entries[0][2] == "kspon-KsponSpeech_0001"

    def test_cap_per_speaker_limits_utterances(self, tmp_path: Path) -> None:
        _write_kspon_corpus(
            tmp_path,
            {
                "KsponSpeech_0001": [
                    (f"KsponSpeech_{i:06d}", "안녕") for i in range(100)
                ],
            },
        )

        entries, speaker_counts = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=60
        )

        # Cap is 60 → exactly 60 utterances retained for the single speaker.
        assert len(entries) == 60
        assert speaker_counts == {"kspon-KsponSpeech_0001": 60}

    def test_min_utts_filter_drops_sparse_speakers(self, tmp_path: Path) -> None:
        _write_kspon_corpus(
            tmp_path,
            {
                "KsponSpeech_0001": [
                    (f"KsponSpeech_{i:06d}", "안녕") for i in range(3)
                ],
                "KsponSpeech_0002": [
                    (f"KsponSpeech_{i:06d}", "안녕") for i in range(20)
                ],
            },
        )

        entries, speaker_counts = parse_kspon_speech(
            tmp_path, min_utts_per_spk=20, cap_per_speaker=None
        )

        assert set(speaker_counts.keys()) == {"kspon-KsponSpeech_0002"}
        assert len(entries) == 20

    def test_skips_utterances_without_audio(self, tmp_path: Path) -> None:
        _write_kspon_corpus(
            tmp_path,
            {"KsponSpeech_0001": [("KsponSpeech_000001", "안녕")]},
            create_audio=False,
        )

        entries, speaker_counts = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=None
        )

        assert entries == []
        assert speaker_counts == {}

    def test_returns_empty_when_split_missing(self, tmp_path: Path) -> None:
        entries, speaker_counts = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=None
        )

        assert entries == []
        assert speaker_counts == {}

    def test_default_audio_ext_is_pcm(self, tmp_path: Path) -> None:
        """Raw KsponSpeech distribution ships headerless .pcm — no WAV conversion."""
        _write_kspon_corpus(
            tmp_path,
            {"KsponSpeech_0001": [("KsponSpeech_000001", "안녕")]},
            # _write_kspon_corpus default is .pcm now.
        )

        entries, speaker_counts = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=None
        )

        assert len(entries) == 1
        _text, audio_path_str, spk = entries[0]
        assert audio_path_str.endswith(".pcm")
        assert spk == "kspon-KsponSpeech_0001"

    def test_wav_ext_still_supported_for_pre_converted_corpora(
        self, tmp_path: Path
    ) -> None:
        """Passing audio_ext='.wav' keeps working for users who pre-converted."""
        _write_kspon_corpus(
            tmp_path,
            {"KsponSpeech_0001": [("KsponSpeech_000001", "안녕")]},
            audio_ext=".wav",
        )

        entries, _ = parse_kspon_speech(
            tmp_path,
            min_utts_per_spk=1,
            cap_per_speaker=None,
            audio_ext=".wav",
        )

        assert len(entries) == 1
        _text, audio_path_str, _spk = entries[0]
        assert audio_path_str.endswith(".wav")

    def test_skips_empty_transcript_after_cleaning(self, tmp_path: Path) -> None:
        # Text that reduces to empty after ETRI cleaning is dropped.
        _write_kspon_corpus(
            tmp_path,
            {"KsponSpeech_0001": [("KsponSpeech_000001", "b/ l/")]},
        )

        entries, _ = parse_kspon_speech(
            tmp_path, min_utts_per_spk=1, cap_per_speaker=None
        )

        assert entries == []


# ---------------------------------------------------------------------------
# parse_common_voice_ko (CML-TTS-shaped csv from export_common_voice_ko.py)
# ---------------------------------------------------------------------------


_CV_HEADER = (
    "wav_filename|wav_filesize|transcript|transcript_wav2vec|"
    "levenshtein|duration|num_words|client_id"
)


def _write_cv_ko_corpus(
    base: Path,
    rows: list[tuple[str, str, str]],
    *,
    split: str = "cv",
    utmos_by_client: dict[str, float] | None = None,
    create_wavs: bool = True,
) -> None:
    """rows = [(wav_filename, transcript, client_id), ...]."""
    base.mkdir(parents=True, exist_ok=True)
    lines = [_CV_HEADER]
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
    (base / f"{split}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if utmos_by_client is not None:
        utmos_path = base / "utmos.tsv"
        with utmos_path.open("w", encoding="utf-8") as f:
            f.write("client_id\tutmos\n")
            for client_id, score in utmos_by_client.items():
                f.write(f"{client_id}\t{score}\n")


@pytest.mark.unit
class TestParseCommonVoiceKo:
    def test_minimal_selection_with_utmos_filter(self, tmp_path: Path) -> None:
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        rows += [(f"audios/cv_bob/u{i}.wav", "저는 밥", "bob") for i in range(25)]
        _write_cv_ko_corpus(
            tmp_path,
            rows,
            utmos_by_client={"alice": 3.0, "bob": 3.2},
        )

        entries, speaker_counts = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        assert len(entries) == 45
        assert set(speaker_counts.keys()) == {"cv-alice", "cv-bob"}

    def test_utmos_filter_drops_low_score(self, tmp_path: Path) -> None:
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        rows += [(f"audios/cv_low/u{i}.wav", "낮음", "low") for i in range(20)]
        _write_cv_ko_corpus(
            tmp_path,
            rows,
            utmos_by_client={"alice": 3.0, "low": 1.9},
        )

        entries, speaker_counts = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        assert set(speaker_counts.keys()) == {"cv-alice"}
        assert all(spk == "cv-alice" for _, _, spk in entries)

    def test_min_clips_filter_drops_sparse_speakers(self, tmp_path: Path) -> None:
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        rows += [(f"audios/cv_short/u{i}.wav", "적음", "short") for i in range(5)]
        _write_cv_ko_corpus(
            tmp_path,
            rows,
            utmos_by_client={"alice": 3.0, "short": 3.0},
        )

        _entries, speaker_counts = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        assert set(speaker_counts.keys()) == {"cv-alice"}

    def test_speaker_id_prefix_cv(self, tmp_path: Path) -> None:
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        _write_cv_ko_corpus(
            tmp_path,
            rows,
            utmos_by_client={"alice": 3.0},
        )

        entries, _ = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        assert all(spk == "cv-alice" for _, _, spk in entries)

    def test_utmos_missing_disables_filter(self, tmp_path: Path) -> None:
        # No utmos.tsv → all speakers with ≥ min_clips pass regardless of MOS.
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        _write_cv_ko_corpus(tmp_path, rows, utmos_by_client=None)

        entries, speaker_counts = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        assert speaker_counts == {"cv-alice": 20}
        assert len(entries) == 20

    def test_returns_empty_when_csv_missing(self, tmp_path: Path) -> None:
        entries, speaker_counts = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=1, min_utmos=0.0
        )

        assert entries == []
        assert speaker_counts == {}

    def test_skips_rows_with_missing_audio(self, tmp_path: Path) -> None:
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        _write_cv_ko_corpus(
            tmp_path,
            rows,
            utmos_by_client={"alice": 3.0},
            create_wavs=False,
        )

        entries, speaker_counts = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        assert entries == []
        assert speaker_counts == {}

    def test_skips_rows_with_too_few_columns(self, tmp_path: Path) -> None:
        rows = [(f"audios/cv_alice/u{i}.wav", "안녕", "alice") for i in range(20)]
        _write_cv_ko_corpus(
            tmp_path,
            rows,
            utmos_by_client={"alice": 3.0},
        )
        with (tmp_path / "cv.csv").open("a", encoding="utf-8") as f:
            f.write("not|enough|columns\n")

        entries, _ = parse_common_voice_ko(
            tmp_path, min_clips_per_spk=20, min_utmos=2.5
        )

        # Malformed row is dropped, all 20 valid rows survive.
        assert len(entries) == 20

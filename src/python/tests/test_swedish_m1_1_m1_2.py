"""Tests for M1.1 (NST dictionary conversion) and M1.2 (phoneme inventory + PUA)."""

from __future__ import annotations

import gzip
import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# M1.2: Phoneme inventory + PUA
# ---------------------------------------------------------------------------

from piper_plus_g2p.encode.pua import (
    CHAR2TOKEN,
    FIXED_PUA_MAPPING,
    TOKEN2CHAR,
    map_token,
)
from piper_plus_g2p.encode.id_maps import _SWEDISH_PHONEMES as SWEDISH_PHONEMES


class TestM12PhonemeInventory:
    """M1.2: Swedish phoneme inventory + PUA allocation."""

    @pytest.mark.unit
    def test_swedish_phonemes_not_empty(self):
        assert len(SWEDISH_PHONEMES) > 0

    @pytest.mark.unit
    def test_swedish_phonemes_count(self):
        assert len(SWEDISH_PHONEMES) == 19  # 10 single-CP + 9 long vowels

    @pytest.mark.unit
    def test_single_codepoint_phonemes_no_pua(self):
        single_cp = ["ɖ", "ʈ", "ɳ", "ɭ", "ɧ", "ɵ", "ʏ", "œ", "ɑ", "ø"]
        for ph in single_cp:
            assert len(ph) == 1, f"{ph!r} is not single codepoint"
            ch = map_token(ph)
            assert ch == ph, f"Single-CP {ph!r} should map to itself"

    @pytest.mark.unit
    def test_long_vowels_have_pua(self):
        long_vowels = ["iː", "yː", "eː", "ɛː", "øː", "ɑː", "oː", "uː", "ʉː"]
        for lv in long_vowels:
            ch = map_token(lv)
            assert len(ch) == 1, f"{lv!r} should map to single PUA char"
            cp = ord(ch)
            assert 0xE059 <= cp <= 0xE061, (
                f"{lv!r} PUA 0x{cp:04X} outside SV range"
            )

    @pytest.mark.unit
    def test_pua_assignments_are_unique(self):
        values = list(FIXED_PUA_MAPPING.values())
        assert len(values) == len(set(values)), "Duplicate PUA codepoints found"

    @pytest.mark.unit
    def test_pua_assignments_no_key_conflict(self):
        keys = list(FIXED_PUA_MAPPING.keys())
        assert len(keys) == len(set(keys)), "Duplicate PUA token keys found"

    @pytest.mark.unit
    def test_pua_max_codepoint(self):
        # PUA v2 (2026-05): added en/fr/pt multi-CP entries at 0xE062-0xE064.
        # Allocation map lives in docs/spec/pua-contract.toml.
        max_cp = max(FIXED_PUA_MAPPING.values())
        assert max_cp <= 0xE064, f"Max PUA codepoint 0x{max_cp:04X} exceeds PUA v2 range"

    @pytest.mark.unit
    def test_sv_pua_range(self):
        expected = {
            "iː": 0xE059,
            "yː": 0xE05A,
            "eː": 0xE05B,
            "ɛː": 0xE05C,
            "øː": 0xE05D,
            "ɑː": 0xE05E,
            "oː": 0xE05F,
            "uː": 0xE060,
            "ʉː": 0xE061,
        }
        for token, cp in expected.items():
            assert FIXED_PUA_MAPPING[token] == cp, (
                f"{token!r}: expected 0x{cp:04X}, got 0x{FIXED_PUA_MAPPING.get(token, 0):04X}"
            )

    @pytest.mark.unit
    def test_no_conflict_with_existing_languages(self):
        # SV starts at 0xE059, FR ends at 0xE058
        sv_min = min(v for k, v in FIXED_PUA_MAPPING.items() if 0xE059 <= v <= 0xE061)
        fr_max = 0xE058  # FR ɔ̃
        assert sv_min > fr_max

    @pytest.mark.unit
    def test_bidirectional_mapping(self):
        long_vowels = ["iː", "yː", "eː", "ɛː", "øː", "ɑː", "oː", "uː", "ʉː"]
        for token in long_vowels:
            ch = TOKEN2CHAR[token]
            assert CHAR2TOKEN[ch] == token, (
                f"Bidirectional mismatch for {token!r}"
            )

    @pytest.mark.unit
    def test_map_token_idempotent(self):
        ch1 = map_token("ɧ")
        ch2 = map_token("ɧ")
        assert ch1 == ch2

    @pytest.mark.unit
    def test_existing_ja_pua_unchanged(self):
        ja_mappings = {
            "a:": 0xE000, "i:": 0xE001, "u:": 0xE002,
            "e:": 0xE003, "o:": 0xE004, "cl": 0xE005,
        }
        for token, cp in ja_mappings.items():
            assert FIXED_PUA_MAPPING[token] == cp

    @pytest.mark.unit
    def test_existing_zh_pua_unchanged(self):
        # Spot-check a few ZH entries
        assert FIXED_PUA_MAPPING["pʰ"] == 0xE020
        assert FIXED_PUA_MAPPING["tɕ"] == 0xE023
        assert FIXED_PUA_MAPPING["tone5"] == 0xE04A

    @pytest.mark.unit
    def test_existing_ko_pua_unchanged(self):
        assert FIXED_PUA_MAPPING["p\u0348"] == 0xE04B  # p͈
        assert FIXED_PUA_MAPPING["p\u031a"] == 0xE052  # p̚

    @pytest.mark.unit
    def test_existing_es_pt_fr_pua_unchanged(self):
        assert FIXED_PUA_MAPPING["tʃ"] == 0xE054
        assert FIXED_PUA_MAPPING["dʒ"] == 0xE055
        assert FIXED_PUA_MAPPING["ɛ̃"] == 0xE056
        assert FIXED_PUA_MAPPING["ɑ̃"] == 0xE057
        assert FIXED_PUA_MAPPING["ɔ̃"] == 0xE058

    @pytest.mark.unit
    def test_all_sv_pua_within_reserved_range(self):
        # 0xE062-0xE063 are reserved for SV future expansion
        sv_long_vowels = ["iː", "yː", "eː", "ɛː", "øː", "ɑː", "oː", "uː", "ʉː"]
        for lv in sv_long_vowels:
            cp = FIXED_PUA_MAPPING[lv]
            assert cp <= 0xE063, f"{lv!r} PUA 0x{cp:04X} exceeds reserved range"


# ---------------------------------------------------------------------------
# M1.1: NST dictionary conversion
# ---------------------------------------------------------------------------

from piper_train.tools.convert_nst_dictionary import (
    NST_SAMPA_TO_IPA,
    SPOT_CHECK,
    convert_sampa_to_ipa,
    is_simple_word,
    parse_nst_line,
    run_spot_check,
    should_skip_entry,
)


class TestM11SampaToIpa:
    """M1.1: SAMPA → IPA conversion tests."""

    @pytest.mark.unit
    def test_sampa_to_ipa_long_vowels(self):
        assert convert_sampa_to_ipa('"b A: n`') == "ˈbɑːɳ"

    @pytest.mark.unit
    def test_sampa_to_ipa_short_vowels(self):
        assert convert_sampa_to_ipa('"f E s t') == "ˈfɛst"

    @pytest.mark.unit
    def test_sampa_to_ipa_sj_sound(self):
        assert convert_sampa_to_ipa('"S e: d') == "ˈɧeːd"

    @pytest.mark.unit
    def test_sampa_to_ipa_tj_sound(self):
        assert convert_sampa_to_ipa('"s\' I n d') == "ˈɕɪnd"

    @pytest.mark.unit
    def test_sampa_to_ipa_retroflex(self):
        assert convert_sampa_to_ipa('"b u: d`') == "ˈbuːɖ"

    @pytest.mark.unit
    def test_sampa_to_ipa_velar_nasal(self):
        assert convert_sampa_to_ipa('"k u0 N') == "ˈkʉŋ"

    @pytest.mark.unit
    def test_sampa_to_ipa_stress_mid_word(self):
        assert convert_sampa_to_ipa('s t a "S u: n') == "staˈɧuːn"

    @pytest.mark.unit
    def test_sampa_to_ipa_secondary_stress(self):
        assert convert_sampa_to_ipa('%h }: s') == "ˌhʉːs"

    @pytest.mark.unit
    def test_sampa_to_ipa_g_to_ipa_g(self):
        result = convert_sampa_to_ipa('"g A: t a')
        assert result == "ˈɡɑːta"
        # Verify the 'g' is IPA ɡ (U+0261), not ASCII g (U+0067)
        assert "\u0261" in result

    @pytest.mark.unit
    def test_sampa_to_ipa_diphthong(self):
        assert convert_sampa_to_ipa('"a*U') == "ˈaʊ"

    @pytest.mark.unit
    def test_sampa_to_ipa_unknown_token(self):
        result = convert_sampa_to_ipa('"x y z')
        # Unknown tokens pass through with warning
        assert result == "ˈxyz"


class TestM11Filtering:
    """M1.1: Entry filtering tests."""

    @pytest.mark.unit
    def test_filter_silence(self):
        skip, reason = should_skip_entry("!sil", "...", set())
        assert skip is True
        assert reason == "silence_marker"

    @pytest.mark.unit
    def test_filter_unknown(self):
        skip, reason = should_skip_entry("<unk>", "...", set())
        assert skip is True
        assert reason == "unknown_marker"

    @pytest.mark.unit
    def test_filter_hyphen_prefix(self):
        skip, reason = should_skip_entry("-tion", '"S u: n', set())
        assert skip is True
        assert reason == "hyphen_prefix"

    @pytest.mark.unit
    def test_filter_empty_pronunciation(self):
        skip, reason = should_skip_entry("word", "", set())
        assert skip is True
        assert reason == "empty_pronunciation"

    @pytest.mark.unit
    def test_filter_duplicate(self):
        seen = {"barn"}
        skip, reason = should_skip_entry("barn", '"b A: n`', seen)
        assert skip is True
        assert reason == "duplicate"

    @pytest.mark.unit
    def test_core_tier_filters_compounds(self):
        # Secondary stress (%) indicates compound
        assert is_simple_word('"b A: n`') is True
        assert is_simple_word('"S }: k %h }: s') is False


class TestM11Parsing:
    """M1.1: Line parsing tests."""

    @pytest.mark.unit
    def test_parse_malformed_line(self):
        assert parse_nst_line("no tabs here") is None

    @pytest.mark.unit
    def test_parse_empty_line(self):
        assert parse_nst_line("") is None

    @pytest.mark.unit
    def test_parse_valid_line(self):
        result = parse_nst_line("BARN\t\"b A: n`")
        assert result is not None
        word, sampa = result
        assert word == "barn"
        assert sampa == '"b A: n`'

    @pytest.mark.unit
    def test_nfc_normalization(self):
        # NFD å (a + combining ring above) should normalize to NFC å
        nfd_line = "A\u030aR\t\"O: r"
        result = parse_nst_line(nfd_line)
        assert result is not None
        word, _ = result
        assert word == "\u00e5r"  # NFC å


class TestM11SpotCheck:
    """M1.1: Spot-check validation tests."""

    @pytest.mark.unit
    def test_spot_check_20_words(self):
        # Build a dictionary from spot-check data
        dictionary = {}
        for word, sampa, expected in SPOT_CHECK:
            dictionary[word] = convert_sampa_to_ipa(sampa)
        assert run_spot_check(dictionary) is True

    @pytest.mark.unit
    def test_spot_check_count(self):
        assert len(SPOT_CHECK) == 20


class TestM11CLI:
    """M1.1: CLI integration tests."""

    def _make_lexicon(self, entries: list[tuple[str, str]], path: Path) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for word, sampa in entries:
                f.write(f"{word}\t{sampa}\n")

    @pytest.mark.unit
    def test_cli_input_not_found(self):
        import subprocess
        result = subprocess.run(
            ["uv", "run", "python", "-m", "piper_train.tools.convert_nst_dictionary",
             "-i", "nonexistent.txt", "-o", "out.json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    @pytest.mark.unit
    def test_cli_basic_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = Path(tmpdir) / "lexicon.txt"
            out = Path(tmpdir) / "out.json"

            self._make_lexicon([
                ("BARN", '"b A: n`'),
                ("FEST", '"f E s t'),
                ("HUS", '"h }: s'),
            ], inp)

            import subprocess
            result = subprocess.run(
                ["uv", "run", "python", "-m", "piper_train.tools.convert_nst_dictionary",
                 "-i", str(inp), "-o", str(out), "-q"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "PYTHONUTF8": "1"},
            )
            assert result.returncode == 0
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["barn"] == "ˈbɑːɳ"
            assert data["fest"] == "ˈfɛst"
            assert data["hus"] == "ˈhʉːs"

    @pytest.mark.unit
    def test_cli_gzip_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = Path(tmpdir) / "lexicon.txt"
            out = Path(tmpdir) / "out.json.gz"

            self._make_lexicon([("SOL", '"s u: l')], inp)

            import subprocess
            result = subprocess.run(
                ["uv", "run", "python", "-m", "piper_train.tools.convert_nst_dictionary",
                 "-i", str(inp), "-o", str(out), "--gzip", "-q"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "PYTHONUTF8": "1"},
            )
            assert result.returncode == 0
            with gzip.open(out, "rt", encoding="utf-8") as f:
                data = json.load(f)
            assert data["sol"] == "ˈsuːl"

    @pytest.mark.unit
    def test_cli_validate_pass(self):
        """Build a lexicon with all 20 spot-check words and validate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = Path(tmpdir) / "lexicon.txt"
            out = Path(tmpdir) / "out.json"

            entries = [(w.upper(), s) for w, s, _ in SPOT_CHECK]
            self._make_lexicon(entries, inp)

            import subprocess
            result = subprocess.run(
                ["uv", "run", "python", "-m", "piper_train.tools.convert_nst_dictionary",
                 "-i", str(inp), "-o", str(out), "--validate", "-q"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "PYTHONUTF8": "1"},
            )
            assert result.returncode == 0

    @pytest.mark.unit
    def test_cli_validate_fail(self):
        """Build a corrupted lexicon and verify validation fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = Path(tmpdir) / "lexicon.txt"
            out = Path(tmpdir) / "out.json"

            # Include all spot-check words but corrupt 'barn'
            entries = [(w.upper(), s) for w, s, _ in SPOT_CHECK]
            entries[0] = ("BARN", '"b a n')  # wrong SAMPA
            self._make_lexicon(entries, inp)

            import subprocess
            result = subprocess.run(
                ["uv", "run", "python", "-m", "piper_train.tools.convert_nst_dictionary",
                 "-i", str(inp), "-o", str(out), "--validate", "-q"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "PYTHONUTF8": "1"},
            )
            assert result.returncode == 4

    @pytest.mark.unit
    def test_output_keys_sorted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = Path(tmpdir) / "lexicon.txt"
            out = Path(tmpdir) / "out.json"

            self._make_lexicon([
                ("ZOO", '"s u: l'),
                ("ALFA", '"a l f a'),
                ("BARN", '"b A: n`'),
            ], inp)

            import subprocess
            subprocess.run(
                ["uv", "run", "python", "-m", "piper_train.tools.convert_nst_dictionary",
                 "-i", str(inp), "-o", str(out), "-q"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "PYTHONUTF8": "1"},
            )
            raw = out.read_text(encoding="utf-8")
            keys = list(json.loads(raw).keys())
            assert keys == sorted(keys)

    @pytest.mark.unit
    def test_sampa_mapping_count(self):
        assert len(NST_SAMPA_TO_IPA) == 43

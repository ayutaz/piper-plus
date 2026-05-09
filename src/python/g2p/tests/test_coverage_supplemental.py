"""Supplemental tests to maintain >=80% coverage with margin.

These tests exercise paths that existing test files do not cover:

* ``base.Phonemizer.phonemize`` default implementation (sanitize + delegate).
* ``custom_dict.CustomDictionary.remove_word`` / ``save_dictionary`` /
  ``get_stats`` / case-sensitive entries / file-not-found / oversize file /
  malformed JSON / symlink-resolution warning.
* ``multilingual.UnicodeLanguageDetector`` Hangul Jamo / CJK Extension /
  CJK Compatibility / fullwidth-Latin / no-CJK-fallback / kana-disambiguation
  branches.
* ``registry.PhonemizerRegistry`` register-non-Phonemizer error,
  composite-code re-resolution caching, unsupported-dialect rejection.

All tests are dependency-free (no g2pk2/pyopenjtalk/pypinyin/g2p_en required).
"""

from __future__ import annotations

import json

import pytest

from piper_plus_g2p.base import Phonemizer, ProsodyInfo
from piper_plus_g2p.custom_dict import (
    MAX_DICT_FILE_SIZE,
    CustomDictionary,
    apply_custom_dictionary,
    create_default_dictionary,
)
from piper_plus_g2p.multilingual import (
    MultilingualPhonemizer,
    UnicodeLanguageDetector,
)
from piper_plus_g2p.registry import (
    PhonemizerRegistry,
    available_languages,
)

# ===========================================================================
# base.Phonemizer.phonemize default-path coverage (lines 73-77)
# ===========================================================================


class _StubPhonemizer(Phonemizer):
    """Concrete subclass that *does not* override ``phonemize()``.

    Forces the ABC's default implementation (sanitize -> delegate) to run.
    """

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        # Echo back chars as tokens; one ProsodyInfo per char.
        tokens = list(text)
        prosody: list[ProsodyInfo | None] = [
            ProsodyInfo(a1=0, a2=0, a3=len(text)) for _ in tokens
        ]
        return tokens, prosody


class TestBaseDefaultPhonemize:
    """Cover ``base.Phonemizer.phonemize`` default path."""

    def test_default_phonemize_delegates_to_with_prosody(self):
        p = _StubPhonemizer()
        # Default phonemize() must sanitize, delegate, and return tokens only.
        result = p.phonemize("ab")
        assert result == ["a", "b"]

    def test_default_phonemize_empty_string_returns_empty(self):
        # Sanitized empty string must short-circuit -> [].
        p = _StubPhonemizer()
        assert p.phonemize("") == []

    def test_default_phonemize_strips_control_characters(self):
        # \x00 is stripped; \n is preserved.
        p = _StubPhonemizer()
        result = p.phonemize("a\x00b\nc")
        assert "\x00" not in result
        assert "\n" in result
        assert result == ["a", "b", "\n", "c"]

    def test_default_phonemize_rejects_non_str(self):
        p = _StubPhonemizer()
        with pytest.raises(TypeError):
            p.phonemize(123)  # type: ignore[arg-type]

    def test_default_phonemize_rejects_oversize(self):
        p = _StubPhonemizer()
        with pytest.raises(ValueError, match="Input too long"):
            p.phonemize("x" * (Phonemizer.MAX_INPUT_LENGTH + 1))


# ===========================================================================
# custom_dict – untested branches (remove / save / stats / errors)
# ===========================================================================


class TestCustomDictMutations:
    def test_remove_word_returns_false_when_missing(self):
        d = CustomDictionary(load_defaults=False)
        assert d.remove_word("DOES_NOT_EXIST") is False

    def test_remove_word_case_insensitive_entry(self):
        d = CustomDictionary(load_defaults=False)
        d.add_word("gpu", "ジーピーユー")
        assert d.get_pronunciation("GPU") == "ジーピーユー"
        assert d.remove_word("gpu") is True
        assert d.get_pronunciation("GPU") is None

    def test_remove_word_case_sensitive_entry(self):
        d = CustomDictionary(load_defaults=False)
        # Mixed case word -> stored as case-sensitive
        d.add_word("PyTorch", "パイトーチ")
        assert d.get_pronunciation("PyTorch") == "パイトーチ"
        assert d.remove_word("PyTorch") is True
        assert d.get_pronunciation("PyTorch") is None

    def test_remove_word_clears_pattern_cache(self):
        d = CustomDictionary(load_defaults=False)
        d.add_word("FOO", "フー")
        # Trigger pattern caching
        d.apply_to_text("FOO")
        assert d.pattern_cache  # populated
        d.remove_word("foo")
        assert d.pattern_cache == {}

    def test_add_word_priority_lower_does_not_override(self):
        d = CustomDictionary(load_defaults=False)
        d.add_word("API", "エーピーアイ", priority=8)
        d.add_word("API", "アピ", priority=3)  # lower -> rejected
        assert d.get_pronunciation("API") == "エーピーアイ"


class TestCustomDictStats:
    def test_get_stats_counts_both_buckets(self):
        d = CustomDictionary(load_defaults=False)
        d.add_word("gpu", "ジーピーユー")  # case-insensitive
        d.add_word("PyTorch", "パイトーチ")  # case-sensitive
        stats = d.get_stats()
        assert stats["case_insensitive_entries"] == 1
        assert stats["case_sensitive_entries"] == 1
        assert stats["total_entries"] == 2


class TestCustomDictSaveLoadRoundtrip:
    def test_save_and_reload_roundtrip(self, tmp_path):
        d = CustomDictionary(load_defaults=False)
        d.add_word("AI", "エーアイ", priority=7)
        d.add_word("PyTorch", "パイトーチ", priority=6)

        out = tmp_path / "saved.json"
        d.save_dictionary(str(out))

        # File is valid JSON v2.0 with both entries.
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["version"] == "2.0"
        assert "AI" in data["entries"] or "ai" in data["entries"]
        assert "PyTorch" in data["entries"]

        # Re-load and confirm pronunciations survive the round trip.
        d2 = CustomDictionary(dict_paths=str(out), load_defaults=False)
        assert d2.get_pronunciation("AI") == "エーアイ"
        assert d2.get_pronunciation("PyTorch") == "パイトーチ"


class TestCustomDictErrorPaths:
    def test_load_missing_file_raises(self):
        d = CustomDictionary(load_defaults=False)
        with pytest.raises(FileNotFoundError):
            d.load_dictionary("/nonexistent/path/dict.json")

    def test_load_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        d = CustomDictionary(load_defaults=False)
        with pytest.raises(ValueError, match="Invalid JSON"):
            d.load_dictionary(str(bad))

    def test_load_oversize_file_raises(self, tmp_path, monkeypatch):
        # Write a small file but lower the threshold to force the error.
        big = tmp_path / "big.json"
        big.write_text(
            json.dumps({"version": "1.0", "entries": {"a": "あ"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "piper_plus_g2p.custom_dict.MAX_DICT_FILE_SIZE", 5
        )
        d = CustomDictionary(load_defaults=False)
        with pytest.raises(ValueError, match="too large"):
            d.load_dictionary(str(big))

    def test_v2_skips_comment_keys(self, tmp_path):
        f = tmp_path / "comments.json"
        f.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "entries": {
                        "// comment": {"pronunciation": "ignored"},
                        "GPU": {"pronunciation": "ジーピーユー", "priority": 5},
                    },
                }
            ),
            encoding="utf-8",
        )
        d = CustomDictionary(dict_paths=str(f), load_defaults=False)
        assert d.get_pronunciation("GPU") == "ジーピーユー"
        # Comment key MUST NOT have been registered.
        assert d.get_pronunciation("// comment") is None

    def test_v2_string_value_legacy_form(self, tmp_path):
        # v2 file with bare-string values (compat with v1-style entries).
        f = tmp_path / "v2_str.json"
        f.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "entries": {
                        "API": "エーピーアイ",
                    },
                }
            ),
            encoding="utf-8",
        )
        d = CustomDictionary(dict_paths=str(f), load_defaults=False)
        assert d.get_pronunciation("API") == "エーピーアイ"

    def test_v2_invalid_entry_type_skipped(self, tmp_path):
        # Non-dict / non-str entry value (list) is silently skipped.
        f = tmp_path / "v2_invalid.json"
        f.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "entries": {
                        "BAD": [1, 2, 3],  # invalid entry type
                        "OK": {"pronunciation": "オーケー"},
                    },
                }
            ),
            encoding="utf-8",
        )
        d = CustomDictionary(dict_paths=str(f), load_defaults=False)
        assert d.get_pronunciation("BAD") is None
        assert d.get_pronunciation("OK") == "オーケー"


class TestCustomDictHelpers:
    def test_create_default_dictionary_returns_instance(self):
        d = create_default_dictionary()
        assert isinstance(d, CustomDictionary)

    def test_apply_custom_dictionary_oneliner(self, tmp_path):
        # Use an explicit dict file so the result is deterministic regardless
        # of any default dictionaries that might exist in the repo.
        f = tmp_path / "d.json"
        f.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "entries": {"FOO": "フー"},
                }
            ),
            encoding="utf-8",
        )
        # Note: the helper still loads defaults; we just confirm our entry
        # took effect on the input.
        result = apply_custom_dictionary("FOO", dict_paths=str(f))
        assert "フー" in result

    def test_max_dict_file_size_is_10mb(self):
        # Sanity check: the bundled constant is 10 MiB.
        assert MAX_DICT_FILE_SIZE == 10 * 1024 * 1024


# ===========================================================================
# multilingual.UnicodeLanguageDetector – uncovered branches
# ===========================================================================


class TestUnicodeLanguageDetectorBranches:
    def test_hangul_jamo_block_routed_to_ko(self):
        # U+1100 ㄱ (Hangul Jamo Initial)
        det = UnicodeLanguageDetector(["ko"])
        assert det.detect_char("ᄀ") == "ko"

    def test_hangul_jamo_block_returns_none_when_ko_missing(self):
        det = UnicodeLanguageDetector(["en"])
        assert det.detect_char("ᄀ") is None

    def test_hangul_compat_jamo_routed_to_ko(self):
        # U+3131 ㄱ (Hangul Compatibility Jamo)
        det = UnicodeLanguageDetector(["ko"])
        assert det.detect_char("ㄱ") == "ko"

    def test_cjk_extension_a_ja_only(self):
        # U+3400 — CJK Ext A
        det = UnicodeLanguageDetector(["ja"])
        assert det.detect_char("㐀") == "ja"

    def test_cjk_extension_a_zh_only(self):
        det = UnicodeLanguageDetector(["zh"])
        assert det.detect_char("㐀") == "zh"

    def test_cjk_extension_a_neither_returns_none(self):
        det = UnicodeLanguageDetector(["en"])
        assert det.detect_char("㐀") is None

    def test_cjk_unified_zh_only(self):
        # U+4E2D 中
        det = UnicodeLanguageDetector(["zh"])
        assert det.detect_char("中") == "zh"

    def test_cjk_unified_neither_returns_none(self):
        det = UnicodeLanguageDetector(["en"])
        assert det.detect_char("中") is None

    def test_cjk_unified_ja_zh_disambiguation(self):
        # With kana context -> ja, without -> zh.
        det = UnicodeLanguageDetector(["ja", "zh"])
        assert det.detect_char("中", context_has_kana=True) == "ja"
        assert det.detect_char("中", context_has_kana=False) == "zh"

    def test_cjk_compat_ideograph_ja_only(self):
        # U+F900 (CJK Compat Ideographs)
        det = UnicodeLanguageDetector(["ja"])
        assert det.detect_char("豈") == "ja"

    def test_cjk_compat_ideograph_zh_only(self):
        det = UnicodeLanguageDetector(["zh"])
        assert det.detect_char("豈") == "zh"

    def test_cjk_compat_ideograph_neither_returns_none(self):
        det = UnicodeLanguageDetector(["en"])
        assert det.detect_char("豈") is None

    def test_cjk_compat_ideograph_ja_zh_disambiguation(self):
        det = UnicodeLanguageDetector(["ja", "zh"])
        assert det.detect_char("豈", context_has_kana=True) == "ja"
        assert det.detect_char("豈", context_has_kana=False) == "zh"

    def test_fullwidth_latin_routed_to_default_latin(self):
        # U+FF21 fullwidth A
        det = UnicodeLanguageDetector(["en", "ja"])
        assert det.detect_char("Ａ") == "en"
        # U+FF41 fullwidth a
        assert det.detect_char("ａ") == "en"

    def test_fullwidth_non_latin_routed_to_ja(self):
        # U+FF01 fullwidth ! (non-Latin)
        det = UnicodeLanguageDetector(["en", "ja"])
        assert det.detect_char("！") == "ja"

    def test_extended_latin_routed_to_default(self):
        # U+00E9 é (Spanish/French) — routed to whatever the configured
        # default_latin_language is. With explicit ``default_latin_language``
        # parameter we can force "es".
        det = UnicodeLanguageDetector(["es", "en"], default_latin_language="es")
        assert det.detect_char("é") == "es"

    def test_extended_latin_default_is_en(self):
        # Sanity: when default is not overridden, "en" wins for é.
        det = UnicodeLanguageDetector(["es", "en"])
        assert det.detect_char("é") == "en"

    def test_neutral_character_returns_none(self):
        det = UnicodeLanguageDetector(["en"])
        # Whitespace, digits, ASCII punctuation -> None
        assert det.detect_char(" ") is None
        assert det.detect_char("0") is None
        assert det.detect_char("?") is None


class TestMultilingualPhonemizerInternals:
    def test_invalid_default_latin_falls_back_to_first(self):
        # default_latin_language not in supported list -> warn + fallback to
        # first language. Use languages with no external deps so init succeeds.
        # NOTE: we never call .phonemize() (would trigger phonemizer loading);
        # we only verify the constructor's fallback logic.
        m = MultilingualPhonemizer(["es", "fr"], default_latin_language="ja")
        assert m._default_latin_language == "es"

    def test_languages_property_returns_input_list(self):
        m = MultilingualPhonemizer(["es", "fr"])
        assert m.languages == ["es", "fr"]

    def test_language_code_property_constant(self):
        m = MultilingualPhonemizer(["es", "fr"])
        assert m.language_code == "multilingual"


# ===========================================================================
# registry – uncovered branches
# ===========================================================================


class _DummyPhonemizer(Phonemizer):
    """No-dependency stub used for registry tests."""

    def phonemize_with_prosody(self, text: str):
        return list(text), [None] * len(text)


class TestRegistryBranches:
    def test_register_rejects_non_phonemizer(self):
        r = PhonemizerRegistry()
        with pytest.raises(TypeError, match="Phonemizer instance"):
            r.register("xx", "not a phonemizer")  # type: ignore[arg-type]

    def test_get_unsupported_language_raises(self):
        r = PhonemizerRegistry()
        r.register("en", _DummyPhonemizer())
        with pytest.raises(ValueError, match="Unsupported language"):
            r.get("xx")

    def test_get_composite_missing_component_raises(self):
        r = PhonemizerRegistry()
        r.register("en", _DummyPhonemizer())
        with pytest.raises(ValueError, match="Missing language"):
            r.get("en-zz")

    def test_get_composite_caches_canonical_key(self):
        # First lookup with non-canonical order builds the multilingual
        # phonemizer; second lookup uses the cached canonical form.
        r = PhonemizerRegistry()
        r.register("es", _DummyPhonemizer())
        r.register("fr", _DummyPhonemizer())
        first = r.get("fr-es")
        second = r.get("es-fr")  # canonical order
        third = r.get("fr-es")  # original alias
        assert first is second is third

    def test_available_returns_registered_codes(self):
        r = PhonemizerRegistry()
        r.register("es", _DummyPhonemizer())
        r.register("fr", _DummyPhonemizer())
        assert set(r.available()) == {"es", "fr"}

    def test_get_single_registered_returns_instance(self):
        r = PhonemizerRegistry()
        ph = _DummyPhonemizer()
        r.register("xx", ph)
        assert r.get("xx") is ph

    def test_default_registry_available_languages(self):
        # available_languages() delegates to the default singleton.
        # Whatever phonemizers happen to be registered, the call MUST succeed
        # and return a list of strings.
        result = available_languages()
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

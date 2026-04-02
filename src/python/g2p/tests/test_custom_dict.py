"""Tests for piper_plus_g2p.custom_dict -- CustomDictionary."""

import json

from piper_plus_g2p.custom_dict import CustomDictionary
from tests.conftest import requires_ko


class TestApplyToText:
    def test_apply_to_text(self):
        """apply_to_text replaces dictionary entries in the text."""
        d = CustomDictionary(load_defaults=False)
        d.add_word("NVIDIA", "エヌビディア")
        result = d.apply_to_text("NVIDIAの最新GPU")
        assert "エヌビディア" in result
        assert "NVIDIA" not in result

    def test_case_insensitive(self):
        """Case-insensitive matching works for all-lowercase entries."""
        d = CustomDictionary(load_defaults=False)
        d.add_word("gpu", "ジーピーユー")
        result = d.apply_to_text("GPUとCPU")
        assert "ジーピーユー" in result


class TestJsonV1:
    def test_json_v1_load(self, tmp_path):
        """JSON v1.0 format is loaded correctly."""
        dict_file = tmp_path / "v1.json"
        dict_data = {
            "version": "1.0",
            "entries": {
                "AI": "エーアイ",
                "GPU": "ジーピーユー",
            },
        }
        dict_file.write_text(
            json.dumps(dict_data, ensure_ascii=False),
            encoding="utf-8",
        )

        d = CustomDictionary(dict_paths=str(dict_file), load_defaults=False)
        assert d.get_pronunciation("AI") == "エーアイ"
        assert d.get_pronunciation("GPU") == "ジーピーユー"

    def test_json_v1_apply(self, tmp_path):
        """JSON v1.0 entries are applied to text."""
        dict_file = tmp_path / "v1_apply.json"
        dict_data = {
            "version": "1.0",
            "entries": {
                "TTS": "ティーティーエス",
            },
        }
        dict_file.write_text(
            json.dumps(dict_data, ensure_ascii=False),
            encoding="utf-8",
        )

        d = CustomDictionary(dict_paths=str(dict_file), load_defaults=False)
        result = d.apply_to_text("TTS技術")
        assert "ティーティーエス" in result


class TestJsonV2:
    def test_json_v2_load(self, tmp_path):
        """JSON v2.0 format with priority is loaded correctly."""
        dict_file = tmp_path / "v2.json"
        dict_data = {
            "version": "2.0",
            "entries": {
                "CUDA": {
                    "pronunciation": "クーダ",
                    "priority": 8,
                },
                "PyTorch": {
                    "pronunciation": "パイトーチ",
                    "priority": 7,
                },
            },
        }
        dict_file.write_text(
            json.dumps(dict_data, ensure_ascii=False),
            encoding="utf-8",
        )

        d = CustomDictionary(dict_paths=str(dict_file), load_defaults=False)
        assert d.get_pronunciation("CUDA") == "クーダ"
        assert d.get_pronunciation("PyTorch") == "パイトーチ"

    def test_json_v2_priority(self, tmp_path):
        """Higher priority entries override lower priority ones."""
        dict_file1 = tmp_path / "low.json"
        dict_file2 = tmp_path / "high.json"

        low_data = {
            "version": "2.0",
            "entries": {
                "API": {"pronunciation": "エーピーアイ", "priority": 3},
            },
        }
        high_data = {
            "version": "2.0",
            "entries": {
                "API": {"pronunciation": "アピ", "priority": 9},
            },
        }
        dict_file1.write_text(
            json.dumps(low_data, ensure_ascii=False),
            encoding="utf-8",
        )
        dict_file2.write_text(
            json.dumps(high_data, ensure_ascii=False),
            encoding="utf-8",
        )

        d = CustomDictionary(
            dict_paths=[str(dict_file1), str(dict_file2)],
            load_defaults=False,
        )
        assert d.get_pronunciation("API") == "アピ"


class TestLongestMatch:
    def test_longest_match(self):
        """Longer dictionary entries are matched before shorter ones."""
        d = CustomDictionary(load_defaults=False)
        d.add_word("AI", "エーアイ")
        d.add_word("AI技術", "エーアイギジュツ")

        # Japanese text: longest match should apply first
        result = d.apply_to_text("AI技術の発展")
        assert "エーアイギジュツ" in result

    def test_non_overlapping(self):
        """Non-overlapping entries are both replaced."""
        d = CustomDictionary(load_defaults=False)
        d.add_word("GPU", "ジーピーユー")
        d.add_word("CPU", "シーピーユー")
        result = d.apply_to_text("GPUとCPU")
        assert "ジーピーユー" in result
        assert "シーピーユー" in result


class TestSwedishIntegration:
    """Integration tests: CustomDictionary + SwedishPhonemizer."""

    def test_word_replacement(self):
        """Custom dict overrides default phonemization for a Swedish word."""
        from piper_plus_g2p.swedish import SwedishPhonemizer

        p = SwedishPhonemizer()

        # Default phonemization of "hej"
        default_tokens = p.phonemize("hej")

        # Override "hej" with a custom pronunciation
        d = CustomDictionary(load_defaults=False)
        d.add_word("hej", "hallansen")
        replaced = d.apply_to_text("hej")
        custom_tokens = p.phonemize(replaced)

        assert default_tokens != custom_tokens, (
            "Custom dict should change phonemizer output"
        )

    def test_non_overridden_words_unchanged(self):
        """Words not in the custom dict still use default phonemization."""
        from piper_plus_g2p.swedish import SwedishPhonemizer

        p = SwedishPhonemizer()
        default_tokens = p.phonemize("världen")

        d = CustomDictionary(load_defaults=False)
        d.add_word("hej", "hallansen")
        replaced = d.apply_to_text("världen")
        custom_tokens = p.phonemize(replaced)

        assert default_tokens == custom_tokens

    def test_empty_dict_no_effect(self):
        """Empty custom dict does not alter phonemizer output."""
        from piper_plus_g2p.swedish import SwedishPhonemizer

        p = SwedishPhonemizer()
        text = "God morgon"
        default_tokens = p.phonemize(text)

        d = CustomDictionary(load_defaults=False)
        replaced = d.apply_to_text(text)
        custom_tokens = p.phonemize(replaced)

        assert default_tokens == custom_tokens


@requires_ko
class TestKoreanIntegration:
    """Integration tests: CustomDictionary + KoreanPhonemizer."""

    def test_word_replacement(self):
        """Custom dict overrides default phonemization for a Korean word."""
        from piper_plus_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()

        # Default phonemization of "서울"
        default_tokens = p.phonemize("서울")

        # Override "서울" with a custom pronunciation
        d = CustomDictionary(load_defaults=False)
        d.add_word("서울", "수도")
        replaced = d.apply_to_text("서울")
        custom_tokens = p.phonemize(replaced)

        assert default_tokens != custom_tokens, (
            "Custom dict should change phonemizer output"
        )

    def test_non_overridden_words_unchanged(self):
        """Words not in the custom dict still use default phonemization."""
        from piper_plus_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        default_tokens = p.phonemize("감사합니다")

        d = CustomDictionary(load_defaults=False)
        d.add_word("서울", "수도")
        replaced = d.apply_to_text("감사합니다")
        custom_tokens = p.phonemize(replaced)

        assert default_tokens == custom_tokens

    def test_empty_dict_no_effect(self):
        """Empty custom dict does not alter phonemizer output."""
        from piper_plus_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        text = "안녕하세요"
        default_tokens = p.phonemize(text)

        d = CustomDictionary(load_defaults=False)
        replaced = d.apply_to_text(text)
        custom_tokens = p.phonemize(replaced)

        assert default_tokens == custom_tokens

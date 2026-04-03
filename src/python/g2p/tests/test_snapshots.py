"""Snapshot tests with fixed expected outputs.

These tests use hardcoded expected values to detect regressions.
If a test fails after a dependency upgrade, the expected value
should be reviewed and updated intentionally.
"""

import pytest

from piper_plus_g2p import get_phonemizer

# =====================================================================
# JA snapshots (requires pyopenjtalk)
# =====================================================================


class TestJASnapshots:
    """Fixed JA output snapshots."""

    def test_konnichiwa(self, ja_phonemizer):
        tokens = ja_phonemizer.phonemize("こんにちは")
        assert tokens == ["k", "o", "[", "N_n", "n", "i", "ch", "i", "w", "a"]

    def test_konnichiwa_no_bos_eos(self, ja_phonemizer):
        tokens = ja_phonemizer.phonemize("こんにちは")
        assert "^" not in tokens
        assert "$" not in tokens

    def test_question(self, ja_phonemizer):
        tokens = ja_phonemizer.phonemize("何？")
        assert tokens[-1] == "?"
        assert "n" in tokens

    def test_arigatou(self, ja_phonemizer):
        tokens = ja_phonemizer.phonemize("ありがとうございます")
        assert tokens == [
            "a",
            "[",
            "r",
            "i",
            "]",
            "g",
            "a",
            "t",
            "o",
            "o",
            "g",
            "o",
            "[",
            "z",
            "a",
            "i",
            "m",
            "a",
            "]",
            "s",
            "U",
        ]

    def test_prosody_konnichiwa(self, ja_phonemizer):
        tokens, prosody = ja_phonemizer.phonemize_with_prosody("こんにちは")
        assert len(tokens) == len(prosody)
        # Accent marker "[" has None prosody
        bracket_idx = tokens.index("[")
        assert prosody[bracket_idx] is None


# =====================================================================
# EN snapshots (requires g2p-en)
# =====================================================================


class TestENSnapshots:
    """Fixed EN output snapshots."""

    def test_hello(self, en_phonemizer):
        tokens = en_phonemizer.phonemize("Hello")
        assert tokens == ["h", "ə", "l", "\u02c8", "o", "ʊ"]

    def test_goodbye_with_period(self, en_phonemizer):
        tokens = en_phonemizer.phonemize("Goodbye.")
        assert tokens == [
            "ɡ",
            "\u02cc",
            "ʊ",
            "d",
            "b",
            "\u02c8",
            "a",
            "ɪ",
            ".",
        ]

    def test_how_are_you(self, en_phonemizer):
        tokens = en_phonemizer.phonemize("How are you?")
        assert tokens == [
            "h",
            "\u02c8",
            "a",
            "ʊ",
            " ",
            "ɑ",
            "\u02d0",
            "ɹ",
            " ",
            "j",
            "u",
            "\u02d0",
            "?",
        ]

    def test_hello_world(self, en_phonemizer):
        tokens = en_phonemizer.phonemize("Hello, world!")
        assert tokens == [
            "h",
            "ə",
            "l",
            "\u02c8",
            "o",
            "ʊ",
            ",",
            " ",
            "w",
            "\u02c8",
            "ɜ",
            "\u02d0",
            "l",
            "d",
            "!",
        ]

    def test_prosody_hello(self, en_phonemizer):
        tokens, prosody = en_phonemizer.phonemize_with_prosody("Hello")
        assert len(tokens) == len(prosody)
        # Stress marker should have a2=2
        stress_idx = tokens.index("\u02c8")
        assert prosody[stress_idx].a2 == 2


# =====================================================================
# ZH snapshots (requires pypinyin)
# =====================================================================


class TestZHSnapshots:
    """Fixed ZH output snapshots."""

    @pytest.fixture(autouse=True)
    def _check_pypinyin(self):
        pytest.importorskip("pypinyin")

    def test_nihao(self):
        zh = get_phonemizer("zh")
        tokens = zh.phonemize("你好")
        assert tokens == ["n", "i", "tone2", "x", "aʊ", "tone3"]

    def test_xiexie(self):
        zh = get_phonemizer("zh")
        tokens = zh.phonemize("谢谢")
        assert tokens == ["ɕ", "iɛ", "tone4", "ɕ", "iɛ", "tone4"]

    def test_weather(self):
        zh = get_phonemizer("zh")
        tokens = zh.phonemize("今天天气很好。")
        assert tokens == [
            "tɕ",
            "in",
            "tone1",
            "tʰ",
            "iɛn",
            "tone1",
            "tʰ",
            "iɛn",
            "tone1",
            "tɕʰ",
            "i",
            "tone4",
            "x",
            "ən",
            "tone2",
            "x",
            "aʊ",
            "tone3",
            ".",
        ]


# =====================================================================
# ES snapshots (no dependencies)
# =====================================================================


class TestESSnapshots:
    """Fixed ES output snapshots."""

    def test_hola(self):
        tokens = get_phonemizer("es").phonemize("Hola")
        assert tokens == ["\u02c8", "o", "l", "a"]

    def test_buenos_dias(self):
        tokens = get_phonemizer("es").phonemize("Buenos días")
        assert tokens == [
            "b",
            "\u02c8",
            "u",
            "e",
            "n",
            "o",
            "s",
            " ",
            "d",
            "\u02c8",
            "i",
            "a",
            "s",
        ]

    def test_question(self):
        tokens = get_phonemizer("es").phonemize("¿Hola, cómo estás?")
        assert tokens == [
            "¿",
            "\u02c8",
            "o",
            "l",
            "a",
            ",",
            " ",
            "k",
            "\u02c8",
            "o",
            "m",
            "o",
            " ",
            "e",
            "s",
            "t",
            "\u02c8",
            "a",
            "s",
            "?",
        ]

    def test_el_gato(self):
        tokens = get_phonemizer("es").phonemize("El gato come pescado.")
        assert tokens == [
            "e",
            "l",
            " ",
            "ɡ",
            "\u02c8",
            "a",
            "t",
            "o",
            " ",
            "k",
            "\u02c8",
            "o",
            "m",
            "e",
            " ",
            "p",
            "e",
            "s",
            "k",
            "\u02c8",
            "a",
            "ð",
            "o",
            ".",
        ]

    def test_prosody_hola(self):
        tokens, prosody = get_phonemizer("es").phonemize_with_prosody("Hola")
        assert len(tokens) == len(prosody)
        # Stress marker has a2=2
        assert prosody[0].a2 == 2  # stress marker position


# =====================================================================
# FR snapshots (no dependencies)
# =====================================================================


class TestFRSnapshots:
    """Fixed FR output snapshots."""

    def test_bonjour(self):
        tokens = get_phonemizer("fr").phonemize("Bonjour")
        assert tokens == ["b", "ɔ̃", "ʒ", "u", "ʁ"]

    def test_comment_allez_vous(self):
        tokens = get_phonemizer("fr").phonemize("Comment allez-vous?")
        assert tokens == [
            "k",
            "o",
            "m",
            "ɑ̃",
            " ",
            "a",
            "l",
            "ə",
            " ",
            "v",
            "u",
            "?",
        ]

    def test_merci_beaucoup(self):
        tokens = get_phonemizer("fr").phonemize("Merci beaucoup.")
        assert tokens == [
            "m",
            "ɛ",
            "ʁ",
            "s",
            "i",
            " ",
            "b",
            "o",
            "k",
            "u",
            ".",
        ]

    def test_je_suis(self):
        tokens = get_phonemizer("fr").phonemize("Je suis content.")
        assert tokens == [
            "ʒ",
            " ",
            "s",
            "ɥ",
            "i",
            " ",
            "k",
            "ɔ̃",
            "t",
            "ɑ̃",
            ".",
        ]


# =====================================================================
# PT snapshots (no dependencies)
# =====================================================================


class TestPTSnapshots:
    """Fixed PT output snapshots."""

    def test_bom_dia(self):
        tokens = get_phonemizer("pt").phonemize("Bom dia.")
        assert tokens == ["b", "õ", " ", "dʒ", "i", "a", "."]

    def test_obrigado(self):
        tokens = get_phonemizer("pt").phonemize("Obrigado.")
        assert tokens == ["o", "b", "ʁ", "i", "ɡ", "a", "d", "u", "."]

    def test_brasil(self):
        tokens = get_phonemizer("pt").phonemize("O Brasil é grande.")
        assert tokens == [
            "o",
            " ",
            "b",
            "ʁ",
            "a",
            "z",
            "i",
            "w",
            " ",
            "ɛ",
            " ",
            "ɡ",
            "ʁ",
            "ã",
            "dʒ",
            "i",
            ".",
        ]

    def test_como_voce(self):
        tokens = get_phonemizer("pt").phonemize("Olá, como você está?")
        assert tokens == [
            "o",
            "l",
            "a",
            ",",
            " ",
            "k",
            "o",
            "m",
            "u",
            " ",
            "v",
            "o",
            "s",
            "e",
            " ",
            "e",
            "s",
            "t",
            "a",
            "?",
        ]

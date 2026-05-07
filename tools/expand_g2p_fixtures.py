#!/usr/bin/env python3
"""Expand `tests/fixtures/g2p/phoneme_test_cases.json` toward FR-TEST-1
(8 languages × 50+ cases) for cross-runtime parity.

Adds carefully chosen test cases per language, picking inputs that exercise
distinct phoneme paths (numbers, punctuation, long sentences, edge cases,
language-specific features). Inputs are short enough to keep fixtures
reviewable and golden generation fast.

Usage::

    python tools/expand_g2p_fixtures.py            # add cases, save
    python tools/expand_g2p_fixtures.py --dry-run  # show counts only
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Per-language case generators. Each item is (input, description, optional
# expected_token_count_min). The description is mandatory; the count_min is
# optional (None means we let the structural test pass without that guard
# and let the byte-for-byte parity catch regressions).
# ---------------------------------------------------------------------------

EN_CASES: list[tuple[str, str, int | None]] = [
    ("a", "Single short vowel — minimal English G2P", 1),
    ("the", "Common function word with theta", 2),
    ("cat", "CVC word — three core phonemes", 3),
    ("dog", "Voiced stop coda", 3),
    ("bird", "rhotacised vowel + voiced stop", 3),
    ("school", "Initial consonant cluster + long u", 4),
    ("strength", "Triple-cluster onset, fricative coda", 5),
    ("photograph", "G2P stress placement on antepenult", 7),
    ("photography", "Stress shift vs photograph", 8),
    ("Mississippi", "Repeated /s/ + double consonants + final /i/", 8),
    ("Albuquerque", "Loanword, multiple syllables", 7),
    ("through", "Silent letters + theta", 3),
    ("knight", "Silent k + diphthong", 3),
    ("rhythm", "Syllabic m, no written vowel between consonants", 4),
    ("xylophone", "Initial /z/ from x", 7),
    ("zebra", "Initial /z/ + diphthong", 4),
    ("queue", "Multi-letter spelling for /kjuː/", 2),
    ("uniform", "Initial palatal-glide /j/", 6),
    ("hour", "Silent h + diphthong", 2),
    ("colonel", "Highly irregular spelling", 4),
    ("schedule", "American /sk/ vs British /ʃ/", 6),
    ("0", "Digit zero", 1),
    ("1", "Digit one", 1),
    ("123", "Three digit number", 1),
    ("3.14", "Decimal number", 1),
    ("100", "Round hundred", 1),
    ("Hello, world!", "Greeting with punctuation", 4),
    ("Good morning, everyone.", "Sentence with punctuation and stress", 8),
    ("She doesn't know.", "Contraction handling", 5),
    ("It's 3 o'clock.", "Mixed digits and apostrophe", 5),
    ("I love New York.", "Proper noun handling", 5),
    ("ChatGPT and GitHub", "All-caps acronyms", 6),
    ("The cat sat on the mat.", "Classic short sentence", 8),
    ("a-b-c", "Hyphen-separated letters", 3),
    ("\"quoted\" text", "ASCII quotes", 4),
    ("e.g. and i.e.", "Abbreviations with periods", 4),
    ("uh-huh", "Expressive lowercase token", 2),
    ("aaaaa", "Repeated vowels", 1),
    ("xyz", "Sequence of less-frequent letters", 3),
    ("supercalifragilistic", "Very long synthetic word", 12),
    ("naïve", "Latin-1 diaeresis on i", 3),
    ("café", "Latin-1 acute on e", 3),
    ("résumé", "Two acute accents", 4),
    ("hello world how are you doing today", "Long sentence", 14),
    ("UPPERCASE", "All caps word", 3),
    ("MixedCase", "Camel case", 3),
    ("'quote'", "Single quotes only", 2),
]

ES_CASES: list[tuple[str, str, int | None]] = [
    ("sí", "Affirmation with acute on i", 1),
    ("no", "Spanish negation", 1),
    ("hola", "Common greeting", 4),
    ("adiós", "Goodbye with diphthong + accent", 4),
    ("España", "Country name with ñ", 5),
    ("año", "Year word, ñ between vowels", 3),
    ("niño", "Child word, palatal nasal", 3),
    ("mañana", "Tomorrow / morning", 5),
    ("señor", "Mr. with palatal nasal", 4),
    ("doña", "Title for women", 3),
    ("piña", "Pineapple", 3),
    ("muñeca", "Doll", 5),
    ("perro", "Dog with double r (trill)", 4),
    ("carro", "Car with double r", 4),
    ("río", "River with stressed i", 3),
    ("queso", "Cheese — qu = /k/", 4),
    ("aquí", "Here, qu + acute i", 4),
    ("pequeño", "Small, qu + ñ", 6),
    ("guitarra", "Guitar, gu + double r", 6),
    ("cinco", "Five", 4),
    ("once", "Eleven (zero-tone)", 4),
    ("trece", "Thirteen, soft c", 4),
    ("cien", "Hundred with diphthong", 3),
    ("mil", "Thousand", 3),
    ("Buenos días", "Good morning", 7),
    ("Muchas gracias", "Thank you very much", 8),
    ("Por favor", "Please", 5),
    ("¿Dónde está el baño?", "Where is the bathroom — full question", 11),
    ("¡Qué bueno!", "Exclamation with inverted mark", 5),
    ("0", "Digit", 1),
    ("100", "Hundred", 1),
    ("3.14", "Decimal — Spanish writes 3,14 but ASCII test", 1),
    ("Madrid es la capital.", "Sentence with proper noun", 8),
    ("Yo soy estudiante.", "I am a student", 7),
    ("Tú eres mi amigo.", "You are my friend", 7),
    ("Hasta luego", "See you later", 6),
]

FR_CASES: list[tuple[str, str, int | None]] = [
    ("oui", "Yes — diphthong", 2),
    ("non", "No — nasal vowel", 2),
    ("salut", "Hi", 4),
    ("bonjour", "Good day", 5),
    ("au revoir", "Goodbye — liaison candidate", 6),
    ("merci", "Thank you", 5),
    ("ça va", "How's it going", 4),
    ("français", "French language with cedilla", 5),
    ("garçon", "Boy with cedilla", 5),
    ("leçon", "Lesson with cedilla", 4),
    ("français", "Language adjective", 5),
    ("être", "To be — circumflex", 3),
    ("forêt", "Forest — circumflex", 4),
    ("hôtel", "Hotel — circumflex", 4),
    ("Noël", "Christmas — diaeresis", 3),
    ("naïf", "Naive (m.) — diaeresis", 3),
    ("où", "Where — grave accent", 1),
    ("là", "There — grave", 1),
    ("après", "After — grave", 4),
    ("très", "Very — grave", 3),
    ("école", "School — acute", 4),
    ("élève", "Student — acute + grave", 4),
    ("café", "Coffee — acute", 4),
    ("roi", "King — diphthong /wa/", 2),
    ("loi", "Law — diphthong", 2),
    ("noir", "Black — back diphthong + r", 3),
    ("oiseau", "Bird — multi-vowel", 4),
    ("monsieur", "Sir — irregular pronunciation", 5),
    ("aujourd'hui", "Today — apostrophe", 6),
    ("c'est", "It is — contraction", 3),
    ("un", "Indefinite article — nasal", 1),
    ("une", "Indefinite (f.)", 2),
    ("dix", "Ten", 2),
    ("vingt", "Twenty — silent t", 2),
    ("cent", "Hundred — silent t", 2),
    ("0", "Digit", 1),
    ("Bonjour, comment allez-vous ?", "Polite greeting + space-question", 9),
    ("Je m'appelle Pierre.", "My name is Pierre", 6),
    ("Voulez-vous danser ?", "Will you dance", 6),
    ("Quelle heure est-il ?", "What time is it", 5),
]

PT_CASES: list[tuple[str, str, int | None]] = [
    ("sim", "Yes — nasal vowel", 2),
    ("não", "No — nasal diphthong with tilde", 2),
    ("oi", "Hi (BR)", 2),
    ("olá", "Hi (PT/BR)", 3),
    ("obrigado", "Thanks (m.)", 6),
    ("obrigada", "Thanks (f.)", 6),
    ("Brasil", "Country name", 5),
    ("Portugal", "Country name", 6),
    ("São Paulo", "City with tilde and capital", 5),
    ("açaí", "Loanword with cedilla + acute", 4),
    ("avião", "Airplane — nasal diphthong", 4),
    ("coração", "Heart — palatalised + nasal diphthong", 6),
    ("anão", "Dwarf — nasal diphthong", 3),
    ("mãe", "Mother — nasal diphthong", 2),
    ("pão", "Bread", 2),
    ("limões", "Lemons (pl.) — nasal diphthong oe", 4),
    ("fé", "Faith — acute on e", 1),
    ("pé", "Foot", 1),
    ("vovó", "Grandma — acute o", 3),
    ("você", "You (formal)", 3),
    ("comê-lo", "To eat it — circumflex", 4),
    ("dê-me", "Give me — clitic", 3),
    ("já", "Already — acute", 2),
    ("até", "Until — acute", 3),
    ("número", "Number — acute on u", 5),
    ("último", "Last — acute on u", 5),
    ("açúcar", "Sugar — cedilla + acute", 5),
    ("dia", "Day", 2),
    ("noite", "Night", 4),
    ("amor", "Love", 3),
    ("paz", "Peace", 3),
    ("luz", "Light", 3),
    ("cinco", "Five", 5),
    ("sete", "Seven", 4),
    ("Bom dia", "Good morning", 5),
    ("Boa tarde", "Good afternoon", 6),
    ("Como você está?", "How are you", 7),
    ("Eu te amo.", "I love you", 5),
    ("0", "Digit", 1),
    ("100", "Hundred", 1),
]

SV_CASES: list[tuple[str, str, int | None]] = [
    ("ja", "Yes", 2),
    ("nej", "No", 2),
    ("hej", "Hi", 2),
    ("hejdå", "Bye — å", 4),
    ("tack", "Thanks", 3),
    ("varsågod", "You're welcome — å", 7),
    ("Sverige", "Country name — soft g", 5),
    ("Stockholm", "Capital city", 7),
    ("Göteborg", "Gothenburg — ö + soft g", 6),
    ("Skåne", "Region name with å", 4),
    ("öl", "Beer — ö", 2),
    ("är", "To be (3sg.) — ä", 1),
    ("å", "Single rounded back vowel", 1),
    ("ö", "Single rounded front vowel", 1),
    ("ä", "Single open front vowel", 1),
    ("åtta", "Eight — å", 3),
    ("nio", "Nine", 3),
    ("tio", "Ten", 3),
    ("hundra", "Hundred", 5),
    ("tusen", "Thousand", 4),
    ("blå", "Blue — å", 2),
    ("grön", "Green — ö", 3),
    ("röd", "Red — ö", 2),
    ("vit", "White", 3),
    ("svart", "Black", 5),
    ("kärlek", "Love — ä + soft k? (rule says hard before ä)", 5),
    ("stjärna", "Star — sj-sound", 5),
    ("sjö", "Lake — sj + ö", 2),
    ("kyckling", "Chicken — soft k + ng", 6),
    ("smörgås", "Sandwich — ö + å", 6),
    ("räka", "Shrimp — ä + soft k? expected hard", 4),
    ("flicka", "Girl", 5),
    ("pojke", "Boy — j", 5),
    ("Tack så mycket", "Thanks a lot", 8),
    ("God morgon", "Good morning", 6),
    ("Hej hej", "Casual hi-hi", 4),
    ("Vad heter du?", "What's your name", 7),
    ("0", "Digit", 1),
    ("100", "Hundred", 1),
    ("kaffe", "Coffee", 4),
    ("te", "Tea", 2),
    ("vatten", "Water", 5),
]

ZH_CASES: list[tuple[str, str, int | None]] = [
    ("是", "Yes / be — single character", 1),
    ("不", "No / not", 1),
    ("我", "I / me", 1),
    ("你", "You", 1),
    ("他", "He", 1),
    ("她", "She", 1),
    ("我们", "We", 2),
    ("你们", "You (pl.)", 2),
    ("他们", "They (m.)", 2),
    ("早上好", "Good morning", 3),
    ("晚上好", "Good evening", 3),
    ("再见", "Goodbye", 2),
    ("谢谢你", "Thank you", 3),
    ("不客气", "You're welcome", 3),
    ("对不起", "Sorry", 3),
    ("没关系", "It's okay", 3),
    ("一", "One", 1),
    ("二", "Two", 1),
    ("三", "Three", 1),
    ("四", "Four", 1),
    ("五", "Five", 1),
    ("六", "Six", 1),
    ("七", "Seven", 1),
    ("八", "Eight", 1),
    ("九", "Nine", 1),
    ("十", "Ten", 1),
    ("一百", "Hundred", 2),
    ("一千", "Thousand", 2),
    ("一万", "Ten thousand", 2),
    ("中国", "China", 2),
    ("日本", "Japan", 2),
    ("北京", "Beijing", 2),
    ("上海", "Shanghai", 2),
    ("世界", "World", 2),
    ("电脑", "Computer", 2),
    ("手机", "Mobile phone", 2),
    ("Hello, 你好!", "ZH-EN code-switch with greeting", 4),
    ("我用 GPS 导航", "ZH-EN with acronym GPS", 4),
    ("我喜欢 Python", "ZH-EN with loanword Python", 3),
    ("ChatGPT 很厉害", "ZH-EN sentence start", 3),
    ("Apple 公司", "Loanword + Chinese", 2),
    ("0", "Digit zero", 1),
    ("100", "Hundred", 1),
    ("。", "Single period", 1),
    ("！", "Single exclamation", 1),
    ("，", "Comma alone", 1),
]

JA_CASES: list[tuple[str, str, int | None]] = [
    ("はい", "Yes (formal)", 2),
    ("いいえ", "No (formal)", 2),
    ("ありがとう", "Thank you", 5),
    ("すみません", "Excuse me / sorry", 5),
    ("おはよう", "Good morning (informal)", 4),
    ("おやすみ", "Good night", 4),
    ("お疲れ様", "Good work / thank you (formal)", 5),
    ("いただきます", "Bon appétit (before meal)", 5),
    ("ごちそうさま", "After meal", 5),
    ("私は学生です。", "I am a student", 8),
    ("あなたは誰ですか？", "Who are you", 8),
    ("何時ですか？", "What time", 5),
    ("どこですか？", "Where", 5),
    ("一", "One", 1),
    ("二", "Two", 1),
    ("三", "Three", 1),
    ("四", "Four", 1),
    ("五", "Five", 1),
    ("六", "Six", 1),
    ("七", "Seven", 1),
    ("八", "Eight", 1),
    ("九", "Nine", 1),
    ("十", "Ten", 1),
    ("百", "Hundred", 1),
    ("千", "Thousand", 1),
    ("万", "Ten thousand", 1),
    ("赤", "Red", 1),
    ("青", "Blue", 1),
    ("白", "White", 1),
    ("黒", "Black", 1),
    ("猫", "Cat", 1),
    ("犬", "Dog", 1),
    ("鳥", "Bird", 1),
    ("魚", "Fish", 1),
    ("水", "Water", 1),
    ("火", "Fire", 1),
    ("山", "Mountain", 1),
    ("川", "River", 1),
    ("海", "Sea", 1),
    ("空", "Sky", 1),
    ("雨", "Rain", 1),
    ("雪", "Snow", 1),
    ("月", "Moon", 1),
    ("日", "Sun / day", 1),
    ("お元気ですか？", "How are you", 6),
    ("初めまして", "Nice to meet you", 4),
]

KO_CASES: list[tuple[str, str, int | None]] = [
    ("네", "Yes", 1),
    ("아니요", "No", 2),
    ("안녕", "Hi (casual)", 2),
    ("안녕하세요", "Hello (formal)", 4),
    ("안녕히 가세요", "Goodbye (to leaving person)", 5),
    ("감사합니다", "Thank you (formal)", 4),
    ("죄송합니다", "I'm sorry", 4),
    ("천만에요", "You're welcome", 3),
    ("실례합니다", "Excuse me", 4),
    ("좋은 아침", "Good morning", 4),
    ("좋은 밤", "Good night", 3),
    ("이름이 뭐예요?", "What's your name", 6),
    ("어디예요?", "Where is it", 4),
    ("얼마예요?", "How much", 4),
    ("일", "One", 1),
    ("이", "Two", 1),
    ("삼", "Three", 1),
    ("사", "Four", 1),
    ("오", "Five", 1),
    ("육", "Six", 1),
    ("칠", "Seven", 1),
    ("팔", "Eight", 1),
    ("구", "Nine", 1),
    ("십", "Ten", 1),
    ("백", "Hundred", 1),
    ("천", "Thousand", 1),
    ("만", "Ten thousand", 1),
    ("빨강", "Red", 1),
    ("파랑", "Blue", 1),
    ("초록", "Green", 1),
    ("노랑", "Yellow", 1),
    ("물", "Water", 1),
    ("불", "Fire", 1),
    ("하늘", "Sky", 2),
    ("바다", "Sea", 2),
    ("산", "Mountain", 1),
    ("나라", "Country", 2),
    ("사람", "Person", 2),
    ("학교", "School", 2),
    ("선생님", "Teacher", 3),
    ("학생", "Student", 2),
    ("친구", "Friend", 2),
    ("가족", "Family", 2),
    ("사랑해요", "I love you", 4),
    ("한국어", "Korean language", 3),
    ("커피", "Coffee", 2),
    ("차", "Tea / car", 1),
    ("어머니", "Mother", 3),
    ("아버지", "Father", 3),
    ("형", "Older brother", 1),
    ("누나", "Older sister (m. speaker)", 2),
    ("동생", "Younger sibling", 2),
]


CASES: dict[str, list[tuple[str, str, int | None]]] = {
    "en": EN_CASES,
    "es": ES_CASES,
    "fr": FR_CASES,
    "pt": PT_CASES,
    "sv": SV_CASES,
    "zh": ZH_CASES,
    "ja": JA_CASES,
    "ko": KO_CASES,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="tests/fixtures/g2p/phoneme_test_cases.json",
        help="Fixture path (read+write)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print expected counts without modifying the fixture",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    in_path = (repo_root / args.input).resolve()
    fixture = json.loads(in_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = fixture.get("test_cases", [])

    existing_inputs: set[tuple[str, str]] = {
        (c["language"], c["input"]) for c in cases
    }

    added_per_lang: dict[str, int] = {lang: 0 for lang in CASES}
    new_cases: list[dict[str, Any]] = []
    for lang, items in CASES.items():
        for text, desc, count_min in items:
            if (lang, text) in existing_inputs:
                continue
            entry: dict[str, Any] = {
                "language": lang,
                "input": text,
                "description": desc,
            }
            if count_min is not None:
                entry["expected_token_count_min"] = count_min
            new_cases.append(entry)
            added_per_lang[lang] += 1

    print("Per-language additions:")
    for lang, n in added_per_lang.items():
        before = sum(1 for c in cases if c["language"] == lang)
        print(f"  {lang}: {before:3d} → {before + n:3d}  (+{n})")
    print(f"Total: {len(cases)} → {len(cases) + len(new_cases)} (+{len(new_cases)})")

    if args.dry_run:
        return 0

    # Append new cases (preserve existing order so byte diffs stay readable).
    cases.extend(new_cases)
    fixture = copy.deepcopy(fixture)
    fixture["test_cases"] = cases
    # Bump version so the loader-side schema check stays explicit.
    fixture["version"] = max(int(fixture.get("version", 1)), 2)

    out = json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"
    in_path.write_text(out, encoding="utf-8")
    print(f"Wrote expanded fixture to {in_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

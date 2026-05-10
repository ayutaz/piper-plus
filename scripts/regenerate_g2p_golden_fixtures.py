#!/usr/bin/env python3
"""Regenerate ES/PT/FR/SV golden phoneme drift fixtures.

Source of truth: the rule-based phonemizers in
``src/python/g2p/piper_plus_g2p/{spanish,portuguese,french,swedish}.py``.

Output:
    ``tests/fixtures/g2p/{es,pt,fr,sv}_golden.json``

Each fixture pins the *current* phoneme output of the implementation for a
matrix of words covering the rules listed in CLAUDE.md (per-language
"必須カバー"). The golden values are the implementation's actual output;
this is intentional — the test detects *drift* (any rule change) rather than
asserting linguistic ideal values.

Usage::

    python scripts/regenerate_g2p_golden_fixtures.py            # regenerate
    python scripts/regenerate_g2p_golden_fixtures.py --check    # CI: drift gate
    python scripts/regenerate_g2p_golden_fixtures.py --lang es  # one language

The fixture path layout matches ``tests/fixtures/g2p/zh_en_loanword_matrix.json``
and is consumed by ``src/python/g2p/tests/test_golden_fixtures.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/g2p"
G2P_PKG = REPO_ROOT / "src/python/g2p"

# Make the in-tree package importable when run as a stand-alone script.
sys.path.insert(0, str(G2P_PKG))


# ---------------------------------------------------------------------------
# Per-language test matrices
#
# (text, notes) tuples. ``notes`` documents which rule each case exercises so
# that a future drift failure is easy to interpret.
# ---------------------------------------------------------------------------

ES_CASES: list[tuple[str, str]] = [
    # Basic
    ("hola", "basic word"),
    ("gracias", "basic word"),
    ("sí", "accent on i"),
    ("no", "function word, no stress"),
    ("bueno", "diphthong ue"),
    ("día", "accent on i, hiatus"),
    ("casa", "basic word"),
    ("agua", "spirantization g→ɣ intervocalic"),
    # Double consonants
    ("perro", "rr digraph"),
    ("carro", "rr digraph"),
    ("lluvia", "ll → ʝ"),
    ("calle", "ll → ʝ"),
    # Spirantization
    ("gato", "g initial (no spirantization)"),
    ("haba", "b spirantization between vowels (silent h)"),
    ("vida", "v→b, d spirantization"),
    # ñ
    ("mañana", "ñ → ɲ"),
    ("niño", "ñ → ɲ"),
    ("año", "ñ → ɲ initial-ish"),
    # ch / qu / gu
    ("chico", "ch → tʃ"),
    ("queso", "qu → k"),
    ("guitarra", "gui → gi (silent u), rr digraph"),
    ("guerra", "gue → ge (silent u)"),
    # Accents
    ("canción", "accent on penult o"),
    ("café", "accent on final e"),
    ("fácil", "accent on a"),
    ("música", "accent on antepenult u"),
    # Vowel sequences
    ("hierro", "ie diphthong + rr (silent h)"),
    ("piedra", "ie diphthong + dr cluster"),
    ("ciudad", "iu diphthong"),
    # Function words (no stress)
    ("de", "function word"),
    ("la", "function word"),
    ("el", "function word"),
    ("en", "function word"),
    ("y", "function word"),
    # Clusters
    ("transporte", "transp- cluster"),
    ("obstáculo", "bs cluster + accent"),
    ("instrumento", "nstr cluster"),
    # x / z / c
    ("zapato", "z → s (seseo)"),
    ("cinco", "ce/ci → s"),
    ("examen", "x intervocalic"),
    # Common verbs / adjectives
    ("comer", "stress on -er ending"),
    ("vivir", "ir verb"),
    ("hablar", "ar verb (silent h)"),
    ("rojo", "j → x"),
    ("amigo", "stress on penult"),
    # Edge cases
    ("hueso", "silent h before ue"),
    ("yerno", "y as consonant"),
    ("quien", "qu + ie"),
    ("ahora", "silent h between vowels"),
    ("cero", "ce → s"),
    ("rápido", "rr at word start (single r)"),
]

PT_CASES: list[tuple[str, str]] = [
    # Basic
    ("oi", "basic"),
    ("bom", "nasal om"),
    ("obrigado", "stress on -ga-"),
    ("brasil", "coda l vocalisation"),
    # Nasals
    ("irmã", "ã nasal"),
    ("entender", "en nasal"),
    ("sim", "im → ĩ"),
    ("limão", "ão diphthong"),
    ("um", "um nasal"),
    ("manhã", "nh + ã"),
    ("maçã", "ç + ã"),
    # nh / lh / ch
    ("melhor", "lh"),
    ("filho", "lh"),
    ("chão", "ch + ão"),
    ("chave", "ch initial"),
    # Final reduction
    ("cidade", "final e → i, palatalisation"),
    ("novo", "final o → u"),
    ("amigo", "final o → u"),
    ("verde", "final e → i"),
    # Coda l
    ("animal", "coda l → w"),
    ("papel", "coda l → w"),
    # Intervocalic s
    ("mesa", "s → z intervocalic"),
    ("casa", "s → z intervocalic"),
    # Palatalisation
    ("tia", "ti → tʃi"),
    ("dia", "di → dʒi"),
    ("verdade", "stress + final e palatalisation"),
    ("tio", "ti palatalisation"),
    # ç / r / rr
    ("aço", "ç → s"),
    ("carro", "rr"),
    ("rato", "initial r → ʁ"),
    ("para", "intervocalic single r → ɾ"),
    # Stress / accent
    ("café", "final é stress"),
    ("você", "final ê stress"),
    ("também", "final em nasal"),
    ("história", "antepenult stress + ia"),
    # Function words
    ("de", "function word"),
    ("o", "function word"),
    ("a", "function word"),
    ("e", "function word"),
    ("que", "function word"),
    # Verbs / common
    ("falar", "ar verb"),
    ("comer", "er verb"),
    ("partir", "ir verb"),
    ("muito", "ui diphthong"),
    ("não", "ão diphthong"),
    ("ontem", "stress + em nasal"),
    # x irregular
    ("texto", "x → s/ks heuristic"),
    ("exemplo", "intervocalic x"),
    # Common nouns
    ("pão", "ão"),
    ("amor", "final r"),
]

FR_CASES: list[tuple[str, str]] = [
    # Basic
    ("oui", "basic ui"),
    ("non", "nasal on"),
    ("merci", "basic"),
    ("bonjour", "on nasal + jour"),
    # Nasals
    ("bon", "on nasal"),
    ("vin", "in nasal"),
    ("fin", "in nasal"),
    ("un", "un nasal"),
    ("blanc", "an nasal + silent c"),
    ("temps", "em nasal + silent ps"),
    # Silent final consonants
    ("petit", "silent t"),
    ("grand", "silent d"),
    ("parle", "silent e"),
    ("nez", "silent z"),
    ("trop", "silent p"),
    # Liaison (multi-word)
    ("les amis", "z-liaison"),
    ("mes amis", "z-liaison"),
    ("un ami", "n-liaison"),
    ("très important", "z-liaison"),
    # Élision
    ("l'eau", "l-elision"),
    ("j'ai", "j-elision"),
    ("c'est", "c-elision"),
    ("n'a", "n-elision"),
    ("qu'est", "qu-elision"),
    # ille / eille
    ("famille", "ille → ij"),
    ("soleil", "eil → ɛj"),
    ("oreille", "eille → ɛj"),
    ("ville", "exception ille → il"),
    ("mille", "exception ille → il"),
    # Accents
    ("été", "é → e"),
    ("où", "où → u"),
    ("à", "à → a"),
    ("ça", "ç → s"),
    ("être", "ê → ɛ"),
    # ER as EHR exceptions
    ("hier", "exception er → jɛʁ"),
    ("fier", "exception er → fjɛʁ"),
    ("cher", "exception er → ʃɛʁ"),
    # Common digraphs
    ("eau", "eau → o"),
    ("au", "au → o"),
    ("ou", "ou → u"),
    ("oi", "oi → wa"),
    ("ai", "ai → ɛ"),
    # Common words
    ("maison", "ai + nasal on"),
    ("matin", "in nasal"),
    ("femme", "irregular e → a"),
    ("monsieur", "irregular pronunciation"),
    ("aujourd'hui", "elision + ui"),
    # ch / gn / ph
    ("chat", "ch → ʃ"),
    ("agneau", "gn → ɲ"),
    ("photo", "ph → f"),
    # Common verbs
    ("manger", "-er verb"),
    ("aller", "-er irregular"),
    ("avoir", "common irreg verb"),
]

SV_CASES: list[tuple[str, str]] = [
    # Basic
    ("hej", "basic greeting"),
    ("ja", "basic"),
    ("nej", "basic"),
    ("god", "g + back → ɡ"),
    # sj-sound
    ("sjö", "sj → ɧ"),
    ("skön", "sk + front vowel → ɧ"),
    ("station", "tion suffix"),
    ("religion", "tion-like suffix"),
    # tj-sound
    ("tjugo", "tj → ɕ"),
    ("kjol", "kj → ɕ"),
    ("kär", "k + front → ɕ"),
    # Retroflex (r + C cascade)
    ("kort", "rt → retroflex"),
    ("hjärta", "rt retroflex inside"),
    ("mars", "rs retroflex"),
    ("svart", "rt retroflex"),
    # Soft / hard k
    ("katt", "k + back → k"),
    ("kö", "k + front → ɕ"),
    ("kall", "k + back → k"),
    ("köpa", "k + front → ɕ"),
    # Soft / hard g
    ("gärna", "g + front → j"),
    ("gata", "g + back → ɡ"),
    ("ge", "g + front → j"),
    ("gick", "g + i + ck"),
    # Quantity (length encoded in vowel quality)
    ("matt", "short a + double tt"),
    ("mat", "long a"),
    ("vill", "short i"),
    ("vi", "long i"),
    # Loanword suffixes
    ("nation", "tion suffix"),
    ("pension", "sion suffix"),
    ("garage", "age suffix"),
    # Common words
    ("tack", "ck digraph"),
    ("fika", "f + i"),
    ("flicka", "ck"),
    ("pojke", "j after consonant"),
    ("svenska", "sv cluster"),
    ("Sverige", "country name"),
    # ng
    ("ung", "ng → ŋ"),
    ("lång", "å + ng"),
    ("säng", "ng → ŋ"),
    # Vowels
    ("hus", "u long"),
    ("hund", "u + nd"),
    ("öl", "ö → ø"),
    ("åka", "å → o"),
    ("är", "ä → ɛ"),
    # Function-y short words
    ("att", "function-y"),
    ("och", "och irregular"),
    ("jag", "1sg pronoun"),
    ("du", "2sg pronoun"),
    # ck / sch / sh
    ("schack", "sch → ɧ"),
    ("dusch", "sch final"),
]


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _build_cases(
    phonemize_fn,
    cases: Iterable[tuple[str, str]],
) -> list[dict]:
    out: list[dict] = []
    for text, notes in cases:
        tokens = phonemize_fn(text)
        out.append(
            {
                "text": text,
                "expected_phonemes": list(tokens),
                "notes": notes,
            }
        )
    return out


def _build_fixture(language: str, description: str, cases: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "language": language,
        "description": description,
        "metadata": {
            "source": (
                "Python piper_plus_g2p — pinned by "
                "scripts/regenerate_g2p_golden_fixtures.py. The expected "
                "values capture the *current* implementation output. "
                "Drift in any rule will fail "
                "src/python/g2p/tests/test_golden_fixtures.py."
            ),
            "py_runtime": (
                f"src/python/g2p/piper_plus_g2p/{_lang_module(language)}.py"
            ),
            "version": 1,
        },
        "cases": cases,
    }


def _lang_module(language: str) -> str:
    return {
        "es": "spanish",
        "pt": "portuguese",
        "fr": "french",
        "sv": "swedish",
    }[language]


def _phonemize_fn(language: str):
    from piper_plus_g2p import get_phonemizer

    p = get_phonemizer(language)
    return p.phonemize


def _build_for_language(language: str) -> dict:
    fn = _phonemize_fn(language)
    if language == "es":
        cases = _build_cases(fn, ES_CASES)
        desc = "Spanish G2P golden phoneme matrix (pins current implementation output)."
    elif language == "pt":
        cases = _build_cases(fn, PT_CASES)
        desc = "Brazilian Portuguese G2P golden phoneme matrix (pins current implementation output)."
    elif language == "fr":
        cases = _build_cases(fn, FR_CASES)
        desc = "French G2P golden phoneme matrix (pins current implementation output)."
    elif language == "sv":
        cases = _build_cases(fn, SV_CASES)
        desc = "Swedish G2P golden phoneme matrix (pins current implementation output)."
    else:
        raise ValueError(f"unsupported language: {language}")
    return _build_fixture(language, desc, cases)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--lang",
        choices=["es", "pt", "fr", "sv", "all"],
        default="all",
        help="language to regenerate (default: all)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="CI mode: verify on-disk fixtures match phonemizer output (no write).",
    )
    args = ap.parse_args()

    languages = ["es", "pt", "fr", "sv"] if args.lang == "all" else [args.lang]

    drift: list[tuple[str, str]] = []
    for lang in languages:
        fixture_path = FIXTURE_DIR / f"{lang}_golden.json"
        new_obj = _build_for_language(lang)
        new_text = json.dumps(new_obj, ensure_ascii=False, indent=2) + "\n"

        if args.check:
            if not fixture_path.exists():
                drift.append((lang, "fixture missing"))
                continue
            old_text = fixture_path.read_text(encoding="utf-8")
            if old_text != new_text:
                drift.append((lang, "drift between phonemizer and fixture"))
                continue
            print(f"[ok]   {lang}: fixture in sync ({len(new_obj['cases'])} cases)")
        else:
            FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            fixture_path.write_text(new_text, encoding="utf-8")
            print(
                f"[write] {fixture_path.relative_to(REPO_ROOT)} "
                f"({len(new_obj['cases'])} cases)"
            )

    if drift:
        print("\nDrift detected:", file=sys.stderr)
        for lang, why in drift:
            print(f"  - {lang}: {why}", file=sys.stderr)
        print(
            "\nRun `python scripts/regenerate_g2p_golden_fixtures.py` to "
            "intentionally update the fixtures.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

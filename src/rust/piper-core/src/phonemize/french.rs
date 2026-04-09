//! Rule-based French grapheme-to-phoneme conversion for Piper TTS.
//!
//! Port of `src/cpp/french_phonemize.cpp` (1196 lines) and
//! `src/python/piper_train/phonemize/french.py` to Rust.
//!
//! Converts French text to IPA phonemes using grapheme-to-phoneme rules.
//! No external G2P engine required.
//!
//! ## Key features
//!
//! - Nasal vowels: PUA E056, PUA E057, PUA E058
//! - Silent final consonants
//! - Consonant digraphs: ch, gn, ph, th, qu, gu
//! - Vowel digraphs: ou, au, eau, ai, ei, eu, oi, etc.
//! - -tion -> /sj + nasal-on/, -ille -> /ij/ (with exceptions)
//! - Front rounded vowels: slashed-o, oe-ligature, y_vowel (PUA E01E)
//! - Semi-vowel: turned-h (labial-palatal approximant)
//! - Intervocalic s voicing, -er verb endings, context-dependent x
//! - Exception dictionaries for ille-as-il and er-as-ehr words
//! - Prosody: a1=0, a2=word-final vowel stress, a3=word phoneme count

use super::token_map::token_to_pua;
use super::{Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::config::PhonemeIdMap;
use crate::error::PiperError;

// ---------------------------------------------------------------------------
// PUA codepoints for multi-character phoneme tokens
// ---------------------------------------------------------------------------

const PUA_Y_VOWEL: char = '\u{E01E}'; // y_vowel [y] (lune, tu)
const PUA_NASAL_EIN: char = '\u{E056}'; // nasal open-mid front unrounded
const PUA_NASAL_AN: char = '\u{E057}'; // nasal open back unrounded
const PUA_NASAL_ON: char = '\u{E058}'; // nasal open-mid back rounded

// Single IPA codepoints
const IPA_OPEN_E: char = '\u{025B}'; // open-mid front unrounded
const IPA_OPEN_O: char = '\u{0254}'; // open-mid back rounded
const IPA_SCHWA: char = '\u{0259}'; // schwa
const IPA_VOICED_G: char = '\u{0261}'; // voiced velar plosive (IPA g)
const IPA_ESH: char = '\u{0283}'; // voiceless postalveolar fricative
const IPA_EZH: char = '\u{0292}'; // voiced postalveolar fricative
const IPA_UVULAR_R: char = '\u{0281}'; // voiced uvular fricative
const IPA_PALATAL_N: char = '\u{0272}'; // palatal nasal
const IPA_TURNED_H: char = '\u{0265}'; // labial-palatal approximant
const IPA_SLASHED_O: char = '\u{00F8}'; // close-mid front rounded
const IPA_OE_LIG: char = '\u{0153}'; // open-mid front rounded

// ---------------------------------------------------------------------------
// Character classification
// ---------------------------------------------------------------------------

fn is_vowel_char(ch: char) -> bool {
    matches!(
        ch,
        'a' | 'e'
            | 'i'
            | 'o'
            | 'u'
            | 'y'
            | '\u{00E0}' // a-grave
            | '\u{00E2}' // a-circ
            | '\u{00E6}' // ae ligature
            | '\u{00E9}' // e-acute
            | '\u{00E8}' // e-grave
            | '\u{00EA}' // e-circ
            | '\u{00EB}' // e-diaeresis
            | '\u{00EE}' // i-circ
            | '\u{00EF}' // i-diaeresis
            | '\u{00F4}' // o-circ
            | '\u{00F9}' // u-grave
            | '\u{00FB}' // u-circ
            | '\u{00FC}' // u-diaeresis
            | '\u{0153}' // oe ligature
    )
}

fn is_consonant_char(ch: char) -> bool {
    matches!(
        ch,
        'b' | 'c'
            | 'd'
            | 'f'
            | 'g'
            | 'h'
            | 'j'
            | 'k'
            | 'l'
            | 'm'
            | 'n'
            | 'p'
            | 'q'
            | 'r'
            | 's'
            | 't'
            | 'v'
            | 'w'
            | 'x'
            | 'z'
    )
}

fn is_silent_final(ch: char) -> bool {
    matches!(
        ch,
        'd' | 'g' | 'h' | 'm' | 'n' | 'p' | 's' | 't' | 'x' | 'z'
    )
}

fn is_punctuation(ch: char) -> bool {
    matches!(
        ch,
        ',' | '.'
            | ';'
            | ':'
            | '!'
            | '?'
            | '\u{00A1}'
            | '\u{00BF}'
            | '\u{2014}'
            | '\u{2013}'
            | '\u{2026}'
            | '\u{00AB}'
            | '\u{00BB}'
    )
}

fn is_front_vowel_for_cg(ch: char) -> bool {
    matches!(
        ch,
        'e' | 'i'
            | 'y'
            | '\u{00E9}'
            | '\u{00E8}'
            | '\u{00EA}'
            | '\u{00EB}'
            | '\u{00EE}'
            | '\u{00EF}'
    )
}

fn is_letter_fr(ch: char) -> bool {
    if ch.is_ascii_lowercase() {
        return true;
    }
    matches!(
        ch,
        '\u{00E0}'
            | '\u{00E2}'
            | '\u{00E6}'
            | '\u{00E9}'
            | '\u{00E8}'
            | '\u{00EA}'
            | '\u{00EB}'
            | '\u{00EE}'
            | '\u{00EF}'
            | '\u{00F4}'
            | '\u{00F9}'
            | '\u{00FB}'
            | '\u{00FC}'
            | '\u{0153}'
            | '\u{00E7}'
            | '\u{00F1}'
    )
}

// ---------------------------------------------------------------------------
// Exception word sets
// ---------------------------------------------------------------------------

fn is_ille_as_il(word: &[char]) -> bool {
    let s: String = word.iter().collect();
    matches!(s.as_str(), "ville" | "mille" | "tranquille")
}

fn is_er_as_ehr(word: &[char]) -> bool {
    let s: String = word.iter().collect();
    matches!(
        s.as_str(),
        "hiver"
            | "enfer"
            | "amer"
            | "cancer"
            | "super"
            | "laser"
            | "hamster"
            | "master"
            | "poster"
            | "cluster"
            | "starter"
            | "leader"
            | "transfer"
            | "fer"
    )
}

// ---------------------------------------------------------------------------
// Normalization
// ---------------------------------------------------------------------------

/// Collapse NFD combining sequences into NFC pre-composed forms.
fn collapse_nfd(input: &[char]) -> Vec<char> {
    let mut out = Vec::with_capacity(input.len());
    let mut i = 0;
    let n = input.len();

    while i < n {
        let ch = input[i];

        if i + 1 < n {
            let comb = input[i + 1];
            let composed = match comb {
                '\u{0300}' => match ch {
                    'A' => Some('\u{00C0}'),
                    'a' => Some('\u{00E0}'),
                    'E' => Some('\u{00C8}'),
                    'e' => Some('\u{00E8}'),
                    'U' => Some('\u{00D9}'),
                    'u' => Some('\u{00F9}'),
                    _ => None,
                },
                '\u{0301}' => match ch {
                    'E' => Some('\u{00C9}'),
                    'e' => Some('\u{00E9}'),
                    _ => None,
                },
                '\u{0302}' => match ch {
                    'A' => Some('\u{00C2}'),
                    'a' => Some('\u{00E2}'),
                    'E' => Some('\u{00CA}'),
                    'e' => Some('\u{00EA}'),
                    'I' => Some('\u{00CE}'),
                    'i' => Some('\u{00EE}'),
                    'O' => Some('\u{00D4}'),
                    'o' => Some('\u{00F4}'),
                    'U' => Some('\u{00DB}'),
                    'u' => Some('\u{00FB}'),
                    _ => None,
                },
                '\u{0303}' => match ch {
                    'N' => Some('\u{00D1}'),
                    'n' => Some('\u{00F1}'),
                    _ => None,
                },
                '\u{0308}' => match ch {
                    'E' => Some('\u{00CB}'),
                    'e' => Some('\u{00EB}'),
                    'I' => Some('\u{00CF}'),
                    'i' => Some('\u{00EF}'),
                    'U' => Some('\u{00DC}'),
                    'u' => Some('\u{00FC}'),
                    _ => None,
                },
                '\u{0327}' => match ch {
                    'C' => Some('\u{00C7}'),
                    'c' => Some('\u{00E7}'),
                    _ => None,
                },
                _ => None,
            };

            if let Some(c) = composed {
                out.push(c);
                i += 2;
                continue;
            }
        }

        out.push(ch);
        i += 1;
    }

    out
}

/// French-specific lowercase conversion.
fn to_lower_fr(ch: char) -> char {
    if ch.is_ascii_uppercase() {
        return (ch as u8 + 32) as char;
    }
    let code = ch as u32;
    if (0x00C0..=0x00D6).contains(&code) || (0x00D8..=0x00DE).contains(&code) {
        return char::from_u32(code + 0x20).unwrap_or(ch);
    }
    if code == 0x0152 {
        return '\u{0153}';
    }
    ch
}

/// Normalize text: collapse NFD, lowercase, collapse whitespace.
fn normalize(text: &str) -> Vec<char> {
    let chars: Vec<char> = text.chars().collect();
    let nfc = collapse_nfd(&chars);

    let mut result = Vec::with_capacity(nfc.len());
    let mut last_was_space = true;

    for ch in nfc {
        if ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r' {
            if !last_was_space {
                result.push(' ');
                last_was_space = true;
            }
            continue;
        }
        last_was_space = false;
        result.push(to_lower_fr(ch));
    }

    if result.last() == Some(&' ') {
        result.pop();
    }

    result
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

fn normalize_apostrophes(chars: &[char]) -> Vec<char> {
    chars
        .iter()
        .map(|&ch| {
            if ch == '\'' || ch == '\u{2019}' || ch == '\u{2018}' {
                ' '
            } else {
                ch
            }
        })
        .collect()
}

#[derive(Debug)]
struct Token {
    text: Vec<char>,
    is_punct: bool,
}

fn split_words(text: &[char]) -> Vec<Token> {
    let processed = normalize_apostrophes(text);
    let mut tokens = Vec::new();
    let n = processed.len();
    let mut i = 0;

    while i < n {
        let ch = processed[i];

        if ch == ' ' {
            i += 1;
            continue;
        }

        if is_punctuation(ch) {
            tokens.push(Token {
                text: vec![ch],
                is_punct: true,
            });
            i += 1;
            continue;
        }

        if is_letter_fr(ch) {
            let mut word = Vec::new();
            while i < n && is_letter_fr(processed[i]) {
                word.push(processed[i]);
                i += 1;
            }
            tokens.push(Token {
                text: word,
                is_punct: false,
            });
            continue;
        }

        i += 1;
    }

    tokens
}

// ---------------------------------------------------------------------------
// Core word conversion: French G2P rules
// ---------------------------------------------------------------------------

fn count_vowels(word: &[char]) -> usize {
    word.iter().filter(|&&ch| is_vowel_char(ch)).count()
}

/// Convert a French word to IPA phoneme characters.
///
/// Implements all G2P rules from the C++ `french_phonemize.cpp`:
/// multi-character sequences (longest match first), nasal vowels,
/// vowel digraphs, context-dependent single vowels, consonant digraphs,
/// silent final consonants, doubled consonant dedup, intervocalic s voicing.
fn convert_word(word: &[char]) -> Vec<char> {
    let mut phonemes: Vec<char> = Vec::new();
    let mut i = 0;
    let n = word.len();

    while i < n {
        let ch = word[i];

        // ---------------------------------------------------------------
        // Multi-character sequences (longest match first)
        // ---------------------------------------------------------------

        // -er word-final: verb infinitive ending -> /e/
        if ch == 'e' && i + 1 == n - 1 && word[i + 1] == 'r' {
            let vc = count_vowels(word);
            if vc >= 2 && !is_er_as_ehr(word) {
                phonemes.push('e');
                i += 2;
                continue;
            }
        }

        // "eau" -> o
        if ch == 'e' && i + 2 < n && word[i + 1] == 'a' && word[i + 2] == 'u' {
            phonemes.push('o');
            i += 3;
            continue;
        }

        // "ouille" -> /uj/
        if ch == 'o'
            && i + 5 < n
            && word[i + 1] == 'u'
            && word[i + 2] == 'i'
            && word[i + 3] == 'l'
            && word[i + 4] == 'l'
            && word[i + 5] == 'e'
            && (i + 6 >= n || !is_vowel_char(word[i + 6]))
        {
            phonemes.push('u');
            phonemes.push('j');
            i += 6;
            continue;
        }

        // "aille" -> /aj/
        if ch == 'a'
            && i + 4 < n
            && word[i + 1] == 'i'
            && word[i + 2] == 'l'
            && word[i + 3] == 'l'
            && word[i + 4] == 'e'
            && (i + 5 >= n || !is_vowel_char(word[i + 5]))
        {
            phonemes.push('a');
            phonemes.push('j');
            i += 5;
            continue;
        }

        // "euille" -> /oej/ at word end (feuille)
        if ch == 'e'
            && i + 5 < n
            && word[i + 1] == 'u'
            && word[i + 2] == 'i'
            && word[i + 3] == 'l'
            && word[i + 4] == 'l'
            && word[i + 5] == 'e'
            && i + 6 >= n
        {
            phonemes.push(IPA_OE_LIG);
            phonemes.push('j');
            i += 6;
            continue;
        }

        // "eil" at word end -> /ej/ (soleil, reveil)
        if ch == 'e' && i + 2 < n && word[i + 1] == 'i' && word[i + 2] == 'l' && i + 3 >= n {
            phonemes.push(IPA_OPEN_E);
            phonemes.push('j');
            i += 3;
            continue;
        }

        // "eille" -> /ej/
        if ch == 'e'
            && i + 4 < n
            && word[i + 1] == 'i'
            && word[i + 2] == 'l'
            && word[i + 3] == 'l'
            && word[i + 4] == 'e'
            && (i + 5 >= n || !is_vowel_char(word[i + 5]))
        {
            phonemes.push(IPA_OPEN_E);
            phonemes.push('j');
            i += 5;
            continue;
        }

        // "ain", "aim" -> nasal-epsilon-tilde
        if ch == 'a'
            && i + 2 < n
            && word[i + 1] == 'i'
            && (word[i + 2] == 'n' || word[i + 2] == 'm')
            && (i + 3 >= n || !is_vowel_char(word[i + 3]))
        {
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "ein", "eim" -> nasal-epsilon-tilde
        if ch == 'e'
            && i + 2 < n
            && word[i + 1] == 'i'
            && (word[i + 2] == 'n' || word[i + 2] == 'm')
            && (i + 3 >= n || !is_vowel_char(word[i + 3]))
        {
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "oin" -> w + nasal-epsilon-tilde
        if ch == 'o'
            && i + 2 < n
            && word[i + 1] == 'i'
            && word[i + 2] == 'n'
            && (i + 3 >= n || !is_vowel_char(word[i + 3]))
        {
            phonemes.push('w');
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "ien" -> j + nasal-epsilon-tilde
        if ch == 'i'
            && i + 2 < n
            && word[i + 1] == 'e'
            && word[i + 2] == 'n'
            && (i + 3 >= n || !is_vowel_char(word[i + 3]))
        {
            phonemes.push('j');
            phonemes.push(PUA_NASAL_EIN);
            i += 3;
            continue;
        }

        // "tion" -> /sj + nasal-on/ (or /tj + nasal-on/ after 's')
        if ch == 't'
            && i + 3 < n
            && word[i + 1] == 'i'
            && word[i + 2] == 'o'
            && word[i + 3] == 'n'
            && (i + 4 >= n || !is_vowel_char(word[i + 4]))
        {
            if i > 0 && word[i - 1] == 's' {
                phonemes.push('t');
            } else {
                phonemes.push('s');
            }
            phonemes.push('j');
            phonemes.push(PUA_NASAL_ON);
            i += 4;
            continue;
        }

        // "ille" -> /ij/ default, /il/ for exceptions
        if ch == 'i'
            && i + 3 < n
            && word[i + 1] == 'l'
            && word[i + 2] == 'l'
            && word[i + 3] == 'e'
            && (i + 4 >= n || !is_vowel_char(word[i + 4]))
        {
            phonemes.push('i');
            if is_ille_as_il(word) {
                phonemes.push('l');
            } else {
                phonemes.push('j');
            }
            i += 4;
            continue;
        }

        // "gn" -> palatal nasal
        if ch == 'g' && i + 1 < n && word[i + 1] == 'n' {
            phonemes.push(IPA_PALATAL_N);
            i += 2;
            continue;
        }

        // "ph" -> f
        if ch == 'p' && i + 1 < n && word[i + 1] == 'h' {
            phonemes.push('f');
            i += 2;
            continue;
        }

        // "th" -> t
        if ch == 't' && i + 1 < n && word[i + 1] == 'h' {
            phonemes.push('t');
            i += 2;
            continue;
        }

        // "ch" -> voiceless postalveolar fricative
        if ch == 'c' && i + 1 < n && word[i + 1] == 'h' {
            phonemes.push(IPA_ESH);
            i += 2;
            continue;
        }

        // "qu" -> k
        if ch == 'q' && i + 1 < n && word[i + 1] == 'u' {
            phonemes.push('k');
            i += 2;
            continue;
        }

        // "gu" + front vowel -> voiced velar (silent u)
        if ch == 'g'
            && i + 1 < n
            && word[i + 1] == 'u'
            && i + 2 < n
            && is_front_vowel_for_cg(word[i + 2])
        {
            phonemes.push(IPA_VOICED_G);
            i += 2;
            continue;
        }

        // ---------------------------------------------------------------
        // Nasal vowels: vowel + n/m before consonant or end
        // ---------------------------------------------------------------

        // "an", "am", "en", "em" -> nasal-alpha-tilde
        if (ch == 'a' || ch == 'e') && i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm') {
            if i + 2 >= n {
                phonemes.push(PUA_NASAL_AN);
                i += 2;
                continue;
            }
            if !is_vowel_char(word[i + 2]) && word[i + 2] != word[i + 1] {
                phonemes.push(PUA_NASAL_AN);
                i += 2;
                continue;
            }
        }

        // "in", "im" -> nasal-epsilon-tilde
        if ch == 'i' && i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm') {
            if i + 2 >= n {
                phonemes.push(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
            if !is_vowel_char(word[i + 2]) && word[i + 2] != word[i + 1] {
                phonemes.push(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
        }

        // "on", "om" -> nasal-open-o-tilde
        if ch == 'o' && i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm') {
            if i + 2 >= n {
                phonemes.push(PUA_NASAL_ON);
                i += 2;
                continue;
            }
            if !is_vowel_char(word[i + 2]) && word[i + 2] != word[i + 1] {
                phonemes.push(PUA_NASAL_ON);
                i += 2;
                continue;
            }
        }

        // "un", "um" -> nasal-epsilon-tilde (modern French merger)
        if ch == 'u' && i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm') {
            if i + 2 >= n {
                phonemes.push(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
            if !is_vowel_char(word[i + 2]) && word[i + 2] != word[i + 1] {
                phonemes.push(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
        }

        // "yn", "ym" -> nasal-epsilon-tilde (syndicat, symbole)
        if ch == 'y' && i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm') {
            if i + 2 >= n {
                phonemes.push(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
            if !is_vowel_char(word[i + 2]) && word[i + 2] != word[i + 1] {
                phonemes.push(PUA_NASAL_EIN);
                i += 2;
                continue;
            }
        }

        // ---------------------------------------------------------------
        // Vowel digraphs
        // ---------------------------------------------------------------

        // "ou" -> u
        if ch == 'o' && i + 1 < n && word[i + 1] == 'u' {
            phonemes.push('u');
            i += 2;
            continue;
        }

        // "au" -> o
        if ch == 'a' && i + 1 < n && word[i + 1] == 'u' {
            phonemes.push('o');
            i += 2;
            continue;
        }

        // "oi" -> wa
        if ch == 'o' && i + 1 < n && word[i + 1] == 'i' {
            phonemes.push('w');
            phonemes.push('a');
            i += 2;
            continue;
        }

        // "ai" -> open-e
        if ch == 'a' && i + 1 < n && word[i + 1] == 'i' {
            phonemes.push(IPA_OPEN_E);
            i += 2;
            continue;
        }

        // "ei" -> open-e
        if ch == 'e' && i + 1 < n && word[i + 1] == 'i' {
            phonemes.push(IPA_OPEN_E);
            i += 2;
            continue;
        }

        // "eu", "oeu" -> slashed-o (closed) or oe-ligature (open before pronounced consonant)
        if (ch == 'e' || ch == '\u{0153}') && i + 1 < n && word[i + 1] == 'u' {
            if i + 2 < n && is_consonant_char(word[i + 2]) && !is_silent_final(word[i + 2]) {
                phonemes.push(IPA_OE_LIG);
            } else {
                phonemes.push(IPA_SLASHED_O);
            }
            i += 2;
            continue;
        }

        // ---------------------------------------------------------------
        // Single vowels
        // ---------------------------------------------------------------

        if ch == '\u{00E9}' {
            phonemes.push('e');
            i += 1;
            continue;
        }

        if ch == '\u{00E8}' || ch == '\u{00EA}' {
            phonemes.push(IPA_OPEN_E);
            i += 1;
            continue;
        }

        if ch == '\u{00EB}' {
            phonemes.push(IPA_OPEN_E);
            i += 1;
            continue;
        }

        if ch == '\u{00E0}' || ch == '\u{00E2}' {
            phonemes.push('a');
            i += 1;
            continue;
        }

        if ch == 'a' {
            phonemes.push('a');
            i += 1;
            continue;
        }

        if ch == '\u{00EE}' || ch == '\u{00EF}' {
            phonemes.push('i');
            i += 1;
            continue;
        }

        // i: before vowel -> j (semi-vowel), except before word-final silent 'e'
        if ch == 'i' {
            if i + 1 < n && is_vowel_char(word[i + 1]) {
                if i + 1 == n - 1 && word[i + 1] == 'e' {
                    phonemes.push('i');
                } else {
                    phonemes.push('j');
                }
            } else {
                phonemes.push('i');
            }
            i += 1;
            continue;
        }

        if ch == '\u{00F4}' {
            phonemes.push('o');
            i += 1;
            continue;
        }

        // plain o: open before pronounced consonant, closed otherwise
        if ch == 'o' {
            let eff_start = i + 1;
            let mut eff_end = n;
            if eff_end > eff_start {
                if eff_end - eff_start >= 2 && word[eff_end - 2] == 'e' && word[eff_end - 1] == 's'
                {
                    eff_end -= 2;
                } else if word[eff_end - 1] == 'e' {
                    eff_end -= 1;
                }
            }

            let mut has_effective = false;
            let mut all_consonants = true;
            let mut has_pronounced = false;

            for &c in &word[eff_start..eff_end] {
                has_effective = true;
                if !is_consonant_char(c) {
                    all_consonants = false;
                    break;
                }
                if !is_silent_final(c) {
                    has_pronounced = true;
                }
            }

            if has_effective && all_consonants && has_pronounced {
                phonemes.push(IPA_OPEN_O);
            } else {
                phonemes.push('o');
            }
            i += 1;
            continue;
        }

        if ch == '\u{00F9}' || ch == '\u{00FB}' {
            phonemes.push(PUA_Y_VOWEL);
            i += 1;
            continue;
        }

        if ch == '\u{00FC}' {
            phonemes.push(PUA_Y_VOWEL);
            i += 1;
            continue;
        }

        // u: semi-vowel before i, otherwise y_vowel
        if ch == 'u' {
            if i + 1 < n && word[i + 1] == 'i' {
                phonemes.push(IPA_TURNED_H);
                phonemes.push('i');
                i += 2;
                continue;
            }
            phonemes.push(PUA_Y_VOWEL);
            i += 1;
            continue;
        }

        // y: before vowel -> j, otherwise -> i
        if ch == 'y' {
            if i + 1 < n && is_vowel_char(word[i + 1]) {
                phonemes.push('j');
            } else {
                phonemes.push('i');
            }
            i += 1;
            continue;
        }

        if ch == '\u{0153}' {
            phonemes.push(IPA_OE_LIG);
            i += 1;
            continue;
        }

        if ch == '\u{00E6}' {
            phonemes.push('e');
            i += 1;
            continue;
        }

        // plain 'e': context-dependent
        if ch == 'e' {
            if i == n - 1 {
                i += 1;
                continue;
            }

            let mut cons_count = 0;
            for &c in &word[(i + 1)..n] {
                if is_consonant_char(c) {
                    cons_count += 1;
                } else {
                    break;
                }
            }

            if cons_count >= 2 {
                phonemes.push(IPA_OPEN_E);
                i += 1;
                continue;
            }

            let remaining = &word[(i + 1)..];
            let all_cons = !remaining.is_empty() && remaining.iter().all(|&c| is_consonant_char(c));
            let has_pronounced = remaining.iter().any(|&c| !is_silent_final(c));

            if !remaining.is_empty() && all_cons && has_pronounced {
                phonemes.push(IPA_OPEN_E);
            } else {
                phonemes.push(IPA_SCHWA);
            }
            i += 1;
            continue;
        }

        // ---------------------------------------------------------------
        // Consonants
        // ---------------------------------------------------------------

        if ch == 'c' {
            if i + 1 < n && is_front_vowel_for_cg(word[i + 1]) {
                phonemes.push('s');
            } else {
                phonemes.push('k');
            }
            i += 1;
            continue;
        }

        if ch == '\u{00E7}' {
            phonemes.push('s');
            i += 1;
            continue;
        }

        if ch == 'g' {
            if i + 1 < n && is_front_vowel_for_cg(word[i + 1]) {
                phonemes.push(IPA_EZH);
            } else {
                phonemes.push(IPA_VOICED_G);
            }
            i += 1;
            continue;
        }

        if ch == 'j' {
            phonemes.push(IPA_EZH);
            i += 1;
            continue;
        }

        if ch == 'r' {
            phonemes.push(IPA_UVULAR_R);
            if i + 1 < n && word[i + 1] == 'r' {
                i += 2;
            } else {
                i += 1;
            }
            continue;
        }

        // x: context-dependent
        if ch == 'x' {
            if i == n - 1 {
                i += 1;
                continue;
            }
            {
                let rem_len = n - (i + 1);
                let silent_before = if rem_len == 1 && word[i + 1] == 'e' {
                    true
                } else {
                    rem_len == 2 && word[i + 1] == 'e' && word[i + 2] == 's'
                };
                if silent_before {
                    i += 1;
                    continue;
                }
            }
            if i > 0 && word[i - 1] == 'e' && i + 1 < n && is_vowel_char(word[i + 1]) {
                phonemes.push(IPA_VOICED_G);
                phonemes.push('z');
                i += 1;
                continue;
            }
            phonemes.push('k');
            phonemes.push('s');
            i += 1;
            continue;
        }

        if ch == 'h' {
            i += 1;
            continue;
        }

        // ---------------------------------------------------------------
        // Simple consonant mappings
        // ---------------------------------------------------------------
        let mapped = match ch {
            'b' => Some('b'),
            'd' => Some('d'),
            'f' => Some('f'),
            'k' => Some('k'),
            'l' => Some('l'),
            'm' => Some('m'),
            'n' => Some('n'),
            'p' => Some('p'),
            's' => Some('s'),
            't' => Some('t'),
            'v' => Some('v'),
            'w' => Some('w'),
            'z' => Some('z'),
            _ => None,
        };

        if let Some(mapped_ch) = mapped {
            let is_word_final = i == n - 1;
            let is_before_final_s = n >= 2 && i == n - 2 && word[n - 1] == 's';
            let is_final = is_word_final || is_before_final_s;

            if is_final && is_silent_final(ch) {
                i += 1;
                continue;
            }

            if ch == 's' {
                let prev_vowel = i > 0 && is_vowel_char(word[i - 1]);
                let next_vowel = i + 1 < n && is_vowel_char(word[i + 1]);
                let is_single = !(i + 1 < n && word[i + 1] == 's');
                if prev_vowel && next_vowel && is_single {
                    phonemes.push('z');
                    i += 1;
                    continue;
                }
            }

            phonemes.push(mapped_ch);
            if i + 1 < n && word[i + 1] == ch {
                i += 2;
            } else {
                i += 1;
            }
            continue;
        }

        if is_punctuation(ch) {
            phonemes.push(ch);
            i += 1;
            continue;
        }

        i += 1;
    }

    phonemes
}

// ---------------------------------------------------------------------------
// Vowel phoneme detection (for prosody stress marking)
// ---------------------------------------------------------------------------

fn is_vowel_phoneme(ch: char) -> bool {
    matches!(
        ch,
        'a' | 'e'
            | 'i'
            | 'o'
            | 'u'
            | IPA_OPEN_E
            | IPA_OPEN_O
            | IPA_SCHWA
            | IPA_SLASHED_O
            | IPA_OE_LIG
            | PUA_Y_VOWEL
            | PUA_NASAL_EIN
            | PUA_NASAL_AN
            | PUA_NASAL_ON
    )
}

// ---------------------------------------------------------------------------
// PUA mapping helper
// ---------------------------------------------------------------------------

fn map_sequence(tokens: Vec<String>) -> Vec<String> {
    tokens
        .into_iter()
        .map(|t| {
            if let Some(pua_char) = token_to_pua(&t) {
                pua_char.to_string()
            } else {
                t
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Top-level French phonemization
// ---------------------------------------------------------------------------

/// Convert French text to phoneme tokens with prosody information.
///
/// Prosody:
/// - a1 = 0 (French has no pitch accent like Japanese)
/// - a2 = 2 for the last vowel phoneme in each word (word-final stress), 0 otherwise
/// - a3 = number of phonemes in the word
pub fn phonemize_french_with_prosody(text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
    let normalized = normalize(text);
    let tokens = split_words(&normalized);

    let mut phonemes: Vec<String> = Vec::new();
    let mut prosody_list: Vec<Option<ProsodyInfo>> = Vec::new();
    let mut need_space = false;

    for tok in &tokens {
        if !tok.is_punct && need_space {
            phonemes.push(" ".to_string());
            prosody_list.push(Some(ProsodyInfo {
                a1: 0,
                a2: 0,
                a3: 0,
            }));
        }

        if tok.is_punct {
            for &ch in &tok.text {
                phonemes.push(ch.to_string());
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 0,
                }));
            }
        } else {
            let word_phonemes = convert_word(&tok.text);
            let word_phoneme_count = word_phonemes.len() as i32;

            let last_vowel_idx = word_phonemes
                .iter()
                .enumerate()
                .rev()
                .find(|&(_, &ph)| is_vowel_phoneme(ph))
                .map(|(idx, _)| idx);

            for (j, &ph) in word_phonemes.iter().enumerate() {
                let a2 = if Some(j) == last_vowel_idx { 2 } else { 0 };
                phonemes.push(ph.to_string());
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2,
                    a3: word_phoneme_count,
                }));
            }
        }

        need_space = true;
    }

    let mapped = map_sequence(phonemes);
    (mapped, prosody_list)
}

/// Convert French text to phoneme list (without prosody).
pub fn phonemize_french(text: &str) -> Vec<String> {
    let (phonemes, _) = phonemize_french_with_prosody(text);
    phonemes
}

// ---------------------------------------------------------------------------
// FrenchPhonemizer struct
// ---------------------------------------------------------------------------

/// French rule-based phonemizer.
///
/// Stateless: no external dictionary or G2P engine required.
pub struct FrenchPhonemizer;

impl FrenchPhonemizer {
    pub fn new() -> Self {
        Self
    }
}

impl Default for FrenchPhonemizer {
    fn default() -> Self {
        Self::new()
    }
}

impl Phonemizer for FrenchPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        Ok(phonemize_french_with_prosody(text))
    }

    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> {
        None
    }

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
        // BOS (^) + intersperse padding (_) + EOS ($)
        let bos_id = id_map
            .get("^")
            .and_then(|v| v.first().copied())
            .unwrap_or(1);
        let eos_id = id_map
            .get("$")
            .and_then(|v| v.first().copied())
            .unwrap_or(2);
        let pad_id = id_map
            .get("_")
            .and_then(|v| v.first().copied())
            .unwrap_or(0);

        // Output: BOS, pad, id0, pad, id1, pad, ..., idN, pad, EOS
        let out_len = 1 + ids.len() * 2 + 1;
        let mut out_ids = Vec::with_capacity(out_len);
        let mut out_prosody: Vec<Option<ProsodyFeature>> = Vec::with_capacity(out_len);

        out_ids.push(bos_id);
        out_prosody.push(None);

        for (idx, &id) in ids.iter().enumerate() {
            out_ids.push(pad_id);
            out_prosody.push(None);
            out_ids.push(id);
            out_prosody.push(prosody.get(idx).copied().flatten());
        }

        out_ids.push(pad_id);
        out_prosody.push(None);
        out_ids.push(eos_id);
        out_prosody.push(None);

        (out_ids, out_prosody)
    }

    fn language_code(&self) -> &str {
        "fr"
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: get word phonemes directly from convert_word.
    fn word_ph(word: &str) -> String {
        let chars: Vec<char> = word.chars().collect();
        convert_word(&chars).iter().collect()
    }

    /// Helper: join phoneme tokens into a single string.
    fn ph_str(text: &str) -> String {
        let (tokens, _) = phonemize_french_with_prosody(text);
        tokens.join("")
    }

    // ===== 1. Nasal vowels =====

    #[test]
    fn test_nasal_an() {
        let result = word_ph("france");
        assert!(
            result.contains(PUA_NASAL_AN),
            "expected nasal-an in france: {result}"
        );
    }

    #[test]
    fn test_nasal_on() {
        assert_eq!(word_ph("bon"), format!("b{PUA_NASAL_ON}"));
    }

    #[test]
    fn test_nasal_ein() {
        assert_eq!(word_ph("vin"), format!("v{PUA_NASAL_EIN}"));
    }

    // ===== 2. Silent final consonants =====

    #[test]
    fn test_silent_final_t() {
        let result = word_ph("chat");
        assert!(result.contains(IPA_ESH), "expected esh in chat: {result}");
        assert!(
            !result.ends_with('t'),
            "final t should be silent in chat: {result}"
        );
    }

    // ===== 3. -tion =====

    #[test]
    fn test_tion_suffix() {
        let result = word_ph("nation");
        assert!(result.contains('s'), "expected 's' from -tion: {result}");
        assert!(result.contains('j'), "expected 'j' from -tion: {result}");
        assert!(result.contains(PUA_NASAL_ON), "expected nasal-on: {result}");
    }

    // ===== 4. -ille =====

    #[test]
    fn test_ille_default() {
        let result = word_ph("fille");
        assert!(result.contains('j'), "fille should have j: {result}");
        assert!(!result.contains('l'), "fille should not have l: {result}");
    }

    #[test]
    fn test_ille_exception_ville() {
        let result = word_ph("ville");
        assert!(result.contains('l'), "ville should have l: {result}");
    }

    // ===== 5. Vowel digraphs =====

    #[test]
    fn test_eau() {
        assert_eq!(word_ph("beau"), "bo");
    }

    #[test]
    fn test_oi() {
        assert_eq!(word_ph("moi"), "mwa");
    }

    // ===== 6. -er verb ending =====

    #[test]
    fn test_er_verb_ending() {
        let result = word_ph("parler");
        assert!(
            result.ends_with('e'),
            "polysyllabic -er should end /e/: {result}"
        );
    }

    #[test]
    fn test_er_exception() {
        let result = word_ph("hiver");
        assert!(
            result.contains(IPA_UVULAR_R),
            "hiver should have uvular-R: {result}"
        );
    }

    // ===== 7. ch/gn digraphs =====

    #[test]
    fn test_ch_digraph() {
        let result = word_ph("cher");
        assert!(result.contains(IPA_ESH), "expected esh in cher: {result}");
    }

    #[test]
    fn test_gn_digraph() {
        let result = word_ph("ligne");
        assert!(
            result.contains(IPA_PALATAL_N),
            "expected palatal-N in ligne: {result}"
        );
    }

    // ===== 8. Intervocalic s =====

    #[test]
    fn test_intervocalic_s() {
        let result = word_ph("maison");
        assert!(
            result.contains('z'),
            "intervocalic s should be z in maison: {result}"
        );
    }

    // ===== 9. Semi-vowel =====

    #[test]
    fn test_u_before_i() {
        let result = word_ph("lui");
        assert!(
            result.contains(IPA_TURNED_H),
            "u before i -> turned-h in lui: {result}"
        );
    }

    // ===== 10. Normalization =====

    #[test]
    fn test_uppercase_normalization() {
        let result = ph_str("BONJOUR");
        assert!(result.contains('b'), "uppercase should normalize: {result}");
    }

    #[test]
    fn test_nfd_normalization() {
        let nfd = "e\u{0301}";
        let chars: Vec<char> = nfd.chars().collect();
        let collapsed = collapse_nfd(&chars);
        assert_eq!(collapsed, vec!['\u{00E9}']);
    }

    // ===== 11. Post-process IDs =====

    #[test]
    fn test_post_process_ids_bos_eos_padding() {
        use std::collections::HashMap;

        let phonemizer = FrenchPhonemizer::new();
        let mut id_map: HashMap<String, Vec<i64>> = HashMap::new();
        id_map.insert("^".into(), vec![1]);
        id_map.insert("$".into(), vec![2]);
        id_map.insert("_".into(), vec![0]);

        let ids = vec![10, 20, 30];
        let prosody = vec![Some([0, 0, 3]), Some([0, 2, 3]), Some([0, 0, 3])];

        let (out_ids, out_prosody) = phonemizer.post_process_ids(ids, prosody, &id_map);

        assert_eq!(out_ids, vec![1, 0, 10, 0, 20, 0, 30, 0, 2]);
        assert_eq!(out_prosody.len(), out_ids.len());
        assert!(out_prosody[0].is_none());
        assert_eq!(out_prosody[2], Some([0, 0, 3]));
    }

    // ===== 12. Full sentence =====

    #[test]
    fn test_full_sentence() {
        let (tokens, prosody) = phonemize_french_with_prosody("Bonjour, comment allez-vous?");
        assert!(!tokens.is_empty());
        assert_eq!(tokens.len(), prosody.len());
        assert!(tokens.contains(&",".to_string()));
        assert!(tokens.contains(&"?".to_string()));
    }

    // ===== 13. Doubled consonants =====

    #[test]
    fn test_doubled_consonants() {
        let result = word_ph("belle");
        let l_count = result.chars().filter(|&c| c == 'l').count();
        assert_eq!(l_count, 1, "doubled l -> single l in belle: {result}");
    }

    // ===== 14. C/G softening =====

    #[test]
    fn test_c_before_front_vowel() {
        let result = word_ph("ciel");
        assert!(result.starts_with('s'), "c before i -> s in ciel: {result}");
    }

    #[test]
    fn test_g_before_front_vowel() {
        let result = word_ph("gel");
        assert!(
            result.starts_with(IPA_EZH),
            "g before e -> ezh in gel: {result}"
        );
    }

    // ===== 15. PUA mapping =====

    #[test]
    fn test_pua_nasal_in_output() {
        let (tokens, _) = phonemize_french_with_prosody("bon");
        let nasal_on_pua = PUA_NASAL_ON.to_string();
        assert!(
            tokens.contains(&nasal_on_pua),
            "bon -> PUA nasal-on: {:?}",
            tokens
        );
    }

    // ===== 16. Language code =====

    #[test]
    fn test_language_code() {
        assert_eq!(FrenchPhonemizer::new().language_code(), "fr");
    }

    // ===== 17. Prosody stress =====

    #[test]
    fn test_prosody_stress_on_last_vowel() {
        let (_, prosody) = phonemize_french_with_prosody("bonjour");
        let stressed: Vec<_> = prosody
            .iter()
            .filter(|p| p.is_some_and(|pi| pi.a2 == 2))
            .collect();
        assert!(!stressed.is_empty(), "should have stressed phoneme");
    }

    // ===== 18. Empty input =====

    #[test]
    fn test_empty_input() {
        let (tokens, prosody) = phonemize_french_with_prosody("");
        assert!(tokens.is_empty());
        assert!(prosody.is_empty());
    }

    // ===== 19. Oin nasal =====

    #[test]
    fn test_oin_nasal() {
        let result = word_ph("loin");
        assert!(result.contains('w'), "oin -> w: {result}");
        assert!(result.contains(PUA_NASAL_EIN), "oin -> nasal-ein: {result}");
    }

    // ===== 20. Qu digraph =====

    #[test]
    fn test_qu_digraph() {
        assert_eq!(word_ph("que"), "k");
    }

    // ===== 21. Eu open/closed =====

    #[test]
    fn test_eu_open() {
        let result = word_ph("fleur");
        assert!(
            result.contains(IPA_OE_LIG),
            "eu before r -> open in fleur: {result}"
        );
    }

    #[test]
    fn test_eu_closed() {
        let result = word_ph("jeu");
        assert!(
            result.contains(IPA_SLASHED_O),
            "eu at end -> closed in jeu: {result}"
        );
    }

    // ===== 22. Phonemizer trait =====

    #[test]
    fn test_phonemizer_trait() {
        let p = FrenchPhonemizer::new();
        let result = p.phonemize_with_prosody("Bonjour");
        assert!(result.is_ok());
        let (tokens, prosody) = result.unwrap();
        assert!(!tokens.is_empty());
        assert_eq!(tokens.len(), prosody.len());
    }

    // ===== 23. Gu before front vowel =====

    #[test]
    fn test_gu_before_front_vowel() {
        let result = word_ph("guerre");
        assert!(
            result.contains(IPA_VOICED_G),
            "gu+e -> voiced-g in guerre: {result}"
        );
    }

    // ===== 24. Cedilla =====

    #[test]
    fn test_c_cedilla() {
        let result = word_ph("gar\u{00E7}on");
        assert!(result.contains('s'), "c-cedilla -> s: {result}");
    }

    // ===== 25. Eille pattern =====

    #[test]
    fn test_eille_pattern() {
        let result = word_ph("abeille");
        assert!(result.contains(IPA_OPEN_E), "eille -> open-e: {result}");
        assert!(result.contains('j'), "eille -> j: {result}");
    }

    // ===== 26. Y vowel PUA =====

    #[test]
    fn test_y_vowel_pua() {
        let (tokens, _) = phonemize_french_with_prosody("tu");
        let y_pua = PUA_Y_VOWEL.to_string();
        assert!(tokens.contains(&y_pua), "tu -> PUA y_vowel: {:?}", tokens);
    }

    // ===== 27. Doubled r =====

    #[test]
    fn test_doubled_r() {
        let result = word_ph("terre");
        let r_count = result.chars().filter(|&c| c == IPA_UVULAR_R).count();
        assert_eq!(r_count, 1, "doubled r -> single R in terre: {result}");
    }

    // ===== 28. Ien nasal =====

    #[test]
    fn test_ien_nasal() {
        let result = word_ph("bien");
        assert!(result.contains('j'), "ien -> j: {result}");
        assert!(result.contains(PUA_NASAL_EIN), "ien -> nasal-ein: {result}");
    }

    // ===== 29. Ph digraph =====

    #[test]
    fn test_ph_digraph() {
        let result = word_ph("photo");
        assert!(result.starts_with('f'), "ph -> f in photo: {result}");
    }

    // ===== 30. Apostrophe tokenization =====

    #[test]
    fn test_apostrophe_word_boundary() {
        let result = ph_str("l'ami");
        assert!(result.contains('l'), "expected l in l'ami: {result}");
        assert!(result.contains('a'), "expected a in l'ami: {result}");
    }
}

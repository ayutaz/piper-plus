//! Rule-based Brazilian Portuguese phonemizer for Piper TTS.
//!
//! Ported from `src/cpp/portuguese_phonemize.cpp` (1004 lines) and
//! `src/python/piper_train/phonemize/portuguese.py`.
//!
//! Converts Brazilian Portuguese text to IPA phonemes using grapheme-to-phoneme
//! rules.  No external G2P engine required.
//!
//! ## Key features
//!
//! - Nasal vowels (a\u{0303}, e\u{0303}, i\u{0303}, o\u{0303}, u\u{0303})
//! - Coda-l vocalization (l -> w at syllable end)
//! - t/d palatalization before i: t -> PUA E054 (tS), d -> PUA E055 (dZ)
//! - r polymorphism: word-initial/coda -> voiced uvular, intervocalic -> tap
//! - lh -> palatal lateral, nh -> palatal nasal
//! - Stress assignment (accent marks or positional defaults)
//! - BR post-processing (final vowel reduction, t/d palatalization before
//!   unstressed final e)

use crate::error::G2pError;
use crate::phonemizer::{Phonemizer, ProsodyInfo};

// ---------------------------------------------------------------------------
// PUA codepoints for multi-codepoint IPA tokens
// ---------------------------------------------------------------------------

const PUA_AFFRICATE_TCH: char = '\u{E054}'; // tS (palatalized t before i)
const PUA_AFFRICATE_DZH: char = '\u{E055}'; // dZ (palatalized d before i)

// ---------------------------------------------------------------------------
// Single IPA codepoints
// ---------------------------------------------------------------------------

const IPA_EPSILON: char = '\u{025B}'; // open-mid front unrounded (e aberto)
const IPA_OPEN_O: char = '\u{0254}'; // open-mid back rounded   (o aberto)
const IPA_VOICED_G: char = '\u{0261}'; // voiced velar plosive
const IPA_ESH: char = '\u{0283}'; // voiceless postalveolar fricative
const IPA_EZH: char = '\u{0292}'; // voiced postalveolar fricative
const IPA_UVULAR_R: char = '\u{0281}'; // voiced uvular fricative
const IPA_PALATAL_N: char = '\u{0272}'; // palatal nasal
const IPA_TAP: char = '\u{027E}'; // alveolar tap
const IPA_PALATAL_L: char = '\u{028E}'; // palatal lateral approximant

// Precomposed nasal vowels (NFC single codepoints)
const NASAL_A: char = '\u{00E3}'; // a tilde
const NASAL_E: char = '\u{1EBD}'; // e tilde
const NASAL_I: char = '\u{0129}'; // i tilde
const NASAL_O: char = '\u{00F5}'; // o tilde
const NASAL_U: char = '\u{0169}'; // u tilde

// ---------------------------------------------------------------------------
// Character classification helpers
// ---------------------------------------------------------------------------

/// Portuguese vowel letters (including accented forms).
fn is_vowel_char(ch: char) -> bool {
    matches!(
        ch,
        'a' | 'e'
            | 'i'
            | 'o'
            | 'u'
            | '\u{E1}' // a acute
            | '\u{E0}' // a grave
            | '\u{E2}' // a circumflex
            | '\u{E3}' // a tilde
            | '\u{E9}' // e acute
            | '\u{EA}' // e circumflex
            | '\u{ED}' // i acute
            | '\u{F3}' // o acute
            | '\u{F4}' // o circumflex
            | '\u{F5}' // o tilde
            | '\u{FA}' // u acute
            | '\u{FC}' // u diaeresis
    )
}

/// Acute accents: open vowels, primary stress.
fn is_stress_accent(ch: char) -> bool {
    matches!(ch, '\u{E1}' | '\u{E9}' | '\u{ED}' | '\u{F3}' | '\u{FA}')
}

/// Circumflex: closed vowels.
fn is_circumflex(ch: char) -> bool {
    matches!(ch, '\u{E2}' | '\u{EA}' | '\u{F4}')
}

/// Tilde: nasal vowels.
fn is_tilde(ch: char) -> bool {
    matches!(ch, '\u{E3}' | '\u{F5}')
}

/// Any accent mark (stress, circumflex, tilde, grave, diaeresis).
#[allow(dead_code)]
fn is_accented(ch: char) -> bool {
    is_stress_accent(ch)
        || is_circumflex(ch)
        || is_tilde(ch)
        || ch == '\u{E0}' // a grave
        || ch == '\u{FC}' // u diaeresis
}

/// Map accented letter to its base vowel.
fn accent_base(ch: char) -> char {
    match ch {
        '\u{E1}' | '\u{E0}' | '\u{E2}' | '\u{E3}' => 'a',
        '\u{E9}' | '\u{EA}' => 'e',
        '\u{ED}' => 'i',
        '\u{F3}' | '\u{F4}' | '\u{F5}' => 'o',
        '\u{FA}' | '\u{FC}' => 'u',
        _ => ch,
    }
}

/// IPA oral vowel phonemes.
fn is_ipa_oral_vowel(ch: char) -> bool {
    matches!(ch, 'a' | 'e' | 'i' | 'o' | 'u' | IPA_EPSILON | IPA_OPEN_O)
}

/// IPA nasal vowel phonemes.
fn is_ipa_nasal_vowel(ch: char) -> bool {
    matches!(ch, NASAL_A | NASAL_E | NASAL_I | NASAL_O | NASAL_U)
}

/// IPA vowel phonemes (oral + nasal).
fn is_ipa_vowel(ch: char) -> bool {
    is_ipa_oral_vowel(ch) || is_ipa_nasal_vowel(ch)
}

/// IPA consonant phonemes (for coda-l detection).
fn is_ipa_consonant(ch: char) -> bool {
    matches!(
        ch,
        'b' | 'c'
            | 'd'
            | 'f'
            | 'h'
            | 'j'
            | 'k'
            | 'l'
            | 'm'
            | 'n'
            | 'p'
            | 's'
            | 't'
            | 'v'
            | 'w'
            | 'z'
            | IPA_VOICED_G
            | IPA_PALATAL_N
            | IPA_TAP
            | IPA_UVULAR_R
            | IPA_ESH
            | IPA_PALATAL_L
            | IPA_EZH
    )
}

/// Punctuation characters.
fn is_punctuation(ch: char) -> bool {
    matches!(
        ch,
        ',' | '.'
            | ';'
            | ':'
            | '!'
            | '?'
            | '\u{A1}'   // inverted exclamation
            | '\u{BF}'   // inverted question
            | '\u{2014}' // em dash
            | '\u{2013}' // en dash
            | '\u{2026}' // horizontal ellipsis
    )
}

/// "Soft" vowels that trigger c->s and g->zh.
fn is_soft_vowel(ch: char) -> bool {
    matches!(
        ch,
        'e' | 'i'
            | '\u{E9}' // e acute
            | '\u{EA}' // e circumflex
            | '\u{ED}' // i acute
    )
}

/// Word character: a-z + common Portuguese accented range.
fn is_word_char(ch: char) -> bool {
    if ch.is_ascii_lowercase() {
        return true;
    }
    // Latin-1 supplement lowercase (0xE0-0xFF except 0xF7 division sign)
    let cp = ch as u32;
    if (0xE0..=0xFF).contains(&cp) && cp != 0xF7 {
        return true;
    }
    // c cedilla, n tilde
    if ch == '\u{E7}' || ch == '\u{F1}' {
        return true;
    }
    false
}

// ---------------------------------------------------------------------------
// NFC normalization for combining accents
// ---------------------------------------------------------------------------

/// Collapse NFD combining accent sequences into precomposed NFC codepoints.
///
/// Handles the common Portuguese combining marks:
///   U+0300 COMBINING GRAVE ACCENT
///   U+0301 COMBINING ACUTE ACCENT
///   U+0302 COMBINING CIRCUMFLEX ACCENT
///   U+0303 COMBINING TILDE
///   U+0308 COMBINING DIAERESIS
///   U+0327 COMBINING CEDILLA
fn collapse_nfd_combining_accents(cps: &[char]) -> Vec<char> {
    if cps.len() < 2 {
        return cps.to_vec();
    }

    let mut out = Vec::with_capacity(cps.len());
    let mut i = 0;
    let n = cps.len();

    while i < n {
        if i + 1 < n {
            let base = cps[i];
            let comb = cps[i + 1];
            let composed = match comb {
                '\u{0300}' => match base {
                    'a' => Some('\u{00E0}'),
                    'A' => Some('\u{00C0}'),
                    _ => None,
                },
                '\u{0301}' => match base {
                    'a' => Some('\u{00E1}'),
                    'e' => Some('\u{00E9}'),
                    'i' => Some('\u{00ED}'),
                    'o' => Some('\u{00F3}'),
                    'u' => Some('\u{00FA}'),
                    'A' => Some('\u{00C1}'),
                    'E' => Some('\u{00C9}'),
                    'I' => Some('\u{00CD}'),
                    'O' => Some('\u{00D3}'),
                    'U' => Some('\u{00DA}'),
                    _ => None,
                },
                '\u{0302}' => match base {
                    'a' => Some('\u{00E2}'),
                    'e' => Some('\u{00EA}'),
                    'o' => Some('\u{00F4}'),
                    'A' => Some('\u{00C2}'),
                    'E' => Some('\u{00CA}'),
                    'O' => Some('\u{00D4}'),
                    _ => None,
                },
                '\u{0303}' => match base {
                    'a' => Some('\u{00E3}'),
                    'o' => Some('\u{00F5}'),
                    'A' => Some('\u{00C3}'),
                    'O' => Some('\u{00D5}'),
                    'n' => Some('\u{00F1}'),
                    'N' => Some('\u{00D1}'),
                    _ => None,
                },
                '\u{0308}' => match base {
                    'u' => Some('\u{00FC}'),
                    'U' => Some('\u{00DC}'),
                    _ => None,
                },
                '\u{0327}' => match base {
                    'c' => Some('\u{00E7}'),
                    'C' => Some('\u{00C7}'),
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

        out.push(cps[i]);
        i += 1;
    }

    out
}

/// Simple lowercase for Latin + common accented letters.
fn to_lower(cp: char) -> char {
    let c = cp as u32;
    if (b'A' as u32..=b'Z' as u32).contains(&c) {
        return char::from_u32(c + 32).unwrap_or(cp);
    }
    // Latin-1 supplement uppercase (C0-DE except D7 multiply)
    if (0xC0..=0xDE).contains(&c) && c != 0xD7 {
        return char::from_u32(c + 32).unwrap_or(cp);
    }
    cp
}

/// Normalize text: NFC lowercase, collapse whitespace, trim.
fn normalize(text: &str) -> Vec<char> {
    let cps: Vec<char> = text.chars().collect();

    // NFD -> NFC: collapse combining accents
    let cps = collapse_nfd_combining_accents(&cps);

    // Lowercase
    let cps: Vec<char> = cps.iter().map(|&c| to_lower(c)).collect();

    // Collapse whitespace + trim
    let mut out = Vec::with_capacity(cps.len());
    let mut prev_space = true; // trim leading
    for &cp in &cps {
        let ws = matches!(cp, ' ' | '\t' | '\n' | '\r');
        if ws {
            if !prev_space {
                out.push(' ');
            }
            prev_space = true;
        } else {
            out.push(cp);
            prev_space = false;
        }
    }
    // trim trailing
    if out.last() == Some(&' ') {
        out.pop();
    }
    out
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

#[derive(Debug)]
struct Token {
    chars: Vec<char>,
    is_punct: bool,
}

fn tokenize(cps: &[char]) -> Vec<Token> {
    let mut tokens = Vec::new();
    let mut i = 0;
    let n = cps.len();

    while i < n {
        let ch = cps[i];
        if is_word_char(ch) {
            let mut tok = Token {
                chars: Vec::new(),
                is_punct: false,
            };
            while i < n && is_word_char(cps[i]) {
                tok.chars.push(cps[i]);
                i += 1;
            }
            tokens.push(tok);
        } else if is_punctuation(ch) {
            tokens.push(Token {
                chars: vec![ch],
                is_punct: true,
            });
            i += 1;
        } else {
            // whitespace or unknown: skip
            i += 1;
        }
    }

    tokens
}

// ---------------------------------------------------------------------------
// Vowel-group counting (digraph-aware)
// ---------------------------------------------------------------------------

fn count_vowel_groups(word: &[char]) -> i32 {
    let mut count = 0i32;
    let mut i = 0;
    let n = word.len();

    while i < n {
        let ch = word[i];
        // qu digraph: u silent or glide -- skip both
        if ch == 'q' && i + 1 < n && word[i + 1] == 'u' {
            i += 2;
            continue;
        }
        // gu before e/i: u silent
        if ch == 'g' && i + 1 < n && word[i + 1] == 'u' && i + 2 < n && is_soft_vowel(word[i + 2]) {
            i += 2;
            continue;
        }
        // ou diphthong: one vowel group
        if ch == 'o' && i + 1 < n && word[i + 1] == 'u' {
            count += 1;
            i += 2;
            continue;
        }
        if is_vowel_char(ch) {
            count += 1;
        }
        i += 1;
    }

    count
}

// ---------------------------------------------------------------------------
// Stress position finder
// ---------------------------------------------------------------------------

/// Find the stressed syllable index (0-based from end).
///
/// Portuguese stress rules:
/// - Words with acute/circumflex/tilde accent: stress on accented syllable
/// - Words ending in a, e, o, am, em, en: penultimate (paroxytone)
/// - Words ending in consonant (except s), i, u: ultimate (oxytone)
fn find_stress_position(word: &[char]) -> i32 {
    let vowel_group_count = count_vowel_groups(word);

    // Find accented vowel group position
    let mut accent_group: i32 = -1;
    let mut current_group = 0i32;
    let mut i = 0;
    let n = word.len();

    while i < n {
        let ch = word[i];
        // Skip digraphs same as count_vowel_groups
        if ch == 'q' && i + 1 < n && word[i + 1] == 'u' {
            i += 2;
            continue;
        }
        if ch == 'g' && i + 1 < n && word[i + 1] == 'u' && i + 2 < n && is_soft_vowel(word[i + 2]) {
            i += 2;
            continue;
        }
        if ch == 'o' && i + 1 < n && word[i + 1] == 'u' {
            if is_stress_accent(ch) || is_circumflex(ch) || is_tilde(ch) {
                accent_group = current_group;
            }
            current_group += 1;
            i += 2;
            continue;
        }
        if is_vowel_char(ch) {
            if is_stress_accent(ch) || is_circumflex(ch) || is_tilde(ch) {
                accent_group = current_group;
            }
            current_group += 1;
        }
        i += 1;
    }

    if vowel_group_count == 0 {
        return 0;
    }

    if accent_group >= 0 {
        return vowel_group_count - 1 - accent_group;
    }

    // Default rules based on ending
    // Strip trailing 's' for rule check
    let mut stripped: Vec<char> = word.to_vec();
    while stripped.last() == Some(&'s') {
        stripped.pop();
    }
    let sn = stripped.len();

    // Check endings: a, e, o, am, em, en -> paroxytone
    let mut paroxytone = false;
    if sn >= 1 {
        let last = stripped[sn - 1];
        if last == 'a' || last == 'e' || last == 'o' {
            paroxytone = true;
        }
    }
    if !paroxytone && sn >= 2 {
        let sl = stripped[sn - 2];
        let el = stripped[sn - 1];
        if matches!((sl, el), ('a', 'm') | ('e', 'm') | ('e', 'n')) {
            paroxytone = true;
        }
    }

    if paroxytone {
        return std::cmp::min(1, vowel_group_count - 1);
    }
    // Oxytone: last syllable
    0
}

// ---------------------------------------------------------------------------
// Intervocalic helper
// ---------------------------------------------------------------------------

fn is_intervocalic(i: usize, word: &[char]) -> bool {
    if i == 0 || i >= word.len() - 1 {
        return false;
    }
    is_vowel_char(word[i - 1]) && is_vowel_char(word[i + 1])
}

// ---------------------------------------------------------------------------
// Word conversion result
// ---------------------------------------------------------------------------

struct WordResult {
    phonemes: Vec<char>,
    stress_idx: i32, // index into phonemes of the stressed vowel (-1 if none)
}

// ---------------------------------------------------------------------------
// Vowel helpers
// ---------------------------------------------------------------------------

/// Map base vowel to its nasal counterpart.
fn nasal_of(base: char) -> char {
    match base {
        'a' => NASAL_A,
        'e' => NASAL_E,
        'i' => NASAL_I,
        'o' => NASAL_O,
        'u' => NASAL_U,
        _ => base,
    }
}

/// Map base vowel (with acute accent) to open IPA vowel.
fn open_vowel_of(base: char) -> char {
    match base {
        'a' => 'a',
        'e' => IPA_EPSILON,
        'i' => 'i',
        'o' => IPA_OPEN_O,
        'u' => 'u',
        _ => base,
    }
}

// ---------------------------------------------------------------------------
// Convert a single word to IPA phonemes
// ---------------------------------------------------------------------------

fn convert_word(word: &[char]) -> WordResult {
    let mut ph: Vec<char> = Vec::new();
    let mut stress_idx: i32 = -1;
    let mut i = 0;
    let n = word.len();

    // Determine stress target
    let stress_from_end = find_stress_position(word);
    let vowel_group_count = count_vowel_groups(word);
    let stress_vowel_target = vowel_group_count - 1 - stress_from_end;
    let mut current_vowel_group = 0i32;

    while i < n {
        let ch = word[i];

        // === Multi-character sequences (longest first) ===

        // "nh" -> palatal nasal
        if ch == 'n' && i + 1 < n && word[i + 1] == 'h' {
            ph.push(IPA_PALATAL_N);
            i += 2;
            continue;
        }
        // "lh" -> palatal lateral
        if ch == 'l' && i + 1 < n && word[i + 1] == 'h' {
            ph.push(IPA_PALATAL_L);
            i += 2;
            continue;
        }
        // "ch" -> voiceless postalveolar fricative
        if ch == 'c' && i + 1 < n && word[i + 1] == 'h' {
            ph.push(IPA_ESH);
            i += 2;
            continue;
        }
        // "rr" -> uvular fricative
        if ch == 'r' && i + 1 < n && word[i + 1] == 'r' {
            ph.push(IPA_UVULAR_R);
            i += 2;
            continue;
        }
        // "ss" -> voiceless alveolar sibilant
        if ch == 's' && i + 1 < n && word[i + 1] == 's' {
            ph.push('s');
            i += 2;
            continue;
        }
        // "sc" before e/i -> s
        if ch == 's' && i + 1 < n && word[i + 1] == 'c' && i + 2 < n && is_soft_vowel(word[i + 2]) {
            ph.push('s');
            i += 2; // skip "sc", vowel handled next iteration
            continue;
        }
        // "qu" digraph
        if ch == 'q' && i + 1 < n && word[i + 1] == 'u' {
            ph.push('k');
            if i + 2 < n && is_soft_vowel(word[i + 2]) {
                // Silent u before e/i
                i += 2;
            } else {
                // Pronounced u before a/o -> append w glide
                ph.push('w');
                i += 2;
            }
            continue;
        }
        // "gu" before e/i -> voiced velar plosive (u silent)
        if ch == 'g' && i + 1 < n && word[i + 1] == 'u' && i + 2 < n && is_soft_vowel(word[i + 2]) {
            ph.push(IPA_VOICED_G);
            i += 2;
            continue;
        }
        // "ou" -> o (common BR reduction, single vowel group)
        if ch == 'o' && i + 1 < n && word[i + 1] == 'u' {
            let is_stressed = current_vowel_group == stress_vowel_target;
            if is_stressed {
                stress_idx = ph.len() as i32;
            }
            ph.push('o');
            current_vowel_group += 1;
            i += 2;
            continue;
        }

        // === Consonants ===

        if ch == 'r' {
            if is_intervocalic(i, word) {
                ph.push(IPA_TAP);
            } else {
                ph.push(IPA_UVULAR_R);
            }
            i += 1;
            continue;
        }
        if ch == 's' {
            // Intervocalic s -> z
            if i > 0 && i + 1 < n && is_vowel_char(word[i - 1]) && is_vowel_char(word[i + 1]) {
                ph.push('z');
            } else {
                ph.push('s');
            }
            i += 1;
            continue;
        }
        if ch == 'x' {
            if i == 0 {
                ph.push(IPA_ESH);
            } else if i > 0 && is_vowel_char(word[i - 1]) && i + 1 < n && is_vowel_char(word[i + 1])
            {
                ph.push('z');
            } else {
                ph.push(IPA_ESH);
            }
            i += 1;
            continue;
        }
        if ch == 'c' {
            if i + 1 < n && is_soft_vowel(word[i + 1]) {
                ph.push('s');
            } else {
                ph.push('k');
            }
            i += 1;
            continue;
        }
        if ch == '\u{E7}' {
            // c cedilla
            ph.push('s');
            i += 1;
            continue;
        }
        if ch == 'g' {
            if i + 1 < n && is_soft_vowel(word[i + 1]) {
                ph.push(IPA_EZH);
            } else {
                ph.push(IPA_VOICED_G);
            }
            i += 1;
            continue;
        }
        if ch == 'j' {
            ph.push(IPA_EZH);
            i += 1;
            continue;
        }
        if ch == 't' {
            // BR Portuguese: t before i -> affricate
            if i + 1 < n && (word[i + 1] == 'i' || word[i + 1] == '\u{ED}') {
                ph.push(PUA_AFFRICATE_TCH);
            } else {
                ph.push('t');
            }
            i += 1;
            continue;
        }
        if ch == 'd' {
            // BR Portuguese: d before i -> affricate
            if i + 1 < n && (word[i + 1] == 'i' || word[i + 1] == '\u{ED}') {
                ph.push(PUA_AFFRICATE_DZH);
            } else {
                ph.push('d');
            }
            i += 1;
            continue;
        }
        if ch == 'h' {
            // Silent (digraphs already handled above)
            i += 1;
            continue;
        }
        // Simple consonant pass-through: b f k l m n p v
        if matches!(ch, 'b' | 'f' | 'k' | 'l' | 'm' | 'n' | 'p' | 'v') {
            ph.push(ch);
            i += 1;
            continue;
        }
        if ch == 'z' {
            ph.push('z');
            i += 1;
            continue;
        }
        if ch == 'w' {
            ph.push('w');
            i += 1;
            continue;
        }

        // === Vowels ===

        if is_vowel_char(ch) {
            let is_stressed = current_vowel_group == stress_vowel_target;
            let base = accent_base(ch);

            // --- Nasalization check ---
            let mut is_nasal = false;
            let mut nasal_absorbed = false;

            if is_tilde(ch) {
                is_nasal = true;
            } else if i + 1 < n && (word[i + 1] == 'n' || word[i + 1] == 'm') {
                // Exception: "nh" digraph -- do NOT nasalize before nh
                if word[i + 1] == 'n' && i + 2 < n && word[i + 2] == 'h' {
                    // is_nasal stays false
                } else if i + 2 >= n {
                    // n/m at end of word: absorb nasal consonant
                    is_nasal = true;
                    nasal_absorbed = true;
                } else if !is_vowel_char(word[i + 2]) {
                    // n/m followed by consonant: absorb nasal coda
                    is_nasal = true;
                    nasal_absorbed = true;
                }
            }

            let phoneme = if is_nasal {
                nasal_of(base)
            } else if is_stress_accent(ch) {
                // Acute accent = open vowel
                open_vowel_of(base)
            } else if is_circumflex(ch) {
                // Circumflex = closed vowel (base)
                base
            } else {
                base
            };

            if is_stressed {
                stress_idx = ph.len() as i32;
            }
            ph.push(phoneme);
            current_vowel_group += 1;

            if nasal_absorbed {
                i += 2; // skip vowel + nasal consonant
            } else {
                i += 1;
            }
            continue;
        }

        // Punctuation pass-through
        if is_punctuation(ch) {
            ph.push(ch);
            i += 1;
            continue;
        }

        // Unknown character: skip
        i += 1;
    }

    WordResult {
        phonemes: ph,
        stress_idx,
    }
}

// ---------------------------------------------------------------------------
// Post-processing step 1: remove duplicate nasal coda
// ---------------------------------------------------------------------------

fn remove_duplicate_nasal_coda(ph: &mut Vec<char>, stress_idx: &mut i32) {
    let mut i = ph.len() as i32 - 1;
    while i >= 1 {
        let idx = i as usize;
        if (ph[idx] == 'n' || ph[idx] == 'm') && is_ipa_nasal_vowel(ph[idx - 1]) {
            // Check boundary: at end, or next is space / punctuation
            let at_boundary =
                idx == ph.len() - 1 || ph[idx + 1] == ' ' || is_punctuation(ph[idx + 1]);
            if at_boundary {
                if *stress_idx >= 0 && i < *stress_idx {
                    *stress_idx -= 1;
                }
                ph.remove(idx);
            }
        }
        i -= 1;
    }
}

// ---------------------------------------------------------------------------
// Post-processing step 2: coda-l vocalization (l -> w in coda)
// ---------------------------------------------------------------------------

fn apply_coda_l_vocalization(ph: &mut [char]) {
    for i in 0..ph.len() {
        if ph[i] != 'l' {
            continue;
        }

        // l at end of list -> coda
        if i == ph.len() - 1 {
            ph[i] = 'w';
            continue;
        }
        let next = ph[i + 1];
        // l before space or punctuation -> coda (word-final)
        if next == ' ' || is_punctuation(next) {
            ph[i] = 'w';
            continue;
        }
        // l before a consonant -> coda (also handle PUA affricates)
        if (is_ipa_consonant(next) || next == PUA_AFFRICATE_TCH || next == PUA_AFFRICATE_DZH)
            && !is_ipa_vowel(next)
        {
            ph[i] = 'w';
        }
    }
}

// ---------------------------------------------------------------------------
// Post-processing step 3: BR postprocessing
// (t/d palatalization before final unstressed e, final vowel reduction)
// ---------------------------------------------------------------------------

/// Find (start, end) ranges for each word delimited by space phonemes.
fn find_word_ranges(ph: &[char]) -> Vec<(usize, usize)> {
    let mut ranges = Vec::new();
    let mut start = 0;
    for (i, &ch) in ph.iter().enumerate() {
        if ch == ' ' {
            if i > start {
                ranges.push((start, i));
            }
            start = i + 1;
        }
    }
    if start < ph.len() {
        ranges.push((start, ph.len()));
    }
    ranges
}

fn apply_br_postprocessing(ph: &mut [char], stress_idx: i32) {
    // --- Pass 1: t/d palatalization + unstressed final e/o reduction ---
    let ranges = find_word_ranges(ph);

    for (start, end) in ranges {
        if end - start < 2 {
            continue;
        }

        let mut last_idx = end as i32 - 1;
        // Skip trailing punctuation
        while last_idx >= start as i32 && is_punctuation(ph[last_idx as usize]) {
            last_idx -= 1;
        }
        if last_idx < start as i32 {
            continue;
        }
        let last_idx = last_idx as usize;

        // Unstressed final 'e'
        if ph[last_idx] == 'e' && last_idx as i32 != stress_idx {
            // Preceded by 't' -> t + e -> affricate + i
            if last_idx > start && ph[last_idx - 1] == 't' {
                ph[last_idx - 1] = PUA_AFFRICATE_TCH;
                ph[last_idx] = 'i';
                continue;
            }
            // Preceded by 'd' -> d + e -> affricate + i
            if last_idx > start && ph[last_idx - 1] == 'd' {
                ph[last_idx - 1] = PUA_AFFRICATE_DZH;
                ph[last_idx] = 'i';
                continue;
            }
            // General reduction: unstressed final e -> i
            ph[last_idx] = 'i';
        }
        // Unstressed final 'o' -> u
        else if ph[last_idx] == 'o' && last_idx as i32 != stress_idx {
            ph[last_idx] = 'u';
        }
    }
}

// ---------------------------------------------------------------------------
// Full word conversion pipeline
// ---------------------------------------------------------------------------

fn process_word(word: &[char]) -> WordResult {
    let mut wr = convert_word(word);
    remove_duplicate_nasal_coda(&mut wr.phonemes, &mut wr.stress_idx);
    apply_coda_l_vocalization(&mut wr.phonemes);
    apply_br_postprocessing(&mut wr.phonemes, wr.stress_idx);
    wr
}

// ---------------------------------------------------------------------------
// Map char phonemes to String tokens
// ---------------------------------------------------------------------------

/// Convert a char phoneme to its String token representation.
///
/// Single IPA codepoints (including PUA E054/E055) pass through as a
/// single-char string.
fn phoneme_char_to_token(ch: char) -> String {
    ch.to_string()
}

// ---------------------------------------------------------------------------
// Top-level phonemization
// ---------------------------------------------------------------------------

/// Phonemize a Portuguese sentence, returning (tokens, prosody).
fn phonemize_sentence_with_prosody(text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
    let cps = normalize(text);
    let tokens = tokenize(&cps);

    let mut phonemes: Vec<String> = Vec::new();
    let mut prosody_list: Vec<Option<ProsodyInfo>> = Vec::new();
    let mut need_space = false;

    for tok in &tokens {
        if tok.is_punct {
            // Punctuation: no space before
            for &ch in &tok.chars {
                phonemes.push(phoneme_char_to_token(ch));
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 0,
                }));
            }
            need_space = true;
        } else {
            if need_space {
                phonemes.push(" ".to_string());
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 0,
                }));
            }
            let wr = process_word(&tok.chars);
            let word_phoneme_count = wr.phonemes.len() as i32;

            for (j, &ph) in wr.phonemes.iter().enumerate() {
                let a2 = if j as i32 == wr.stress_idx { 2 } else { 0 };
                phonemes.push(phoneme_char_to_token(ph));
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2,
                    a3: word_phoneme_count,
                }));
            }
            need_space = true;
        }
    }

    (phonemes, prosody_list)
}

// ---------------------------------------------------------------------------
// PortuguesePhonemizer struct + Phonemizer trait
// ---------------------------------------------------------------------------

/// Brazilian Portuguese rule-based phonemizer.
pub struct PortuguesePhonemizer;

impl PortuguesePhonemizer {
    pub fn new() -> Self {
        Self
    }
}

impl Default for PortuguesePhonemizer {
    fn default() -> Self {
        Self::new()
    }
}

impl Phonemizer for PortuguesePhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        let (tokens, prosody) = phonemize_sentence_with_prosody(text);
        Ok((tokens, prosody))
    }

    fn language_code(&self) -> &str {
        "pt"
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: phonemize text and return phoneme chars (before token mapping).
    fn phonemize_chars(text: &str) -> Vec<char> {
        let cps = normalize(text);
        let tokens = tokenize(&cps);
        let mut result = Vec::new();
        let mut need_space = false;

        for tok in &tokens {
            if tok.is_punct {
                for &ch in &tok.chars {
                    result.push(ch);
                }
                need_space = true;
            } else {
                if need_space {
                    result.push(' ');
                }
                let wr = process_word(&tok.chars);
                result.extend_from_slice(&wr.phonemes);
                need_space = true;
            }
        }
        result
    }

    // ------------------------------------------------------------------
    // Test 1: simple word "bom" -> nasal vowel
    // ------------------------------------------------------------------
    #[test]
    fn test_nasal_vowel_bom() {
        // "bom" -> b + nasal o (o tilde)
        let ph = phonemize_chars("bom");
        assert!(ph.contains(&NASAL_O), "expected nasal o in {:?}", ph);
        // Should NOT have trailing 'm' after nasal vowel (duplicate removed)
        assert_eq!(
            ph.last(),
            Some(&NASAL_O),
            "no trailing m after nasal: {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 2: coda-l vocalization "Brasil"
    // ------------------------------------------------------------------
    #[test]
    fn test_coda_l_vocalization_brasil() {
        // "Brasil" -> b ʁ a z i w (final l -> w)
        let ph = phonemize_chars("Brasil");
        assert!(ph.contains(&'w'), "expected coda-l -> w in {:?}", ph);
        assert!(
            !ph.contains(&'l'),
            "should not contain 'l' in coda: {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 3: t/d palatalization before i "tia" / "dia"
    // ------------------------------------------------------------------
    #[test]
    fn test_palatalization_tia_dia() {
        let ph_tia = phonemize_chars("tia");
        assert!(
            ph_tia.contains(&PUA_AFFRICATE_TCH),
            "expected tS affricate in 'tia': {:?}",
            ph_tia
        );

        let ph_dia = phonemize_chars("dia");
        assert!(
            ph_dia.contains(&PUA_AFFRICATE_DZH),
            "expected dZ affricate in 'dia': {:?}",
            ph_dia
        );
    }

    // ------------------------------------------------------------------
    // Test 4: r polymorphism - intervocalic vs initial
    // ------------------------------------------------------------------
    #[test]
    fn test_r_polymorphism() {
        // "caro" -> k a ɾ u  (intervocalic r -> tap)
        let ph_caro = phonemize_chars("caro");
        assert!(
            ph_caro.contains(&IPA_TAP),
            "expected tap in 'caro': {:?}",
            ph_caro
        );

        // "rato" -> ʁ a t u  (initial r -> uvular)
        let ph_rato = phonemize_chars("rato");
        assert!(
            ph_rato.contains(&IPA_UVULAR_R),
            "expected uvular r in 'rato': {:?}",
            ph_rato
        );
    }

    // ------------------------------------------------------------------
    // Test 5: digraphs "lh" -> palatal lateral, "nh" -> palatal nasal
    // ------------------------------------------------------------------
    #[test]
    fn test_digraphs_lh_nh() {
        let ph_filho = phonemize_chars("filho");
        assert!(
            ph_filho.contains(&IPA_PALATAL_L),
            "expected palatal L in 'filho': {:?}",
            ph_filho
        );

        let ph_junho = phonemize_chars("junho");
        assert!(
            ph_junho.contains(&IPA_PALATAL_N),
            "expected palatal N in 'junho': {:?}",
            ph_junho
        );
    }

    // ------------------------------------------------------------------
    // Test 6: stress on accented vowels
    // ------------------------------------------------------------------
    #[test]
    fn test_stress_accented_vowels() {
        // "caf\u{E9}" (cafe with acute) -> stress on last vowel group
        let word: Vec<char> = "caf\u{E9}".chars().collect();
        let pos = find_stress_position(&word);
        // Acute on last vowel -> oxytone -> pos from end = 0
        assert_eq!(pos, 0, "cafe should be oxytone");
    }

    // ------------------------------------------------------------------
    // Test 7: default stress rules (paroxytone)
    // ------------------------------------------------------------------
    #[test]
    fn test_default_stress_paroxytone() {
        // "casa" ends in 'a' -> paroxytone (penultimate)
        let word: Vec<char> = "casa".chars().collect();
        let pos = find_stress_position(&word);
        assert_eq!(pos, 1, "casa should be paroxytone (stress from end = 1)");
    }

    // ------------------------------------------------------------------
    // Test 8: BR postprocessing - unstressed final e -> i
    //         and t + unstressed final e -> tS + i
    // ------------------------------------------------------------------
    #[test]
    fn test_final_e_reduction() {
        // "grande" -> final 'e' is unstressed -> d+e becomes dZ+i
        let ph = phonemize_chars("grande");
        let last_two: Vec<char> = ph[ph.len().saturating_sub(2)..].to_vec();
        assert_eq!(
            last_two,
            vec![PUA_AFFRICATE_DZH, 'i'],
            "grande should end with dZ+i: {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 9: c cedilla -> s
    // ------------------------------------------------------------------
    #[test]
    fn test_cedilla() {
        // "coracao" with cedilla and tilde
        let ph = phonemize_chars("cora\u{E7}\u{E3}o");
        assert!(
            ph.contains(&'s'),
            "expected 's' from cedilla in 'coracao': {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 10: "rr" -> uvular fricative
    // ------------------------------------------------------------------
    #[test]
    fn test_rr_uvular() {
        // "carro" -> k a ʁ u (rr -> uvular)
        let ph = phonemize_chars("carro");
        assert!(
            ph.contains(&IPA_UVULAR_R),
            "expected uvular R in 'carro': {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 11: "qu" digraph
    // ------------------------------------------------------------------
    #[test]
    fn test_qu_digraph() {
        // "quero" -> k e ʁ u  (qu before e: u is silent)
        let ph = phonemize_chars("quero");
        assert_eq!(ph[0], 'k', "quero should start with k: {:?}", ph);

        // "quando" -> k w ... (qu before a: u is pronounced as w)
        let ph_quando = phonemize_chars("quando");
        assert_eq!(ph_quando[0], 'k', "quando starts with k");
        assert_eq!(ph_quando[1], 'w', "quando has w glide after k");
    }

    // ------------------------------------------------------------------
    // Test 12: intervocalic s -> z
    // ------------------------------------------------------------------
    #[test]
    fn test_intervocalic_s() {
        // "casa" -> k a z a (s between vowels -> z)
        let ph = phonemize_chars("casa");
        assert!(
            ph.contains(&'z'),
            "expected 'z' from intervocalic s in 'casa': {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 13: prosody info (a1=0, a2=stress level, a3=word phoneme count)
    // ------------------------------------------------------------------
    #[test]
    fn test_prosody_info() {
        let (tokens, prosody) = phonemize_sentence_with_prosody("bom");
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must match length"
        );
        // At least one phoneme should have a2=2 (stressed)
        let has_stress = prosody.iter().any(|p| p.is_some_and(|info| info.a2 == 2));
        assert!(has_stress, "should have at least one stressed phoneme");
    }

    // ------------------------------------------------------------------
    // Test 15: NFD combining accent normalization
    // ------------------------------------------------------------------
    #[test]
    fn test_nfd_normalization() {
        // "cafe\u{0301}" (NFD: e + combining acute) should produce same
        // as "caf\u{E9}" (NFC)
        let nfd = phonemize_chars("cafe\u{0301}");
        let nfc = phonemize_chars("caf\u{E9}");
        assert_eq!(nfd, nfc, "NFD and NFC should produce identical phonemes");
    }

    // ------------------------------------------------------------------
    // Test 16: unstressed final o -> u
    // ------------------------------------------------------------------
    #[test]
    fn test_final_o_reduction() {
        // "gato" -> g a t u (unstressed final o -> u)
        let ph = phonemize_chars("gato");
        assert_eq!(
            ph.last(),
            Some(&'u'),
            "gato should end with 'u' (final o reduction): {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 17: "ss" -> single s
    // ------------------------------------------------------------------
    #[test]
    fn test_ss_digraph() {
        // "passo" -> p a s u (ss -> s, final o -> u)
        let ph = phonemize_chars("passo");
        let s_count = ph.iter().filter(|&&c| c == 's').count();
        assert_eq!(s_count, 1, "ss should produce single s: {:?}", ph);
    }

    // ------------------------------------------------------------------
    // Test 18: multi-word sentence with space
    // ------------------------------------------------------------------
    #[test]
    fn test_multi_word() {
        let ph = phonemize_chars("bom dia");
        assert!(
            ph.contains(&' '),
            "multi-word should contain space: {:?}",
            ph
        );
    }

    // ------------------------------------------------------------------
    // Test 19: "ou" diphthong reduction -> o
    // ------------------------------------------------------------------
    #[test]
    fn test_ou_reduction() {
        // "outro" -> o t ʁ u (ou -> o, BR reduction)
        let ph = phonemize_chars("outro");
        // First phoneme should be 'o' (from 'ou' reduction)
        assert_eq!(ph[0], 'o', "ou should reduce to o: {:?}", ph);
    }

    // ------------------------------------------------------------------
    // Test 20: language_code returns "pt"
    // ------------------------------------------------------------------
    #[test]
    fn test_language_code() {
        let pt = PortuguesePhonemizer::new();
        assert_eq!(pt.language_code(), "pt");
    }
}

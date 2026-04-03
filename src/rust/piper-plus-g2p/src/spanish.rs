//! Rule-based Spanish G2P (grapheme-to-phoneme) phonemizer.
//!
//! Converts Spanish text to IPA phonemes using orthographic rules.
//! No external dependencies required -- Spanish has nearly phonemic
//! orthography, making rule-based G2P highly effective.
//!
//! Uses Latin American pronunciation by default (seseo: c/z -> s).
//!
//! ## PUA codepoints
//!
//! | Token | PUA      | IPA  | Description                         |
//! |-------|----------|------|-------------------------------------|
//! | `rr`  | U+E01D   |      | Alveolar trill (rr, word-initial r) |
//! | `tʃ`  | U+E054   | tʃ   | Voiceless postalveolar affricate    |
//! | `dʒ`  | U+E055   | dʒ   | Voiced postalveolar affricate       |

use std::collections::HashSet;
use std::sync::LazyLock;

use crate::error::G2pError;
use crate::phonemizer::{Phonemizer, ProsodyInfo};
use crate::token_map::token_to_pua;

// ---------------------------------------------------------------------------
// IPA codepoints used in output
// ---------------------------------------------------------------------------

/// Voiced bilabial fricative (allophone of /b/)
const IPA_BETA: char = '\u{03B2}';
/// Voiced dental fricative (allophone of /d/)
const IPA_ETH: char = '\u{00F0}';
/// Voiced velar stop (IPA g U+0261)
const IPA_G: char = '\u{0261}';
/// Voiced velar fricative (allophone of /g/)
const IPA_GAMMA: char = '\u{0263}';
/// Palatal nasal (ñ)
const IPA_PALATAL_NASAL: char = '\u{0272}';
/// Alveolar tap (single r)
const IPA_TAP: char = '\u{027E}';
/// Voiced palatal fricative (y, ll - yeísmo)
const IPA_PALATAL_FRIC: char = '\u{029D}';
/// Primary stress marker
const IPA_STRESS: char = '\u{02C8}';

// PUA codepoints
const PUA_RR: char = '\u{E01D}';
const PUA_TCH: char = '\u{E054}';

// ---------------------------------------------------------------------------
// Punctuation
// ---------------------------------------------------------------------------

fn is_punctuation(c: char) -> bool {
    matches!(
        c,
        ',' | '.' | ';' | ':' | '!' | '?' | '\u{00A1}' | '\u{00BF}'
    )
}

// ---------------------------------------------------------------------------
// Vowels & accents
// ---------------------------------------------------------------------------

fn is_vowel(c: char) -> bool {
    matches!(c, 'a' | 'e' | 'i' | 'o' | 'u')
}

fn is_strong_vowel(c: char) -> bool {
    matches!(c, 'a' | 'e' | 'o')
}

fn is_weak_vowel(c: char) -> bool {
    matches!(c, 'i' | 'u')
}

/// Map accented vowel to base vowel.
fn accent_base(c: char) -> char {
    match c {
        '\u{00E1}' => 'a', // á
        '\u{00E9}' => 'e', // é
        '\u{00ED}' => 'i', // í
        '\u{00F3}' => 'o', // ó
        '\u{00FA}' => 'u', // ú
        '\u{00FC}' => 'u', // ü
        _ => c,
    }
}

fn has_stress_accent(c: char) -> bool {
    matches!(
        c,
        '\u{00E1}' | '\u{00E9}' | '\u{00ED}' | '\u{00F3}' | '\u{00FA}'
    )
}

fn is_vowel_or_accented(c: char) -> bool {
    is_vowel(c) || has_stress_accent(c) || c == '\u{00FC}'
}

// ---------------------------------------------------------------------------
// Spanish alpha check (lowercase)
// ---------------------------------------------------------------------------

fn is_spanish_alpha(c: char) -> bool {
    if c.is_ascii_lowercase() {
        return true;
    }
    matches!(
        c,
        '\u{00F1}'  // ñ
        | '\u{00E1}' | '\u{00E9}' | '\u{00ED}' | '\u{00F3}' | '\u{00FA}' | '\u{00FC}'
    )
}

// ---------------------------------------------------------------------------
// Lowercase for Spanish
// ---------------------------------------------------------------------------

fn to_lower_sp(c: char) -> char {
    if c.is_ascii_uppercase() {
        return (c as u8 + 32) as char;
    }
    match c {
        '\u{00C1}' => '\u{00E1}', // Á → á
        '\u{00C9}' => '\u{00E9}', // É → é
        '\u{00CD}' => '\u{00ED}', // Í → í
        '\u{00D3}' => '\u{00F3}', // Ó → ó
        '\u{00DA}' => '\u{00FA}', // Ú → ú
        '\u{00DC}' => '\u{00FC}', // Ü → ü
        '\u{00D1}' => '\u{00F1}', // Ñ → ñ
        _ => c,
    }
}

// ---------------------------------------------------------------------------
// NFC normalization for combining accents
// ---------------------------------------------------------------------------

/// Collapse NFD combining accent sequences into precomposed NFC codepoints.
///
/// Handles the combining marks relevant to Spanish:
///   U+0301 COMBINING ACUTE ACCENT  -> á é í ó ú / Á É Í Ó Ú
///   U+0303 COMBINING TILDE         -> ñ / Ñ
///   U+0308 COMBINING DIAERESIS     -> ü / Ü
fn collapse_combiners(cps: &[char]) -> Vec<char> {
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
                '\u{0301}' => match base {
                    // combining acute
                    'A' => Some('\u{00C1}'),
                    'a' => Some('\u{00E1}'),
                    'E' => Some('\u{00C9}'),
                    'e' => Some('\u{00E9}'),
                    'I' => Some('\u{00CD}'),
                    'i' => Some('\u{00ED}'),
                    'O' => Some('\u{00D3}'),
                    'o' => Some('\u{00F3}'),
                    'U' => Some('\u{00DA}'),
                    'u' => Some('\u{00FA}'),
                    _ => None,
                },
                '\u{0308}' => match base {
                    // combining diaeresis
                    'U' => Some('\u{00DC}'),
                    'u' => Some('\u{00FC}'),
                    _ => None,
                },
                '\u{0303}' => match base {
                    // combining tilde
                    'N' => Some('\u{00D1}'),
                    'n' => Some('\u{00F1}'),
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

// ---------------------------------------------------------------------------
// Normalize: NFC collapse + lowercase
// ---------------------------------------------------------------------------

fn normalize(text: &str) -> Vec<char> {
    let cps: Vec<char> = text.chars().collect();
    let nfc = collapse_combiners(&cps);
    nfc.into_iter().map(to_lower_sp).collect()
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

#[derive(Debug)]
enum Token {
    Word(Vec<char>),
    Punct(Vec<char>),
}

fn tokenize(cps: &[char]) -> Vec<Token> {
    let mut tokens = Vec::new();
    let n = cps.len();
    let mut i = 0;
    while i < n {
        if is_spanish_alpha(cps[i]) {
            let mut chars = Vec::new();
            while i < n && is_spanish_alpha(cps[i]) {
                chars.push(cps[i]);
                i += 1;
            }
            tokens.push(Token::Word(chars));
        } else if is_punctuation(cps[i]) {
            let mut chars = Vec::new();
            while i < n && is_punctuation(cps[i]) {
                chars.push(cps[i]);
                i += 1;
            }
            tokens.push(Token::Punct(chars));
        } else {
            i += 1; // skip whitespace, digits, unknown
        }
    }
    tokens
}

// ---------------------------------------------------------------------------
// Function words (unstressed)
// ---------------------------------------------------------------------------

static UNSTRESSED_FUNCTION_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "el", "la", "los", "las", "un", "una", "de", "del", "al", "a", "en", "con", "por", "y",
        "o", "que", "se", "me", "te", "le", "lo", "nos", "su", "mi", "tu", "es", "no", "si",
    ]
    .into_iter()
    .collect()
});

/// Convert a char slice to a UTF-8 string (for function-word lookup).
fn chars_to_string(chars: &[char]) -> String {
    chars.iter().collect()
}

// ---------------------------------------------------------------------------
// Grapheme segmentation
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct GUnit {
    chars: Vec<char>,
    is_vowel: bool,
    is_silent: bool,
}

fn segment_graphemes(word: &[char]) -> Vec<GUnit> {
    let bw: Vec<char> = word.iter().map(|&c| accent_base(c)).collect();
    let mut units = Vec::new();
    let n = word.len();
    let mut i = 0;
    while i < n {
        let bc = bw[i];

        // "qu" (u is silent)
        if bc == 'q' && i + 1 < n && bw[i + 1] == 'u' {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "gü" before e/i — diaeresis makes u pronounced
        if bc == 'g'
            && i + 1 < n
            && word[i + 1] == '\u{00FC}'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "gu" before e/i (u silent)
        if bc == 'g'
            && i + 1 < n
            && bw[i + 1] == 'u'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "ch"
        if bc == 'c' && i + 1 < n && bw[i + 1] == 'h' {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "ll"
        if bc == 'l' && i + 1 < n && bw[i + 1] == 'l' {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "rr"
        if bc == 'r' && i + 1 < n && bw[i + 1] == 'r' {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "sc" before e/i
        if bc == 's'
            && i + 1 < n
            && bw[i + 1] == 'c'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // "xc" before e/i
        if bc == 'x'
            && i + 1 < n
            && bw[i + 1] == 'c'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            units.push(GUnit {
                chars: vec![word[i], word[i + 1]],
                is_vowel: false,
                is_silent: false,
            });
            i += 2;
            continue;
        }

        // Silent "h"
        if bc == 'h' {
            units.push(GUnit {
                chars: vec![word[i]],
                is_vowel: false,
                is_silent: true,
            });
            i += 1;
            continue;
        }

        // Vowels (including accented)
        if is_vowel(bc) {
            units.push(GUnit {
                chars: vec![word[i]],
                is_vowel: true,
                is_silent: false,
            });
            i += 1;
            continue;
        }

        // All other consonants
        units.push(GUnit {
            chars: vec![word[i]],
            is_vowel: false,
            is_silent: false,
        });
        i += 1;
    }
    units
}

// ---------------------------------------------------------------------------
// Syllabification
// ---------------------------------------------------------------------------

/// 13 inseparable onset clusters
fn is_inseparable(c1: char, c2: char) -> bool {
    if c2 == 'l' {
        return matches!(c1, 'b' | 'c' | 'f' | 'g' | 'p' | 't');
    }
    if c2 == 'r' {
        return matches!(c1, 'b' | 'c' | 'd' | 'f' | 'g' | 'p' | 't');
    }
    false
}

/// Return the base consonant letter from a grapheme unit.
fn base_cons_of_unit(u: &GUnit) -> char {
    accent_base(*u.chars.last().unwrap())
}

fn find_syllable_boundaries(units: &[GUnit]) -> Vec<usize> {
    // Build non-silent mask
    let mut ns_idx: Vec<usize> = Vec::new();
    let mut ns_vow: Vec<bool> = Vec::new();
    for (idx, unit) in units.iter().enumerate() {
        if unit.is_silent {
            continue;
        }
        ns_idx.push(idx);
        ns_vow.push(unit.is_vowel);
    }

    let ns_n = ns_idx.len();
    if ns_n == 0 {
        return vec![0];
    }

    let mut ns_bounds: Vec<usize> = vec![0];

    let mut i = 1;
    while i < ns_n {
        if ns_vow[i] {
            if i > 0 && ns_vow[i - 1] {
                // Two adjacent vowels: hiatus vs diphthong
                let prev_g = *units[ns_idx[i - 1]].chars.last().unwrap();
                let curr_g = *units[ns_idx[i]].chars.last().unwrap();
                let prev_b = accent_base(prev_g);
                let curr_b = accent_base(curr_g);
                if is_strong_vowel(prev_b) && is_strong_vowel(curr_b) {
                    ns_bounds.push(i); // hiatus
                } else {
                    // Accented weak vowel forces hiatus
                    if (is_weak_vowel(curr_b) && has_stress_accent(curr_g))
                        || (is_weak_vowel(prev_b) && has_stress_accent(prev_g))
                    {
                        ns_bounds.push(i);
                    }
                }
            }
            i += 1;
        } else {
            // Consonant cluster before next vowel
            let cons_start = i;
            while i < ns_n && !ns_vow[i] {
                i += 1;
            }
            let cons_count = i - cons_start;
            if i < ns_n {
                // vowel follows
                if cons_count == 1 {
                    ns_bounds.push(cons_start);
                } else if cons_count == 2 {
                    let c1 = base_cons_of_unit(&units[ns_idx[cons_start]]);
                    let c2 = base_cons_of_unit(&units[ns_idx[cons_start + 1]]);
                    if is_inseparable(c1, c2) {
                        ns_bounds.push(cons_start);
                    } else {
                        ns_bounds.push(cons_start + 1);
                    }
                } else {
                    // 3+ consonants
                    let c1 = base_cons_of_unit(&units[ns_idx[i - 2]]);
                    let c2 = base_cons_of_unit(&units[ns_idx[i - 1]]);
                    if is_inseparable(c1, c2) {
                        ns_bounds.push(i - 2);
                    } else {
                        ns_bounds.push(i - 1);
                    }
                }
            }
        }
    }

    // Map back to unit indices
    ns_bounds.iter().map(|&b| ns_idx[b]).collect()
}

// ---------------------------------------------------------------------------
// Stress assignment
// ---------------------------------------------------------------------------

/// Find the character-index of the first accented vowel in a word, or None.
fn find_accent_index(word: &[char]) -> Option<usize> {
    word.iter().position(|&c| has_stress_accent(c))
}

fn get_stressed_syllable(word: &[char], units: &[GUnit], boundaries: &[usize]) -> usize {
    let num_syl = boundaries.len();
    if num_syl == 0 {
        return 0;
    }

    // Check for explicit accent
    if let Some(acc_idx) = find_accent_index(word) {
        // Map char index to unit index
        let mut char_off = 0usize;
        let mut acc_unit_idx = 0usize;
        for (uid, unit) in units.iter().enumerate() {
            let u_len = unit.chars.len();
            if char_off <= acc_idx && acc_idx < char_off + u_len {
                acc_unit_idx = uid;
                break;
            }
            char_off += u_len;
        }
        // Find which syllable contains this unit
        for s in (0..num_syl).rev() {
            if boundaries[s] <= acc_unit_idx {
                return s;
            }
        }
        return 0;
    }

    if num_syl == 1 {
        return 0;
    }

    // Default stress rules
    let last = accent_base(*word.last().unwrap());
    if is_vowel(last) || last == 'n' || last == 's' {
        num_syl.saturating_sub(2) // penultimate
    } else {
        num_syl - 1 // ultimate
    }
}

// ---------------------------------------------------------------------------
// G2P: grapheme-to-phoneme conversion
// ---------------------------------------------------------------------------

struct G2PResult {
    phonemes: Vec<char>,
    stressed_syl: usize,
    units: Vec<GUnit>,
    boundaries: Vec<usize>,
}

fn g2p_word(word: &[char]) -> G2PResult {
    let mut ph: Vec<char> = Vec::new();
    let n = word.len();

    // Build base-form word
    let bw: Vec<char> = word.iter().map(|&c| accent_base(c)).collect();

    let prev_is_vowel = |idx: usize| -> bool { idx > 0 && is_vowel_or_accented(word[idx - 1]) };
    let is_after_nasal =
        |idx: usize| -> bool { idx > 0 && (bw[idx - 1] == 'm' || bw[idx - 1] == 'n') };
    let is_word_initial = |idx: usize| -> bool { idx == 0 };

    let mut i = 0;
    while i < n {
        let bc = bw[i];

        // --- Vowels ---
        if is_vowel(bc) {
            ph.push(bc);
            i += 1;
            continue;
        }

        // --- Multi-character sequences (longest first) ---

        // "qu" -> k
        if bc == 'q' && i + 1 < n && bw[i + 1] == 'u' {
            ph.push('k');
            i += 2;
            continue;
        }

        // "ch" -> tʃ (PUA)
        if bc == 'c' && i + 1 < n && bw[i + 1] == 'h' {
            ph.push(PUA_TCH);
            i += 2;
            continue;
        }

        // "ll" -> palatal fricative (yeísmo)
        if bc == 'l' && i + 1 < n && bw[i + 1] == 'l' {
            ph.push(IPA_PALATAL_FRIC);
            i += 2;
            continue;
        }

        // "rr" -> trill (PUA)
        if bc == 'r' && i + 1 < n && bw[i + 1] == 'r' {
            ph.push(PUA_RR);
            i += 2;
            continue;
        }

        // "gü" before e/i -> g w
        if bc == 'g'
            && i + 1 < n
            && word[i + 1] == '\u{00FC}'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            ph.push(IPA_G);
            ph.push('w');
            i += 2;
            continue;
        }

        // "gu" before e/i -> g (u silent); allophonic
        if bc == 'g'
            && i + 1 < n
            && bw[i + 1] == 'u'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            if prev_is_vowel(i) && !is_after_nasal(i) {
                ph.push(IPA_GAMMA);
            } else {
                ph.push(IPA_G);
            }
            i += 2;
            continue;
        }

        // "sc" before e/i -> s (seseo, no geminate)
        if bc == 's'
            && i + 1 < n
            && bw[i + 1] == 'c'
            && i + 2 < n
            && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
        {
            ph.push('s');
            i += 2;
            continue;
        }

        // --- Single character rules ---

        // b / v (betacismo)
        if bc == 'b' || bc == 'v' {
            if is_word_initial(i) || is_after_nasal(i) || (i > 0 && bw[i - 1] == 'l') {
                ph.push('b');
            } else {
                ph.push(IPA_BETA);
            }
            i += 1;
            continue;
        }

        // c
        if bc == 'c' {
            if i + 1 < n && (bw[i + 1] == 'e' || bw[i + 1] == 'i') {
                ph.push('s'); // seseo
            } else {
                ph.push('k');
            }
            i += 1;
            continue;
        }

        // d
        if bc == 'd' {
            if is_word_initial(i) || is_after_nasal(i) || (i > 0 && bw[i - 1] == 'l') {
                ph.push('d');
            } else {
                ph.push(IPA_ETH);
            }
            i += 1;
            continue;
        }

        // f
        if bc == 'f' {
            ph.push('f');
            i += 1;
            continue;
        }

        // g
        if bc == 'g' {
            if i + 1 < n && (bw[i + 1] == 'e' || bw[i + 1] == 'i') {
                ph.push('x'); // velar fricative (jota)
            } else if is_word_initial(i) || is_after_nasal(i) || (i > 0 && bw[i - 1] == 'l') {
                ph.push(IPA_G);
            } else {
                ph.push(IPA_GAMMA);
            }
            i += 1;
            continue;
        }

        // h (silent)
        if bc == 'h' {
            i += 1;
            continue;
        }

        // j
        if bc == 'j' {
            ph.push('x');
            i += 1;
            continue;
        }

        // k
        if bc == 'k' {
            ph.push('k');
            i += 1;
            continue;
        }

        // l
        if bc == 'l' {
            ph.push('l');
            i += 1;
            continue;
        }

        // m
        if bc == 'm' {
            ph.push('m');
            i += 1;
            continue;
        }

        // n
        if bc == 'n' {
            ph.push('n');
            i += 1;
            continue;
        }

        // ñ
        if bc == '\u{00F1}' {
            ph.push(IPA_PALATAL_NASAL);
            i += 1;
            continue;
        }

        // p
        if bc == 'p' {
            ph.push('p');
            i += 1;
            continue;
        }

        // r (single)
        if bc == 'r' {
            if is_word_initial(i) {
                ph.push(PUA_RR); // trill
            } else if i > 0 && (bw[i - 1] == 'l' || bw[i - 1] == 'n' || bw[i - 1] == 's') {
                ph.push(PUA_RR); // trill after l/n/s
            } else {
                ph.push(IPA_TAP);
            }
            i += 1;
            continue;
        }

        // s
        if bc == 's' {
            ph.push('s');
            i += 1;
            continue;
        }

        // t
        if bc == 't' {
            ph.push('t');
            i += 1;
            continue;
        }

        // w
        if bc == 'w' {
            ph.push('w');
            i += 1;
            continue;
        }

        // x
        if bc == 'x' {
            // xc+e/i: c is absorbed, x provides /ks/
            if i + 1 < n && bw[i + 1] == 'c' && i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i')
            {
                ph.push('k');
                ph.push('s');
                i += 2;
                continue;
            }
            ph.push('k');
            ph.push('s');
            i += 1;
            continue;
        }

        // y
        if bc == 'y' {
            if i == n - 1 {
                ph.push('i'); // word-final y -> vowel
            } else {
                ph.push(IPA_PALATAL_FRIC);
            }
            i += 1;
            continue;
        }

        // z (seseo)
        if bc == 'z' {
            ph.push('s');
            i += 1;
            continue;
        }

        // Unknown -> skip
        i += 1;
    }

    // Syllabification & stress
    let units = segment_graphemes(word);
    let boundaries = find_syllable_boundaries(&units);
    let stressed_syl = get_stressed_syllable(word, &units, &boundaries);

    G2PResult {
        phonemes: ph,
        stressed_syl,
        units,
        boundaries,
    }
}

// ---------------------------------------------------------------------------
// Phoneme count per grapheme unit (for stress marker insertion)
// ---------------------------------------------------------------------------

fn phoneme_count_for_unit(unit: &GUnit) -> usize {
    let base: Vec<char> = unit.chars.iter().map(|&c| accent_base(c)).collect();

    // Silent h -> 0
    if base.len() == 1 && base[0] == 'h' {
        return 0;
    }

    // "gü" digraph -> 2 (g + w)
    if base.len() == 2 && base[0] == 'g' && unit.chars[1] == '\u{00FC}' {
        return 2;
    }

    // "xc" digraph before e/i -> k s (2 phonemes)
    if base.len() == 2 && base[0] == 'x' && base[1] == 'c' {
        return 2;
    }

    // x -> ks (2)
    if base.len() == 1 && base[0] == 'x' {
        return 2;
    }

    // Everything else -> 1
    1
}

// ---------------------------------------------------------------------------
// Insert stress marker
// ---------------------------------------------------------------------------

fn insert_stress_marker(
    phonemes: &mut Vec<char>,
    units: &[GUnit],
    boundaries: &[usize],
    stressed_syl: usize,
) {
    if phonemes.is_empty() || boundaries.is_empty() {
        return;
    }
    if stressed_syl >= boundaries.len() {
        return;
    }

    let num_units = units.len();
    let syl_start = boundaries[stressed_syl];
    let syl_end = if stressed_syl + 1 < boundaries.len() {
        boundaries[stressed_syl + 1]
    } else {
        num_units
    };

    // Find first vowel unit in stressed syllable
    let stressed_unit_idx = units[syl_start..syl_end.min(num_units)]
        .iter()
        .enumerate()
        .find(|(_, u)| u.is_vowel)
        .map(|(offset, _)| syl_start + offset);

    let stressed_unit_idx = match stressed_unit_idx {
        Some(idx) => idx,
        None => return,
    };

    // Walk units -> accumulate phoneme count to find insertion point
    let mut ph_i = 0usize;
    for (uid, unit) in units.iter().enumerate() {
        if uid == stressed_unit_idx {
            phonemes.insert(ph_i, IPA_STRESS);
            return;
        }
        ph_i += phoneme_count_for_unit(unit);
    }
}

// ---------------------------------------------------------------------------
// Map multi-character tokens to PUA single codepoints
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
// Public phonemization with prosody
// ---------------------------------------------------------------------------

/// Convert Spanish text to phoneme list and prosody features.
///
/// Returns (phonemes, prosody_info_list) where each phoneme has corresponding
/// prosody info with a1=0, a2=stress-based (0 or 2), a3=word phoneme count.
pub fn phonemize_spanish_with_prosody(text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
    let cps = normalize(text);
    let tokens = tokenize(&cps);
    if tokens.is_empty() {
        return (Vec::new(), Vec::new());
    }

    let mut phonemes: Vec<String> = Vec::new();
    let mut prosody_list: Vec<Option<ProsodyInfo>> = Vec::new();
    let mut need_space = false;

    for tok in &tokens {
        match tok {
            Token::Punct(chars) => {
                for &c in chars {
                    phonemes.push(c.to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2: 0,
                        a3: 0,
                    }));
                }
            }
            Token::Word(chars) => {
                if need_space {
                    phonemes.push(" ".to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2: 0,
                        a3: 0,
                    }));
                }

                let mut res = g2p_word(chars);
                let word_utf8 = chars_to_string(chars);
                let is_function = UNSTRESSED_FUNCTION_WORDS.contains(word_utf8.as_str());

                if !is_function {
                    insert_stress_marker(
                        &mut res.phonemes,
                        &res.units,
                        &res.boundaries,
                        res.stressed_syl,
                    );
                }

                // Count phonemes without stress marker for a3
                let word_phoneme_count =
                    res.phonemes.iter().filter(|&&c| c != IPA_STRESS).count() as i32;

                for (idx, &ph_char) in res.phonemes.iter().enumerate() {
                    if ph_char == IPA_STRESS {
                        phonemes.push(IPA_STRESS.to_string());
                        prosody_list.push(Some(ProsodyInfo {
                            a1: 0,
                            a2: 2,
                            a3: word_phoneme_count,
                        }));
                    } else {
                        // Check if this phoneme is right after a stress marker
                        let is_stressed_vowel =
                            idx > 0 && res.phonemes[idx - 1] == IPA_STRESS && is_vowel(ph_char);
                        let a2 = if is_stressed_vowel { 2 } else { 0 };
                        phonemes.push(ph_char.to_string());
                        prosody_list.push(Some(ProsodyInfo {
                            a1: 0,
                            a2,
                            a3: word_phoneme_count,
                        }));
                    }
                }

                need_space = true;
            }
        }
    }

    // Map multi-character tokens to PUA single chars
    let mapped = map_sequence(phonemes);
    (mapped, prosody_list)
}

/// Convert Spanish text to phoneme list (without prosody).
pub fn phonemize_spanish(text: &str) -> Vec<String> {
    let (phonemes, _) = phonemize_spanish_with_prosody(text);
    phonemes
}

// ---------------------------------------------------------------------------
// SpanishPhonemizer
// ---------------------------------------------------------------------------

/// Spanish phonemizer using rule-based G2P.
///
/// Converts Spanish text to IPA phonemes using orthographic rules.
/// No external dependencies required. Uses Latin American pronunciation
/// (seseo: c/z -> s).
pub struct SpanishPhonemizer;

impl SpanishPhonemizer {
    pub fn new() -> Self {
        Self
    }
}

impl Default for SpanishPhonemizer {
    fn default() -> Self {
        Self::new()
    }
}

impl Phonemizer for SpanishPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        Ok(phonemize_spanish_with_prosody(text))
    }

    fn language_code(&self) -> &str {
        "es"
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: phonemize and return the phoneme strings.
    fn ph(text: &str) -> Vec<String> {
        phonemize_spanish(text)
    }

    /// Helper: phonemize and return (phonemes, prosody).
    fn ph_with_prosody(text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
        phonemize_spanish_with_prosody(text)
    }

    // ===== Basic G2P rules =====

    #[test]
    fn test_simple_word_hola() {
        // "hola" -> h is silent, o l a with stress on penultimate (o)
        let result = ph("hola");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "should have stress marker: {:?}",
            result
        );
        assert!(result.contains(&"o".to_string()));
        assert!(result.contains(&"l".to_string()));
        assert!(result.contains(&"a".to_string()));
        // h should NOT appear (silent)
        assert!(
            !result.iter().any(|s| s == "h"),
            "h should be silent: {:?}",
            result
        );
    }

    #[test]
    fn test_seseo_c_before_e_and_z() {
        // "ce" -> s e (seseo: c before e -> s)
        let result_ce = ph("ce");
        assert!(
            result_ce.contains(&"s".to_string()),
            "c before e -> s: {:?}",
            result_ce
        );

        // "zapato" -> s a p a t o (z -> s)
        let result_z = ph("zapato");
        assert!(
            result_z.contains(&"s".to_string()),
            "z -> s: {:?}",
            result_z
        );
        assert!(
            !result_z.iter().any(|s| s == "z"),
            "z should not appear: {:?}",
            result_z
        );
    }

    #[test]
    fn test_ch_affricate() {
        // "chico" -> tʃ (PUA_TCH) i k o
        let result = ph("chico");
        let tch_str = PUA_TCH.to_string();
        assert!(result.contains(&tch_str), "ch -> PUA_TCH: {:?}", result);
    }

    #[test]
    fn test_ll_yeismo() {
        // "calle" -> k a ʝ e
        let result = ph("calle");
        let palatal = IPA_PALATAL_FRIC.to_string();
        assert!(result.contains(&palatal), "ll -> ʝ: {:?}", result);
    }

    #[test]
    fn test_rr_trill_and_word_initial_r() {
        // "perro" -> rr (PUA_RR)
        let result_rr = ph("perro");
        let rr_str = PUA_RR.to_string();
        assert!(result_rr.contains(&rr_str), "rr -> PUA_RR: {:?}", result_rr);

        // "rosa" -> word-initial r -> trill
        let result_r = ph("rosa");
        assert!(
            result_r.contains(&rr_str),
            "word-initial r -> PUA_RR: {:?}",
            result_r
        );
    }

    #[test]
    fn test_ntilde_palatal_nasal() {
        // "niño" -> n i ɲ o
        let result = ph("niño");
        let palatal = IPA_PALATAL_NASAL.to_string();
        assert!(result.contains(&palatal), "ñ -> ɲ: {:?}", result);
    }

    #[test]
    fn test_intervocalic_allophony_b_d_g() {
        // "lobo" -> l o β o
        assert!(
            ph("lobo").contains(&IPA_BETA.to_string()),
            "intervocalic b -> β"
        );
        // "todo" -> t o ð o
        assert!(
            ph("todo").contains(&IPA_ETH.to_string()),
            "intervocalic d -> ð"
        );
        // "lago" -> l a ɣ o
        assert!(
            ph("lago").contains(&IPA_GAMMA.to_string()),
            "intervocalic g -> ɣ"
        );
    }

    // ===== Stress rules =====

    #[test]
    fn test_stress_penultimate_and_final() {
        let stress = IPA_STRESS.to_string();
        // "casa" ends in vowel -> penultimate stress
        assert!(ph("casa").contains(&stress), "penultimate stress for casa");
        // "ciudad" ends in 'd' (not n/s) -> final syllable stress
        assert!(ph("ciudad").contains(&stress), "final stress for ciudad");
        // "teléfono" has accent on é -> stress on that syllable
        assert!(
            ph("teléfono").contains(&stress),
            "accent mark stress for teléfono"
        );
    }

    // ===== Function word stress removal =====

    #[test]
    fn test_function_word_no_stress() {
        let stress = IPA_STRESS.to_string();
        assert!(!ph("el").contains(&stress), "function word 'el' no stress");
        assert!(!ph("de").contains(&stress), "function word 'de' no stress");
    }

    #[test]
    fn test_non_function_word_has_stress() {
        let stress = IPA_STRESS.to_string();
        assert!(ph("sol").contains(&stress), "content word 'sol' has stress");
    }

    // ===== Punctuation =====

    #[test]
    fn test_punctuation_preserved() {
        let result = ph("¡hola!");
        assert!(result.contains(&"\u{00A1}".to_string()), "¡ preserved");
        assert!(result.contains(&"!".to_string()), "! preserved");
    }

    // ===== Prosody =====

    #[test]
    fn test_prosody_length_matches_phonemes() {
        let (phonemes, prosody) = ph_with_prosody("hola mundo");
        assert_eq!(phonemes.len(), prosody.len());
    }

    #[test]
    fn test_prosody_stress_a2() {
        let (phonemes, prosody) = ph_with_prosody("casa");
        let stress = IPA_STRESS.to_string();
        if let Some(pos) = phonemes.iter().position(|s| s == &stress) {
            let pi = prosody[pos].unwrap();
            assert_eq!(pi.a2, 2, "stress marker should have a2=2");
        }
    }

    // ===== Language code =====

    #[test]
    fn test_language_code() {
        assert_eq!(SpanishPhonemizer::new().language_code(), "es");
    }

    // ===== Normalize / NFC =====

    #[test]
    fn test_uppercase_normalized() {
        assert_eq!(ph("HOLA"), ph("hola"), "uppercase normalizes to lowercase");
    }

    // ===== Additional G2P rules =====

    #[test]
    fn test_qu_produces_k() {
        let result = ph("queso");
        assert!(result.contains(&"k".to_string()), "qu -> k: {:?}", result);
    }

    #[test]
    fn test_gu_before_e_silent_u() {
        let result = ph("guerra");
        let g_str = IPA_G.to_string();
        assert!(result.contains(&g_str), "gu before e -> g: {:?}", result);
    }

    #[test]
    fn test_j_and_g_before_e_produce_x() {
        assert!(ph("jardín").contains(&"x".to_string()), "j -> x");
        assert!(ph("gente").contains(&"x".to_string()), "g before e -> x");
    }

    #[test]
    fn test_word_final_y_vowel() {
        let result = ph("hoy");
        // h is silent, o is a vowel, y at end -> i
        assert!(
            result.contains(&"i".to_string()),
            "word-final y -> i: {:?}",
            result
        );
    }

    #[test]
    fn test_x_produces_ks() {
        let result = ph("examen");
        assert!(result.iter().any(|s| s == "k"), "x -> k: {:?}", result);
        assert!(result.iter().any(|s| s == "s"), "x -> s: {:?}", result);
    }

    #[test]
    fn test_v_same_as_b_word_initial() {
        assert!(ph("vino").contains(&"b".to_string()), "word-initial v -> b");
    }

    #[test]
    fn test_empty_text() {
        assert!(ph("").is_empty());
    }

    #[test]
    fn test_space_between_words() {
        assert!(
            ph("el sol").contains(&" ".to_string()),
            "space between words"
        );
    }

    #[test]
    fn test_b_after_nasal_is_stop() {
        let result = ph("amba");
        assert!(result.contains(&"b".to_string()), "b after nasal -> stop");
        assert!(
            !result.contains(&IPA_BETA.to_string()),
            "b after nasal NOT β"
        );
    }

    #[test]
    fn test_r_after_n_is_trill() {
        let result = ph("enrique");
        assert!(
            result.contains(&PUA_RR.to_string()),
            "r after n -> trill: {:?}",
            result
        );
    }

    #[test]
    fn test_multiple_words_sentence() {
        let (phonemes, prosody) = ph_with_prosody("hola, como estas");
        assert_eq!(phonemes.len(), prosody.len());
        let stress = IPA_STRESS.to_string();
        let stress_count = phonemes.iter().filter(|s| **s == stress).count();
        assert!(
            stress_count >= 2,
            "multiple content words have stress: {:?}",
            phonemes
        );
    }

    #[test]
    fn test_sc_before_e_produces_single_s() {
        // "escena" -> sc before e -> single s, no geminate
        let result = ph("escena");
        assert!(
            result.iter().any(|s| s == "s"),
            "sc before e -> s: {:?}",
            result
        );
    }
}

//! Korean phonemizer -- Hangul decomposition + IPA mapping.
//!
//! Ports the C++ `korean_phonemize.cpp` to Rust.
//! Converts Korean text to IPA phonemes by decomposing Hangul syllable blocks
//! into jamo (initial, medial, final) and mapping each to IPA tokens.
//! Multi-codepoint IPA tokens use PUA codepoints matching `token_map.rs`.
//!
//! Without g2pk2, only basic liaison (연음화) is applied as a phonological rule.

use crate::error::G2pError;
use crate::phonemizer::{Phonemizer, ProsodyInfo};

// ---------------------------------------------------------------------------
// Hangul syllable block range (U+AC00 .. U+D7A3)
// ---------------------------------------------------------------------------
const HANGUL_START: u32 = 0xAC00;
const HANGUL_END: u32 = 0xD7A3;

// Decomposition constants
const N_INITIALS: usize = 19;
const N_MEDIALS: usize = 21;
const N_FINALS: usize = 28;

// ---------------------------------------------------------------------------
// PUA codepoints for multi-character IPA tokens
// Must match token_map.rs / token_mapper.py
// ---------------------------------------------------------------------------

// Aspirated consonants (shared with Chinese)
const PUA_PH: char = '\u{E020}'; // pʰ
const PUA_TH: char = '\u{E021}'; // tʰ
const PUA_KH: char = '\u{E022}'; // kʰ

// Affricates (shared with Chinese)
const PUA_TC: char = '\u{E023}'; // tɕ
const PUA_TCH: char = '\u{E024}'; // tɕʰ

// Tense consonants (Korean-only)
const PUA_PP: char = '\u{E04B}'; // p͈
const PUA_TT: char = '\u{E04C}'; // t͈
const PUA_KK: char = '\u{E04D}'; // k͈
const PUA_SS: char = '\u{E04E}'; // s͈
const PUA_TTCH: char = '\u{E04F}'; // t͈ɕ

// Unreleased finals (Korean-only)
const PUA_K_UNREL: char = '\u{E050}'; // k̚
const PUA_T_UNREL: char = '\u{E051}'; // t̚
const PUA_P_UNREL: char = '\u{E052}'; // p̚

// Single IPA codepoints used in output
const IPA_FLAP: char = '\u{027E}'; // ɾ alveolar flap (ㄹ initial)
const IPA_ENG: char = '\u{014B}'; // ŋ velar nasal (ㅇ coda)
const IPA_OPEN_E: char = '\u{025B}'; // ɛ open-mid front unrounded (ㅐ)
const IPA_OPEN_MID_BACK: char = '\u{028C}'; // ʌ open-mid back unrounded (ㅓ)
const IPA_CLOSE_BACK_UNR: char = '\u{026F}'; // ɯ close back unrounded (ㅡ)
const IPA_VELAR_APPROX: char = '\u{0270}'; // ɰ velar approximant (ㅢ)

// ---------------------------------------------------------------------------
// Initial consonants (초성) -- 19 entries, index -> Option<char>
// None = silent (ㅇ in initial position)
// ---------------------------------------------------------------------------
const INITIAL_TABLE: [Option<char>; N_INITIALS] = [
    Some('k'),      //  0: ㄱ
    Some(PUA_KK),   //  1: ㄲ (tense)
    Some('n'),      //  2: ㄴ
    Some('t'),      //  3: ㄷ
    Some(PUA_TT),   //  4: ㄸ (tense)
    Some(IPA_FLAP), //  5: ㄹ
    Some('m'),      //  6: ㅁ
    Some('p'),      //  7: ㅂ
    Some(PUA_PP),   //  8: ㅃ (tense)
    Some('s'),      //  9: ㅅ
    Some(PUA_SS),   // 10: ㅆ (tense)
    None,           // 11: ㅇ (silent in initial)
    Some(PUA_TC),   // 12: ㅈ
    Some(PUA_TTCH), // 13: ㅉ (tense)
    Some(PUA_TCH),  // 14: ㅊ (aspirated)
    Some(PUA_KH),   // 15: ㅋ (aspirated)
    Some(PUA_TH),   // 16: ㅌ (aspirated)
    Some(PUA_PH),   // 17: ㅍ (aspirated)
    Some('h'),      // 18: ㅎ
];

// ---------------------------------------------------------------------------
// Medial vowels (중성) -- 21 entries, index -> 1-2 phonemes
// Diphthongs produce glide + vowel (2 phonemes).
// ---------------------------------------------------------------------------
const MEDIAL_TABLE: [(char, Option<char>); N_MEDIALS] = [
    ('a', None),                    //  0: ㅏ
    (IPA_OPEN_E, None),             //  1: ㅐ
    ('j', Some('a')),               //  2: ㅑ
    ('j', Some(IPA_OPEN_E)),        //  3: ㅒ
    (IPA_OPEN_MID_BACK, None),      //  4: ㅓ
    ('e', None),                    //  5: ㅔ
    ('j', Some(IPA_OPEN_MID_BACK)), //  6: ㅕ
    ('j', Some('e')),               //  7: ㅖ
    ('o', None),                    //  8: ㅗ
    ('w', Some('a')),               //  9: ㅘ
    ('w', Some(IPA_OPEN_E)),        // 10: ㅙ
    ('w', Some('e')),               // 11: ㅚ (modern Seoul: [we])
    ('j', Some('o')),               // 12: ㅛ
    ('u', None),                    // 13: ㅜ
    ('w', Some(IPA_OPEN_MID_BACK)), // 14: ㅝ
    ('w', Some('e')),               // 15: ㅞ
    ('w', Some('i')),               // 16: ㅟ
    ('j', Some('u')),               // 17: ㅠ
    (IPA_CLOSE_BACK_UNR, None),     // 18: ㅡ
    (IPA_VELAR_APPROX, Some('i')),  // 19: ㅢ
    ('i', None),                    // 20: ㅣ
];

// ---------------------------------------------------------------------------
// Final consonants (종성) -- 28 entries
//
// Finals are neutralized to 7 surface forms: k̚, t̚, p̚, n, m, l, ŋ.
// Complex finals (겹받침) are simplified to their representative sound.
// Index 0 = no final consonant.
//
// For liaison: `liaison_initial` is the initial index the final "becomes"
// when followed by ㅇ (silent initial). -1 means no liaison.
// `residual_final` holds the index remaining in the current syllable after
// liaison (for complex finals); 0 means the final moves entirely.
// ---------------------------------------------------------------------------
struct FinalEntry {
    ph: Option<char>,
    liaison_initial: i32,
    residual_final: usize,
}

const FINAL_TABLE: [FinalEntry; N_FINALS] = [
    FinalEntry {
        ph: None,
        liaison_initial: -1,
        residual_final: 0,
    }, //  0: (none)
    FinalEntry {
        ph: Some(PUA_K_UNREL),
        liaison_initial: 0,
        residual_final: 0,
    }, //  1: ㄱ
    FinalEntry {
        ph: Some(PUA_K_UNREL),
        liaison_initial: 1,
        residual_final: 0,
    }, //  2: ㄲ
    FinalEntry {
        ph: Some(PUA_K_UNREL),
        liaison_initial: 9,
        residual_final: 1,
    }, //  3: ㄳ -> ㅅ, residual ㄱ
    FinalEntry {
        ph: Some('n'),
        liaison_initial: -1,
        residual_final: 0,
    }, //  4: ㄴ
    FinalEntry {
        ph: Some('n'),
        liaison_initial: 12,
        residual_final: 4,
    }, //  5: ㄵ -> ㅈ, residual ㄴ
    FinalEntry {
        ph: Some('n'),
        liaison_initial: -1,
        residual_final: 0,
    }, //  6: ㄶ (ㄴ+ㅎ -> n)
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: 3,
        residual_final: 0,
    }, //  7: ㄷ
    FinalEntry {
        ph: Some('l'),
        liaison_initial: 5,
        residual_final: 0,
    }, //  8: ㄹ
    FinalEntry {
        ph: Some(PUA_K_UNREL),
        liaison_initial: 0,
        residual_final: 8,
    }, //  9: ㄺ -> ㄱ, residual ㄹ
    FinalEntry {
        ph: Some('m'),
        liaison_initial: 6,
        residual_final: 8,
    }, // 10: ㄻ -> ㅁ, residual ㄹ
    FinalEntry {
        ph: Some('l'),
        liaison_initial: 7,
        residual_final: 8,
    }, // 11: ㄼ -> ㅂ, residual ㄹ
    FinalEntry {
        ph: Some('l'),
        liaison_initial: 9,
        residual_final: 8,
    }, // 12: ㄽ -> ㅅ, residual ㄹ
    FinalEntry {
        ph: Some('l'),
        liaison_initial: 16,
        residual_final: 8,
    }, // 13: ㄾ -> ㅌ, residual ㄹ
    FinalEntry {
        ph: Some('l'),
        liaison_initial: 17,
        residual_final: 8,
    }, // 14: ㄿ -> ㅍ, residual ㄹ
    FinalEntry {
        ph: Some('l'),
        liaison_initial: -1,
        residual_final: 0,
    }, // 15: ㅀ (ㄹ+ㅎ -> l)
    FinalEntry {
        ph: Some('m'),
        liaison_initial: -1,
        residual_final: 0,
    }, // 16: ㅁ
    FinalEntry {
        ph: Some(PUA_P_UNREL),
        liaison_initial: 7,
        residual_final: 0,
    }, // 17: ㅂ
    FinalEntry {
        ph: Some(PUA_P_UNREL),
        liaison_initial: 9,
        residual_final: 17,
    }, // 18: ㅄ -> ㅅ, residual ㅂ
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: 9,
        residual_final: 0,
    }, // 19: ㅅ
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: 10,
        residual_final: 0,
    }, // 20: ㅆ
    FinalEntry {
        ph: Some(IPA_ENG),
        liaison_initial: -1,
        residual_final: 0,
    }, // 21: ㅇ (velar nasal)
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: 12,
        residual_final: 0,
    }, // 22: ㅈ
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: 14,
        residual_final: 0,
    }, // 23: ㅊ
    FinalEntry {
        ph: Some(PUA_K_UNREL),
        liaison_initial: 15,
        residual_final: 0,
    }, // 24: ㅋ
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: 16,
        residual_final: 0,
    }, // 25: ㅌ
    FinalEntry {
        ph: Some(PUA_P_UNREL),
        liaison_initial: 17,
        residual_final: 0,
    }, // 26: ㅍ
    FinalEntry {
        ph: Some(PUA_T_UNREL),
        liaison_initial: -1,
        residual_final: 0,
    }, // 27: ㅎ (h dropped)
];

// ---------------------------------------------------------------------------
// Hangul decomposition
// ---------------------------------------------------------------------------

fn is_hangul_syllable(ch: char) -> bool {
    let code = ch as u32;
    (HANGUL_START..=HANGUL_END).contains(&code)
}

/// Decompose a Hangul syllable into (initial, medial, final) indices.
fn decompose(ch: char) -> (usize, usize, usize) {
    let code = (ch as u32 - HANGUL_START) as usize;
    let initial = code / (N_MEDIALS * N_FINALS);
    let medial = (code % (N_MEDIALS * N_FINALS)) / N_FINALS;
    let final_ = code % N_FINALS;
    (initial, medial, final_)
}

// ---------------------------------------------------------------------------
// NFD Hangul jamo -> NFC recomposition
//
// macOS decomposes Hangul into NFD jamo sequences (U+1100-U+11FF).
// This function recomposes them into precomposed syllables (U+AC00-U+D7A3).
// ---------------------------------------------------------------------------

fn is_leading_jamo(ch: char) -> bool {
    let c = ch as u32;
    (0x1100..=0x1112).contains(&c)
}

fn is_vowel_jamo(ch: char) -> bool {
    let c = ch as u32;
    (0x1161..=0x1175).contains(&c)
}

fn is_trailing_jamo(ch: char) -> bool {
    let c = ch as u32;
    (0x11A8..=0x11C2).contains(&c)
}

fn compose_hangul_jamo(cps: &[char]) -> Vec<char> {
    let mut out = Vec::with_capacity(cps.len());
    let n = cps.len();
    let mut i = 0;

    while i < n {
        if is_leading_jamo(cps[i]) && i + 1 < n && is_vowel_jamo(cps[i + 1]) {
            let leading = cps[i] as u32 - 0x1100;
            let vowel = cps[i + 1] as u32 - 0x1161;
            let trailing;
            if i + 2 < n && is_trailing_jamo(cps[i + 2]) {
                trailing = cps[i + 2] as u32 - 0x11A8 + 1;
                i += 3;
            } else {
                trailing = 0;
                i += 2;
            }
            let composed = (leading * 21 + vowel) * 28 + trailing + 0xAC00;
            if let Some(c) = char::from_u32(composed) {
                out.push(c);
            }
        } else {
            out.push(cps[i]);
            i += 1;
        }
    }

    out
}

// ---------------------------------------------------------------------------
// Punctuation
// ---------------------------------------------------------------------------

fn is_punctuation(ch: char) -> bool {
    matches!(
        ch,
        ',' | '.' | ';' | ':' | '!' | '?'
            | '\u{3002}' // 。 CJK period
            | '\u{FF0C}' // ， CJK comma
            | '\u{FF01}' // ！ CJK exclamation
            | '\u{FF1F}' // ？ CJK question
            | '\u{3001}' // 、 CJK enumeration comma
    )
}

// ---------------------------------------------------------------------------
// Syllable structure for liaison processing
// ---------------------------------------------------------------------------

struct KoSyllable {
    initial: usize,
    medial: usize,
    final_: usize,
}

// ---------------------------------------------------------------------------
// Emit phonemes for a single syllable (after liaison adjustment)
// ---------------------------------------------------------------------------

fn emit_syllable(syl: &KoSyllable, out: &mut Vec<char>) {
    // Initial consonant
    if syl.initial < N_INITIALS
        && let Some(ph) = INITIAL_TABLE[syl.initial]
    {
        out.push(ph);
    }

    // Medial vowel (1-2 phonemes)
    if syl.medial < N_MEDIALS {
        let (ph1, ph2) = MEDIAL_TABLE[syl.medial];
        out.push(ph1);
        if let Some(p2) = ph2 {
            out.push(p2);
        }
    }

    // Final consonant
    if syl.final_ > 0
        && syl.final_ < N_FINALS
        && let Some(ph) = FINAL_TABLE[syl.final_].ph
    {
        out.push(ph);
    }
}

// ---------------------------------------------------------------------------
// Process a run of Hangul syllables: decompose, apply liaison, emit phonemes
// ---------------------------------------------------------------------------

fn process_hangul_run(cps: &[char], out: &mut Vec<char>) {
    if cps.is_empty() {
        return;
    }

    // Decompose all syllables
    let mut syls: Vec<KoSyllable> = cps
        .iter()
        .map(|&ch| {
            let (initial, medial, final_) = decompose(ch);
            KoSyllable {
                initial,
                medial,
                final_,
            }
        })
        .collect();

    // Apply basic liaison (연음화):
    // If syllable[i] has a final consonant and syllable[i+1] starts with
    // ㅇ (initial==11, silent), move the final to become the next initial.
    for i in 0..syls.len().saturating_sub(1) {
        let fi = syls[i].final_;
        if fi == 0 || fi >= N_FINALS {
            continue;
        }
        if syls[i + 1].initial != 11 {
            continue;
        }

        let liaison_init = FINAL_TABLE[fi].liaison_initial;
        if liaison_init < 0 {
            continue;
        }

        // Move final -> next initial (released form)
        syls[i + 1].initial = liaison_init as usize;
        // For complex finals, keep residual; for simple finals, clears entirely.
        syls[i].final_ = FINAL_TABLE[fi].residual_final;
    }

    // Emit phonemes for all syllables
    for syl in &syls {
        emit_syllable(syl, out);
    }
}

// ---------------------------------------------------------------------------
// Core phonemization
// ---------------------------------------------------------------------------

/// Convert Korean text to a sequence of phoneme chars.
///
/// Returns a flat vector of chars representing IPA phonemes (single chars or
/// PUA-encoded multi-char tokens). Each char is already a final output token.
fn text_to_phoneme_chars(text: &str) -> Vec<char> {
    let cps: Vec<char> = text.chars().collect();
    if cps.is_empty() {
        return Vec::new();
    }

    // Recompose NFD Hangul jamo sequences (macOS) into NFC precomposed syllables
    let cps = compose_hangul_jamo(&cps);

    let mut sentence: Vec<char> = Vec::new();
    let mut need_space = false;

    let n = cps.len();
    let mut i = 0;

    while i < n {
        let ch = cps[i];

        // Whitespace -> mark word boundary
        if ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r' {
            need_space = true;
            i += 1;
            continue;
        }

        // Punctuation -> emit directly
        if is_punctuation(ch) {
            sentence.push(ch);
            need_space = false;
            i += 1;
            continue;
        }

        // Hangul syllable run
        if is_hangul_syllable(ch) {
            if need_space && !sentence.is_empty() {
                sentence.push(' ');
            }

            // Find the extent of the Hangul run
            let run_start = i;
            while i < n && is_hangul_syllable(cps[i]) {
                i += 1;
            }
            process_hangul_run(&cps[run_start..i], &mut sentence);
            need_space = true;
            continue;
        }

        // Latin alphabetic -> pass through lowercase
        if ch.is_ascii_alphabetic() {
            if need_space && !sentence.is_empty() {
                sentence.push(' ');
            }
            sentence.push(ch.to_ascii_lowercase());
            need_space = true;
            i += 1;
            continue;
        }

        // Unknown character -> skip
        i += 1;
    }

    sentence
}

// ---------------------------------------------------------------------------
// KoreanPhonemizer
// ---------------------------------------------------------------------------

/// Korean phonemizer using Hangul decomposition + IPA mapping.
///
/// Converts Korean text to IPA phonemes by decomposing Hangul syllable blocks
/// into jamo and mapping each to IPA tokens. Basic liaison (연음화) is applied
/// as the only phonological rule (no g2pk2 dependency).
///
/// Prosody values are fixed at a1=0, a2=0, a3=0 for Korean.
pub struct KoreanPhonemizer;

impl KoreanPhonemizer {
    pub fn new() -> Self {
        Self
    }
}

impl Default for KoreanPhonemizer {
    fn default() -> Self {
        Self::new()
    }
}

impl Phonemizer for KoreanPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        let chars = text_to_phoneme_chars(text);

        // Convert each char to a single-char String token.
        // PUA codepoints are already assigned during phoneme emission,
        // so no additional map_sequence step is needed.
        let tokens: Vec<String> = chars.iter().map(|c| c.to_string()).collect();

        // Prosody: all fixed at (0, 0, 0) for Korean
        let prosody: Vec<Option<ProsodyInfo>> = tokens
            .iter()
            .map(|_| {
                Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 0,
                })
            })
            .collect();

        Ok((tokens, prosody))
    }

    fn language_code(&self) -> &str {
        "ko"
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // ===== Hangul decomposition =====

    #[test]
    fn test_decompose_ga() {
        // 가 = U+AC00 = initial 0 (ㄱ), medial 0 (ㅏ), final 0 (none)
        let (i, m, f) = decompose('\u{AC00}');
        assert_eq!((i, m, f), (0, 0, 0));
    }

    #[test]
    fn test_decompose_han() {
        // 한 = initial 18 (ㅎ), medial 0 (ㅏ), final 4 (ㄴ)
        let (i, m, f) = decompose('한');
        assert_eq!((i, m, f), (18, 0, 4));
    }

    #[test]
    fn test_decompose_gul() {
        // 글 = initial 0 (ㄱ), medial 18 (ㅡ), final 8 (ㄹ)
        let (i, m, f) = decompose('글');
        assert_eq!((i, m, f), (0, 18, 8));
    }

    #[test]
    fn test_is_hangul_syllable() {
        assert!(is_hangul_syllable('\u{AC00}')); // 가
        assert!(is_hangul_syllable('\u{D7A3}')); // 힣
        assert!(!is_hangul_syllable('A'));
        assert!(!is_hangul_syllable('あ'));
        assert!(!is_hangul_syllable(' '));
    }

    // ===== NFD recomposition =====

    #[test]
    fn test_compose_hangul_jamo_with_trailing() {
        // NFD for 한 = ㅎ (U+1112) + ㅏ (U+1161) + ㄴ (U+11AB)
        let nfd = vec!['\u{1112}', '\u{1161}', '\u{11AB}'];
        let composed = compose_hangul_jamo(&nfd);
        assert_eq!(composed, vec!['한']);
    }

    #[test]
    fn test_compose_hangul_jamo_no_trailing() {
        // NFD for 가 = ㄱ (U+1100) + ㅏ (U+1161)
        let nfd = vec!['\u{1100}', '\u{1161}'];
        let composed = compose_hangul_jamo(&nfd);
        assert_eq!(composed, vec!['\u{AC00}']); // 가
    }

    // ===== Single syllable phonemization =====

    #[test]
    fn test_single_syllable_ga() {
        // 가 -> k + a
        let chars = text_to_phoneme_chars("가");
        assert_eq!(chars, vec!['k', 'a']);
    }

    #[test]
    fn test_single_syllable_han() {
        // 한 -> h + a + n
        let chars = text_to_phoneme_chars("한");
        assert_eq!(chars, vec!['h', 'a', 'n']);
    }

    #[test]
    fn test_single_syllable_eung() {
        // 앙 -> (silent ㅇ) + a + ŋ
        let chars = text_to_phoneme_chars("앙");
        assert_eq!(chars, vec!['a', IPA_ENG]);
    }

    // ===== Multi-syllable word =====

    #[test]
    fn test_word_hangul() {
        // 한글 -> h a n + k ɯ l
        let chars = text_to_phoneme_chars("한글");
        assert_eq!(chars, vec!['h', 'a', 'n', 'k', IPA_CLOSE_BACK_UNR, 'l']);
    }

    // ===== Liaison (연음화) =====

    #[test]
    fn test_liaison_guk_eo() {
        // 국어 = ㄱ+ㅜ+ㄱ(final=1) + ㅇ(initial=11)+ㅓ
        // Liaison: final ㄱ (idx 1) has liaison_initial=0 (ㄱ initial)
        // After liaison: 구 + 거 -> k u + k ʌ
        let chars = text_to_phoneme_chars("국어");
        assert_eq!(chars, vec!['k', 'u', 'k', IPA_OPEN_MID_BACK]);
    }

    #[test]
    fn test_liaison_complex_final() {
        // 읽어 = ㅇ+ㅣ+ㄺ(final=9) + ㅇ(initial=11)+ㅓ
        // ㄺ (final=9): liaison_initial=0 (ㄱ), residual_final=8 (ㄹ)
        // After liaison: 일(residual ㄹ) + 거(ㄱ initial)
        // -> (silent)i l + k ʌ
        let chars = text_to_phoneme_chars("읽어");
        assert_eq!(chars, vec!['i', 'l', 'k', IPA_OPEN_MID_BACK]);
    }

    // ===== Tense and aspirated consonants =====

    #[test]
    fn test_tense_initial_kk() {
        // 까 = ㄲ(initial=1) + ㅏ -> PUA_KK + a
        let chars = text_to_phoneme_chars("까");
        assert_eq!(chars, vec![PUA_KK, 'a']);
    }

    #[test]
    fn test_aspirated_initial_kh() {
        // 카 = ㅋ(initial=15) + ㅏ -> PUA_KH + a
        let chars = text_to_phoneme_chars("카");
        assert_eq!(chars, vec![PUA_KH, 'a']);
    }

    // ===== Diphthongs =====

    #[test]
    fn test_diphthong_wa() {
        // 와 = ㅇ(silent) + ㅘ(medial=9: w+a) -> w a
        let chars = text_to_phoneme_chars("와");
        assert_eq!(chars, vec!['w', 'a']);
    }

    // ===== Unreleased finals =====

    #[test]
    fn test_unreleased_final_k() {
        // 박 = ㅂ + ㅏ + ㄱ(final=1) -> p a k̚
        let chars = text_to_phoneme_chars("박");
        assert_eq!(chars, vec!['p', 'a', PUA_K_UNREL]);
    }

    #[test]
    fn test_unreleased_final_t() {
        // 맛 = ㅁ + ㅏ + ㅅ(final=19) -> m a t̚
        let chars = text_to_phoneme_chars("맛");
        assert_eq!(chars, vec!['m', 'a', PUA_T_UNREL]);
    }

    #[test]
    fn test_unreleased_final_p() {
        // 밥 = ㅂ + ㅏ + ㅂ(final=17) -> p a p̚
        let chars = text_to_phoneme_chars("밥");
        assert_eq!(chars, vec!['p', 'a', PUA_P_UNREL]);
    }

    // ===== Punctuation and mixed text =====

    #[test]
    fn test_punctuation_passthrough() {
        let chars = text_to_phoneme_chars("가.");
        assert_eq!(chars, vec!['k', 'a', '.']);
    }

    #[test]
    fn test_latin_passthrough() {
        // Each Latin char is processed individually; space inserted between each
        // (matches C++ korean_phonemize.cpp behavior)
        let chars = text_to_phoneme_chars("Hello");
        assert_eq!(chars, vec!['h', ' ', 'e', ' ', 'l', ' ', 'l', ' ', 'o']);
    }

    #[test]
    fn test_mixed_hangul_latin() {
        // Space between Hangul and Latin runs; each Latin char gets spaces
        let chars = text_to_phoneme_chars("가 OK");
        assert_eq!(chars, vec!['k', 'a', ' ', 'o', ' ', 'k']);
    }

    // ===== Phonemizer trait implementation =====

    #[test]
    fn test_phonemizer_language_code() {
        let p = KoreanPhonemizer::new();
        assert_eq!(p.language_code(), "ko");
    }

    #[test]
    fn test_phonemizer_prosody_all_zero() {
        let p = KoreanPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("가").unwrap();
        assert!(!tokens.is_empty());
        assert_eq!(tokens.len(), prosody.len());
        for pi in &prosody {
            let info = pi.unwrap();
            assert_eq!((info.a1, info.a2, info.a3), (0, 0, 0));
        }
    }

    #[test]
    fn test_phonemizer_returns_single_char_tokens() {
        let p = KoreanPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("한글").unwrap();
        for t in &tokens {
            assert_eq!(
                t.chars().count(),
                1,
                "Expected single-char token, got: {:?}",
                t
            );
        }
    }

    #[test]
    fn test_phonemizer_empty_input() {
        let p = KoreanPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("").unwrap();
        assert!(tokens.is_empty());
        assert!(prosody.is_empty());
    }

    // ===== Affricate consonants =====

    #[test]
    fn test_affricate_j() {
        // 자 = ㅈ(initial=12) + ㅏ -> PUA_TC(tɕ) + a
        let chars = text_to_phoneme_chars("자");
        assert_eq!(chars, vec![PUA_TC, 'a']);
    }

    #[test]
    fn test_affricate_ch() {
        // 차 = ㅊ(initial=14) + ㅏ -> PUA_TCH(tɕʰ) + a
        let chars = text_to_phoneme_chars("차");
        assert_eq!(chars, vec![PUA_TCH, 'a']);
    }

    // ===== Alveolar flap (ㄹ) =====

    #[test]
    fn test_initial_rieul() {
        // 라 = ㄹ(initial=5) + ㅏ -> ɾ + a
        let chars = text_to_phoneme_chars("라");
        assert_eq!(chars, vec![IPA_FLAP, 'a']);
    }

    // ===== Word boundary =====

    #[test]
    fn test_word_boundary_space() {
        let chars = text_to_phoneme_chars("가 나");
        assert_eq!(chars, vec!['k', 'a', ' ', 'n', 'a']);
    }

    #[test]
    fn test_no_leading_space() {
        let chars = text_to_phoneme_chars("  가");
        assert_eq!(chars, vec!['k', 'a']);
    }

    // ===== Velar approximant (ㅢ) =====

    #[test]
    fn test_medial_ui() {
        // 의 = ㅇ(silent) + ㅢ(medial=19: ɰ+i) -> ɰ i
        let chars = text_to_phoneme_chars("의");
        assert_eq!(chars, vec![IPA_VELAR_APPROX, 'i']);
    }

    // ===== No liaison when next initial is not ㅇ =====

    #[test]
    fn test_no_liaison_non_ieung_initial() {
        // 국민 = ㄱ+ㅜ+ㄱ(final=1) + ㅁ(initial=6)+ㅣ+ㄴ(final=4)
        // No liaison: next initial is ㅁ(6), not ㅇ(11)
        // -> k u k̚ + m i n
        let chars = text_to_phoneme_chars("국민");
        assert_eq!(chars, vec!['k', 'u', PUA_K_UNREL, 'm', 'i', 'n']);
    }

    // ===== Tense affricate =====

    #[test]
    fn test_tense_affricate_jj() {
        // 짜 = ㅉ(initial=13) + ㅏ -> PUA_TTCH(t͈ɕ) + a
        let chars = text_to_phoneme_chars("짜");
        assert_eq!(chars, vec![PUA_TTCH, 'a']);
    }

    // ===== Multiple liaison in sequence =====

    #[test]
    fn test_liaison_does_not_cascade() {
        // 먹어요 = ㅁ+ㅓ+ㄱ(final=1) + ㅇ+ㅓ + ㅇ+ㅛ
        // First liaison: ㄱ -> next syllable initial ㄱ(0)
        // Second: 어(no final) + 요(initial=ㅇ but no final to move)
        // -> m ʌ + k ʌ + jo
        let chars = text_to_phoneme_chars("먹어요");
        assert_eq!(
            chars,
            vec!['m', IPA_OPEN_MID_BACK, 'k', IPA_OPEN_MID_BACK, 'j', 'o']
        );
    }
}

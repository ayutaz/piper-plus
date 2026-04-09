//! Rule-based Swedish G2P (grapheme-to-phoneme) phonemizer.
//!
//! Converts Swedish text to IPA phonemes using orthographic rules.
//! No espeak-ng dependency -- all rules are native Rust.
//!
//! Pipeline (per word):
//!   Stage 2: Loanword suffix detection (-tion/-sion/-age etc.)
//!   Stage 3: Loanword prefix detection (sch/sh/ch/ph/th)  [in `convert_consonant`]
//!   Stage 4: Native G2P conversion (consonants + vowels)
//!   Stage 5: Retroflex assimilation (r+C -> retroflex, cascade)
//!   Stage 6: Stress detection + marker insertion
//!
//! ## PUA codepoints (long vowels)
//!
//! | Token | PUA    | IPA  | Description                     |
//! |-------|--------|------|---------------------------------|
//! | `iː`  | U+E059 | iː  | Close front unrounded long      |
//! | `yː`  | U+E05A | yː  | Close front rounded long        |
//! | `eː`  | U+E05B | eː  | Close-mid front unrounded long  |
//! | `ɛː`  | U+E05C | ɛː  | Open-mid front unrounded long   |
//! | `øː`  | U+E05D | øː  | Close-mid front rounded long    |
//! | `ɑː`  | U+E05E | ɑː  | Open back unrounded long        |
//! | `oː`  | U+E05F | oː  | Close-mid back rounded long     |
//! | `uː`  | U+E060 | uː  | Close back rounded long         |
//! | `ʉː`  | U+E061 | ʉː  | Close central rounded long      |

use std::collections::HashSet;
use std::sync::LazyLock;

use crate::error::G2pError;
use crate::phonemizer::{Phonemizer, ProsodyInfo};
use crate::token_map::token_to_pua;

// ---------------------------------------------------------------------------
// IPA codepoints
// ---------------------------------------------------------------------------

/// Open-mid front unrounded vowel (ɛ)
const IPA_OPEN_E: char = '\u{025B}';
/// Near-close near-front unrounded vowel (ɪ)
const IPA_SMALL_I: char = '\u{026A}';
/// Open-mid back rounded vowel (ɔ)
const IPA_OPEN_O: char = '\u{0254}';
/// Close central rounded vowel (ɵ)
const IPA_BARRED_O: char = '\u{0275}';
/// Near-close near-front rounded vowel (ʏ)
const IPA_SMALL_Y: char = '\u{028F}';
/// Open-mid front rounded vowel (œ)
const IPA_OE_LIG: char = '\u{0153}';
/// Voiceless alveolopalatal fricative (ɕ)
const IPA_CURLY_C: char = '\u{0255}';
/// Sj-sound -- simultaneous [ɧ]
const IPA_HOOK_H: char = '\u{0267}';
/// Velar nasal (ŋ)
const IPA_ENG: char = '\u{014B}';
/// Voiced velar stop -- IPA g (ɡ) U+0261
const IPA_G: char = '\u{0261}';
/// Primary stress marker (ˈ)
const IPA_STRESS: char = '\u{02C8}';

// Retroflex consonants
/// Retroflex t (ʈ)
const IPA_RETRO_T: char = '\u{0288}';
/// Retroflex d (ɖ)
const IPA_RETRO_D: char = '\u{0256}';
/// Retroflex s (ʂ)
const IPA_RETRO_S: char = '\u{0282}';
/// Retroflex n (ɳ)
const IPA_RETRO_N: char = '\u{0273}';
/// Retroflex l (ɭ)
const IPA_RETRO_L: char = '\u{026D}';

// ---------------------------------------------------------------------------
// Character classification
// ---------------------------------------------------------------------------

fn is_front_vowel(c: char) -> bool {
    matches!(c, 'e' | 'i' | 'y' | '\u{00E4}' | '\u{00F6}') // ä ö
}

fn is_back_vowel(c: char) -> bool {
    matches!(c, 'a' | 'o' | 'u' | '\u{00E5}') // å
}

fn is_vowel(c: char) -> bool {
    is_front_vowel(c) || is_back_vowel(c)
}

fn is_consonant(c: char) -> bool {
    matches!(
        c,
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

fn is_punctuation(c: char) -> bool {
    matches!(c, ',' | '.' | ';' | ':' | '!' | '?')
}

fn is_swedish_alpha(c: char) -> bool {
    if c.is_ascii_lowercase() {
        return true;
    }
    matches!(
        c,
        '\u{00E5}' // å
        | '\u{00E4}' // ä
        | '\u{00F6}' // ö
        | '\u{00E9}' // é
        | '\u{00E0}' // à
        | '\u{00FC}' // ü
        | '\u{00E1}' // á
        | '\u{00E8}' // è
        | '\u{00EB}' // ë
        | '\u{00EF}' // ï
    )
}

// ---------------------------------------------------------------------------
// Lowercase for Swedish
// ---------------------------------------------------------------------------

fn to_lower_sv(c: char) -> char {
    if c.is_ascii_uppercase() {
        return (c as u8 + 32) as char;
    }
    match c {
        '\u{00C5}' => '\u{00E5}', // Å → å
        '\u{00C4}' => '\u{00E4}', // Ä → ä
        '\u{00D6}' => '\u{00F6}', // Ö → ö
        '\u{00C9}' => '\u{00E9}', // É → é
        '\u{00C0}' => '\u{00E0}', // À → à
        '\u{00DC}' => '\u{00FC}', // Ü → ü
        '\u{00C1}' => '\u{00E1}', // Á → á
        '\u{00C8}' => '\u{00E8}', // È → è
        '\u{00CB}' => '\u{00EB}', // Ë → ë
        '\u{00CF}' => '\u{00EF}', // Ï → ï
        _ => c,
    }
}

// ---------------------------------------------------------------------------
// NFC normalization (collapse combining accents)
// ---------------------------------------------------------------------------

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
                    _ => None,
                },
                '\u{0308}' => match base {
                    // combining diaeresis
                    'A' => Some('\u{00C4}'),
                    'a' => Some('\u{00E4}'),
                    'O' => Some('\u{00D6}'),
                    'o' => Some('\u{00F6}'),
                    'U' => Some('\u{00DC}'),
                    'u' => Some('\u{00FC}'),
                    _ => None,
                },
                '\u{030A}' => match base {
                    // combining ring above
                    'A' => Some('\u{00C5}'),
                    'a' => Some('\u{00E5}'),
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

fn normalize(text: &str) -> Vec<char> {
    let cps: Vec<char> = text.chars().collect();
    let nfc = collapse_combiners(&cps);
    nfc.into_iter().map(to_lower_sv).collect()
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
        if is_swedish_alpha(cps[i]) {
            let mut chars = Vec::new();
            while i < n && is_swedish_alpha(cps[i]) {
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
// Exception word lists
// ---------------------------------------------------------------------------

static HARD_K_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "kille", "kissa", "kiosk", "kebab", "kennel", "keps", "ketchup", "kick", "kilt", "kimono",
        "kitsch", "kibbutz", "kiwi", "kilo", "kex", "kent", "kerna", "keso", "kikare", "kines",
        "kinesisk", "leker", "leken", "lekerska", "steker", "steket", "söker", "söket", "tänker",
        "tänket", "dyker", "dyket", "ryker", "röker", "röket", "smeker", "läker", "läket",
        "märker", "märket", "räcker", "väcker", "viker", "stryker", "sjunker", "sticker", "pojke",
        "fröken", "onkel", "sockel", "socker", "ocker", "märke", "mörker", "tecken", "vacker",
        "naken", "säker", "enkel", "paket", "raket", "staket", "silke", "vinkel", "skelett",
        "ficka", "dricka", "docka", "backe", "flicka", "bricka", "trycke", "skicka", "rike",
        "kirke",
    ]
    .into_iter()
    .collect()
});

static HARD_K_STEMS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "lek", "stek", "sök", "tänk", "dyk", "ryk", "rök", "smek", "läk", "märk", "räck", "väck",
        "vik", "stryk", "sjunk", "stick", "back", "block", "trick", "tryck", "skick", "flick",
        "brick", "drick", "dock", "fick", "sick", "tack", "sack", "pack", "lock", "sock", "rock",
    ]
    .into_iter()
    .collect()
});

static HARD_G_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "bagel",
        "bageri",
        "bygel",
        "bygge",
        "båge",
        "dager",
        "flygel",
        "gecko",
        "hage",
        "hagel",
        "hunger",
        "lager",
        "läge",
        "läger",
        "mage",
        "nagel",
        "regel",
        "segel",
        "seger",
        "stege",
        "tagel",
        "tegel",
        "tiger",
        "tygel",
        "finger",
        "ängel",
        "fågel",
        "spegel",
        "fogel",
        "duger",
        "flyger",
        "ligger",
        "ljuger",
        "lägger",
        "stiger",
        "suger",
        "tigger",
        "väger",
        "äger",
        "ger",
        "agera",
        "delegera",
        "reagera",
        "segregera",
        "tangera",
        "engagera",
        "arrangera",
        "ignorera",
        "navigera",
        "negera",
        "intrigera",
        "ge",
        "gel",
        "berg",
        "borg",
    ]
    .into_iter()
    .collect()
});

static HARD_G_STEMS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "lig", "stig", "sug", "tig", "väg", "äg", "flyg", "ljug", "lägg", "dug", "drag", "lag",
        "dag", "mag", "nag", "bag", "byg", "tag", "seg", "vag", "reg", "berg", "borg",
    ]
    .into_iter()
    .collect()
});

/// "o" -> /o:/ instead of default /u:/
static O_LONG_AS_OO: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "son", "mor", "bror", "lov", "dom", "ton", "zon", "fon", "ion", "ko", "lo", "ro", "tro",
        "bo", "god", "jord", "ord", "kol", "pol", "kontroll", "roll", "mol", "fot", "rot", "blod",
        "flod", "mod", "nod", "rod", "tog",
    ]
    .into_iter()
    .collect()
});

/// Words ending in m that use short vowel despite single-C ending
static FINAL_M_SHORT_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "hem", "rum", "fem", "lem", "kam", "dam", "ham", "lam", "ram", "stam", "tom", "som", "dom",
        "dum", "gum", "glöm", "dröm", "ström",
    ]
    .into_iter()
    .collect()
});

static FUNCTION_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "jag", "du", "han", "hon", "vi", "de", "dem", "den", "det", "sig", "sin", "min", "din",
        "av", "i", "på", "för", "med", "om", "till", "från", "hos", "ur", "och", "men", "att",
        "som", "när", "var", "en", "ett", "är", "har", "kan", "ska", "vill", "inte",
    ]
    .into_iter()
    .collect()
});

static SK_BACK_VOWEL_EXCEPTIONS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| ["människa", "marskalk"].into_iter().collect());

/// ch exceptions that are /k/ not /ɧ/
static CH_EXCEPTIONS_K: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    ["kristus", "krist", "kron", "kronik", "och"]
        .into_iter()
        .collect()
});

/// Words where -age is Swedish (not French loan)
static AGE_NATIVE_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "bage", "lage", "sage", "dage", "mage", "hage", "tage", "klage", "frage", "plage", "drage",
    ]
    .into_iter()
    .collect()
});

// ---------------------------------------------------------------------------
// Stress detection constants
// ---------------------------------------------------------------------------

const UNSTRESSED_PREFIXES: &[&str] = &["för", "be", "ge", "er", "an"];

const STRESS_ATTRACTING_SUFFIXES: &[&str] = &[
    "ssion", "tion", "sion", "itet", "eri", "era", "ist", "ör", "ment", "ans", "ens", "ell", "ent",
    "ant", "ik", "ur", "al", "ös",
];

// ---------------------------------------------------------------------------
// Vowel mappings (Complementary Quantity)
// ---------------------------------------------------------------------------

/// Return the IPA string for a long vowel.
fn long_vowel(ch: char) -> &'static str {
    match ch {
        'a' => "\u{0251}\u{02D0}",        // ɑː
        'e' => "e\u{02D0}",               // eː
        'i' => "i\u{02D0}",               // iː
        'o' => "u\u{02D0}",               // uː (default; oː for O_LONG_AS_OO)
        'u' => "\u{0289}\u{02D0}",        // ʉː
        'y' => "y\u{02D0}",               // yː
        '\u{00E5}' => "o\u{02D0}",        // å → oː
        '\u{00E4}' => "\u{025B}\u{02D0}", // ä → ɛː
        '\u{00F6}' => "\u{00F8}\u{02D0}", // ö → øː
        _ => "?",
    }
}

/// Return the IPA char for a short vowel.
fn short_vowel(ch: char) -> char {
    match ch {
        'a' => 'a',
        'e' => IPA_OPEN_E,        // ɛ
        'i' => IPA_SMALL_I,       // ɪ
        'o' => IPA_OPEN_O,        // ɔ
        'u' => IPA_BARRED_O,      // ɵ
        'y' => IPA_SMALL_Y,       // ʏ
        '\u{00E5}' => IPA_OPEN_O, // å → ɔ
        '\u{00E4}' => IPA_OPEN_E, // ä → ɛ
        '\u{00F6}' => IPA_OE_LIG, // ö → œ
        _ => ch,
    }
}

// ---------------------------------------------------------------------------
// Retroflex map
// ---------------------------------------------------------------------------

fn retroflex_of(c: char) -> Option<char> {
    match c {
        't' => Some(IPA_RETRO_T),
        'd' => Some(IPA_RETRO_D),
        's' => Some(IPA_RETRO_S),
        'n' => Some(IPA_RETRO_N),
        'l' => Some(IPA_RETRO_L),
        _ => None,
    }
}

fn is_propagating_retroflex(c: char) -> bool {
    matches!(c, '\u{0288}' | '\u{0256}' | '\u{0282}' | '\u{0273}')
    // ʈ ɖ ʂ ɳ   (ɭ does NOT propagate)
}

// ---------------------------------------------------------------------------
// Loanword suffix rules (Stage 2)
// ---------------------------------------------------------------------------

/// (suffix, phoneme_chars)
const LOANWORD_SUFFIX_RULES: &[(&str, &[&str])] = &[
    ("ssion", &["\u{0267}", "u\u{02D0}", "n"]), // ɧ uː n
    ("tion", &["\u{0267}", "u\u{02D0}", "n"]),  // ɧ uː n
    ("sion", &["\u{0267}", "u\u{02D0}", "n"]),  // ɧ uː n
    ("age", &["\u{0251}\u{02D0}", "\u{0267}"]), // ɑː ɧ
    ("eur", &["\u{00F8}\u{02D0}", "r"]),        // øː r
    ("eum", &["e\u{02D0}", "\u{0275}", "m"]),   // eː ɵ m
    ("ium", &["\u{026A}", "\u{0275}", "m"]),    // ɪ ɵ m
];

// ---------------------------------------------------------------------------
// Default consonant -> IPA (single-letter fallback)
// ---------------------------------------------------------------------------

fn default_consonant(ch: char) -> &'static str {
    match ch {
        'b' => "b",
        'c' => "k",
        'd' => "d",
        'f' => "f",
        'g' => "\u{0261}", // ɡ
        'h' => "h",
        'j' => "j",
        'k' => "k",
        'l' => "l",
        'm' => "m",
        'n' => "n",
        'p' => "p",
        'q' => "k",
        'r' => "r",
        's' => "s",
        't' => "t",
        'v' => "v",
        'w' => "v",
        'x' => "ks",
        'z' => "s",
        _ => "",
    }
}

// ---------------------------------------------------------------------------
// Soft/Hard consonant decision helpers
// ---------------------------------------------------------------------------

fn is_hard_k(word: &str) -> bool {
    if HARD_K_WORDS.contains(word) {
        return true;
    }
    let char_count = word.chars().count();
    for suffix_len in [3, 2, 1] {
        if char_count > suffix_len {
            let stem: String = word.chars().take(char_count - suffix_len).collect();
            if HARD_K_STEMS.contains(stem.as_str()) {
                return true;
            }
        }
    }
    false
}

fn is_hard_g(word: &str) -> bool {
    if HARD_G_WORDS.contains(word) {
        return true;
    }
    // -era/-erar/-erade verb heuristic: loanword verbs keep hard g
    if word.ends_with("era") || word.ends_with("erar") || word.ends_with("erade") {
        return true;
    }
    let char_count = word.chars().count();
    for suffix_len in [3, 2, 1] {
        if char_count > suffix_len {
            let stem: String = word.chars().take(char_count - suffix_len).collect();
            if HARD_G_STEMS.contains(stem.as_str()) {
                return true;
            }
        }
    }
    false
}

// ---------------------------------------------------------------------------
// Safe char access
// ---------------------------------------------------------------------------

fn char_at(word: &[char], pos: usize) -> char {
    if pos < word.len() { word[pos] } else { '\0' }
}

// ---------------------------------------------------------------------------
// Consonant conversion (Stage 3 + 4)
// ---------------------------------------------------------------------------

/// Convert consonant(s) starting at `pos`.
/// Returns (ipa_phonemes, chars_consumed).
fn convert_consonant(word: &[char], pos: usize, full_word: &str) -> (Vec<String>, usize) {
    let remaining = word.len() - pos;
    let ch = word[pos];
    let next_ch = char_at(word, pos + 1);

    // === 3-char patterns ===
    if remaining >= 3 {
        let tri: String = word[pos..pos + 3].iter().collect();
        match tri.as_str() {
            "skj" => return (vec![IPA_HOOK_H.to_string()], 3),
            "stj" => return (vec![IPA_HOOK_H.to_string()], 3),
            "sch" => return (vec![IPA_HOOK_H.to_string()], 3),
            "sng" => return (vec!["s".into(), "n".into()], 3),
            "ckj" => return (vec![IPA_CURLY_C.to_string()], 3),
            _ => {}
        }
    }

    // === 2-char patterns ===
    if remaining >= 2 {
        let di: String = word[pos..pos + 2].iter().collect();
        match di.as_str() {
            "sk" => {
                if remaining >= 3
                    && is_front_vowel(char_at(word, pos + 2))
                    && !SK_BACK_VOWEL_EXCEPTIONS.contains(full_word)
                {
                    return (vec![IPA_HOOK_H.to_string()], 2);
                }
                return (vec!["s".into(), "k".into()], 2);
            }
            "sj" => return (vec![IPA_HOOK_H.to_string()], 2),
            "sh" => return (vec![IPA_HOOK_H.to_string()], 2),
            "ch" => {
                if CH_EXCEPTIONS_K.contains(full_word) {
                    return (vec!["k".into()], 2);
                }
                return (vec![IPA_HOOK_H.to_string()], 2);
            }
            "ph" => return (vec!["f".into()], 2),
            "th" => return (vec!["t".into()], 2),
            "tj" => return (vec![IPA_CURLY_C.to_string()], 2),
            "kj" => return (vec![IPA_CURLY_C.to_string()], 2),
            "gn" => {
                if pos == 0 {
                    return (vec![IPA_G.to_string(), "n".into()], 2);
                }
                return (vec![IPA_ENG.to_string(), "n".into()], 2);
            }
            "ng" => return (vec![IPA_ENG.to_string()], 2),
            "nk" => return (vec![IPA_ENG.to_string(), "k".into()], 2),
            "ck" => return (vec!["k".into()], 2),
            "gj" if pos == 0 => return (vec!["j".into()], 2),
            "lj" if pos == 0 => return (vec!["j".into()], 2),
            "dj" if pos == 0 => return (vec!["j".into()], 2),
            "hj" if pos == 0 => return (vec!["j".into()], 2),
            _ => {}
        }
    }

    // === 1-char patterns ===

    // k + front vowel -> soft /ɕ/ or hard /k/
    if ch == 'k' && is_front_vowel(next_ch) {
        if is_hard_k(full_word) {
            return (vec!["k".into()], 1);
        }
        return (vec![IPA_CURLY_C.to_string()], 1);
    }

    // g + front vowel -> soft /j/ or hard /ɡ/
    if ch == 'g' && is_front_vowel(next_ch) {
        if is_hard_g(full_word) {
            return (vec![IPA_G.to_string()], 1);
        }
        return (vec!["j".into()], 1);
    }

    // g + back vowel / consonant -> /ɡ/
    if ch == 'g' {
        return (vec![IPA_G.to_string()], 1);
    }

    // c before e/i -> /s/, otherwise /k/
    if ch == 'c' {
        if next_ch == 'e' || next_ch == 'i' {
            return (vec!["s".into()], 1);
        }
        return (vec!["k".into()], 1);
    }

    // x -> /ks/
    if ch == 'x' {
        return (vec!["k".into(), "s".into()], 1);
    }

    // Default single consonant
    let ipa = default_consonant(ch);
    if ipa.is_empty() {
        return (vec![ch.to_string()], 1);
    }
    if ipa.len() > 1 {
        // Multi-char like "ks" for x
        return (ipa.chars().map(|c| c.to_string()).collect(), 1);
    }
    (vec![ipa.to_string()], 1)
}

// ---------------------------------------------------------------------------
// Count following consonants
// ---------------------------------------------------------------------------

fn count_following_consonants(word: &[char], pos: usize) -> usize {
    let mut count = 0;
    let mut i = pos + 1;
    while i < word.len() && is_consonant(word[i]) {
        count += 1;
        i += 1;
    }
    count
}

// ---------------------------------------------------------------------------
// Vowel phoneme assignment (Complementary Quantity)
// ---------------------------------------------------------------------------

fn get_vowel_phoneme(word: &[char], pos: usize, full_word: &str, is_stressed: bool) -> String {
    let ch = word[pos];

    // Unstressed -> short
    if !is_stressed {
        return short_vowel(ch).to_string();
    }

    // Function word -> short
    if FUNCTION_WORDS.contains(full_word) {
        return short_vowel(ch).to_string();
    }

    // Final-m exception -> short
    if FINAL_M_SHORT_WORDS.contains(full_word) {
        return short_vowel(ch).to_string();
    }

    let n_following = count_following_consonants(word, pos);

    // Word-final vowel -> long
    if n_following == 0 && pos == word.len() - 1 {
        let vowel = if ch == 'o' && O_LONG_AS_OO.contains(full_word) {
            "o\u{02D0}" // oː
        } else {
            long_vowel(ch)
        };
        return vowel.to_string();
    }

    // r + single C exception: vowel stays long (r merges into retroflex)
    // Exception: 'o' is excluded
    if n_following == 2 && ch != 'o' && pos + 1 < word.len() && word[pos + 1] == 'r' {
        return long_vowel(ch).to_string();
    }

    // Geminate / cluster (2+ consonants) -> short
    if n_following >= 2 {
        return short_vowel(ch).to_string();
    }

    // Single consonant -> long
    let vowel = if ch == 'o' && O_LONG_AS_OO.contains(full_word) {
        "o\u{02D0}" // oː
    } else {
        long_vowel(ch)
    };
    vowel.to_string()
}

// ---------------------------------------------------------------------------
// Retroflex assimilation (Stage 5)
// ---------------------------------------------------------------------------

fn apply_retroflex(phonemes: &[String]) -> Vec<String> {
    let mut result: Vec<String> = Vec::new();
    let mut i = 0;
    let n = phonemes.len();

    #[derive(PartialEq)]
    enum State {
        Normal,
        RDetected,
        Cascading,
    }
    let mut state = State::Normal;

    while i < n {
        let ph = &phonemes[i];
        // Get single char from phoneme if it is single-char
        let ph_char = if ph.chars().count() == 1 {
            ph.chars().next().unwrap()
        } else {
            '\0'
        };

        match state {
            State::Normal => {
                if ph == "r" {
                    state = State::RDetected;
                } else {
                    result.push(ph.clone());
                }
            }
            State::RDetected => {
                if ph == "r" {
                    // rr -> geminate block, no assimilation
                    result.push("r".into());
                    result.push("r".into());
                    state = State::Normal;
                } else if let Some(retro) = retroflex_of(ph_char) {
                    result.push(retro.to_string());
                    if is_propagating_retroflex(retro) {
                        state = State::Cascading;
                    } else {
                        state = State::Normal;
                    }
                } else {
                    // r + non-assimilable -> output r and reprocess
                    result.push("r".into());
                    result.push(ph.clone());
                    state = State::Normal;
                }
            }
            State::Cascading => {
                if let Some(retro) = retroflex_of(ph_char) {
                    result.push(retro.to_string());
                    if !is_propagating_retroflex(retro) {
                        state = State::Normal; // ɭ stops cascade
                    }
                } else {
                    result.push(ph.clone());
                    state = State::Normal;
                }
            }
        }
        i += 1;
    }

    // Flush pending r
    if state == State::RDetected {
        result.push("r".into());
    }

    result
}

// ---------------------------------------------------------------------------
// Stress detection (Stage 6)
// ---------------------------------------------------------------------------

fn count_syllables(word: &[char]) -> usize {
    let mut count = 0;
    let mut prev_vowel = false;
    for &ch in word {
        if is_vowel(ch) {
            if !prev_vowel {
                count += 1;
            }
            prev_vowel = true;
        } else {
            prev_vowel = false;
        }
    }
    count.max(1)
}

fn count_syllables_str(word: &str) -> usize {
    let chars: Vec<char> = word.chars().collect();
    count_syllables(&chars)
}

fn detect_stress(word: &str) -> i32 {
    if FUNCTION_WORDS.contains(word) {
        return -1;
    }

    let n_syl = count_syllables_str(word);
    if n_syl <= 1 {
        return 0;
    }

    // Check stress-attracting suffixes
    for suffix in STRESS_ATTRACTING_SUFFIXES {
        if word.ends_with(suffix) && word.len() > suffix.len() {
            let prefix_part = &word[..word.len() - suffix.len()];
            return count_syllables_str(prefix_part) as i32;
        }
    }

    // Check unstressed prefixes
    for prefix in UNSTRESSED_PREFIXES {
        if word.starts_with(prefix) && word.len() > prefix.len() + 1 {
            return 1;
        }
    }

    // Default: first syllable
    0
}

// ---------------------------------------------------------------------------
// IPA vowel check
// ---------------------------------------------------------------------------

fn is_ipa_vowel_str(ph: &str) -> bool {
    const IPA_VOWEL_CHARS: &[char] = &[
        'a', 'e', 'i', 'o', 'u', 'y', '\u{00E5}', '\u{00E4}', '\u{00F6}', // å ä ö
        '\u{0251}', // ɑ
        '\u{025B}', // ɛ
        '\u{026A}', // ɪ
        '\u{0254}', // ɔ
        '\u{028A}', // ʊ
        '\u{0289}', // ʉ
        '\u{028F}', // ʏ
        '\u{0153}', // œ
        '\u{00F8}', // ø
        '\u{0275}', // ɵ
    ];
    ph.chars().any(|c| IPA_VOWEL_CHARS.contains(&c))
}

// ---------------------------------------------------------------------------
// Insert stress marker
// ---------------------------------------------------------------------------

fn insert_stress_marker(phonemes: &[String], stress_syl: i32) -> Vec<String> {
    if stress_syl < 0 || phonemes.is_empty() {
        return phonemes.to_vec();
    }

    let target = stress_syl as usize;

    // Find index of first vowel of the target syllable
    let mut syl_count: usize = 0;
    let mut vowel_idx: Option<usize> = None;
    let mut prev_was_vowel = false;

    for (i, ph) in phonemes.iter().enumerate() {
        let is_v = is_ipa_vowel_str(ph);
        if is_v && !prev_was_vowel {
            if syl_count == target {
                vowel_idx = Some(i);
                break;
            }
            syl_count += 1;
        }
        prev_was_vowel = is_v;
    }

    let vowel_idx = match vowel_idx {
        Some(idx) => idx,
        None => return phonemes.to_vec(),
    };

    // Walk backwards to find syllable onset
    let mut onset_idx = vowel_idx;
    while onset_idx > 0 && !is_ipa_vowel_str(&phonemes[onset_idx - 1]) {
        onset_idx -= 1;
    }

    // For syllable 0, onset starts at beginning
    if target == 0 {
        onset_idx = 0;
    }

    let mut result = phonemes.to_vec();
    result.insert(onset_idx, IPA_STRESS.to_string());
    result
}

// ---------------------------------------------------------------------------
// Loanword detection (Stage 2)
// ---------------------------------------------------------------------------

fn detect_loanword_suffix(word: &str) -> Option<(String, Vec<String>)> {
    for &(suffix, phonemes) in LOANWORD_SUFFIX_RULES {
        if word.ends_with(suffix) && word.len() > suffix.len() {
            // Check native exceptions for -age
            if suffix == "age" && AGE_NATIVE_WORDS.contains(word) {
                continue;
            }
            let stem = word[..word.len() - suffix.len()].to_string();
            let suffix_phonemes: Vec<String> = phonemes.iter().map(|s| s.to_string()).collect();
            return Some((stem, suffix_phonemes));
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Native word conversion (Stage 4)
// ---------------------------------------------------------------------------

fn convert_word_native(word_chars: &[char], full_word: &str, stressed_syl: i32) -> Vec<String> {
    let mut phonemes: Vec<String> = Vec::new();
    let mut pos = 0;
    let mut syl_count: i32 = 0;
    let mut prev_was_vowel = false;

    while pos < word_chars.len() {
        let ch = word_chars[pos];

        if is_vowel(ch) {
            if !prev_was_vowel {
                let is_stressed = syl_count == stressed_syl && stressed_syl >= 0;
                let vowel = get_vowel_phoneme(word_chars, pos, full_word, is_stressed);
                phonemes.push(vowel);
                syl_count += 1;
            } else {
                // Consecutive vowel in same syllable (rare)
                phonemes.push(short_vowel(ch).to_string());
            }
            prev_was_vowel = true;
            pos += 1;
        } else if is_consonant(ch) {
            prev_was_vowel = false;
            let (ipa_list, consumed) = convert_consonant(word_chars, pos, full_word);
            phonemes.extend(ipa_list);
            pos += consumed;
        } else {
            // Skip unknown
            prev_was_vowel = false;
            pos += 1;
        }
    }

    phonemes
}

// ---------------------------------------------------------------------------
// Full word pipeline (Stage 2-6)
// ---------------------------------------------------------------------------

fn phonemize_word(word_chars: &[char]) -> Vec<String> {
    if word_chars.is_empty() {
        return Vec::new();
    }

    let word_str: String = word_chars.iter().collect();

    // Detect stress syllable
    let stressed_syl = detect_stress(&word_str);

    // Stage 2: Check loanword suffix
    let raw_phonemes = if let Some((stem, suffix_phonemes)) = detect_loanword_suffix(&word_str) {
        let stem_chars: Vec<char> = stem.chars().collect();
        let stem_syl_count = count_syllables(&stem_chars) as i32;
        let stem_stressed = if stressed_syl >= stem_syl_count {
            -1
        } else {
            stressed_syl
        };
        let mut stem_phonemes = convert_word_native(&stem_chars, &word_str, stem_stressed);
        stem_phonemes.extend(suffix_phonemes);
        stem_phonemes
    } else {
        // Stage 4: Native conversion
        convert_word_native(word_chars, &word_str, stressed_syl)
    };

    // Stage 5: Retroflex assimilation
    let phonemes = apply_retroflex(&raw_phonemes);

    // Stage 6: Stress markers
    insert_stress_marker(&phonemes, stressed_syl)
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

/// Convert Swedish text to phoneme list and prosody features.
///
/// Returns (phonemes, prosody_info_list) where each phoneme has corresponding
/// prosody info with a1=0, a2=stress-based (0/1/2), a3=word phoneme count.
pub fn phonemize_swedish_with_prosody(text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
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

                let word_phonemes = phonemize_word(chars);

                // Count non-stress phonemes for a3
                let stress_str = IPA_STRESS.to_string();
                let word_phoneme_count =
                    word_phonemes.iter().filter(|p| **p != stress_str).count() as i32;

                for ph in &word_phonemes {
                    let a2 = if *ph == stress_str {
                        2 // primary stress
                    } else {
                        0
                    };
                    phonemes.push(ph.clone());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2,
                        a3: word_phoneme_count,
                    }));
                }

                need_space = true;
            }
        }
    }

    // Map multi-character tokens to PUA single chars
    let mapped = map_sequence(phonemes);
    (mapped, prosody_list)
}

/// Convert Swedish text to phoneme list (without prosody).
pub fn phonemize_swedish(text: &str) -> Vec<String> {
    let (phonemes, _) = phonemize_swedish_with_prosody(text);
    phonemes
}

// ---------------------------------------------------------------------------
// SwedishPhonemizer
// ---------------------------------------------------------------------------

/// Swedish phonemizer using rule-based G2P.
///
/// Converts Swedish text to IPA phonemes using orthographic rules.
/// No external dependencies required.
pub struct SwedishPhonemizer;

impl SwedishPhonemizer {
    pub fn new() -> Self {
        Self
    }
}

impl Default for SwedishPhonemizer {
    fn default() -> Self {
        Self::new()
    }
}

impl Phonemizer for SwedishPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        Ok(phonemize_swedish_with_prosody(text))
    }

    fn language_code(&self) -> &str {
        "sv"
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
        phonemize_swedish(text)
    }

    /// Helper: phonemize and return (phonemes, prosody).
    fn ph_with_prosody(text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
        phonemize_swedish_with_prosody(text)
    }

    // ===== Long vowels =====

    #[test]
    fn test_long_a_mat() {
        // mat: single consonant -> long ɑː (PUA E05E)
        let result = ph("mat");
        let pua_alpha_long = '\u{E05E}'.to_string();
        assert!(
            result.contains(&pua_alpha_long),
            "mat should have long ɑː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_i_vit() {
        // vit: single consonant -> long iː (PUA E059)
        let result = ph("vit");
        let pua_i_long = '\u{E059}'.to_string();
        assert!(
            result.contains(&pua_i_long),
            "vit should have long iː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_y_syn() {
        // syn: long yː (PUA E05A)
        let result = ph("syn");
        let pua_y_long = '\u{E05A}'.to_string();
        assert!(
            result.contains(&pua_y_long),
            "syn should have long yː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_e_vet() {
        // vet: long eː (PUA E05B)
        let result = ph("vet");
        let pua_e_long = '\u{E05B}'.to_string();
        assert!(
            result.contains(&pua_e_long),
            "vet should have long eː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_ae_sael() {
        // säl: long ɛː (PUA E05C)
        let result = ph("s\u{00E4}l");
        let pua_ae_long = '\u{E05C}'.to_string();
        assert!(
            result.contains(&pua_ae_long),
            "säl should have long ɛː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_oe_oel() {
        // öl: long øː (PUA E05D)
        let result = ph("\u{00F6}l");
        let pua_oe_long = '\u{E05D}'.to_string();
        assert!(
            result.contains(&pua_oe_long),
            "öl should have long øː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_u_hus() {
        // hus: long ʉː (PUA E061)
        let result = ph("hus");
        let pua_barred_u_long = '\u{E061}'.to_string();
        assert!(
            result.contains(&pua_barred_u_long),
            "hus should have long ʉː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_o_default_sol() {
        // sol: "o" default -> uː (PUA E060)
        let result = ph("sol");
        let pua_u_long = '\u{E060}'.to_string();
        assert!(
            result.contains(&pua_u_long),
            "sol should have long uː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_o_son_as_oo() {
        // son: O_LONG_AS_OO -> oː (PUA E05F)
        let result = ph("son");
        let pua_o_long = '\u{E05F}'.to_string();
        assert!(
            result.contains(&pua_o_long),
            "son should have long oː: {:?}",
            result
        );
    }

    // ===== Short vowels =====

    #[test]
    fn test_short_a_matt() {
        // matt: double t -> short a
        let result = ph("matt");
        assert!(
            result.contains(&"a".to_string()),
            "matt should have short 'a': {:?}",
            result
        );
    }

    #[test]
    fn test_short_i_flicka() {
        // flicka: cluster -> short ɪ
        let result = ph("flicka");
        let small_i = IPA_SMALL_I.to_string();
        assert!(
            result.contains(&small_i),
            "flicka should have short ɪ: {:?}",
            result
        );
    }

    #[test]
    fn test_short_e_vett() {
        // vett: double t -> short ɛ
        let result = ph("vett");
        let open_e = IPA_OPEN_E.to_string();
        assert!(
            result.contains(&open_e),
            "vett should have short ɛ: {:?}",
            result
        );
    }

    // ===== Soft k/g =====

    #[test]
    fn test_soft_k_koep() {
        // köp: k + front ö -> ɕ
        let result = ph("k\u{00F6}p");
        let curly_c = IPA_CURLY_C.to_string();
        assert!(
            result.contains(&curly_c),
            "k + front vowel -> ɕ in 'köp': {:?}",
            result
        );
    }

    #[test]
    fn test_hard_k_exception_kille() {
        // kille: HARD_K_WORDS -> /k/
        let result = ph("kille");
        assert!(
            result.contains(&"k".to_string()),
            "hard-k exception 'kille' -> /k/: {:?}",
            result
        );
    }

    #[test]
    fn test_soft_g_goera() {
        // göra: g + front ö -> /j/
        let result = ph("g\u{00F6}ra");
        assert!(
            result.contains(&"j".to_string()),
            "g + front vowel -> j in 'göra': {:?}",
            result
        );
    }

    #[test]
    fn test_hard_g_exception_ge() {
        // ge: HARD_G_WORDS -> /ɡ/
        let result = ph("ge");
        let g_str = IPA_G.to_string();
        assert!(
            result.contains(&g_str),
            "hard-g exception 'ge' -> ɡ: {:?}",
            result
        );
    }

    // ===== Retroflex assimilation =====

    #[test]
    fn test_retroflex_rt_kort() {
        // kort: r+t -> ʈ
        let result = ph("kort");
        let retro_t = IPA_RETRO_T.to_string();
        assert!(
            result.contains(&retro_t),
            "r+t -> ʈ in 'kort': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_rs_fors() {
        // fors: r+s -> ʂ
        let result = ph("fors");
        let retro_s = IPA_RETRO_S.to_string();
        assert!(
            result.contains(&retro_s),
            "r+s -> ʂ in 'fors': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_rd_bord() {
        // bord: r+d -> ɖ
        let result = ph("bord");
        let retro_d = IPA_RETRO_D.to_string();
        assert!(
            result.contains(&retro_d),
            "r+d -> ɖ in 'bord': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_rn_barn() {
        // barn: r+n -> ɳ
        let result = ph("barn");
        let retro_n = IPA_RETRO_N.to_string();
        assert!(
            result.contains(&retro_n),
            "r+n -> ɳ in 'barn': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_cascade_borste() {
        // borste: r+s -> ʂ, then cascade ʂ+t -> ʈ
        let result = ph("borste");
        let retro_s = IPA_RETRO_S.to_string();
        let retro_t = IPA_RETRO_T.to_string();
        assert!(
            result.contains(&retro_s) || result.contains(&retro_t),
            "retroflex cascade in 'borste': {:?}",
            result
        );
    }

    // ===== Stress =====

    #[test]
    fn test_stress_first_syllable_flicka() {
        let result = ph("flicka");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "content word 'flicka' has stress: {:?}",
            result
        );
        assert_eq!(
            result[0], stress,
            "stress at position 0 for 'flicka': {:?}",
            result
        );
    }

    #[test]
    fn test_no_stress_function_word_och() {
        let result = ph("och");
        let stress = IPA_STRESS.to_string();
        assert!(
            !result.contains(&stress),
            "function word 'och' no stress: {:?}",
            result
        );
    }

    #[test]
    fn test_no_stress_function_word_jag() {
        let result = ph("jag");
        let stress = IPA_STRESS.to_string();
        assert!(
            !result.contains(&stress),
            "function word 'jag' no stress: {:?}",
            result
        );
    }

    // ===== Loanword suffixes =====

    #[test]
    fn test_loanword_tion_nation() {
        let result = ph("nation");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            result.contains(&hook_h),
            "-tion -> ɧ in 'nation': {:?}",
            result
        );
    }

    #[test]
    fn test_native_age_mage() {
        // mage is native -> no loanword ɧ
        let result = ph("mage");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            !result.contains(&hook_h),
            "'mage' is native, no ɧ: {:?}",
            result
        );
    }

    // ===== Sj-sound triggers =====

    #[test]
    fn test_sj_sound_sj() {
        let result = ph("sj\u{00F6}");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sj -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sj_sound_sk_front() {
        // sked: sk + front vowel -> ɧ
        let result = ph("sked");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            result.contains(&hook_h),
            "sk + front vowel -> ɧ: {:?}",
            result
        );
    }

    #[test]
    fn test_sk_back_vowel_no_sj() {
        // ska: sk + back vowel -> /sk/
        let result = ph("ska");
        assert!(result.contains(&"s".to_string()), "sk + back keeps s");
        assert!(result.contains(&"k".to_string()), "sk + back keeps k");
    }

    // ===== Prosody =====

    #[test]
    fn test_prosody_length_matches() {
        let (phonemes, prosody) = ph_with_prosody("hej v\u{00E4}rlden");
        assert_eq!(phonemes.len(), prosody.len());
    }

    #[test]
    fn test_prosody_a1_always_zero() {
        let (_, prosody) = ph_with_prosody("flickan gick");
        for info in prosody.iter().flatten() {
            assert_eq!(info.a1, 0, "a1 should always be 0");
        }
    }

    // ===== Edge cases =====

    #[test]
    fn test_empty_text() {
        assert!(ph("").is_empty());
    }

    #[test]
    fn test_uppercase_normalized() {
        assert_eq!(ph("HEJ"), ph("hej"), "uppercase normalizes to lowercase");
    }

    #[test]
    fn test_space_between_words() {
        assert!(
            ph("ett hus").contains(&" ".to_string()),
            "space between words"
        );
    }

    #[test]
    fn test_punctuation_preserved() {
        let result = ph("hej!");
        assert!(result.contains(&"!".to_string()), "! preserved");
    }

    // ===== Language code =====

    #[test]
    fn test_language_code() {
        assert_eq!(SwedishPhonemizer::new().language_code(), "sv");
    }

    // ===== Phonemizer trait =====

    #[test]
    fn test_phonemizer_trait() {
        let p = SwedishPhonemizer::new();
        let result = p.phonemize_with_prosody("hej");
        assert!(result.is_ok());
        let (tokens, prosody) = result.unwrap();
        assert!(!tokens.is_empty());
        assert_eq!(tokens.len(), prosody.len());
    }
}

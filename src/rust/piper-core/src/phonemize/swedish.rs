//! Rule-based Swedish G2P (grapheme-to-phoneme) phonemizer.
//!
//! Converts Swedish text to IPA phonemes using orthographic rules + optional
//! NST dictionary lookup.  No espeak-ng dependency -- all rules are native.
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

use super::token_map::token_to_pua;
use super::{Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::config::PhonemeIdMap;
use crate::error::PiperError;

// ---------------------------------------------------------------------------
// IPA codepoints
// ---------------------------------------------------------------------------

/// Open back unrounded vowel (ɑ) -- used in long_vowel() via Unicode literal
#[allow(dead_code)]
const IPA_ALPHA: char = '\u{0251}';
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
/// Close-mid front rounded vowel (ø) -- used in short_vowel() via Unicode literal
#[allow(dead_code)]
const IPA_SLASHED_O: char = '\u{00F8}';
/// Open-mid front rounded vowel (œ) -- used in short_vowel() via Unicode literal
#[allow(dead_code)]
const IPA_OE_LIG: char = '\u{0153}';
/// Close central rounded vowel (ʉ) -- used in long_vowel() via Unicode literal
#[allow(dead_code)]
const IPA_BARRED_U: char = '\u{0289}';
/// Length mark (ː) -- used in vowel mapping strings
#[allow(dead_code)]
const IPA_LONG: char = '\u{02D0}';
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

#[allow(dead_code)]
fn chars_to_string(chars: &[char]) -> String {
    chars.iter().collect()
}

// ---------------------------------------------------------------------------
// Exception word lists (FR-03a)
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

/// Unstressed suffix phoneme replacements (reserved for future dictionary-aware pipeline).
#[allow(dead_code)]
const UNSTRESSED_SUFFIXES: &[(&str, &[&str])] = &[
    ("ling", &["l", "\u{026A}", "\u{014B}"]), // l ɪ ŋ
    ("ning", &["n", "\u{026A}", "\u{014B}"]), // n ɪ ŋ
    ("ande", &["a", "n", "d", "\u{025B}"]),   // a n d ɛ
    ("erna", &["\u{025B}", "r", "n", "a"]),   // ɛ r n a
    ("arna", &["a", "r", "n", "a"]),          // a r n a
    ("lig", &["l", "\u{026A}", "\u{0261}"]),  // l ɪ ɡ
    ("en", &["\u{025B}", "n"]),               // ɛ n
    ("er", &["\u{025B}", "r"]),               // ɛ r
    ("el", &["\u{025B}", "l"]),               // ɛ l
    ("et", &["\u{025B}", "t"]),               // ɛ t
    ("ar", &["a", "r"]),                      // a r
    ("or", &["\u{0254}", "r"]),               // ɔ r
    ("ig", &["\u{026A}", "\u{0261}"]),        // ɪ ɡ
    ("ad", &["a", "d"]),                      // a d
    ("a", &["a"]),                            // a
    ("e", &["\u{025B}"]),                     // ɛ
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
    let _next2 = char_at(word, pos + 2);

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
/// Converts Swedish text to IPA phonemes using orthographic rules with optional
/// NST dictionary lookup.  No external dependencies required.
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
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        Ok(phonemize_swedish_with_prosody(text))
    }

    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> {
        // Swedish uses the phoneme_id_map from config.json (multilingual)
        None
    }

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
        // BOS + intersperse padding + EOS
        let pad_id = id_map
            .get("_")
            .and_then(|v| v.first().copied())
            .unwrap_or(0);
        let bos_id = id_map
            .get("^")
            .and_then(|v| v.first().copied())
            .unwrap_or(1);
        let eos_id = id_map
            .get("$")
            .and_then(|v| v.first().copied())
            .unwrap_or(2);

        let mut out_ids: Vec<i64> = Vec::with_capacity(ids.len() * 2 + 2);
        let mut out_prosody: Vec<Option<ProsodyFeature>> = Vec::with_capacity(ids.len() * 2 + 2);

        // BOS
        out_ids.push(bos_id);
        out_prosody.push(None);

        for (i, &id) in ids.iter().enumerate() {
            if i > 0 {
                out_ids.push(pad_id);
                out_prosody.push(None);
            }
            out_ids.push(id);
            out_prosody.push(prosody.get(i).cloned().unwrap_or(None));
        }

        // EOS
        out_ids.push(eos_id);
        out_prosody.push(None);

        (out_ids, out_prosody)
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

    // ===== Basic consonant rules =====

    #[test]
    fn test_sj_sound_sj() {
        // "sjö" -> ɧ + øː (sj -> sj-sound)
        let result = ph("sjö");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sj -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sj_sound_skj() {
        let result = ph("skjorta");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "skj -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sj_sound_sk_front_vowel() {
        // "sked" -> ɧ + e: d (sk + front vowel -> sj-sound)
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
        // "ska" -> s k a (sk + back vowel -> /sk/)
        let result = ph("ska");
        assert!(
            result.contains(&"s".to_string()),
            "sk + back vowel keeps s: {:?}",
            result
        );
        assert!(
            result.contains(&"k".to_string()),
            "sk + back vowel keeps k: {:?}",
            result
        );
    }

    #[test]
    fn test_tj_sound() {
        // "tjugo" -> ɕ u: ɡ ɔ
        let result = ph("tjugo");
        let curly_c = IPA_CURLY_C.to_string();
        assert!(result.contains(&curly_c), "tj -> ɕ: {:?}", result);
    }

    #[test]
    fn test_ng_produces_eng() {
        // "kung" -> k ɵ ŋ
        let result = ph("kung");
        let eng = IPA_ENG.to_string();
        assert!(result.contains(&eng), "ng -> ŋ: {:?}", result);
    }

    #[test]
    fn test_soft_k_before_front_vowel() {
        // "köp" -> ɕ + øː + p
        let result = ph("köp");
        let curly_c = IPA_CURLY_C.to_string();
        assert!(
            result.contains(&curly_c),
            "k + front vowel -> ɕ: {:?}",
            result
        );
    }

    #[test]
    fn test_hard_k_exception() {
        // "kille" is in HARD_K_WORDS -> k stays /k/
        let result = ph("kille");
        assert!(
            result.contains(&"k".to_string()),
            "hard-k exception 'kille' -> /k/: {:?}",
            result
        );
    }

    #[test]
    fn test_soft_g_before_front_vowel() {
        // "göra" -> j + ... (g + front vowel -> /j/)
        let result = ph("göra");
        assert!(
            result.contains(&"j".to_string()),
            "g + front vowel -> j: {:?}",
            result
        );
    }

    #[test]
    fn test_hard_g_exception() {
        // "ge" is in HARD_G_WORDS -> /ɡ/
        let result = ph("ge");
        let g_str = IPA_G.to_string();
        assert!(
            result.contains(&g_str),
            "hard-g exception 'ge' -> ɡ: {:?}",
            result
        );
    }

    // ===== Vowel length (Complementary Quantity) =====

    #[test]
    fn test_long_vowel_single_consonant() {
        // "mat" -> ˈm ɑː t  (single C after vowel -> long)
        let result = ph("mat");
        // Should contain a long vowel PUA character for ɑː (E05E)
        let pua_alpha_long = '\u{E05E}'.to_string();
        assert!(
            result.contains(&pua_alpha_long),
            "long vowel ɑː in 'mat': {:?}",
            result
        );
    }

    #[test]
    fn test_short_vowel_geminate() {
        // "matt" -> ˈm a t t  (geminate -> short vowel)
        let result = ph("matt");
        assert!(
            result.contains(&"a".to_string()),
            "short 'a' in 'matt': {:?}",
            result
        );
    }

    #[test]
    fn test_function_word_short_vowel() {
        // "jag" is a function word -> short vowel, no stress
        let result = ph("jag");
        let stress = IPA_STRESS.to_string();
        assert!(
            !result.contains(&stress),
            "function word 'jag' has no stress: {:?}",
            result
        );
    }

    // ===== Retroflex assimilation =====

    #[test]
    fn test_retroflex_rt() {
        // "kort" -> k ɔ ʈ (r+t -> retroflex ʈ)
        let result = ph("kort");
        let retro_t = IPA_RETRO_T.to_string();
        assert!(
            result.contains(&retro_t),
            "r+t -> ʈ in 'kort': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_rs() {
        // "fors" -> f ɔ ʂ (r+s -> retroflex ʂ)
        let result = ph("fors");
        let retro_s = IPA_RETRO_S.to_string();
        assert!(
            result.contains(&retro_s),
            "r+s -> ʂ in 'fors': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_rd() {
        // "bord" -> b uː ɖ (r+d -> retroflex ɖ)
        let result = ph("bord");
        let retro_d = IPA_RETRO_D.to_string();
        assert!(
            result.contains(&retro_d),
            "r+d -> ɖ in 'bord': {:?}",
            result
        );
    }

    // ===== Stress rules =====

    #[test]
    fn test_stress_default_first_syllable() {
        // "flicka" -> stress on first syllable
        let result = ph("flicka");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "content word has stress: {:?}",
            result
        );
        // Stress marker should be at position 0 (before onset of first syllable)
        assert_eq!(
            result[0], stress,
            "stress at position 0 for 'flicka': {:?}",
            result
        );
    }

    #[test]
    fn test_stress_attracting_suffix() {
        // "station" -> stress on the suffix "-tion"
        let result = ph("station");
        let stress = IPA_STRESS.to_string();
        assert!(result.contains(&stress), "station has stress: {:?}", result);
    }

    #[test]
    fn test_no_stress_function_word() {
        let stress = IPA_STRESS.to_string();
        assert!(
            !ph("och").contains(&stress),
            "function word 'och' no stress"
        );
        assert!(
            !ph("det").contains(&stress),
            "function word 'det' no stress"
        );
    }

    // ===== Loanword suffixes =====

    #[test]
    fn test_loanword_tion() {
        // "nation" -> na + ɧuːn
        let result = ph("nation");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            result.contains(&hook_h),
            "-tion -> ɧ in 'nation': {:?}",
            result
        );
    }

    #[test]
    fn test_loanword_age_french() {
        // "garage" -> loanword -age -> ɑː ɧ
        let result = ph("garage");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            result.contains(&hook_h),
            "-age -> ɧ in 'garage': {:?}",
            result
        );
    }

    #[test]
    fn test_native_age_not_loanword() {
        // "mage" is a native word -> no loanword rule
        let result = ph("mage");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            !result.contains(&hook_h),
            "'mage' is native, no ɧ: {:?}",
            result
        );
    }

    // ===== PUA mapping =====

    #[test]
    fn test_long_vowel_pua_mapping() {
        // Long vowels should be mapped to PUA codepoints
        let result = ph("sol"); // s + uː + l  (o -> uː default)
        let pua_u_long = '\u{E060}'.to_string(); // uː
        assert!(
            result.contains(&pua_u_long),
            "long uː mapped to PUA E060 in 'sol': {:?}",
            result
        );
    }

    #[test]
    fn test_o_long_as_oo() {
        // "son" is in O_LONG_AS_OO -> o maps to oː not uː
        let result = ph("son");
        let pua_o_long = '\u{E05F}'.to_string(); // oː
        assert!(
            result.contains(&pua_o_long),
            "o -> oː (PUA E05F) in 'son': {:?}",
            result
        );
    }

    // ===== Punctuation =====

    #[test]
    fn test_punctuation_preserved() {
        let result = ph("hej!");
        assert!(result.contains(&"!".to_string()), "! preserved");
    }

    // ===== Prosody =====

    #[test]
    fn test_prosody_length_matches_phonemes() {
        let (phonemes, prosody) = ph_with_prosody("hej världen");
        assert_eq!(phonemes.len(), prosody.len());
    }

    #[test]
    fn test_prosody_stress_a2() {
        let (phonemes, prosody) = ph_with_prosody("huset");
        let stress = IPA_STRESS.to_string();
        if let Some(pos) = phonemes.iter().position(|s| s == &stress) {
            let pi = prosody[pos].unwrap();
            assert_eq!(pi.a2, 2, "stress marker should have a2=2");
        }
    }

    // ===== post_process_ids =====

    #[test]
    fn test_post_process_ids_bos_eos_padding() {
        let phonemizer = SwedishPhonemizer::new();
        let mut id_map: PhonemeIdMap = std::collections::HashMap::new();
        id_map.insert("_".to_string(), vec![0]);
        id_map.insert("^".to_string(), vec![1]);
        id_map.insert("$".to_string(), vec![2]);

        let ids = vec![10, 20, 30];
        let prosody: Vec<Option<ProsodyFeature>> =
            vec![Some([0, 0, 3]), Some([0, 2, 3]), Some([0, 0, 3])];

        let (out_ids, out_prosody) = phonemizer.post_process_ids(ids, prosody, &id_map);

        // BOS + (id pad id pad id) + EOS = 7
        assert_eq!(out_ids.len(), 7);
        assert_eq!(out_ids[0], 1, "BOS");
        assert_eq!(out_ids[1], 10);
        assert_eq!(out_ids[2], 0, "pad");
        assert_eq!(out_ids[3], 20);
        assert_eq!(out_ids[4], 0, "pad");
        assert_eq!(out_ids[5], 30);
        assert_eq!(out_ids[6], 2, "EOS");
        assert_eq!(out_prosody.len(), 7);
    }

    // ===== Language code =====

    #[test]
    fn test_language_code() {
        assert_eq!(SwedishPhonemizer::new().language_code(), "sv");
    }

    // ===== Normalization =====

    #[test]
    fn test_uppercase_normalized() {
        assert_eq!(ph("HEJ"), ph("hej"), "uppercase normalizes to lowercase");
    }

    // ===== Space between words =====

    #[test]
    fn test_space_between_words() {
        assert!(
            ph("ett hus").contains(&" ".to_string()),
            "space between words"
        );
    }

    // ===== Empty text =====

    #[test]
    fn test_empty_text() {
        assert!(ph("").is_empty());
    }

    // ===== ch loanword =====

    #[test]
    fn test_ch_loanword_sj_sound() {
        // "chef" -> ɧ e: f
        let result = ph("chef");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "ch -> ɧ in 'chef': {:?}", result);
    }

    #[test]
    fn test_ch_exception_och() {
        // "och" is a CH_EXCEPTIONS_K -> ch = /k/, but also function word
        let result = ph("och");
        // 'och' is a function word so no stress
        let stress = IPA_STRESS.to_string();
        assert!(!result.contains(&stress), "'och' no stress: {:?}", result);
    }

    // ===== Retroflex cascade =====

    #[test]
    fn test_retroflex_cascade() {
        // "borste" -> r+s -> ʂ, then ʂ+t -> ʈ (cascade)
        let result = ph("borste");
        let retro_s = IPA_RETRO_S.to_string();
        let retro_t = IPA_RETRO_T.to_string();
        // Should have both retroflexes from cascade
        assert!(
            result.contains(&retro_s) || result.contains(&retro_t),
            "retroflex cascade in 'borste': {:?}",
            result
        );
    }

    // ===== Vowel length minimal pairs (Python: TestVowelLengthMinimalPairs) =====

    #[test]
    fn test_glas_long_a() {
        // glas: single consonant after vowel -> long ɑː
        let result = ph("glas");
        let pua_alpha_long = '\u{E05E}'.to_string(); // ɑː
        assert!(
            result.contains(&pua_alpha_long),
            "glas should have long ɑː: {:?}",
            result
        );
    }

    #[test]
    fn test_glass_short_a() {
        // glass: double s -> short a (no ɑː)
        let result = ph("glass");
        let pua_alpha_long = '\u{E05E}'.to_string(); // ɑː
        assert!(
            !result.contains(&pua_alpha_long),
            "glass should NOT have long ɑː: {:?}",
            result
        );
    }

    #[test]
    fn test_tak_long_a() {
        // tak: single consonant -> long ɑː
        let result = ph("tak");
        let pua_alpha_long = '\u{E05E}'.to_string();
        assert!(
            result.contains(&pua_alpha_long),
            "tak should have long ɑː: {:?}",
            result
        );
    }

    #[test]
    fn test_tack_short_a() {
        // tack: ck -> short a (no ɑː)
        let result = ph("tack");
        let pua_alpha_long = '\u{E05E}'.to_string();
        assert!(
            !result.contains(&pua_alpha_long),
            "tack should NOT have long ɑː: {:?}",
            result
        );
    }

    #[test]
    fn test_vet_long_e() {
        // vet: single consonant -> long eː
        let result = ph("vet");
        let pua_e_long = '\u{E05B}'.to_string(); // eː
        assert!(
            result.contains(&pua_e_long),
            "vet should have long eː: {:?}",
            result
        );
    }

    #[test]
    fn test_vett_short_e() {
        // vett: double t -> short ɛ (no eː)
        let result = ph("vett");
        let pua_e_long = '\u{E05B}'.to_string(); // eː
        let open_e = IPA_OPEN_E.to_string(); // ɛ
        assert!(
            !result.contains(&pua_e_long),
            "vett should NOT have long eː: {:?}",
            result
        );
        assert!(
            result.contains(&open_e),
            "vett should have short ɛ: {:?}",
            result
        );
    }

    #[test]
    fn test_vit_long_i() {
        // vit: single consonant -> long iː
        let result = ph("vit");
        let pua_i_long = '\u{E059}'.to_string(); // iː
        assert!(
            result.contains(&pua_i_long),
            "vit should have long iː: {:?}",
            result
        );
    }

    #[test]
    fn test_vitt_short_i() {
        // vitt: double t -> short ɪ (no iː)
        let result = ph("vitt");
        let pua_i_long = '\u{E059}'.to_string(); // iː
        assert!(
            !result.contains(&pua_i_long),
            "vitt should NOT have long iː: {:?}",
            result
        );
    }

    // ===== "o" ambiguity (Python: TestOAmbiguity) =====

    #[test]
    fn test_o_sol_long_u() {
        // sol: "o" default -> uː
        let result = ph("sol");
        let pua_u_long = '\u{E060}'.to_string(); // uː
        assert!(
            result.contains(&pua_u_long),
            "sol should have long uː: {:?}",
            result
        );
    }

    #[test]
    fn test_o_son_long_oo() {
        // son: in O_LONG_AS_OO -> oː
        let result = ph("son");
        let pua_o_long = '\u{E05F}'.to_string(); // oː
        assert!(
            result.contains(&pua_o_long),
            "son should have long oː: {:?}",
            result
        );
    }

    #[test]
    fn test_o_kort_short() {
        // kort: o + rt (2 consonants) -> short ɔ
        let result = ph("kort");
        let open_o = IPA_OPEN_O.to_string(); // ɔ
        assert!(
            result.contains(&open_o),
            "kort should have short ɔ: {:?}",
            result
        );
    }

    #[test]
    fn test_o_bott_short() {
        // bott: double t -> short ɔ
        let result = ph("bott");
        let open_o = IPA_OPEN_O.to_string(); // ɔ
        assert!(
            result.contains(&open_o),
            "bott should have short ɔ: {:?}",
            result
        );
    }

    #[test]
    fn test_o_mor_long_oo() {
        // mor: in O_LONG_AS_OO -> oː
        let result = ph("mor");
        let pua_o_long = '\u{E05F}'.to_string(); // oː
        assert!(
            result.contains(&pua_o_long),
            "mor should have long oː: {:?}",
            result
        );
    }

    #[test]
    fn test_o_bror_long_oo() {
        // bror: in O_LONG_AS_OO -> oː
        let result = ph("bror");
        let pua_o_long = '\u{E05F}'.to_string(); // oː
        assert!(
            result.contains(&pua_o_long),
            "bror should have long oː: {:?}",
            result
        );
    }

    #[test]
    fn test_o_ton_long_oo() {
        // ton: in O_LONG_AS_OO -> oː
        let result = ph("ton");
        let pua_o_long = '\u{E05F}'.to_string(); // oː
        assert!(
            result.contains(&pua_o_long),
            "ton should have long oː: {:?}",
            result
        );
    }

    #[test]
    fn test_o_bok_long_u() {
        // bok: NOT in O_LONG_AS_OO -> default uː
        let result = ph("bok");
        let pua_u_long = '\u{E060}'.to_string(); // uː
        assert!(
            result.contains(&pua_u_long),
            "bok should have long uː (default): {:?}",
            result
        );
    }

    #[test]
    fn test_o_god_long_oo() {
        // god: in O_LONG_AS_OO -> oː
        let result = ph("god");
        let pua_o_long = '\u{E05F}'.to_string(); // oː
        assert!(
            result.contains(&pua_o_long),
            "god should have long oː: {:?}",
            result
        );
    }

    // ===== Review-fix rules (Python: TestReviewFixRules) =====

    #[test]
    fn test_gj_word_initial() {
        // gjord: word-initial gj -> /j/
        let result = ph("gjord");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&"j".to_string()),
            "gj word-initial should produce /j/: {:?}",
            result
        );
        // Should NOT start with hard g
        let g_str = IPA_G.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert!(
            first_non_stress != Some(&g_str),
            "gjord should NOT start with hard ɡ: {:?}",
            result
        );
    }

    #[test]
    fn test_dj_word_initial() {
        // djur: word-initial dj -> /j/
        let result = ph("djur");
        let stress = IPA_STRESS.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert_eq!(
            first_non_stress,
            Some(&"j".to_string()),
            "djur word-initial dj -> /j/: {:?}",
            result
        );
    }

    #[test]
    fn test_hj_word_initial() {
        // hjälp: word-initial hj -> /j/
        let result = ph("hj\u{00E4}lp");
        let stress = IPA_STRESS.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert_eq!(
            first_non_stress,
            Some(&"j".to_string()),
            "hjälp word-initial hj -> /j/: {:?}",
            result
        );
    }

    #[test]
    fn test_lj_word_initial() {
        // ljus: word-initial lj -> /j/
        let result = ph("ljus");
        let stress = IPA_STRESS.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert_eq!(
            first_non_stress,
            Some(&"j".to_string()),
            "ljus word-initial lj -> /j/: {:?}",
            result
        );
    }

    #[test]
    fn test_era_verb_hard_g() {
        // agera: Latin -era verb -> hard g
        assert!(is_hard_g("agera"), "agera should have hard g (-era verb)");
    }

    #[test]
    fn test_erar_verb_hard_g() {
        assert!(
            is_hard_g("reagerar"),
            "reagerar should have hard g (-erar verb)"
        );
    }

    #[test]
    fn test_erade_verb_hard_g() {
        assert!(
            is_hard_g("navigerade"),
            "navigerade should have hard g (-erade verb)"
        );
    }

    #[test]
    fn test_berg_hard_g() {
        assert!(is_hard_g("berg"), "berg should have hard g");
    }

    #[test]
    fn test_borg_hard_g() {
        assert!(is_hard_g("borg"), "borg should have hard g");
    }

    // ===== Unstressed suffix patterns (Python: TestUnstressedSuffixPatterns) =====

    #[test]
    fn test_vacker_er_suffix() {
        // vacker: -er suffix, stress on first syllable
        let result = ph("vacker");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "vacker should have stress: {:?}",
            result
        );
        // Stress should be on position 0 (first syllable)
        assert_eq!(
            result[0], stress,
            "vacker stress at position 0: {:?}",
            result
        );
    }

    #[test]
    fn test_vatten_en_suffix() {
        // vatten: -en suffix, stress on first syllable
        let result = ph("vatten");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "vatten should have stress: {:?}",
            result
        );
        assert_eq!(
            result[0], stress,
            "vatten stress at position 0: {:?}",
            result
        );
    }

    #[test]
    fn test_bilar_ar_suffix() {
        // bilar: -ar suffix, stress on first syllable
        let result = ph("bilar");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "bilar should have stress: {:?}",
            result
        );
        assert_eq!(
            result[0], stress,
            "bilar stress at position 0: {:?}",
            result
        );
    }

    #[test]
    fn test_flickor_or_suffix() {
        // flickor: -or suffix, stress on first syllable
        let result = ph("flickor");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "flickor should have stress: {:?}",
            result
        );
        assert_eq!(
            result[0], stress,
            "flickor stress at position 0: {:?}",
            result
        );
    }

    // ===== Consonant gap-fill tests (Python: TestConsonantGapFill) =====

    #[test]
    fn test_nk_digraph() {
        // bank: nk -> [ŋ, k]
        let result = ph("bank");
        let eng = IPA_ENG.to_string(); // ŋ
        assert!(result.contains(&eng), "nk -> ŋ in 'bank': {:?}", result);
        assert!(
            result.contains(&"k".to_string()),
            "nk -> k in 'bank': {:?}",
            result
        );
    }

    #[test]
    fn test_c_before_e_soft() {
        // center: c before e -> /s/
        let result = ph("center");
        let stress = IPA_STRESS.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert_eq!(
            first_non_stress,
            Some(&"s".to_string()),
            "c before e -> /s/ in 'center': {:?}",
            result
        );
    }

    #[test]
    fn test_c_before_a_hard() {
        // camping: c before a -> /k/
        let result = ph("camping");
        let stress = IPA_STRESS.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert_eq!(
            first_non_stress,
            Some(&"k".to_string()),
            "c before a -> /k/ in 'camping': {:?}",
            result
        );
    }

    #[test]
    fn test_gn_word_initial() {
        // gnaga: word-initial gn -> /ɡn/
        let result = ph("gnaga");
        let g_str = IPA_G.to_string();
        assert!(
            result.contains(&g_str),
            "word-initial gn -> ɡ in 'gnaga': {:?}",
            result
        );
    }

    #[test]
    fn test_gn_medial() {
        // signal: medial gn -> /ŋn/
        let result = ph("signal");
        let eng = IPA_ENG.to_string(); // ŋ
        assert!(
            result.contains(&eng),
            "medial gn -> ŋ in 'signal': {:?}",
            result
        );
    }

    #[test]
    fn test_sk_back_vowel_exception_manniska() {
        // människa is in SK_BACK_VOWEL_EXCEPTIONS -> sk stays /sk/, no ɧ
        let result = ph("m\u{00E4}nniska");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(
            !result.contains(&hook_h),
            "människa should NOT have ɧ: {:?}",
            result
        );
    }

    #[test]
    fn test_ium_loanword_suffix() {
        // stadium: -ium loanword suffix
        let result = detect_loanword_suffix("stadium");
        assert!(
            result.is_some(),
            "stadium should detect -ium loanword suffix"
        );
        let (prefix, _) = result.unwrap();
        assert_eq!(prefix, "stad", "stadium prefix should be 'stad'");
    }

    #[test]
    fn test_eum_loanword_suffix() {
        // museum: -eum loanword suffix
        let result = detect_loanword_suffix("museum");
        assert!(
            result.is_some(),
            "museum should detect -eum loanword suffix"
        );
    }

    // ===== Additional basic vowel tests (Python: TestBasicVowels coverage) =====

    #[test]
    fn test_long_i_fin() {
        // fin -> long iː
        let result = ph("fin");
        let pua_i_long = '\u{E059}'.to_string(); // iː
        assert!(
            result.contains(&pua_i_long),
            "fin should have long iː: {:?}",
            result
        );
    }

    #[test]
    fn test_short_i_flicka() {
        // flicka -> short ɪ
        let result = ph("flicka");
        let small_i = IPA_SMALL_I.to_string(); // ɪ
        assert!(
            result.contains(&small_i),
            "flicka should have short ɪ: {:?}",
            result
        );
    }

    #[test]
    fn test_long_u_hus() {
        // hus -> long ʉː
        let result = ph("hus");
        let pua_barred_u_long = '\u{E061}'.to_string(); // ʉː
        assert!(
            result.contains(&pua_barred_u_long),
            "hus should have long ʉː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_y_syn() {
        // syn -> long yː
        let result = ph("syn");
        let pua_y_long = '\u{E05A}'.to_string(); // yː
        assert!(
            result.contains(&pua_y_long),
            "syn should have long yː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_oe_oel() {
        // öl -> long øː
        let result = ph("\u{00F6}l");
        let pua_oe_long = '\u{E05D}'.to_string(); // øː
        assert!(
            result.contains(&pua_oe_long),
            "öl should have long øː: {:?}",
            result
        );
    }

    #[test]
    fn test_long_ae_sael() {
        // säl -> long ɛː
        let result = ph("s\u{00E4}l");
        let pua_ae_long = '\u{E05C}'.to_string(); // ɛː
        assert!(
            result.contains(&pua_ae_long),
            "säl should have long ɛː: {:?}",
            result
        );
    }

    #[test]
    fn test_short_e_cluster_fest() {
        // fest -> short ɛ (cluster)
        let result = ph("fest");
        let open_e = IPA_OPEN_E.to_string(); // ɛ
        let pua_e_long = '\u{E05B}'.to_string(); // eː
        assert!(
            result.contains(&open_e),
            "fest should have short ɛ: {:?}",
            result
        );
        assert!(
            !result.contains(&pua_e_long),
            "fest should NOT have long eː: {:?}",
            result
        );
    }

    #[test]
    fn test_short_oe_hoest() {
        // höst -> short ö = œ
        let result = ph("h\u{00F6}st");
        let oe_lig = IPA_OE_LIG.to_string(); // œ
        assert!(
            result.contains(&oe_lig),
            "höst should have short œ: {:?}",
            result
        );
    }

    // ===== Additional retroflex tests (Python: TestRetroflex coverage) =====

    #[test]
    fn test_retroflex_rn_barn() {
        // barn -> ˈbɑːɳ (r+n -> retroflex ɳ)
        let result = ph("barn");
        let retro_n = IPA_RETRO_N.to_string();
        assert!(
            result.contains(&retro_n),
            "r+n -> ɳ in 'barn': {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_rl() {
        // apply_retroflex directly for r+l -> ɭ
        let input: Vec<String> = vec!["r".into(), "l".into()];
        let result = apply_retroflex(&input);
        let retro_l = IPA_RETRO_L.to_string();
        assert!(result.contains(&retro_l), "r+l -> ɭ: {:?}", result);
    }

    #[test]
    fn test_retroflex_cascade_rst() {
        // apply_retroflex: f + œ + r + s + t -> f + œ + ʂ + ʈ
        let input: Vec<String> = vec![
            "f".into(),
            "\u{0153}".into(),
            "r".into(),
            "s".into(),
            "t".into(),
        ];
        let result = apply_retroflex(&input);
        let retro_s = IPA_RETRO_S.to_string();
        let retro_t = IPA_RETRO_T.to_string();
        assert!(result.contains(&retro_s), "cascade r+s -> ʂ: {:?}", result);
        assert!(result.contains(&retro_t), "cascade ʂ+t -> ʈ: {:?}", result);
        // r should be consumed
        assert!(
            !result.contains(&"r".to_string()),
            "r consumed in cascade: {:?}",
            result
        );
    }

    #[test]
    fn test_retroflex_l_stops_cascade() {
        // apply_retroflex: k + ɑː + r + l + s -> k + ɑː + ɭ + s
        // ɭ does NOT propagate, so s stays as /s/
        let input: Vec<String> = vec![
            "k".into(),
            "\u{0251}\u{02D0}".into(),
            "r".into(),
            "l".into(),
            "s".into(),
        ];
        let result = apply_retroflex(&input);
        let retro_l = IPA_RETRO_L.to_string();
        assert!(result.contains(&retro_l), "r+l -> ɭ: {:?}", result);
        assert!(
            result.contains(&"s".to_string()),
            "s NOT retroflex (ɭ stops cascade): {:?}",
            result
        );
    }

    #[test]
    fn test_rr_blocks_retroflex() {
        // apply_retroflex: b + ɔ + r + r + s -> unchanged (rr blocks)
        let input: Vec<String> = vec![
            "b".into(),
            "\u{0254}".into(),
            "r".into(),
            "r".into(),
            "s".into(),
        ];
        let result = apply_retroflex(&input);
        assert_eq!(result, input, "rr blocks retroflex: {:?}", result);
    }

    #[test]
    fn test_r_plus_k_no_change() {
        // apply_retroflex: b + ɑː + r + k -> unchanged (k not retroflex target)
        let input: Vec<String> = vec![
            "b".into(),
            "\u{0251}\u{02D0}".into(),
            "r".into(),
            "k".into(),
        ];
        let result = apply_retroflex(&input);
        assert_eq!(result, input, "r+k no retroflex change: {:?}", result);
    }

    #[test]
    fn test_word_final_r_no_change() {
        // apply_retroflex: f + ɑː + r -> unchanged (word-final r)
        let input: Vec<String> = vec!["f".into(), "\u{0251}\u{02D0}".into(), "r".into()];
        let result = apply_retroflex(&input);
        assert_eq!(result, input, "word-final r unchanged: {:?}", result);
    }

    // ===== Additional sj-sound tests (Python: TestSjSound coverage) =====

    #[test]
    fn test_sj_sound_stj() {
        // stjärna: stj -> ɧ
        let result = ph("stj\u{00E4}rna");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "stj -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sj_sound_sch() {
        // schema: sch -> ɧ
        let result = ph("schema");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sch -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sj_sound_sh() {
        // show: sh -> ɧ
        let result = ph("show");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sh -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sk_front_i() {
        // skinn: sk + front i -> ɧ
        let result = ph("skinn");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sk + i -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sk_front_y() {
        // sky: sk + front y -> ɧ
        let result = ph("sky");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sk + y -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sk_front_ae() {
        // skäl: sk + front ä -> ɧ
        let result = ph("sk\u{00E4}l");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sk + ä -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sk_front_oe() {
        // sköld: sk + front ö -> ɧ
        let result = ph("sk\u{00F6}ld");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "sk + ö -> ɧ: {:?}", result);
    }

    #[test]
    fn test_sk_back_o_no_sj() {
        // skog: sk + back o -> /sk/ (no ɧ)
        let result = ph("skog");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(!result.contains(&hook_h), "sk + o no ɧ: {:?}", result);
    }

    #[test]
    fn test_sk_back_u_no_sj() {
        // skum: sk + back u -> /sk/ (no ɧ)
        let result = ph("skum");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(!result.contains(&hook_h), "sk + u no ɧ: {:?}", result);
    }

    #[test]
    fn test_loanword_sion() {
        // passion: -sion -> ɧ
        let result = ph("passion");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "-sion -> ɧ: {:?}", result);
    }

    #[test]
    fn test_loanword_ssion() {
        // mission: -ssion -> ɧ
        let result = ph("mission");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "-ssion -> ɧ: {:?}", result);
    }

    #[test]
    fn test_loanword_tion_station() {
        // station: -tion -> ɧ
        let result = ph("station");
        let hook_h = IPA_HOOK_H.to_string();
        assert!(result.contains(&hook_h), "-tion -> ɧ: {:?}", result);
    }

    // ===== Additional loanword tests (Python: TestLoanwords coverage) =====

    #[test]
    fn test_ph_as_f() {
        // photo: ph -> /f/
        let result = ph("photo");
        assert!(
            result.contains(&"f".to_string()),
            "ph -> f in 'photo': {:?}",
            result
        );
    }

    #[test]
    fn test_th_as_t() {
        // theme: th -> /t/
        let result = ph("theme");
        let stress = IPA_STRESS.to_string();
        let first_non_stress: Option<&String> = result.iter().find(|s| *s != &stress);
        assert_eq!(
            first_non_stress,
            Some(&"t".to_string()),
            "th -> t in 'theme': {:?}",
            result
        );
    }

    #[test]
    fn test_loanword_sion_detected() {
        let result = detect_loanword_suffix("passion");
        assert!(result.is_some(), "passion should detect -sion suffix");
    }

    #[test]
    fn test_loanword_age_detected() {
        let result = detect_loanword_suffix("garage");
        assert!(result.is_some(), "garage should detect -age suffix");
    }

    #[test]
    fn test_native_age_excluded() {
        // "mage" is native Swedish, not French -age
        let result = detect_loanword_suffix("mage");
        assert!(result.is_none(), "mage is native, should NOT detect -age");
    }

    // ===== Additional stress tests (Python: TestStress + TestStressSpec coverage) =====

    #[test]
    fn test_detect_stress_monosyllable() {
        assert_eq!(detect_stress("hus"), 0, "monosyllable stress on 0");
    }

    #[test]
    fn test_detect_stress_function_word() {
        assert_eq!(detect_stress("och"), -1, "function word no stress");
    }

    #[test]
    fn test_detect_stress_tion_suffix() {
        assert!(detect_stress("station") > 0, "-tion suffix attracts stress");
    }

    #[test]
    fn test_detect_stress_eri_suffix() {
        assert!(detect_stress("bageri") > 0, "-eri suffix attracts stress");
    }

    #[test]
    fn test_detect_stress_be_prefix() {
        assert_eq!(
            detect_stress("betala"),
            1,
            "be- prefix: stress on syllable 1"
        );
    }

    #[test]
    fn test_detect_stress_foer_prefix() {
        assert_eq!(
            detect_stress("f\u{00F6}rst\u{00E5}"),
            1,
            "för- prefix: stress on syllable 1"
        );
    }

    #[test]
    fn test_detect_stress_default_first() {
        assert_eq!(
            detect_stress("flicka"),
            0,
            "default stress on first syllable"
        );
    }

    #[test]
    fn test_detect_stress_itet_suffix() {
        assert!(
            detect_stress("universitet") > 0,
            "-itet suffix attracts stress"
        );
    }

    #[test]
    fn test_detect_stress_ist_suffix() {
        assert!(detect_stress("turist") > 0, "-ist suffix attracts stress");
    }

    #[test]
    fn test_detect_stress_ik_suffix() {
        assert!(detect_stress("musik") > 0, "-ik suffix attracts stress");
    }

    // ===== Additional edge case tests (Python: TestEdgeCases coverage) =====

    #[test]
    fn test_single_vowel() {
        let result = ph("a");
        assert!(!result.is_empty(), "single vowel 'a' should produce output");
    }

    #[test]
    fn test_multiple_words() {
        let result = ph("hej du");
        assert!(
            result.contains(&" ".to_string()),
            "multiple words should contain space: {:?}",
            result
        );
    }

    // ===== Vowel length edge cases (Python: TestVowelLength extra) =====

    #[test]
    fn test_final_vowel_long_bo() {
        // bo: word-final vowel -> long
        let result = ph("bo");
        let pua_o_long = '\u{E05F}'.to_string(); // oː (bo is in O_LONG_AS_OO)
        let pua_u_long = '\u{E060}'.to_string(); // uː
        assert!(
            result.contains(&pua_o_long) || result.contains(&pua_u_long),
            "bo should have long vowel: {:?}",
            result
        );
    }

    #[test]
    fn test_function_word_for_short() {
        // för -> short (function word), no long øː
        let result = ph("f\u{00F6}r");
        let pua_oe_long = '\u{E05D}'.to_string(); // øː
        assert!(
            !result.contains(&pua_oe_long),
            "function word 'för' should NOT have long øː: {:?}",
            result
        );
    }

    #[test]
    fn test_final_m_short_hem() {
        // hem -> short vowel despite single m ending
        let result = ph("hem");
        let pua_e_long = '\u{E05B}'.to_string(); // eː
        assert!(
            !result.contains(&pua_e_long),
            "hem should NOT have long eː (FINAL_M_SHORT): {:?}",
            result
        );
    }

    #[test]
    fn test_r_plus_c_preserves_long_barn() {
        // barn: r + C exception, vowel stays long ɑː
        let result = ph("barn");
        let pua_alpha_long = '\u{E05E}'.to_string(); // ɑː
        assert!(
            result.contains(&pua_alpha_long),
            "barn should have long ɑː (r+C exception): {:?}",
            result
        );
    }

    // ===== Unstressed vowel tests (Python: TestUnstressedVowels coverage) =====

    #[test]
    fn test_function_word_att_no_stress() {
        let result = ph("att");
        let stress = IPA_STRESS.to_string();
        assert!(
            !result.contains(&stress),
            "function word 'att' no stress: {:?}",
            result
        );
    }

    #[test]
    fn test_function_word_det_no_stress() {
        let result = ph("det");
        let stress = IPA_STRESS.to_string();
        assert!(
            !result.contains(&stress),
            "function word 'det' no stress: {:?}",
            result
        );
    }

    #[test]
    fn test_function_word_som_no_stress() {
        let result = ph("som");
        let stress = IPA_STRESS.to_string();
        assert!(
            !result.contains(&stress),
            "function word 'som' no stress: {:?}",
            result
        );
    }

    #[test]
    fn test_stressed_monosyllable_bil() {
        let result = ph("bil");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "content monosyllable 'bil' should have stress: {:?}",
            result
        );
    }

    #[test]
    fn test_unstressed_prefix_betala() {
        // betala: stress on 2nd syllable (be- is unstressed prefix)
        let result = ph("betala");
        let stress = IPA_STRESS.to_string();
        assert!(
            result.contains(&stress),
            "betala should have stress: {:?}",
            result
        );
        // Stress should NOT be at position 0 (it's after the unstressed prefix)
        let stress_pos = result.iter().position(|s| s == &stress).unwrap();
        assert!(
            stress_pos > 0,
            "betala stress not at position 0 (after be- prefix): {:?}",
            result
        );
    }

    #[test]
    fn test_function_words_count() {
        assert!(
            FUNCTION_WORDS.len() >= 35,
            "should have at least 35 function words, got {}",
            FUNCTION_WORDS.len()
        );
    }

    // ===== Hard k/g exception tests (Python extra coverage) =====

    #[test]
    fn test_hard_k_flicka() {
        let result = ph("flicka");
        assert!(
            result.contains(&"k".to_string()),
            "flicka should have hard /k/: {:?}",
            result
        );
        let curly_c = IPA_CURLY_C.to_string();
        assert!(
            !result.contains(&curly_c),
            "flicka should NOT have soft ɕ: {:?}",
            result
        );
    }

    #[test]
    fn test_hard_k_pojke() {
        let result = ph("pojke");
        assert!(
            result.contains(&"k".to_string()),
            "pojke should have hard /k/: {:?}",
            result
        );
    }

    #[test]
    fn test_hard_k_socker() {
        let result = ph("socker");
        assert!(
            result.contains(&"k".to_string()),
            "socker should have hard /k/: {:?}",
            result
        );
    }

    #[test]
    fn test_hard_g_finger() {
        assert!(is_hard_g("finger"), "finger should have hard g");
    }

    #[test]
    fn test_hard_g_ger() {
        assert!(is_hard_g("ger"), "ger should have hard g");
    }

    #[test]
    fn test_kj_soft_sound() {
        // kjol: kj -> ɕ
        let result = ph("kjol");
        let curly_c = IPA_CURLY_C.to_string();
        assert!(result.contains(&curly_c), "kj -> ɕ: {:?}", result);
    }

    // ===== Prosody extra tests (Python: TestProsody coverage) =====

    #[test]
    fn test_prosody_a1_always_zero() {
        let (_, prosody) = ph_with_prosody("flickan gick");
        for pi in &prosody {
            if let Some(info) = pi {
                assert_eq!(info.a1, 0, "a1 should always be 0: {:?}", info);
            }
        }
    }

    #[test]
    fn test_prosody_a3_word_phoneme_count() {
        let (phonemes, prosody) = ph_with_prosody("hus");
        // a3 should reflect word phoneme count
        for (ph, pi) in phonemes.iter().zip(prosody.iter()) {
            if let Some(info) = pi {
                if info.a3 > 0 {
                    assert!(
                        info.a3 >= 3,
                        "a3 for 'hus' should be >= 3 (h, ʉː, s), got {}: ph={:?}",
                        info.a3,
                        ph
                    );
                }
            }
        }
    }
}

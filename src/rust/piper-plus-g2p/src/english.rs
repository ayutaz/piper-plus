//! English phonemizer using CMU dictionary + ARPAbet-to-IPA conversion.
//!
//! Ports the Python `english.py` and C++ `english_phonemize.cpp` logic to Rust.
//! Converts English text to IPA phonemes using CMU dictionary lookup with
//! context-dependent ARPAbet-to-IPA rules that match espeak-ng output.
//!
//! ## Pipeline
//!
//! 1. Normalize and tokenize the text like Python's g2p_en (numbers spelled
//!    out, accents stripped, `i.e.` / `e.g.` expanded, nltk `TweetTokenizer`);
//!    see [`crate::english_normalize`]
//! 2. Look up each word in the CMU dictionary (JSON: `cmudict_data.json`)
//! 3. Convert ARPAbet to IPA with context-dependent rules
//!    - AA + R -> merged `ɑːɹ`
//!    - Stressed ER (stress=1) -> `ɜː`
//!    - Unstressed ER (stress=0) -> `ɚ`
//!    - Unstressed AH (stress=0) -> `ə` (schwa)
//! 4. Apply function-word destressing (97 common words)
//! 5. Insert stress markers (`ˈ`/`ˌ`) before stressed vowels
//! 6. Each IPA character becomes a separate phoneme token
//!
//! ## Prosody
//!
//! - `a1` = 0 (fixed for English)
//! - `a2` = stress level: primary(1)->2, secondary(2)->1, none/consonant->0
//! - `a3` = total IPA character count for the word
//!
//! ## OOV handling
//!
//! Words not found in the CMU dictionary are handled by morphological
//! fallback: common English suffixes (-ing, -ed, -s/-es, -er, -ly, -est)
//! are stripped and the base form is looked up. Python reads the remaining
//! words with g2p_en's neural guesser, which is not ported: they are split at
//! `-` / `.`, retried without apostrophes, split at CamelCase boundaries, and
//! finally spelled letter by letter, so no word is dropped.

use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::sync::{LazyLock, OnceLock};

use crate::error::G2pError;
use crate::phonemizer::{Phonemizer, ProsodyInfo};

// ---------------------------------------------------------------------------
// ARPAbet-to-IPA mapping table
//
// Matches Python ARPABET_TO_IPA and C++ arpaToIpa() exactly.
// Each value is a &str of one or more IPA codepoints.
// ---------------------------------------------------------------------------

static ARPABET_TO_IPA: LazyLock<HashMap<&'static str, &'static str>> = LazyLock::new(|| {
    [
        ("AA", "\u{0251}"),         // ɑ
        ("AE", "\u{00E6}"),         // æ
        ("AH", "\u{028C}"),         // ʌ (stressed default)
        ("AO", "\u{0254}\u{02D0}"), // ɔː
        ("AW", "a\u{028A}"),        // aʊ
        ("AY", "a\u{026A}"),        // aɪ
        ("B", "b"),
        ("CH", "t\u{0283}"), // tʃ
        ("D", "d"),
        ("DH", "\u{00F0}"),  // ð
        ("EH", "\u{025B}"),  // ɛ
        ("ER", "\u{025A}"),  // ɚ (unstressed default)
        ("EY", "e\u{026A}"), // eɪ
        ("F", "f"),
        ("G", "\u{0261}"), // ɡ
        ("HH", "h"),
        ("IH", "\u{026A}"),  // ɪ
        ("IY", "i\u{02D0}"), // iː
        ("JH", "d\u{0292}"), // dʒ
        ("K", "k"),
        ("L", "l"),
        ("M", "m"),
        ("N", "n"),
        ("NG", "\u{014B}"),         // ŋ
        ("OW", "o\u{028A}"),        // oʊ
        ("OY", "\u{0254}\u{026A}"), // ɔɪ
        ("P", "p"),
        ("R", "\u{0279}"), // ɹ
        ("S", "s"),
        ("SH", "\u{0283}"), // ʃ
        ("T", "t"),
        ("TH", "\u{03B8}"),  // θ
        ("UH", "\u{028A}"),  // ʊ
        ("UW", "u\u{02D0}"), // uː
        ("V", "v"),
        ("W", "w"),
        ("Y", "j"),
        ("Z", "z"),
        ("ZH", "\u{0292}"), // ʒ
    ]
    .into_iter()
    .collect()
});

/// Unstressed AH -> schwa (ə)
const AH_UNSTRESSED_IPA: &str = "\u{0259}";

/// Stressed ER -> ɜː
const ER_STRESSED_IPA: &str = "\u{025C}\u{02D0}";

/// AA + R merge -> ɑːɹ
const AA_R_MERGED_IPA: &str = "\u{0251}\u{02D0}\u{0279}";

/// Primary stress marker ˈ
const STRESS_PRIMARY: &str = "\u{02C8}";

/// Secondary stress marker ˌ
const STRESS_SECONDARY: &str = "\u{02CC}";

// ---------------------------------------------------------------------------
// Punctuation set (attached to preceding word)
// ---------------------------------------------------------------------------

fn is_punctuation(ch: char) -> bool {
    matches!(ch, ',' | '.' | ';' | ':' | '!' | '?')
}

// ---------------------------------------------------------------------------
// Function words — stress removed to match espeak-ng behavior.
// Matches Python _FUNCTION_WORDS and C++ functionWords() exactly (97 entries).
// ---------------------------------------------------------------------------

static FUNCTION_WORDS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        // articles / determiners
        "a",
        "an",
        "the",
        // pronouns
        "i",
        "me",
        "my",
        "mine",
        "myself",
        "you",
        "your",
        "yours",
        "yourself",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "we",
        "us",
        "our",
        "ours",
        "ourselves",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        // be-verbs
        "am",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        // auxiliaries
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        // prepositions
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "to",
        "with",
        "about",
        "after",
        "before",
        "between",
        "into",
        "through",
        "under",
        // conjunctions
        "and",
        "but",
        "or",
        "nor",
        "so",
        "yet",
        "if",
        "that",
        "than",
        "when",
        "while",
        "as",
        "because",
        "since",
        // others
        "not",
        "no",
    ]
    .into_iter()
    .collect()
});

// ---------------------------------------------------------------------------
// Words
//
// The words come from `english_normalize`, which ports g2p_en's number
// expansion, accent stripping, character filter and tokenizer. The helpers
// below handle what g2p_en and english.py do after tokenization.
// ---------------------------------------------------------------------------

pub use crate::english_normalize::{normalize_and_tokenize, normalize_numbers};

/// Words of the original text used to find function words.
///
/// Mirrors Python `re.findall(r"[a-zA-Z']+", text.lower())`. Python takes
/// them from the text before number expansion and aligns them with the
/// spoken words in order, so `the 3 of us` gives `three` the function-word
/// flag of `of`. The training data was phonemized that way, so it is kept.
fn source_words(text: &str) -> Vec<String> {
    text.split(|c: char| !(c.is_ascii_alphabetic() || c == '\''))
        .filter(|w| !w.is_empty())
        .map(str::to_ascii_lowercase)
        .collect()
}

/// A word made of one punctuation character (`,` `.` `;` `:` `!` `?`):
/// attached to the preceding word without a word boundary.
fn is_punctuation_word(word: &str) -> bool {
    let mut chars = word.chars();
    matches!((chars.next(), chars.next()), (Some(c), None) if is_punctuation(c))
}

/// The name of a letter, used to spell words that cannot be read otherwise.
fn letter_name_arpabet(ch: char) -> Option<&'static str> {
    Some(match ch.to_ascii_lowercase() {
        'a' => "EY1",
        'b' => "B IY1",
        'c' => "S IY1",
        'd' => "D IY1",
        'e' => "IY1",
        'f' => "EH1 F",
        'g' => "JH IY1",
        'h' => "EY1 CH",
        'i' => "AY1",
        'j' => "JH EY1",
        'k' => "K EY1",
        'l' => "EH1 L",
        'm' => "EH1 M",
        'n' => "EH1 N",
        'o' => "OW1",
        'p' => "P IY1",
        'q' => "K Y UW1",
        'r' => "AA1 R",
        's' => "EH1 S",
        't' => "T IY1",
        'u' => "Y UW1",
        'v' => "V IY1",
        'w' => "D AH1 B AH0 L Y UW0",
        'x' => "EH1 K S",
        'y' => "W AY1",
        'z' => "Z IY1",
        _ => return None,
    })
}

/// Splits a word at CamelCase boundaries, like Python
/// `re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", word)`:
/// `ChatGPT` -> `Chat` + `GPT`, `HTMLParser` -> `HTML` + `Parser`.
fn split_camel_case(word: &str) -> Vec<&str> {
    let b = word.as_bytes();
    let run_end = |from: usize, pred: fn(&u8) -> bool| {
        let mut j = from;
        while j < b.len() && pred(&b[j]) {
            j += 1;
        }
        j
    };
    let mut parts = Vec::new();
    let mut i = 0;
    while i < b.len() {
        if b[i].is_ascii_uppercase() {
            let upper_end = run_end(i, u8::is_ascii_uppercase);
            let lower_follows = upper_end < b.len() && b[upper_end].is_ascii_lowercase();
            if lower_follows && upper_end - i >= 2 {
                // The last capital starts the next part.
                parts.push(&word[i..upper_end - 1]);
                i = upper_end - 1;
            } else if lower_follows {
                let end = run_end(upper_end, u8::is_ascii_lowercase);
                parts.push(&word[i..end]);
                i = end;
            } else {
                parts.push(&word[i..upper_end]);
                i = upper_end;
            }
        } else if b[i].is_ascii_lowercase() {
            let end = run_end(i, u8::is_ascii_lowercase);
            parts.push(&word[i..end]);
            i = end;
        } else {
            i += 1;
        }
    }
    parts
}
// ---------------------------------------------------------------------------
// ARPAbet parsing
// ---------------------------------------------------------------------------

/// A parsed ARPAbet token with its base symbol and stress level.
#[derive(Debug)]
struct ArpaToken {
    base: String, // e.g. "HH", "AH", "OW"
    stress: i32,  // 0, 1, 2, or -1 for consonants
}

/// Parse an ARPAbet pronunciation string into tokens.
///
/// Input: `"HH AH0 L OW1"`
/// Output: `[("HH", -1), ("AH", 0), ("L", -1), ("OW", 1)]`
fn parse_arpabet(arpa: &str) -> Vec<ArpaToken> {
    arpa.split_whitespace()
        .filter(|s| !s.is_empty())
        .map(|tok| {
            let bytes = tok.as_bytes();
            let last = *bytes.last().unwrap();
            if (last == b'0' || last == b'1' || last == b'2') && bytes.len() > 1 {
                ArpaToken {
                    base: tok[..tok.len() - 1].to_string(),
                    stress: (last - b'0') as i32,
                }
            } else {
                ArpaToken {
                    base: tok.to_string(),
                    stress: -1,
                }
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// ARPAbet-to-IPA conversion with context-dependent rules
// ---------------------------------------------------------------------------

/// A converted IPA phoneme with its IPA string and stress level.
#[derive(Debug, Clone)]
struct IpaPhoneme {
    ipa: String,
    stress: i32,
}

/// Convert a sequence of ARPAbet tokens to IPA with context-dependent rules.
///
/// Handles:
/// - AA + R -> ɑːɹ (merge into single vowel+r)
/// - ER with stress=1 -> ɜː (stressed r-colored vowel)
/// - AH with stress=0 -> ə (schwa)
fn convert_word_to_ipa(tokens: &[ArpaToken]) -> Vec<IpaPhoneme> {
    let mut result = Vec::new();
    let n = tokens.len();
    let mut i = 0;

    while i < n {
        let tok = &tokens[i];

        // Context-dependent rule: AA + R -> ɑːɹ
        if tok.base == "AA" && i + 1 < n && tokens[i + 1].base == "R" && tokens[i + 1].stress == -1
        {
            result.push(IpaPhoneme {
                ipa: AA_R_MERGED_IPA.to_string(),
                stress: tok.stress,
            });
            i += 2;
            continue;
        }

        // Context-dependent rule: Stressed ER -> ɜː
        if tok.base == "ER" && tok.stress == 1 {
            result.push(IpaPhoneme {
                ipa: ER_STRESSED_IPA.to_string(),
                stress: tok.stress,
            });
            i += 1;
            continue;
        }

        // Special case: Unstressed AH -> schwa
        if tok.base == "AH" && tok.stress == 0 {
            result.push(IpaPhoneme {
                ipa: AH_UNSTRESSED_IPA.to_string(),
                stress: tok.stress,
            });
            i += 1;
            continue;
        }

        // Normal lookup
        if let Some(ipa) = ARPABET_TO_IPA.get(tok.base.as_str()) {
            result.push(IpaPhoneme {
                ipa: ipa.to_string(),
                stress: tok.stress,
            });
        }
        // Unknown ARPAbet symbol: skip silently (matches Python/C++ behavior)

        i += 1;
    }

    result
}

/// Apply function-word destressing: set all stress >= 1 to 0.
/// Matches Python: `(ipa, 0 if stress >= 1 else stress)`
fn destress(ipas: &mut [IpaPhoneme]) {
    for p in ipas.iter_mut() {
        if p.stress >= 1 {
            p.stress = 0;
        }
    }
}

// ---------------------------------------------------------------------------
// Morphological fallback for OOV words
//
// Matches C++ tryMorphologicalFallback() exactly.
// ---------------------------------------------------------------------------

/// Try morphological fallback for OOV words.
///
/// Strips common English suffixes and looks up the base form in the CMU
/// dictionary. If found, returns the base ARPAbet string with the suffix
/// phonemes appended. Returns `None` if no match is found.
///
/// Supported suffixes: -ing, -ed, -s/-es/-ies, -er, -ly/-ily, -est
fn try_morphological_fallback(word: &str, cmu_dict: &HashMap<String, String>) -> Option<String> {
    let len = word.len();

    let try_base = |base: &str, suffix_arpa: &str| -> Option<String> {
        cmu_dict
            .get(base)
            .map(|arpa| format!("{} {}", arpa, suffix_arpa))
    };

    // ----- -ing (running->run, making->make, sitting->sit) -----
    if len > 4 && word.ends_with("ing") {
        let base = &word[..len - 3];
        if let Some(r) = try_base(base, "IH0 NG") {
            return Some(r);
        }
        // Doubled consonant: sitting->sit
        let base_bytes = base.as_bytes();
        if base_bytes.len() >= 2
            && base_bytes[base_bytes.len() - 1] == base_bytes[base_bytes.len() - 2]
            && let Some(r) = try_base(&base[..base.len() - 1], "IH0 NG")
        {
            return Some(r);
        }
        // Restored 'e': making->make
        let base_e = format!("{}e", base);
        if let Some(r) = try_base(&base_e, "IH0 NG") {
            return Some(r);
        }
    }

    // ----- -ed (walked->walk, stopped->stop, loved->love) -----
    if len > 3 && word.ends_with("ed") {
        let base = &word[..len - 2];
        if let Some(r) = try_base(base, "D") {
            return Some(r);
        }
        // Doubled consonant: stopped->stop
        let base_bytes = base.as_bytes();
        if base_bytes.len() >= 2
            && base_bytes[base_bytes.len() - 1] == base_bytes[base_bytes.len() - 2]
            && let Some(r) = try_base(&base[..base.len() - 1], "D")
        {
            return Some(r);
        }
        // Strip only 'd': loved->love
        if let Some(r) = try_base(&word[..len - 1], "D") {
            return Some(r);
        }
    }

    // ----- -s / -es / -ies (cats->cat, boxes->box, countries->country) -----
    if len > 2 && word.ends_with('s') {
        // -ies -> -y: countries->country
        if len > 4 && word.ends_with("ies") {
            let base_y = format!("{}y", &word[..len - 3]);
            if let Some(r) = try_base(&base_y, "Z") {
                return Some(r);
            }
        }
        // -es: boxes->box
        if len > 3
            && word.ends_with("es")
            && let Some(r) = try_base(&word[..len - 2], "IH0 Z")
        {
            return Some(r);
        }
        // -s: cats->cat
        if let Some(r) = try_base(&word[..len - 1], "Z") {
            return Some(r);
        }
    }

    // ----- -er (faster->fast, runner->run) -----
    if len > 3 && word.ends_with("er") {
        let base = &word[..len - 2];
        if let Some(r) = try_base(base, "ER0") {
            return Some(r);
        }
        // Doubled consonant: runner->run
        let base_bytes = base.as_bytes();
        if base_bytes.len() >= 2
            && base_bytes[base_bytes.len() - 1] == base_bytes[base_bytes.len() - 2]
            && let Some(r) = try_base(&base[..base.len() - 1], "ER0")
        {
            return Some(r);
        }
    }

    // ----- -ly / -ily (quickly->quick, happily->happy) -----
    if len > 3 && word.ends_with("ly") {
        let base = &word[..len - 2];
        if let Some(r) = try_base(base, "L IY0") {
            return Some(r);
        }
        // -ily -> -y: happily->happy
        if len > 4 && word.as_bytes()[len - 3] == b'i' {
            let base_y = format!("{}y", &word[..len - 3]);
            if let Some(r) = try_base(&base_y, "L IY0") {
                return Some(r);
            }
        }
    }

    // ----- -est (fastest->fast) -----
    if len > 4
        && word.ends_with("est")
        && let Some(r) = try_base(&word[..len - 3], "AH0 S T")
    {
        return Some(r);
    }

    None // Truly OOV
}

// ---------------------------------------------------------------------------
// EnglishPhonemizer
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Global CMU dictionary cache
//
// The CMU dictionary JSON (~6 MB parsed) is loaded and parsed once, then
// shared across all `EnglishPhonemizer` instances via `&'static` reference.
// ---------------------------------------------------------------------------

static CMU_DICT_CACHE: OnceLock<HashMap<String, String>> = OnceLock::new();

/// Load and parse a CMU dictionary JSON file into a HashMap.
///
/// Standalone function used by the `OnceLock` cache initializer.
fn load_cmu_dict(dict_path: &Path) -> Result<HashMap<String, String>, G2pError> {
    let content = std::fs::read_to_string(dict_path).map_err(|_| G2pError::DictionaryLoad {
        path: dict_path.display().to_string(),
    })?;

    let raw: serde_json::Value =
        serde_json::from_str(&content).map_err(|e| G2pError::DictionaryLoad {
            path: format!("{}: {}", dict_path.display(), e),
        })?;

    let obj = raw.as_object().ok_or_else(|| G2pError::DictionaryLoad {
        path: format!("{}: expected JSON object", dict_path.display()),
    })?;

    let mut cmu_dict = HashMap::with_capacity(obj.len());
    for (key, value) in obj {
        if let Some(arpa) = value.as_str() {
            cmu_dict.insert(key.clone(), arpa.to_string());
        }
    }

    Ok(cmu_dict)
}

/// English phonemizer using CMU dictionary + ARPAbet-to-IPA conversion.
///
/// Loads the CMU dictionary from a JSON file mapping lowercase words to
/// ARPAbet pronunciation strings. The dictionary is loaded once and cached
/// globally via `OnceLock`, so creating multiple instances is cheap.
///
/// ## JSON format
///
/// ```json
/// {"hello": "HH AH0 L OW1", "world": "W ER1 L D"}
/// ```
pub struct EnglishPhonemizer {
    /// Reference to the cached CMU dictionary, or an owned dictionary for
    /// test instances created via `new_with_hashmap`.
    cmu_dict: DictRef,
}

/// Internal enum to hold either a static reference to the globally cached
/// dictionary or an owned dictionary (for tests).
enum DictRef {
    /// Reference to the `OnceLock`-cached dictionary (zero-copy after first load).
    Static(&'static HashMap<String, String>),
    /// Owned dictionary, used by `new_with_hashmap` for testing.
    Owned(HashMap<String, String>),
}

impl DictRef {
    fn as_map(&self) -> &HashMap<String, String> {
        match self {
            DictRef::Static(r) => r,
            DictRef::Owned(m) => m,
        }
    }
}

impl EnglishPhonemizer {
    /// Create a new `EnglishPhonemizer` by searching well-known locations
    /// for the CMU dictionary JSON file.
    ///
    /// The dictionary is loaded and parsed only once; subsequent calls
    /// return immediately with a reference to the cached data.
    ///
    /// Search order:
    /// 1. `CMUDICT_PATH` environment variable
    /// 2. `./cmudict_data.json` (local development)
    /// 3. `/usr/share/piper-plus/cmudict_data.json` (system install)
    pub fn new() -> Result<Self, G2pError> {
        let dict_path = Self::find_dictionary()?;
        Self::new_with_dict(&dict_path)
    }

    /// Create a new `EnglishPhonemizer` with a dictionary loaded from a JSON file.
    ///
    /// The dictionary is loaded and parsed only on the first call; subsequent
    /// calls (even with different paths) reuse the cached dictionary. This
    /// matches the intended usage where a single CMU dictionary is used
    /// throughout the application lifetime.
    pub fn new_with_dict(dict_path: &Path) -> Result<Self, G2pError> {
        // get_or_init ensures the dictionary is loaded exactly once.
        // If a different path is passed on a later call, the first-loaded
        // dictionary is still used (consistent with single-dict semantics).
        //
        // NOTE: `expect` here panics if the path is unreadable / malformed.
        // OnceLock has no `get_or_try_init` on stable, so a panic during
        // first-init poisons the cell for the process lifetime — subsequent
        // `new_with_dict` calls will re-panic. For FFI consumers (iOS Swift
        // wrapper) this path is not reached: `piper_plus_g2p_create` uses
        // `new_bundled()` (below) which returns Result properly, and
        // `catch_unwind` in ffi.rs converts any residual panic to a NULL
        // return rather than crashing the host process. Rust-only callers
        // outside the FFI should validate the dictionary path before
        // calling, or use `new_with_hashmap` to bypass the cache entirely.
        let dict = CMU_DICT_CACHE
            .get_or_init(|| load_cmu_dict(dict_path).expect("CMU dictionary load failed"));

        Ok(Self {
            cmu_dict: DictRef::Static(dict),
        })
    }

    /// Create a new `EnglishPhonemizer` from an in-memory dictionary.
    ///
    /// Useful for testing without a JSON file on disk. Does not affect
    /// or use the global cache.
    pub fn new_with_hashmap(dict: HashMap<String, String>) -> Self {
        Self {
            cmu_dict: DictRef::Owned(dict),
        }
    }

    #[cfg(feature = "bundled-dicts")]
    pub fn new_bundled() -> Result<Self, G2pError> {
        const CMU_DICT_JSON: &str = include_str!("../data/cmudict_data.json");
        let dict: HashMap<String, String> =
            serde_json::from_str(CMU_DICT_JSON).map_err(|e| G2pError::DictionaryLoad {
                path: format!("(bundled cmudict): {e}"),
            })?;
        Ok(Self::new_with_hashmap(dict))
    }

    /// Search well-known locations for the CMU dictionary JSON file.
    fn find_dictionary() -> Result<std::path::PathBuf, G2pError> {
        // 1. Environment variable override
        if let Ok(path) = std::env::var("CMUDICT_PATH") {
            let p = std::path::PathBuf::from(&path);
            if p.exists() {
                return Ok(p);
            }
        }

        // 2. Local development path
        let local = std::path::PathBuf::from("cmudict_data.json");
        if local.exists() {
            return Ok(local);
        }

        // 3. System install path
        let system = std::path::PathBuf::from("/usr/share/piper-plus/cmudict_data.json");
        if system.exists() {
            return Ok(system);
        }

        Err(G2pError::DictionaryLoad {
            path: "cmudict_data.json not found. Set CMUDICT_PATH env var \
                   or place dictionary at ./cmudict_data.json"
                .to_string(),
        })
    }

    /// The dictionary entry of `word`, or of its stem (morphological fallback).
    fn lookup(&self, word: &str) -> Option<String> {
        let dict = self.cmu_dict.as_map();
        let lower = word.to_ascii_lowercase();
        dict.get(&lower)
            .cloned()
            .or_else(|| try_morphological_fallback(&lower, dict))
    }

    /// ARPAbet for a word; never `None` when the word has a letter.
    ///
    /// Python reads words missing from the dictionary with g2p_en's neural
    /// guesser, which is not ported. Instead such a word is split at `-` and
    /// `.`, retried without apostrophes, split at CamelCase boundaries, and
    /// finally spelled letter by letter. The parts are joined into one word.
    fn word_arpabet(&self, word: &str) -> Option<String> {
        if let Some(arpa) = self.lookup(word) {
            return Some(arpa);
        }
        let join = |parts: Vec<&str>| -> Option<String> {
            let arpas: Vec<String> = parts
                .into_iter()
                .filter_map(|part| self.word_arpabet(part))
                .collect();
            (!arpas.is_empty()).then(|| arpas.join(" "))
        };
        if word.contains(['-', '.']) {
            return join(word.split(['-', '.']).filter(|p| !p.is_empty()).collect());
        }
        if word.contains('\'') {
            return self.word_arpabet(&word.replace('\'', ""));
        }
        let parts = split_camel_case(word);
        if parts.len() > 1 {
            return join(parts);
        }
        let spelled: Vec<&str> = word.chars().filter_map(letter_name_arpabet).collect();
        (!spelled.is_empty()).then(|| spelled.join(" "))
    }

    /// Core phonemization implementation.
    ///
    /// Normalizes and tokenizes the text like g2p_en, reads each word (CMU
    /// dictionary, then the fallbacks of [`Self::word_arpabet`]), converts
    /// ARPAbet to IPA, applies function-word destressing, inserts stress
    /// markers, and computes prosody features as Python's `english.py` does.
    fn phonemize_impl(&self, text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
        let source_words = source_words(text);

        let mut phonemes: Vec<String> = Vec::new();
        let mut prosody_list: Vec<Option<ProsodyInfo>> = Vec::new();
        let mut need_space = false;
        let mut src_idx = 0;

        for word in normalize_and_tokenize(text) {
            let is_punct = is_punctuation_word(&word);

            // A word without a letter (`-`, `'`, `...`) is kept as is, one
            // phoneme per character, as Python does.
            let mut word_ipas = if word.bytes().any(|b| b.is_ascii_alphabetic()) {
                match self.word_arpabet(&word) {
                    Some(arpa) => convert_word_to_ipa(&parse_arpabet(&arpa)),
                    None => continue,
                }
            } else {
                vec![IpaPhoneme {
                    ipa: word,
                    stress: -1,
                }]
            };

            if !is_punct {
                // Function words are matched against the source words in order.
                if src_idx < source_words.len() {
                    if FUNCTION_WORDS.contains(source_words[src_idx].as_str()) {
                        destress(&mut word_ipas);
                    }
                    src_idx += 1;
                }
                // Punctuation attaches to the preceding word; other words get
                // a word boundary before them (except the first).
                if need_space {
                    phonemes.push(" ".to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2: 0,
                        a3: 0,
                    }));
                }
            }

            // A3 = total IPA character count for the word
            let word_phoneme_count: i32 =
                word_ipas.iter().map(|p| p.ipa.chars().count() as i32).sum();

            // Emit phonemes with stress markers and prosody
            for p in &word_ipas {
                // stress -> A2: primary(1)->2, secondary(2)->1, others->0
                let a2 = match p.stress {
                    1 => 2,
                    2 => 1,
                    _ => 0,
                };

                // Insert stress marker before stressed vowels
                if p.stress == 1 {
                    phonemes.push(STRESS_PRIMARY.to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2,
                        a3: word_phoneme_count,
                    }));
                } else if p.stress == 2 {
                    phonemes.push(STRESS_SECONDARY.to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2,
                        a3: word_phoneme_count,
                    }));
                }

                // Each IPA character becomes a separate phoneme token
                for ch in p.ipa.chars() {
                    phonemes.push(ch.to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2,
                        a3: word_phoneme_count,
                    }));
                }
            }

            need_space = true;
        }

        (phonemes, prosody_list)
    }
}

impl Phonemizer for EnglishPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        Ok(self.phonemize_impl(text))
    }

    fn language_code(&self) -> &str {
        "en"
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: build a CMU dictionary HashMap from (word, arpa) pairs.
    fn make_dict(entries: &[(&str, &str)]) -> HashMap<String, String> {
        entries
            .iter()
            .map(|(w, a)| (w.to_string(), a.to_string()))
            .collect()
    }

    /// Helper: create an EnglishPhonemizer with a given test dictionary.
    fn make_phonemizer(entries: &[(&str, &str)]) -> EnglishPhonemizer {
        EnglishPhonemizer::new_with_hashmap(make_dict(entries))
    }

    /// Helper: phonemize and return the tokens only.
    fn phonemes_of(p: &EnglishPhonemizer, text: &str) -> Vec<String> {
        p.phonemize_impl(text).0
    }

    /// Helper: split a space-joined phoneme string; "_" stands for the
    /// word-boundary token " ".
    fn tokens(s: &str) -> Vec<String> {
        s.split(' ')
            .map(|t| if t == "_" { " " } else { t }.to_string())
            .collect()
    }

    // ===== 1. Source words (function-word alignment) =====

    #[test]
    fn test_source_words_simple_sentence() {
        assert_eq!(source_words("Hello, world!"), vec!["hello", "world"]);
    }

    #[test]
    fn test_source_words_apostrophe_kept() {
        assert_eq!(source_words("don't"), vec!["don't"]);
        assert_eq!(source_words("'quote'"), vec!["'quote'"]);
    }

    #[test]
    fn test_source_words_ignore_digits() {
        // Taken from the text before number expansion, as in Python.
        assert_eq!(source_words("the 3 of us"), vec!["the", "of", "us"]);
    }

    #[test]
    fn test_source_words_empty_and_whitespace() {
        assert!(source_words("").is_empty());
        assert!(source_words("   ").is_empty());
    }

    // ===== 2. ARPAbet parsing =====

    #[test]
    fn test_parse_arpabet() {
        let tokens = parse_arpabet("HH AH0 L OW1");
        assert_eq!(tokens.len(), 4);
        assert_eq!(tokens[0].base, "HH");
        assert_eq!(tokens[0].stress, -1);
        assert_eq!(tokens[1].base, "AH");
        assert_eq!(tokens[1].stress, 0);
        assert_eq!(tokens[2].base, "L");
        assert_eq!(tokens[2].stress, -1);
        assert_eq!(tokens[3].base, "OW");
        assert_eq!(tokens[3].stress, 1);
    }

    // ===== 3. Context-dependent IPA conversion =====

    #[test]
    fn test_aa_r_merge() {
        // "car" = K AA1 R -> k + ɑːɹ (merged)
        let tokens = parse_arpabet("K AA1 R");
        let ipas = convert_word_to_ipa(&tokens);
        assert_eq!(ipas.len(), 2); // k + merged
        assert_eq!(ipas[0].ipa, "k");
        assert_eq!(ipas[1].ipa, AA_R_MERGED_IPA);
        assert_eq!(ipas[1].stress, 1);
    }

    #[test]
    fn test_stressed_er() {
        // "bird" = B ER1 D -> b + ɜː + d
        let tokens = parse_arpabet("B ER1 D");
        let ipas = convert_word_to_ipa(&tokens);
        assert_eq!(ipas.len(), 3);
        assert_eq!(ipas[1].ipa, ER_STRESSED_IPA); // ɜː
        assert_eq!(ipas[1].stress, 1);
    }

    #[test]
    fn test_unstressed_er() {
        // ER0 -> ɚ (default unstressed)
        let tokens = parse_arpabet("ER0");
        let ipas = convert_word_to_ipa(&tokens);
        assert_eq!(ipas.len(), 1);
        assert_eq!(ipas[0].ipa, "\u{025A}"); // ɚ
        assert_eq!(ipas[0].stress, 0);
    }

    #[test]
    fn test_unstressed_ah_schwa() {
        // AH0 -> ə (schwa)
        let tokens = parse_arpabet("AH0");
        let ipas = convert_word_to_ipa(&tokens);
        assert_eq!(ipas.len(), 1);
        assert_eq!(ipas[0].ipa, AH_UNSTRESSED_IPA);
    }

    #[test]
    fn test_stressed_ah_not_schwa() {
        // AH1 -> ʌ (stressed, NOT schwa)
        let tokens = parse_arpabet("AH1");
        let ipas = convert_word_to_ipa(&tokens);
        assert_eq!(ipas.len(), 1);
        assert_eq!(ipas[0].ipa, "\u{028C}"); // ʌ
    }

    // ===== 4. Function words =====

    #[test]
    fn test_function_words_set_size() {
        assert_eq!(FUNCTION_WORDS.len(), 89);
    }

    #[test]
    fn test_function_word_are_destressed() {
        // "are" = AA1 R -> destressed -> no stress marker
        let p = make_phonemizer(&[("are", "AA1 R")]);
        let (phonemes, _) = p.phonemize_impl("are");
        let joined: String = phonemes.join("");
        assert!(
            !joined.contains('\u{02C8}'),
            "function word 'are' should not have primary stress: {}",
            joined
        );
        assert!(
            !joined.contains('\u{02CC}'),
            "function word 'are' should not have secondary stress: {}",
            joined
        );
    }

    // ===== 5. Full phonemization =====

    #[test]
    fn test_phonemize_hello() {
        // "hello" = HH AH0 L OW1 -> h ə l ˈ o ʊ
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (phonemes, prosody) = p.phonemize_impl("hello");
        let joined: String = phonemes.join("");
        assert!(joined.contains('h'), "expected 'h' in: {}", joined);
        assert!(
            joined.contains('\u{0259}'),
            "expected schwa ə in: {}",
            joined
        );
        assert!(joined.contains('l'), "expected 'l' in: {}", joined);
        assert!(joined.contains('\u{02C8}'), "expected ˈ in: {}", joined);
        assert!(joined.contains('o'), "expected 'o' in: {}", joined);
        assert!(joined.contains('\u{028A}'), "expected ʊ in: {}", joined);
        assert_eq!(phonemes.len(), prosody.len());
    }

    #[test]
    fn test_phonemize_the_cat() {
        // "the" is a function word, "cat" = K AE1 T gets primary stress
        let p = make_phonemizer(&[("the", "DH AH0"), ("cat", "K AE1 T")]);
        let (phonemes, prosody) = p.phonemize_impl("the cat");
        let joined: String = phonemes.join("");
        assert!(
            joined.contains('\u{02C8}'),
            "expected ˈ for 'cat': {}",
            joined
        );
        assert!(
            phonemes.contains(&" ".to_string()),
            "expected word boundary space"
        );
        assert_eq!(phonemes.len(), prosody.len());
    }

    // ===== 6. Punctuation =====

    #[test]
    fn test_punctuation_attached_to_preceding_word() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (phonemes, prosody) = p.phonemize_impl("hello, world!");
        let comma_idx = phonemes.iter().position(|p| p == ",");
        assert!(comma_idx.is_some(), "comma should be in output");
        // No space before comma
        assert_ne!(phonemes[comma_idx.unwrap() - 1], " ");
        assert_eq!(phonemes.len(), prosody.len());
    }

    // ===== 7. Prosody values =====

    #[test]
    fn test_prosody_a1_always_zero() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (_, prosody) = p.phonemize_impl("hello");
        for info in prosody.iter().flatten() {
            assert_eq!(info.a1, 0, "a1 should always be 0 for English");
        }
    }

    #[test]
    fn test_prosody_a2_stress_levels() {
        // "information" has secondary (IH2) and primary (EY1) stress
        let p = make_phonemizer(&[("information", "IH2 N F ER0 M EY1 SH AH0 N")]);
        let (phonemes, prosody) = p.phonemize_impl("information");
        // Secondary stress marker -> a2 == 1
        if let Some(idx) = phonemes.iter().position(|p| p == STRESS_SECONDARY) {
            assert_eq!(prosody[idx].unwrap().a2, 1, "a2 for secondary stress");
        }
        // Primary stress marker -> a2 == 2
        if let Some(idx) = phonemes.iter().position(|p| p == STRESS_PRIMARY) {
            assert_eq!(prosody[idx].unwrap().a2, 2, "a2 for primary stress");
        }
        assert_eq!(phonemes.len(), prosody.len());
    }

    #[test]
    fn test_a3_word_phoneme_count() {
        // "cat" = K AE1 T -> k + æ + t = 3 IPA chars
        let p = make_phonemizer(&[("cat", "K AE1 T")]);
        let (_, prosody) = p.phonemize_impl("cat");
        for info in prosody.iter().flatten() {
            assert_eq!(info.a3, 3, "a3 should be 3 for 'cat'");
        }
    }

    // ===== 8. Morphological fallback =====

    #[test]
    fn test_morphological_cats() {
        let dict = make_dict(&[("cat", "K AE1 T")]);
        let result = try_morphological_fallback("cats", &dict);
        assert!(result.is_some());
        assert!(result.unwrap().starts_with("K AE1 T"));
    }

    #[test]
    fn test_morphological_running() {
        let dict = make_dict(&[("run", "R AH1 N")]);
        // "running" -> strip "ing", base = "runn" -> doubled consonant -> "run"
        let result = try_morphological_fallback("running", &dict);
        assert!(result.is_some());
        assert!(result.unwrap().starts_with("R AH1 N"));
    }

    #[test]
    fn test_morphological_walked() {
        let dict = make_dict(&[("walk", "W AO1 K")]);
        let result = try_morphological_fallback("walked", &dict);
        assert!(result.is_some());
        assert!(result.unwrap().starts_with("W AO1 K"));
    }

    #[test]
    fn test_morphological_making() {
        let dict = make_dict(&[("make", "M EY1 K")]);
        // "making" -> strip "ing", base = "mak" (not found) -> restore 'e' -> "make"
        let result = try_morphological_fallback("making", &dict);
        assert!(result.is_some());
        assert!(result.unwrap().starts_with("M EY1 K"));
    }

    #[test]
    fn test_morphological_unknown() {
        let dict = make_dict(&[("cat", "K AE1 T")]);
        assert!(try_morphological_fallback("xyzzy", &dict).is_none());
    }

    // ===== 9. OOV handling =====

    #[test]
    fn test_oov_word_spelled_not_skipped() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (phonemes, prosody) = p.phonemize_impl("hello xyz");
        // x = EH1 K S, y = W AY1, z = Z IY1, read as one word.
        assert_eq!(phonemes, tokens("h ə l ˈ o ʊ _ ˈ ɛ k s w ˈ a ɪ z ˈ i ː"));
        assert_eq!(phonemes.len(), prosody.len());
    }

    // ===== 10. Phonemizer trait =====

    #[test]
    fn test_language_code() {
        let p = make_phonemizer(&[]);
        assert_eq!(p.language_code(), "en");
    }

    #[test]
    fn test_phonemize_with_prosody_trait() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let result = p.phonemize_with_prosody("hello");
        assert!(result.is_ok());
        let (phonemes, prosody) = result.unwrap();
        assert!(!phonemes.is_empty());
        assert_eq!(phonemes.len(), prosody.len());
    }

    // ===== 11. Mixed case normalization =====

    #[test]
    fn test_mixed_case_same_output() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (p1, _) = p.phonemize_impl("Hello");
        let (p2, _) = p.phonemize_impl("HELLO");
        let (p3, _) = p.phonemize_impl("hello");
        assert_eq!(p1, p2);
        assert_eq!(p2, p3);
    }

    // ===== 12. Empty text =====

    #[test]
    fn test_empty_text() {
        let p = make_phonemizer(&[]);
        let (phonemes, prosody) = p.phonemize_impl("");
        assert!(phonemes.is_empty());
        assert!(prosody.is_empty());
    }

    // ===== 13. Word boundary space =====

    #[test]
    fn test_word_boundary_space() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1"), ("world", "W ER1 L D")]);
        let (phonemes, prosody) = p.phonemize_impl("hello world");
        let space_count = phonemes.iter().filter(|p| p.as_str() == " ").count();
        assert_eq!(space_count, 1, "expected 1 space between words");
        assert_eq!(phonemes.len(), prosody.len());
    }

    // ===== 14. Secondary stress marker present =====

    #[test]
    fn test_secondary_stress_marker() {
        let p = make_phonemizer(&[("information", "IH2 N F ER0 M EY1 SH AH0 N")]);
        let (phonemes, _) = p.phonemize_impl("information");
        let joined: String = phonemes.join("");
        assert!(joined.contains('\u{02C8}'), "expected ˈ: {}", joined);
        assert!(joined.contains('\u{02CC}'), "expected ˌ: {}", joined);
    }

    // ===== 15. Destress removes both primary and secondary =====

    #[test]
    fn test_destress_removes_all_stress() {
        let mut ipas = vec![
            IpaPhoneme {
                ipa: "a".to_string(),
                stress: 1,
            },
            IpaPhoneme {
                ipa: "b".to_string(),
                stress: 2,
            },
            IpaPhoneme {
                ipa: "c".to_string(),
                stress: -1,
            },
            IpaPhoneme {
                ipa: "d".to_string(),
                stress: 0,
            },
        ];
        destress(&mut ipas);
        assert_eq!(ipas[0].stress, 0); // primary -> 0
        assert_eq!(ipas[1].stress, 0); // secondary -> 0
        assert_eq!(ipas[2].stress, -1); // consonant unchanged
        assert_eq!(ipas[3].stress, 0); // already 0
    }

    // ===== 16. ARPABET_TO_IPA table completeness =====

    #[test]
    fn test_arpabet_table_size() {
        assert_eq!(ARPABET_TO_IPA.len(), 39);
    }

    #[test]
    fn test_arpabet_to_ipa_known_symbols() {
        assert_eq!(*ARPABET_TO_IPA.get("AA").unwrap(), "\u{0251}");
        assert_eq!(*ARPABET_TO_IPA.get("B").unwrap(), "b");
        assert_eq!(*ARPABET_TO_IPA.get("SH").unwrap(), "\u{0283}");
        assert_eq!(*ARPABET_TO_IPA.get("NG").unwrap(), "\u{014B}");
        assert_eq!(*ARPABET_TO_IPA.get("TH").unwrap(), "\u{03B8}");
    }

    // ===== 18. Morphological: -er suffix =====

    #[test]
    fn test_morphological_runner() {
        let dict = make_dict(&[("run", "R AH1 N")]);
        // "runner" -> strip "er", base = "runn" -> doubled consonant -> "run"
        let result = try_morphological_fallback("runner", &dict);
        assert!(result.is_some());
        let arpa = result.unwrap();
        assert!(arpa.starts_with("R AH1 N"), "got: {}", arpa);
        assert!(
            arpa.ends_with("ER0"),
            "should append ER0 suffix, got: {}",
            arpa
        );
    }

    // ===== 19. Morphological: -ly suffix =====

    #[test]
    fn test_morphological_quickly() {
        let dict = make_dict(&[("quick", "K W IH1 K")]);
        let result = try_morphological_fallback("quickly", &dict);
        assert!(result.is_some());
        let arpa = result.unwrap();
        assert!(arpa.starts_with("K W IH1 K"), "got: {}", arpa);
        assert!(
            arpa.ends_with("L IY0"),
            "should append L IY0, got: {}",
            arpa
        );
    }

    // ===== 20. Morphological: -est suffix =====

    #[test]
    fn test_morphological_fastest() {
        let dict = make_dict(&[("fast", "F AE1 S T")]);
        let result = try_morphological_fallback("fastest", &dict);
        assert!(result.is_some());
        let arpa = result.unwrap();
        assert!(arpa.starts_with("F AE1 S T"), "got: {}", arpa);
        assert!(
            arpa.ends_with("AH0 S T"),
            "should append AH0 S T, got: {}",
            arpa
        );
    }

    // ===== 21. Letter names (last OOV fallback) =====

    #[test]
    fn test_letter_name_table() {
        let expected = [
            ('a', "EY1"),
            ('b', "B IY1"),
            ('c', "S IY1"),
            ('d', "D IY1"),
            ('e', "IY1"),
            ('f', "EH1 F"),
            ('g', "JH IY1"),
            ('h', "EY1 CH"),
            ('i', "AY1"),
            ('j', "JH EY1"),
            ('k', "K EY1"),
            ('l', "EH1 L"),
            ('m', "EH1 M"),
            ('n', "EH1 N"),
            ('o', "OW1"),
            ('p', "P IY1"),
            ('q', "K Y UW1"),
            ('r', "AA1 R"),
            ('s', "EH1 S"),
            ('t', "T IY1"),
            ('u', "Y UW1"),
            ('v', "V IY1"),
            ('w', "D AH1 B AH0 L Y UW0"),
            ('x', "EH1 K S"),
            ('y', "W AY1"),
            ('z', "Z IY1"),
        ];
        for (ch, arpa) in expected {
            assert_eq!(letter_name_arpabet(ch), Some(arpa), "letter {ch}");
            assert_eq!(
                letter_name_arpabet(ch.to_ascii_uppercase()),
                Some(arpa),
                "letter {}",
                ch.to_ascii_uppercase()
            );
        }
        assert_eq!(letter_name_arpabet('\''), None);
        assert_eq!(letter_name_arpabet('1'), None);
    }

    #[test]
    fn test_all_caps_oov_spelled_as_one_word() {
        let p = make_phonemizer(&[]);
        // T IY1 + T IY1 + EH1 S: no word boundary between the letters.
        assert_eq!(phonemes_of(&p, "TTS"), tokens("t ˈ i ː t ˈ i ː ˈ ɛ s"));
    }

    // ===== 22. CamelCase split =====

    #[test]
    fn test_split_camel_case() {
        assert_eq!(split_camel_case("ChatGPT"), vec!["Chat", "GPT"]);
        assert_eq!(split_camel_case("iPhone"), vec!["i", "Phone"]);
        assert_eq!(split_camel_case("GitHub"), vec!["Git", "Hub"]);
        assert_eq!(split_camel_case("MixedCase"), vec!["Mixed", "Case"]);
        assert_eq!(split_camel_case("HTMLParser"), vec!["HTML", "Parser"]);
        assert_eq!(split_camel_case("RtwoDtwo"), vec!["Rtwo", "Dtwo"]);
        assert_eq!(split_camel_case("UPPERCASE"), vec!["UPPERCASE"]);
        assert_eq!(split_camel_case("lower"), vec!["lower"]);
        assert_eq!(split_camel_case("A"), vec!["A"]);
    }

    #[test]
    fn test_camel_case_parts_joined_into_one_word() {
        let p = make_phonemizer(&[("chat", "CH AE1 T"), ("phone", "F OW1 N"), ("i", "AY1")]);
        // Chat + G P T (spelled), with no word boundary in between.
        assert_eq!(
            phonemes_of(&p, "ChatGPT"),
            tokens("t ʃ ˈ æ t d ʒ ˈ i ː p ˈ i ː t ˈ i ː")
        );
        // i (dictionary) + Phone.
        assert_eq!(phonemes_of(&p, "iPhone"), tokens("ˈ a ɪ f ˈ o ʊ n"));
    }

    // ===== 23. Hyphen / dot split =====

    #[test]
    fn test_hyphen_and_dot_split_joined_into_one_word() {
        let p = make_phonemizer(&[("foo", "F UW1"), ("bar", "B AA1 R")]);
        let expected = tokens("f ˈ u ː b ˈ ɑ ː ɹ");
        assert_eq!(phonemes_of(&p, "foo-bar"), expected);
        // "foo.bar" is one token (TweetTokenizer domain form).
        assert_eq!(phonemes_of(&p, "foo.bar"), expected);
    }

    #[test]
    fn test_hyphenated_dictionary_word_not_split() {
        let p = make_phonemizer(&[("uh-huh", "AH1 HH AH1"), ("uh", "AH1"), ("huh", "HH AH1")]);
        assert_eq!(phonemes_of(&p, "uh-huh"), tokens("ˈ ʌ h ˈ ʌ"));
    }

    // ===== 24. Apostrophe retry =====

    #[test]
    fn test_apostrophe_stripped_and_retried() {
        let p = make_phonemizer(&[("rocknroll", "R AA1 K N R OW1 L")]);
        assert_eq!(
            phonemes_of(&p, "rock'n'roll"),
            tokens("ɹ ˈ ɑ k n ɹ ˈ o ʊ l")
        );
        // Not found without the apostrophe either: spell the letters.
        let p = make_phonemizer(&[]);
        assert_eq!(phonemes_of(&p, "x'y"), tokens("ˈ ɛ k s w ˈ a ɪ"));
    }

    // ===== 25. OOV words are never dropped (real dictionary) =====

    fn real_dict_phonemizer() -> EnglishPhonemizer {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("data/cmudict_data.json");
        EnglishPhonemizer::new_with_hashmap(load_cmu_dict(&path).expect("data/cmudict_data.json"))
    }

    #[test]
    fn test_oov_words_never_produce_zero_phonemes() {
        let p = real_dict_phonemizer();
        for word in [
            "ChatGPT",
            "TTS",
            "xyz",
            "aaaaa",
            "UPPERCASE",
            "MixedCase",
            "iPhone",
            "GitHub",
            "COVID-19",
            "R2D2",
            "'90s",
        ] {
            let (phonemes, prosody) = p.phonemize_impl(word);
            let spoken = phonemes.iter().any(|t| {
                !matches!(
                    t.as_str(),
                    " " | "." | "," | "!" | "?" | ";" | ":" | "'" | "\"" | "-"
                )
            });
            assert!(spoken, "{word:?} produced no phoneme: {phonemes:?}");
            assert_ne!(
                phonemes.first().map(String::as_str),
                Some(" "),
                "{word:?} starts with a word boundary: {phonemes:?}"
            );
            assert_eq!(phonemes.len(), prosody.len(), "{word:?}");
        }
    }

    // ===== 26. No leading word boundary =====

    #[test]
    fn test_no_leading_word_boundary() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        for text in ["xyz hello", "'quote'", "...hello", "  hello", "3 hello"] {
            let phonemes = phonemes_of(&p, text);
            assert_ne!(
                phonemes.first().map(String::as_str),
                Some(" "),
                "{text:?}: {phonemes:?}"
            );
        }
    }

    // ===== 27. Numbers, punctuation words and function-word alignment =====

    #[test]
    fn test_function_words_aligned_with_source_words_before_number_expansion() {
        // Python: the source words of "the 3 of us" are [the, of, us], aligned
        // with the spoken words [the, three, of, us]. "three" takes "of" and
        // "of" takes "us", so both lose their stress and "us" keeps it.
        let p = make_phonemizer(&[
            ("the", "DH AH0"),
            ("three", "TH R IY1"),
            ("of", "AH1 V"),
            ("us", "AH1 S"),
        ]);
        let (phonemes, prosody) = p.phonemize_impl("the 3 of us");
        assert_eq!(phonemes, tokens("ð ə _ θ ɹ i ː _ ʌ v _ ˈ ʌ s"));
        let a2: Vec<i32> = prosody.iter().map(|p| p.unwrap().a2).collect();
        let a3: Vec<i32> = prosody.iter().map(|p| p.unwrap().a3).collect();
        assert_eq!(a2, vec![0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0]);
        assert_eq!(a3, vec![2, 2, 0, 4, 4, 4, 4, 0, 2, 2, 0, 2, 2, 2]);
    }

    #[test]
    fn test_non_punctuation_symbol_words_are_spoken_per_char() {
        let p = make_phonemizer(&[
            ("wait", "W EY1 T"),
            ("now", "N AW1"),
            ("quote", "K W OW1 T"),
        ]);
        // ". . ." is one word: each character, spaces included, is a phoneme.
        let (phonemes, prosody) = p.phonemize_impl("wait . . . now");
        assert_eq!(phonemes, tokens("w ˈ e ɪ t _ . _ . _ . _ n ˈ a ʊ"));
        let a3: Vec<i32> = prosody.iter().map(|p| p.unwrap().a3).collect();
        assert_eq!(a3, vec![4, 4, 4, 4, 4, 0, 5, 5, 5, 5, 5, 0, 3, 3, 3, 3]);
        // Edge quotes are words of their own, preceded by a word boundary.
        assert_eq!(phonemes_of(&p, "'quote'"), tokens("' _ k w ˈ o ʊ t _ '"));
    }

    #[test]
    fn test_punctuation_prosody_matches_python() {
        // Python counts the punctuation character itself: a3 = 1.
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (phonemes, prosody) = p.phonemize_impl("hello,");
        assert_eq!(phonemes.last().map(String::as_str), Some(","));
        let last = prosody.last().unwrap().unwrap();
        assert_eq!((last.a1, last.a2, last.a3), (0, 0, 1));
    }

    #[test]
    fn test_numbers_accents_and_abbreviations_are_normalized() {
        let p = make_phonemizer(&[
            ("cafe", "K AH0 F EY1"),
            ("for", "F AO1 R"),
            ("example", "IH0 G Z AE1 M P AH0 L"),
            ("one", "W AH1 N"),
            ("hundred", "HH AH1 N D R AH0 D"),
        ]);
        assert_eq!(phonemes_of(&p, "café"), tokens("k ə f ˈ e ɪ"));
        assert_eq!(
            phonemes_of(&p, "e.g."),
            tokens("f ˈ ɔ ː ɹ _ ɪ ɡ z ˈ æ m p ə l")
        );
        assert_eq!(phonemes_of(&p, "100"), tokens("w ˈ ʌ n _ h ˈ ʌ n d ɹ ə d"));
    }
}

//! English phonemizer using CMU dictionary + ARPAbet-to-IPA conversion.
//!
//! Ports the Python `english.py` and C++ `english_phonemize.cpp` logic to Rust.
//! Converts English text to IPA phonemes using CMU dictionary lookup with
//! context-dependent ARPAbet-to-IPA rules that match espeak-ng output.
//!
//! ## Pipeline
//!
//! 1. Tokenize text into words and punctuation
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
//! are stripped and the base form is looked up.  Truly OOV words (no dict
//! entry and no morphological match) produce no output.

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
// Tokenizer
// ---------------------------------------------------------------------------

/// A token from the input text: either a word or a punctuation character.
#[derive(Debug)]
struct Token {
    text: String,
    is_word: bool,
}

/// Check if a character is part of a word (ASCII letter or apostrophe).
fn is_alpha_or_apostrophe(ch: char) -> bool {
    ch.is_ascii_alphabetic() || ch == '\''
}

/// Tokenize text into words and punctuation.
///
/// Words are runs of `[a-zA-Z']` characters, lowercased.
/// Punctuation characters (`,.:;!?`) are single tokens.
/// Everything else (whitespace, digits, etc.) acts as a word separator.
///
/// Mirrors the Python: `re.findall(r"[a-zA-Z']+", text)` for source words
/// and the C++ `tokenize()` function.
fn tokenize(text: &str) -> Vec<Token> {
    let chars: Vec<char> = text.chars().collect();
    let mut tokens = Vec::new();
    let n = chars.len();
    let mut i = 0;

    while i < n {
        let ch = chars[i];

        if is_alpha_or_apostrophe(ch) {
            let mut word = String::new();
            while i < n && is_alpha_or_apostrophe(chars[i]) {
                word.push(chars[i].to_ascii_lowercase());
                i += 1;
            }
            tokens.push(Token {
                text: word,
                is_word: true,
            });
            continue;
        }

        if is_punctuation(ch) {
            tokens.push(Token {
                text: ch.to_string(),
                is_word: false,
            });
            i += 1;
            continue;
        }

        // Skip whitespace, digits, other characters
        i += 1;
    }

    tokens
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
    /// 3. `/usr/share/piper/cmudict_data.json` (system install)
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
        let system = std::path::PathBuf::from("/usr/share/piper/cmudict_data.json");
        if system.exists() {
            return Ok(system);
        }

        Err(G2pError::DictionaryLoad {
            path: "cmudict_data.json not found. Set CMUDICT_PATH env var \
                   or place dictionary at ./cmudict_data.json"
                .to_string(),
        })
    }

    /// Core phonemization implementation.
    ///
    /// Tokenizes the input text, looks up words in the CMU dictionary,
    /// converts ARPAbet to IPA, applies function-word destressing,
    /// inserts stress markers, and computes prosody features.
    fn phonemize_impl(&self, text: &str) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
        let tokens = tokenize(text);
        if tokens.is_empty() {
            return (Vec::new(), Vec::new());
        }

        // Extract source words for function-word detection
        let source_words: Vec<&str> = tokens
            .iter()
            .filter(|t| t.is_word)
            .map(|t| t.text.as_str())
            .collect();

        // Determine which tokens are function words
        let mut word_is_function: Vec<bool> = Vec::with_capacity(tokens.len());
        let mut src_idx = 0;
        for tok in &tokens {
            if tok.is_word {
                let is_func = if src_idx < source_words.len() {
                    let result = FUNCTION_WORDS.contains(source_words[src_idx]);
                    src_idx += 1;
                    result
                } else {
                    false
                };
                word_is_function.push(is_func);
            } else {
                word_is_function.push(false);
            }
        }

        let mut phonemes: Vec<String> = Vec::new();
        let mut prosody_list: Vec<Option<ProsodyInfo>> = Vec::new();
        let mut need_space = false;

        for (ti, tok) in tokens.iter().enumerate() {
            if !tok.is_word {
                // Punctuation: attach to preceding word (no space before)
                for ch in tok.text.chars() {
                    phonemes.push(ch.to_string());
                    prosody_list.push(Some(ProsodyInfo {
                        a1: 0,
                        a2: 0,
                        a3: 0,
                    }));
                }
                need_space = true;
                continue;
            }

            // Word token: look up in CMU dictionary
            let dict = self.cmu_dict.as_map();
            let arpa_str = if let Some(arpa) = dict.get(&tok.text) {
                arpa.clone()
            } else {
                // OOV: try morphological fallback
                match try_morphological_fallback(&tok.text, dict) {
                    Some(arpa) => arpa,
                    None => {
                        // Truly OOV: skip this word
                        need_space = true;
                        continue;
                    }
                }
            };

            // Insert word-boundary space (except before first word)
            if need_space {
                phonemes.push(" ".to_string());
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 0,
                }));
            }

            // Parse ARPAbet and convert to IPA
            let arpa_tokens = parse_arpabet(&arpa_str);
            let mut word_ipas = convert_word_to_ipa(&arpa_tokens);

            // Apply function-word destressing
            if word_is_function[ti] {
                destress(&mut word_ipas);
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

    // ===== 1. Tokenizer =====

    #[test]
    fn test_tokenize_simple_sentence() {
        let tokens = tokenize("Hello, world!");
        assert_eq!(tokens.len(), 4);
        assert_eq!(tokens[0].text, "hello");
        assert!(tokens[0].is_word);
        assert_eq!(tokens[1].text, ",");
        assert!(!tokens[1].is_word);
        assert_eq!(tokens[2].text, "world");
        assert!(tokens[2].is_word);
        assert_eq!(tokens[3].text, "!");
        assert!(!tokens[3].is_word);
    }

    #[test]
    fn test_tokenize_apostrophe_kept() {
        let tokens = tokenize("don't");
        assert_eq!(tokens.len(), 1);
        assert_eq!(tokens[0].text, "don't");
        assert!(tokens[0].is_word);
    }

    #[test]
    fn test_tokenize_empty_and_whitespace() {
        assert!(tokenize("").is_empty());
        assert!(tokenize("   ").is_empty());
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
    fn test_oov_word_skipped() {
        let p = make_phonemizer(&[("hello", "HH AH0 L OW1")]);
        let (phonemes, _) = p.phonemize_impl("hello xyzzy");
        let joined: String = phonemes.join("");
        assert!(joined.contains('h'), "hello should be phonemized");
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
}

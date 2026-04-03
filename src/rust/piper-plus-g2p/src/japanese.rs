//! Japanese phonemizer using jpreprocess (NAIST-JDIC).
//!
//! Ports the Python `japanese.py` Kurihara method to Rust.
//! Converts Japanese text to phoneme tokens with prosody marks
//! using OpenJTalk-style fullcontext labels via jpreprocess.
//!
//! ## Prosody marks (Kurihara method)
//!
//! | Symbol | Meaning                                       |
//! |--------|-----------------------------------------------|
//! | `^`    | Beginning of sentence                         |
//! | `$`    | End of sentence (declarative)                 |
//! | `?`    | End of sentence (generic question)             |
//! | `?!`   | End of sentence (emphatic question)            |
//! | `?.`   | End of sentence (neutral/rhetorical question)  |
//! | `?~`   | End of sentence (tag/confirmation question)    |
//! | `_`    | Short pause (pau)                             |
//! | `#`    | Accent phrase boundary                        |
//! | `[`    | Rising-pitch mark (accent phrase head)         |
//! | `]`    | Falling-pitch mark (accent nucleus)            |

use std::collections::HashSet;
use std::sync::LazyLock;

use regex::Regex;

use crate::custom_dict::CustomDictionary;
use crate::error::G2pError;
use crate::phonemizer::{Phonemizer, ProsodyInfo};
use crate::token_map::token_to_pua;

// ---------------------------------------------------------------------------
// Compiled regex patterns for fullcontext label parsing
// ---------------------------------------------------------------------------

/// Extract current phoneme from label: `-([^+]+)+`
static RE_PHONEME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"-([^+]+)\+").expect("RE_PHONEME"));

/// Extract A1 (relative accent position) from label: `/A:([\d-]+)+`
static RE_A1: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"/A:([\d-]+)\+").expect("RE_A1"));

/// Extract A2 (forward position in accent phrase): `+([0-9]+)+`
static RE_A2: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\+([0-9]+)\+").expect("RE_A2"));

/// Extract A3 (backward position / phrase length): `+([0-9]+)/`
static RE_A3: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\+([0-9]+)/").expect("RE_A3"));

// ---------------------------------------------------------------------------
// Consonant sets for N variant classification
// ---------------------------------------------------------------------------

/// Bilabial consonants: N before these becomes N_m.
static BILABIAL: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| ["m", "my", "b", "by", "p", "py"].into_iter().collect());

/// Alveolar consonants: N before these becomes N_n.
static ALVEOLAR: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    ["n", "ny", "t", "ty", "d", "dy", "ts", "ch"]
        .into_iter()
        .collect()
});

/// Velar consonants: N before these becomes N_ng.
static VELAR: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| ["k", "ky", "kw", "g", "gy", "gw"].into_iter().collect());

/// Tokens that should be skipped when looking for the next phoneme
/// (prosody markers, pause markers, sentence boundaries).
static SKIP_TOKENS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    ["_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"]
        .into_iter()
        .collect()
});

// ---------------------------------------------------------------------------
// Question type detection (Issue #204)
// ---------------------------------------------------------------------------

/// Detect the question type marker from the trailing punctuation of `text`.
///
/// Returns one of:
/// - `"?!"` : Emphatic question (ends with ?! / ！？ / ？！)
/// - `"?."` : Neutral/rhetorical question (ends with ?. / 。？ / ？。)
/// - `"?~"` : Tag/confirmation question (ends with ?~ / ～？ / ？～)
/// - `"?"`  : Generic question (ends with ? / ？)
/// - `"$"`  : Declarative (non-question)
pub fn get_question_type(text: &str) -> &'static str {
    let stripped = text.trim();

    // Multi-char patterns first (check longer patterns before shorter)
    if stripped.ends_with("?!")
        || stripped.ends_with("\u{FF01}\u{FF1F}") // ！？
        || stripped.ends_with("\u{FF1F}\u{FF01}")
    // ？！
    {
        return "?!";
    }
    if stripped.ends_with("?.")
        || stripped.ends_with("\u{3002}\u{FF1F}") // 。？
        || stripped.ends_with("\u{FF1F}\u{3002}")
    // ？。
    {
        return "?.";
    }
    if stripped.ends_with("?~")
        || stripped.ends_with("\u{FF5E}\u{FF1F}") // ～？
        || stripped.ends_with("\u{FF1F}\u{FF5E}")
    // ？～
    {
        return "?~";
    }

    // Single ? fallback
    if stripped.ends_with('?') || stripped.ends_with('\u{FF1F}') {
        return "?";
    }

    "$" // Not a question
}

// ---------------------------------------------------------------------------
// Context-dependent N variant rules (Issue #207)
// ---------------------------------------------------------------------------

/// Apply context-dependent rules to replace `"N"` with specific variants.
///
/// Japanese "ん" (N) has different pronunciations depending on the following
/// phoneme:
///
/// | Variant    | Condition                               | Example   |
/// |------------|-----------------------------------------|-----------|
/// | `N_m`      | before m/b/p/my/by/py (bilabial)        | さんぽ    |
/// | `N_n`      | before n/t/d/ny/ty/dy/ts/ch (alveolar)  | あんない  |
/// | `N_ng`     | before k/g/ky/kw/gy/gw (velar)          | ぎんこう  |
/// | `N_uvular` | at phrase end or before vowels/other     | ほん      |
///
/// Prosody markers (`_`, `#`, `[`, `]`, `^`, `$`, `?`, etc.) are skipped
/// when looking ahead for the next phoneme.
pub fn apply_n_phoneme_rules(tokens: &mut [String]) {
    // Collect (index, variant) pairs first to avoid borrow issues.
    let replacements: Vec<(usize, &str)> = tokens
        .iter()
        .enumerate()
        .filter(|(_, t)| t.as_str() == "N")
        .map(|(i, _)| {
            // Look ahead to find next actual phoneme (skip prosody markers)
            let next_phoneme = tokens[i + 1..]
                .iter()
                .find(|t| !SKIP_TOKENS.contains(t.as_str()))
                .map(|s| s.as_str());

            let variant = match next_phoneme {
                None => "N_uvular",
                Some(ph) if BILABIAL.contains(ph) => "N_m",
                Some(ph) if ALVEOLAR.contains(ph) => "N_n",
                Some(ph) if VELAR.contains(ph) => "N_ng",
                Some(_) => "N_uvular",
            };
            (i, variant)
        })
        .collect();

    for (idx, variant) in replacements {
        tokens[idx] = variant.to_string();
    }
}

// ---------------------------------------------------------------------------
// PUA mapping for multi-char tokens
// ---------------------------------------------------------------------------

/// Map multi-character tokens to single PUA codepoints where possible.
///
/// Tokens that have a PUA mapping (e.g. `"a:"` -> U+E000, `"N_m"` -> U+E019)
/// are replaced with the single-char representation; others are left as-is.
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
// Label parsing helpers
// ---------------------------------------------------------------------------

/// Parse the phoneme string from a fullcontext label line.
fn parse_phoneme(label_str: &str) -> Option<String> {
    RE_PHONEME
        .captures(label_str)
        .and_then(|c| c.get(1))
        .map(|m| m.as_str().to_string())
}

/// Parse A1 value (relative accent position) from a label line.
fn parse_a1(label_str: &str) -> Option<i32> {
    RE_A1
        .captures(label_str)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().parse::<i32>().ok())
}

/// Parse A2 value (forward position in accent phrase) from a label line.
fn parse_a2(label_str: &str) -> Option<i32> {
    RE_A2
        .captures(label_str)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().parse::<i32>().ok())
}

/// Parse A3 value (phrase length) from a label line.
fn parse_a3(label_str: &str) -> Option<i32> {
    RE_A3
        .captures(label_str)
        .and_then(|c| c.get(1))
        .and_then(|m| m.as_str().parse::<i32>().ok())
}

// ---------------------------------------------------------------------------
// Core phonemization (Kurihara method)
// ---------------------------------------------------------------------------

/// Convert fullcontext label strings into phoneme tokens with prosody info.
///
/// This is the Kurihara method that inserts prosody marks based on the
/// A1/A2/A3 accent fields extracted from the labels.
///
/// Prosody mark insertion rules:
/// - `]` when a1==0 && a2_next == a2+1 (accent nucleus / falling pitch)
/// - `#` when a2==a3 && a2_next==1 (accent phrase boundary)
/// - `[` when a2==1 && a2_next==2 (rising pitch mark)
fn labels_to_tokens_with_prosody(
    label_strings: &[String],
    text: &str,
) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
    let mut tokens: Vec<String> = Vec::new();
    let mut prosody_info: Vec<Option<ProsodyInfo>> = Vec::new();
    let num_labels = label_strings.len();

    for (idx, label) in label_strings.iter().enumerate() {
        let phoneme = match parse_phoneme(label) {
            Some(p) => p,
            None => continue,
        };

        // Beginning / end silence handling
        if phoneme == "sil" {
            if idx == 0 {
                tokens.push("^".to_string());
                prosody_info.push(None);
            } else if idx == num_labels - 1 {
                let q = get_question_type(text);
                tokens.push(q.to_string());
                prosody_info.push(None);
            }
            continue;
        }

        // Short pause
        if phoneme == "pau" {
            tokens.push("_".to_string());
            prosody_info.push(None);
            continue;
        }

        // Add phoneme token
        tokens.push(phoneme);

        // Extract A1/A2/A3 values
        let a1_opt = parse_a1(label);
        let a2_opt = parse_a2(label);
        let a3_opt = parse_a3(label);

        if let (Some(a1), Some(a2), Some(a3)) = (a1_opt, a2_opt, a3_opt) {
            prosody_info.push(Some(ProsodyInfo { a1, a2, a3 }));

            // Look-ahead: fetch a2 from the next label
            let a2_next = if idx < num_labels - 1 {
                parse_a2(&label_strings[idx + 1]).unwrap_or(-1)
            } else {
                -1
            };

            // Insert accent nucleus mark "]" at the descending point.
            // Kurihara rule: a1==0 && a2_next == a2 + 1
            if a1 == 0 && a2_next == a2 + 1 {
                tokens.push("]".to_string());
                prosody_info.push(None);
            }

            // Insert accent phrase boundary "#" when current mora is last in phrase
            if a2 == a3 && a2_next == 1 {
                tokens.push("#".to_string());
                prosody_info.push(None);
            }

            // Insert rising mark "[" at phrase head (a2==1) when next mora is 2
            if a2 == 1 && a2_next == 2 {
                tokens.push("[".to_string());
                prosody_info.push(None);
            }
        } else {
            prosody_info.push(None);
        }
    }

    // Apply context-dependent N phoneme rules
    apply_n_phoneme_rules(&mut tokens);

    // Map multi-character tokens to PUA single chars
    let mapped = map_sequence(tokens);

    (mapped, prosody_info)
}

// ---------------------------------------------------------------------------
// JapanesePhonemizer
// ---------------------------------------------------------------------------

/// Japanese phonemizer using jpreprocess for grapheme-to-phoneme conversion.
///
/// Wraps jpreprocess with the NAIST-JDIC dictionary to extract fullcontext
/// labels, then applies the Kurihara method to produce phoneme token
/// sequences with prosody marks and A1/A2/A3 prosody information.
pub struct JapanesePhonemizer {
    njd: jpreprocess::JPreprocess<jpreprocess::DefaultFetcher>,
    dictionary: Option<CustomDictionary>,
}

impl JapanesePhonemizer {
    /// Create a new `JapanesePhonemizer` with the bundled NAIST-JDIC dictionary.
    ///
    /// Requires the `naist-jdic` feature flag.
    #[cfg(feature = "naist-jdic")]
    pub fn new_bundled() -> Result<Self, G2pError> {
        let config = jpreprocess::JPreprocessConfig {
            dictionary: jpreprocess::SystemDictionaryConfig::Bundled(
                jpreprocess::kind::JPreprocessDictionaryKind::NaistJdic,
            ),
            user_dictionary: None,
        };

        let njd = jpreprocess::JPreprocess::from_config(config)
            .map_err(|e| G2pError::JPreprocessInit(e.to_string()))?;

        Ok(Self {
            njd,
            dictionary: None,
        })
    }

    /// Create a new `JapanesePhonemizer` with automatic dictionary search.
    ///
    /// Searches for the jpreprocess dictionary in well-known locations:
    /// 1. `JPREPROCESS_DICT` environment variable (explicit path)
    /// 2. `./jpreprocess-naist-jdic/` (local development)
    /// 3. `/usr/share/jpreprocess/naist-jdic/` (system install)
    pub fn new() -> Result<Self, G2pError> {
        let dict_path = Self::find_dictionary()?;
        Self::new_with_dict(&dict_path)
    }

    /// Create a new `JapanesePhonemizer` with a dictionary loaded from a file path.
    pub fn new_with_dict(dict_path: &std::path::Path) -> Result<Self, G2pError> {
        let config = jpreprocess::JPreprocessConfig {
            dictionary: jpreprocess::SystemDictionaryConfig::File(dict_path.to_path_buf()),
            user_dictionary: None,
        };
        let njd = jpreprocess::JPreprocess::from_config(config)
            .map_err(|e| G2pError::JPreprocessInit(e.to_string()))?;

        Ok(Self {
            njd,
            dictionary: None,
        })
    }

    /// Create a `JapanesePhonemizer` from a bincode-serialized jpreprocess dictionary.
    ///
    /// Used by WASM for external dictionary loading (fetched from URL, cached in IndexedDB).
    pub fn new_from_serialized_dict(data: &[u8]) -> Result<Self, G2pError> {
        let dictionary: jpreprocess::Dictionary =
            bincode::deserialize(data).map_err(|e| G2pError::DictionaryLoad {
                path: format!("(serialized, {} bytes): {e}", data.len()),
            })?;
        let njd = jpreprocess::JPreprocess::with_dictionaries(dictionary, None);
        Ok(Self {
            njd,
            dictionary: None,
        })
    }

    /// Search well-known locations for the jpreprocess NAIST-JDIC dictionary.
    fn find_dictionary() -> Result<std::path::PathBuf, G2pError> {
        // 1. Environment variable override
        if let Ok(path) = std::env::var("JPREPROCESS_DICT") {
            let p = std::path::PathBuf::from(path);
            if p.exists() {
                return Ok(p);
            }
        }

        // 2. Local development path
        let local = std::path::PathBuf::from("jpreprocess-naist-jdic");
        if local.exists() {
            return Ok(local);
        }

        // 3. System install path
        let system = std::path::PathBuf::from("/usr/share/jpreprocess/naist-jdic");
        if system.exists() {
            return Ok(system);
        }

        Err(G2pError::JPreprocessInit(
            "NAIST-JDIC dictionary not found. Set JPREPROCESS_DICT env var \
             or place dictionary at ./jpreprocess-naist-jdic/"
                .to_string(),
        ))
    }

    /// Set a custom dictionary for pre-processing text before phonemization.
    pub fn set_dictionary(&mut self, dict: CustomDictionary) {
        self.dictionary = Some(dict);
    }

    /// Extract fullcontext labels from text using jpreprocess,
    /// returning them as string representations for regex-based parsing.
    fn extract_labels(&self, text: &str) -> Result<Vec<String>, G2pError> {
        let labels = self
            .njd
            .extract_fullcontext(text)
            .map_err(|e| G2pError::Phonemize(e.to_string()))?;

        Ok(labels.iter().map(|l| l.to_string()).collect())
    }
}

impl Phonemizer for JapanesePhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        let mut input = text.to_string();

        // Apply custom dictionary if present
        if let Some(ref dict) = self.dictionary {
            input = dict.apply_to_text(&input);
        }

        let label_strings = self.extract_labels(&input)?;
        Ok(labels_to_tokens_with_prosody(&label_strings, text))
    }

    fn language_code(&self) -> &str {
        "ja"
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: build a Vec<String> from a slice of &str.
    fn vec_s(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    // ===== Question type detection (Issue #204) =====

    #[test]
    fn test_question_type_declarative_period() {
        assert_eq!(get_question_type("こんにちは。"), "$");
    }

    #[test]
    fn test_question_type_declarative_plain() {
        assert_eq!(get_question_type("何もない"), "$");
    }

    #[test]
    fn test_question_type_declarative_whitespace() {
        assert_eq!(get_question_type("  "), "$");
    }

    #[test]
    fn test_question_type_generic_ascii() {
        assert_eq!(get_question_type("本当?"), "?");
    }

    #[test]
    fn test_question_type_generic_fullwidth() {
        assert_eq!(get_question_type("本当？"), "?");
    }

    #[test]
    fn test_question_type_emphatic_ascii() {
        assert_eq!(get_question_type("本当?!"), "?!");
    }

    #[test]
    fn test_question_type_emphatic_fullwidth() {
        assert_eq!(get_question_type("本当！？"), "?!");
        assert_eq!(get_question_type("本当？！"), "?!");
    }

    #[test]
    fn test_question_type_neutral_ascii() {
        assert_eq!(get_question_type("そう?."), "?.");
    }

    #[test]
    fn test_question_type_neutral_fullwidth() {
        assert_eq!(get_question_type("そう。？"), "?.");
        assert_eq!(get_question_type("そう？。"), "?.");
    }

    #[test]
    fn test_question_type_tag_ascii() {
        assert_eq!(get_question_type("行くよね?~"), "?~");
    }

    #[test]
    fn test_question_type_tag_fullwidth() {
        assert_eq!(get_question_type("行くよね～？"), "?~");
        assert_eq!(get_question_type("行くよね？～"), "?~");
    }

    #[test]
    fn test_question_type_with_trailing_whitespace() {
        assert_eq!(get_question_type("本当？  "), "?");
        assert_eq!(get_question_type("本当?!  "), "?!");
    }

    // ===== N variant rules (Issue #207) =====

    #[test]
    fn test_n_before_bilabial_p() {
        // さんぽ: N -> N_m before "p"
        let mut tokens = vec_s(&["^", "s", "a", "N", "p", "o", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_m");
    }

    #[test]
    fn test_n_before_bilabial_m() {
        let mut tokens = vec_s(&["^", "a", "N", "m", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_m");
    }

    #[test]
    fn test_n_before_bilabial_b() {
        let mut tokens = vec_s(&["^", "a", "N", "b", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_m");
    }

    #[test]
    fn test_n_before_alveolar_n() {
        // あんない: N -> N_n before "n"
        let mut tokens = vec_s(&["^", "a", "N", "n", "a", "i", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_n");
    }

    #[test]
    fn test_n_before_alveolar_t() {
        let mut tokens = vec_s(&["^", "a", "N", "t", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_n");
    }

    #[test]
    fn test_n_before_alveolar_ts() {
        let mut tokens = vec_s(&["^", "N", "ts", "u", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_alveolar_ch() {
        let mut tokens = vec_s(&["^", "N", "ch", "i", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_alveolar_ny() {
        let mut tokens = vec_s(&["^", "N", "ny", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_alveolar_dy() {
        let mut tokens = vec_s(&["^", "N", "dy", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_velar_k() {
        // ぎんこう: N -> N_ng before "k"
        let mut tokens = vec_s(&["^", "g", "i", "N", "k", "o", "o", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_ng");
    }

    #[test]
    fn test_n_before_velar_g() {
        let mut tokens = vec_s(&["^", "a", "N", "g", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_ng");
    }

    #[test]
    fn test_n_before_velar_ky() {
        let mut tokens = vec_s(&["^", "a", "N", "ky", "o", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_ng");
    }

    #[test]
    fn test_n_before_velar_kw() {
        let mut tokens = vec_s(&["^", "N", "kw", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_velar_gw() {
        let mut tokens = vec_s(&["^", "N", "gw", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_velar_gy() {
        let mut tokens = vec_s(&["^", "N", "gy", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_palatalized_bilabial_my() {
        let mut tokens = vec_s(&["^", "N", "my", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_before_palatalized_bilabial_by() {
        let mut tokens = vec_s(&["^", "N", "by", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_before_palatalized_bilabial_py() {
        let mut tokens = vec_s(&["^", "N", "py", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_at_end_of_phrase() {
        // ほん: N -> N_uvular at end
        let mut tokens = vec_s(&["^", "h", "o", "N", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_uvular");
    }

    #[test]
    fn test_n_before_vowel() {
        // N before a vowel -> N_uvular
        let mut tokens = vec_s(&["^", "N", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_fricative_s() {
        // N before "s" -> N_uvular (not in any set)
        let mut tokens = vec_s(&["^", "N", "s", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_h() {
        let mut tokens = vec_s(&["^", "N", "h", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_r() {
        let mut tokens = vec_s(&["^", "N", "r", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_w() {
        let mut tokens = vec_s(&["^", "N", "w", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_skips_prosody_marks() {
        // N followed by prosody marks then "k" -> N_ng
        let mut tokens = vec_s(&["^", "N", "#", "[", "k", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_skips_pause() {
        // N followed by "_" then "p" -> N_m
        let mut tokens = vec_s(&["^", "N", "_", "p", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_multiple_n_replacements() {
        let mut tokens = vec_s(&["^", "N", "k", "a", "#", "N", "p", "o", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng"); // before k
        assert_eq!(tokens[5], "N_m"); // before p
    }

    #[test]
    fn test_non_n_tokens_unchanged() {
        let mut tokens = vec_s(&["^", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "$"]);
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "k"); // unchanged
        assert_eq!(tokens[6], "ch"); // unchanged
        assert_eq!(tokens[3], "N_n"); // N before "n"
    }

    // ===== PUA mapping =====

    #[test]
    fn test_map_sequence_long_vowels() {
        let tokens = vec_s(&["a:", "i:", "u:", "e:", "o:"]);
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E000}");
        assert_eq!(mapped[1], "\u{E001}");
        assert_eq!(mapped[2], "\u{E002}");
        assert_eq!(mapped[3], "\u{E003}");
        assert_eq!(mapped[4], "\u{E004}");
    }

    #[test]
    fn test_map_sequence_n_variants() {
        let tokens = vec_s(&["N_m", "N_n", "N_ng", "N_uvular"]);
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E019}");
        assert_eq!(mapped[1], "\u{E01A}");
        assert_eq!(mapped[2], "\u{E01B}");
        assert_eq!(mapped[3], "\u{E01C}");
    }

    #[test]
    fn test_map_sequence_question_marks() {
        let tokens = vec_s(&["?!", "?.", "?~"]);
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E016}");
        assert_eq!(mapped[1], "\u{E017}");
        assert_eq!(mapped[2], "\u{E018}");
    }

    #[test]
    fn test_map_sequence_palatalized_consonants() {
        let tokens = vec_s(&["ky", "gy", "ny", "ch", "ts", "sh"]);
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E006}"); // ky
        assert_eq!(mapped[1], "\u{E008}"); // gy
        assert_eq!(mapped[2], "\u{E013}"); // ny (E013 per Python token_mapper.py)
        assert_eq!(mapped[3], "\u{E00E}"); // ch
        assert_eq!(mapped[4], "\u{E00F}"); // ts
        assert_eq!(mapped[5], "\u{E010}"); // sh
    }

    #[test]
    fn test_map_sequence_cl() {
        let tokens = vec_s(&["cl"]);
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E005}");
    }

    #[test]
    fn test_map_sequence_single_char_preserved() {
        let tokens = vec_s(&["a", "k", "^", "$", "?", "s", "N", "_", "#"]);
        let mapped = map_sequence(tokens);
        assert_eq!(
            mapped,
            vec_s(&["a", "k", "^", "$", "?", "s", "N", "_", "#"])
        );
    }

    #[test]
    fn test_map_sequence_mixed() {
        let tokens = vec_s(&["^", "k", "o", "N_ng", "#", "a:", "$"]);
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "^");
        assert_eq!(mapped[1], "k");
        assert_eq!(mapped[2], "o");
        assert_eq!(mapped[3], "\u{E01B}"); // N_ng
        assert_eq!(mapped[4], "#");
        assert_eq!(mapped[5], "\u{E000}"); // a:
        assert_eq!(mapped[6], "$");
    }

    // ===== Label parsing =====

    #[test]
    fn test_parse_phoneme_sil() {
        let label = "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx";
        assert_eq!(parse_phoneme(label), Some("sil".to_string()));
    }

    #[test]
    fn test_parse_phoneme_regular() {
        let label = "xx^s-a+N=xx/A:0+2+5/B:xx-xx_xx/C:xx_xx+xx";
        assert_eq!(parse_phoneme(label), Some("a".to_string()));
    }

    #[test]
    fn test_parse_phoneme_no_match() {
        let label = "no phoneme here";
        assert_eq!(parse_phoneme(label), None);
    }

    #[test]
    fn test_parse_a1_negative() {
        let label = "xx/A:-3+1+7/B:xx";
        assert_eq!(parse_a1(label), Some(-3));
    }

    #[test]
    fn test_parse_a1_zero() {
        let label = "xx/A:0+2+5/B:xx";
        assert_eq!(parse_a1(label), Some(0));
    }

    #[test]
    fn test_parse_a1_positive() {
        let label = "xx/A:4+2+5/B:xx";
        assert_eq!(parse_a1(label), Some(4));
    }

    #[test]
    fn test_parse_a2() {
        let label = "xx/A:-3+1+7/B:xx";
        assert_eq!(parse_a2(label), Some(1));
    }

    #[test]
    fn test_parse_a3() {
        let label = "xx/A:-3+1+7/B:xx";
        assert_eq!(parse_a3(label), Some(7));
    }

    #[test]
    fn test_parse_a_values_large() {
        let label = "xx/A:-12+15+20/B:xx";
        assert_eq!(parse_a1(label), Some(-12));
        assert_eq!(parse_a2(label), Some(15));
        assert_eq!(parse_a3(label), Some(20));
    }

    // ===== labels_to_tokens_with_prosody =====

    #[test]
    fn test_bos_eos_from_sil() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, prosody) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert_eq!(tokens[0], "^");
        assert_eq!(tokens.last().unwrap(), "$");
        assert!(prosody[0].is_none());
        assert!(prosody.last().unwrap().is_none());
    }

    #[test]
    fn test_question_ending_in_labels() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "本当？");
        assert_eq!(tokens.last().unwrap(), "?");
    }

    #[test]
    fn test_emphatic_question_ending_pua_mapped() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "本当?!");
        // "?!" gets PUA-mapped to U+E016
        assert_eq!(tokens.last().unwrap(), "\u{E016}");
    }

    #[test]
    fn test_pau_becomes_underscore() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-pau+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert_eq!(tokens[1], "_");
    }

    #[test]
    fn test_accent_nucleus_mark_inserted() {
        // a1==0 and a2_next == a2+1 should insert "]"
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:0+2+5/B:xx".to_string(),
            "xx^xx-o+xx=xx/A:1+3+5/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert!(tokens.contains(&"]".to_string()));
    }

    #[test]
    fn test_phrase_boundary_mark_inserted() {
        // a2==a3 and a2_next==1 should insert "#"
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:1+3+3/B:xx".to_string(),
            "xx^xx-a+xx=xx/A:0+1+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert!(tokens.contains(&"#".to_string()));
    }

    #[test]
    fn test_rising_mark_inserted() {
        // a2==1 and a2_next==2 should insert "["
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:1+1+3/B:xx".to_string(),
            "xx^xx-o+xx=xx/A:0+2+3/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert!(tokens.contains(&"[".to_string()));
    }

    #[test]
    fn test_prosody_info_attached_to_phonemes_only() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:-2+1+5/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (_, prosody) = labels_to_tokens_with_prosody(&labels, "テスト。");
        // Index 0 = "^" (None), index 1 = "k" (Some), index 2 = "$" (None)
        assert!(prosody[0].is_none());
        let pi = prosody[1].unwrap();
        assert_eq!(pi.a1, -2);
        assert_eq!(pi.a2, 1);
        assert_eq!(pi.a3, 5);
        assert!(prosody[2].is_none());
    }

    #[test]
    fn test_prosody_marks_have_none_prosody() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:0+2+5/B:xx".to_string(),
            "xx^xx-o+xx=xx/A:1+3+5/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, prosody) = labels_to_tokens_with_prosody(&labels, "テスト。");
        // Find "]" and verify its prosody is None
        if let Some(idx) = tokens.iter().position(|t| t == "]") {
            assert!(prosody[idx].is_none());
        }
    }

    #[test]
    fn test_n_variant_applied_in_label_flow() {
        // N followed by "k" should become N_ng (PUA mapped to U+E01B)
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-N+xx=xx/A:1+1+2/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:0+2+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert!(
            tokens.contains(&"\u{E01B}".to_string()),
            "Expected N_ng PUA char in tokens: {:?}",
            tokens
        );
    }

    #[test]
    fn test_mid_sil_is_skipped() {
        // sil in the middle (not first or last) should be skipped entirely
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:1+1+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(), // middle
            "xx^xx-a+xx=xx/A:0+1+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert_eq!(tokens[0], "^");
        assert_eq!(*tokens.last().unwrap(), "$");
        let bos_count = tokens.iter().filter(|t| t.as_str() == "^").count();
        assert_eq!(bos_count, 1);
    }

    #[test]
    fn test_tokens_and_prosody_same_length() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:0+1+3/B:xx".to_string(),
            "xx^xx-o+xx=xx/A:1+2+3/B:xx".to_string(),
            "xx^xx-N+xx=xx/A:2+3+3/B:xx".to_string(),
            "xx^xx-pau+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-n+xx=xx/A:0+1+2/B:xx".to_string(),
            "xx^xx-i+xx=xx/A:1+2+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, prosody) = labels_to_tokens_with_prosody(&labels, "テスト。");
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens ({}) and prosody ({}) length mismatch.\ntokens: {:?}",
            tokens.len(),
            prosody.len(),
            tokens,
        );
    }

    // ===== Integration: combined N variant + PUA + prosody marks =====

    #[test]
    fn test_full_pipeline_with_n_and_prosody() {
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:1+1+2/B:xx".to_string(),
            "xx^xx-o+xx=xx/A:0+2+2/B:xx".to_string(),
            // Next label starts new phrase: a2_next=1
            "xx^xx-N+xx=xx/A:1+1+3/B:xx".to_string(),
            "xx^xx-k+xx=xx/A:0+2+3/B:xx".to_string(),
            "xx^xx-a+xx=xx/A:1+3+3/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, prosody) = labels_to_tokens_with_prosody(&labels, "テスト。");

        // Lengths must match
        assert_eq!(tokens.len(), prosody.len());

        // N before "k" should become N_ng (PUA U+E01B)
        assert!(
            tokens.contains(&"\u{E01B}".to_string()),
            "Expected N_ng PUA char in tokens: {:?}",
            tokens
        );

        // Should start with "^" and end with "$"
        assert_eq!(tokens[0], "^");
        assert_eq!(*tokens.last().unwrap(), "$");
    }

    #[test]
    fn test_full_pipeline_long_vowel_mapped() {
        // Verify that long vowels in label output get PUA-mapped
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-a:+xx=xx/A:0+1+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        // "a:" should be PUA-mapped to U+E000
        assert!(
            tokens.contains(&"\u{E000}".to_string()),
            "Expected a: PUA char in tokens: {:?}",
            tokens
        );
    }

    #[test]
    fn test_full_pipeline_cl_mapped() {
        // Verify that "cl" (geminate) gets PUA-mapped
        let labels = vec![
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
            "xx^xx-cl+xx=xx/A:1+1+2/B:xx".to_string(),
            "xx^xx-t+xx=xx/A:0+2+2/B:xx".to_string(),
            "xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx".to_string(),
        ];
        let (tokens, _) = labels_to_tokens_with_prosody(&labels, "テスト。");
        // "cl" -> U+E005
        assert!(
            tokens.contains(&"\u{E005}".to_string()),
            "Expected cl PUA char in tokens: {:?}",
            tokens
        );
    }

    #[test]
    fn test_empty_labels() {
        let labels: Vec<String> = vec![];
        let (tokens, prosody) = labels_to_tokens_with_prosody(&labels, "");
        assert!(tokens.is_empty());
        assert!(prosody.is_empty());
    }
}

//! Multilingual phonemizer for code-switching text across N languages.
//!
//! Generalizes the concept of bilingual phonemization to support arbitrary
//! language combinations. Detects language segments via Unicode ranges,
//! delegates to language-specific phonemizers, and returns unified phoneme IDs.
//!
//! Port of the Python `multilingual.py`.

use std::collections::{HashMap, HashSet};
use std::sync::{Mutex, OnceLock};

use super::token_map::token_to_pua;
use super::{Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::config::PhonemeIdMap;
use crate::error::PiperError;

// ---------------------------------------------------------------------------
// UnicodeLanguageDetector
// ---------------------------------------------------------------------------

/// Detect language from Unicode character ranges.
///
/// Supports CJK disambiguation (JA vs ZH) by checking for kana presence.
/// Latin characters are mapped to a configurable default language.
pub struct UnicodeLanguageDetector {
    languages: HashSet<String>,
    default_latin_language: String,
    has_ja: bool,
    has_zh: bool,
    has_ko: bool,
    /// Whether Swedish detection post-pass is enabled.
    /// True when "sv" is in `languages` AND there are 2+ Latin-script languages.
    detect_swedish: bool,
}

// ---------------------------------------------------------------------------
// Swedish detection constants
// ---------------------------------------------------------------------------

/// Swedish-specific characters not used by EN/ES/PT/FR.
/// ä (U+00E4), ö (U+00F6), å (U+00E5) and their uppercase variants.
const SWEDISH_CHARS: [char; 6] = [
    '\u{00E4}', // ä
    '\u{00F6}', // ö
    '\u{00E5}', // å
    '\u{00C4}', // Ä
    '\u{00D6}', // Ö
    '\u{00C5}', // Å
];

/// Swedish function words for word-level disambiguation.
/// These are highly distinctive and do not appear in EN/ES/PT/FR.
/// 45 words, matching the Python `_SWEDISH_FUNCTION_WORDS`.
const SWEDISH_FUNCTION_WORDS: [&str; 45] = [
    "och", "att", "jag", "det", "den", "inte", "som", "han", "hon", "var", "har", "kan", "ska",
    "med", "för", "sig", "sin", "min", "din", "vill", "från", "när", "här", "där", "också", "alla",
    "denna", "efter", "eller", "under", "utan", "mycket", "mellan", "genom", "bara", "sedan",
    "redan", "aldrig", "alltid", "igen", "något", "några", "varje", "vilken", "vilket",
];

impl UnicodeLanguageDetector {
    /// Create a new detector for the given set of languages.
    ///
    /// `default_latin_language` controls which language Latin-script
    /// characters (A-Z, a-z, accented Latin) are assigned to.
    pub fn new(languages: &[String], default_latin_language: &str) -> Self {
        let lang_set: HashSet<String> = languages.iter().cloned().collect();
        let has_sv = lang_set.contains("sv");
        // Latin-script languages in piper-plus
        let latin_count = ["en", "es", "pt", "fr", "sv"]
            .iter()
            .filter(|l| lang_set.contains(**l))
            .count();
        Self {
            has_ja: lang_set.contains("ja"),
            has_zh: lang_set.contains("zh"),
            has_ko: lang_set.contains("ko"),
            detect_swedish: has_sv && latin_count >= 2,
            default_latin_language: default_latin_language.to_string(),
            languages: lang_set,
        }
    }

    /// Detect language for a single character.
    ///
    /// `context_has_kana` is used for CJK ideograph disambiguation: if the
    /// surrounding text contains kana, CJK ideographs are classified as
    /// Japanese rather than Chinese.
    ///
    /// Returns `None` for neutral characters (whitespace, digits,
    /// ASCII punctuation, etc.).
    pub fn detect_char(&self, ch: char, context_has_kana: bool) -> Option<&str> {
        let cp = ch as u32;

        // 1. Hiragana (U+3040-309F), Katakana (U+30A0-30FF),
        //    Katakana Phonetic Extensions (U+31F0-31FF)
        if (0x3040..=0x30FF).contains(&cp) || (0x31F0..=0x31FF).contains(&cp) {
            return if self.has_ja { Some("ja") } else { None };
        }

        // 2. Hangul Syllables (U+AC00-D7AF), Jamo (U+1100-11FF),
        //    Compatibility Jamo (U+3130-318F)
        if (0xAC00..=0xD7AF).contains(&cp)
            || (0x1100..=0x11FF).contains(&cp)
            || (0x3130..=0x318F).contains(&cp)
        {
            return if self.has_ko { Some("ko") } else { None };
        }

        // 3. CJK Unified Ideographs (U+4E00-9FFF), Extension A (U+3400-4DBF),
        //    Compatibility Ideographs (U+F900-FAFF)
        if (0x4E00..=0x9FFF).contains(&cp)
            || (0x3400..=0x4DBF).contains(&cp)
            || (0xF900..=0xFAFF).contains(&cp)
        {
            if self.has_ja && self.has_zh {
                return if context_has_kana {
                    Some("ja")
                } else {
                    Some("zh")
                };
            }
            if self.has_ja {
                return Some("ja");
            }
            if self.has_zh {
                return Some("zh");
            }
            return None;
        }

        // 4. Fullwidth Latin letters: U+FF21-FF3A (A-Z), U+FF41-FF5A (a-z)
        if (0xFF21..=0xFF3A).contains(&cp) || (0xFF41..=0xFF5A).contains(&cp) {
            return if self.languages.contains(&self.default_latin_language) {
                Some(&self.default_latin_language)
            } else {
                None
            };
        }

        // 5. CJK punctuation (U+3000-303F) and fullwidth forms
        //    (U+FF00-FF20, U+FF3B-FF40, U+FF5B-FFEF),
        //    excluding fullwidth Latin letters handled above.
        if (0x3000..=0x303F).contains(&cp)
            || (0xFF00..=0xFF20).contains(&cp)
            || (0xFF3B..=0xFF40).contains(&cp)
            || (0xFF5B..=0xFFEF).contains(&cp)
        {
            return if self.has_ja { Some("ja") } else { None };
        }

        // 6. Latin characters: A-Z, a-z, and extended Latin with diacritics
        //    (U+00C0-00D6, U+00D8-00F6, U+00F8-00FF)
        //    Excludes multiplication sign (U+00D7) and division sign (U+00F7).
        if ch.is_ascii_alphabetic()
            || (0x00C0..=0x00D6).contains(&cp)
            || (0x00D8..=0x00F6).contains(&cp)
            || (0x00F8..=0x00FF).contains(&cp)
        {
            return if self.languages.contains(&self.default_latin_language) {
                Some(&self.default_latin_language)
            } else {
                None
            };
        }

        // 7. Everything else: digits, ASCII punctuation, whitespace → neutral
        None
    }

    /// Check if text contains any Hiragana or Katakana characters.
    pub fn has_kana(&self, text: &str) -> bool {
        text.chars().any(|ch| {
            let cp = ch as u32;
            (0x3040..=0x30FF).contains(&cp) || (0x31F0..=0x31FF).contains(&cp)
        })
    }
}

// ---------------------------------------------------------------------------
// segment_text
// ---------------------------------------------------------------------------

/// Split text into `(language, segment_text)` pairs using Unicode detection.
///
/// Neutral characters (whitespace, digits, punctuation) are absorbed into
/// the preceding language segment. If no language-specific characters are
/// found (e.g., text is only digits), falls back to `default_latin_language`.
pub fn segment_text(text: &str, detector: &UnicodeLanguageDetector) -> Vec<(String, String)> {
    if text.trim().is_empty() {
        return Vec::new();
    }

    let context_has_kana = detector.has_kana(text);

    let mut segments: Vec<(String, String)> = Vec::new();
    let mut current_lang: Option<&str> = None;
    let mut current_chars = String::new();

    for ch in text.chars() {
        let lang = detector.detect_char(ch, context_has_kana);

        if let Some(detected) = lang {
            if let Some(prev) = current_lang
                && detected != prev
            {
                // Language changed — flush the current segment
                segments.push((prev.to_string(), std::mem::take(&mut current_chars)));
                // current_chars is now empty String (no allocation needed for clear)
            }
            current_lang = Some(detected);
        }
        // If lang is None (neutral char), keep current_lang unchanged
        // so the neutral char gets absorbed into the current segment.
        current_chars.push(ch);
    }

    // Flush remaining characters
    if let Some(lang) = current_lang
        && !current_chars.is_empty()
    {
        segments.push((lang.to_string(), current_chars));
    }

    // Fallback: if no language-specific chars were detected, use default
    if segments.is_empty() && !text.trim().is_empty() {
        segments.push((detector.default_latin_language.clone(), text.to_string()));
    }

    // Post-pass: segment-level Swedish detection within Latin segments.
    if detector.detect_swedish {
        segments = refine_latin_segments_for_swedish(segments, &detector.default_latin_language);
    }

    segments
}

/// Lazily-initialized `HashSet` for O(1) Swedish function-word lookups.
fn swedish_function_word_set() -> &'static HashSet<&'static str> {
    static SET: OnceLock<HashSet<&'static str>> = OnceLock::new();
    SET.get_or_init(|| SWEDISH_FUNCTION_WORDS.iter().copied().collect())
}

/// Re-classify Latin segments as Swedish based on indicator count.
///
/// For each segment assigned to the default Latin language, count Swedish
/// indicators (ä/ö/å characters + function words). If at least one
/// indicator is found, the entire segment is re-classified as Swedish.
/// This avoids over-fragmentation from word-by-word splitting.
fn refine_latin_segments_for_swedish(
    segments: Vec<(String, String)>,
    default_latin: &str,
) -> Vec<(String, String)> {
    // If the default Latin language IS Swedish, no refinement is needed.
    if default_latin == "sv" {
        return segments;
    }

    let func_words = swedish_function_word_set();

    segments
        .into_iter()
        .map(|(lang, text)| {
            if lang != default_latin {
                return (lang, text);
            }

            let mut sv_score: usize = 0;
            for word in text.split_whitespace() {
                let word_lower = word
                    .trim_matches(|c: char| matches!(c, '.' | ',' | ';' | ':' | '!' | '?'))
                    .to_lowercase();
                if word_lower.is_empty() {
                    continue;
                }
                // Check for Swedish-specific characters (ä/ö/å) or function words
                if word_lower.chars().any(|c| SWEDISH_CHARS.contains(&c))
                    || func_words.contains(word_lower.as_str())
                {
                    sv_score += 1;
                }
            }

            if sv_score >= 1 {
                ("sv".to_string(), text)
            } else {
                (lang, text)
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// default_post_process_ids
// ---------------------------------------------------------------------------

/// Shared BOS/EOS/padding post-processing (espeak-ng compatible).
///
/// Used by EN, ZH, KO, ES, FR, PT phonemizers and by
/// `MultilingualPhonemizer`. Inserts pad tokens between every phoneme ID
/// and wraps with BOS (^) / EOS markers.
///
/// The `eos_token` parameter allows a dynamic EOS (e.g., `"?"` or PUA
/// question markers from Japanese). Falls back to `"$"` when the
/// requested token is not found in the map.
pub fn default_post_process_ids(
    ids: Vec<i64>,
    prosody: Vec<Option<ProsodyFeature>>,
    id_map: &PhonemeIdMap,
    eos_token: &str,
) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
    let pad_ids = id_map.get("_").cloned().unwrap_or_else(|| vec![0]);
    let bos_ids = id_map.get("^");
    let eos_ids = id_map.get(eos_token).or_else(|| id_map.get("$"));

    // Intersperse: pad after every phoneme, but skip after existing pad
    // tokens to match the training data padding scheme.
    let mut padded_ids = Vec::with_capacity(ids.len() * 2);
    let mut padded_prosody = Vec::with_capacity(ids.len() * 2);

    for (id, p) in ids.iter().zip(prosody.iter()) {
        padded_ids.push(*id);
        padded_prosody.push(*p);
        if !pad_ids.contains(id) {
            padded_ids.extend_from_slice(&pad_ids);
            padded_prosody.extend(std::iter::repeat_n(None, pad_ids.len()));
        }
    }

    // Wrap with BOS
    if let Some(bos) = bos_ids {
        let mut with_bos_ids = Vec::with_capacity(bos.len() + 1 + padded_ids.len());
        with_bos_ids.extend_from_slice(bos);
        with_bos_ids.push(pad_ids[0]);
        with_bos_ids.extend_from_slice(&padded_ids);
        let mut with_bos_prosody = Vec::with_capacity(bos.len() + 1 + padded_prosody.len());
        with_bos_prosody.extend(std::iter::repeat_n(None, bos.len() + 1));
        with_bos_prosody.extend_from_slice(&padded_prosody);
        padded_ids = with_bos_ids;
        padded_prosody = with_bos_prosody;
    }

    // Append EOS
    if let Some(eos) = eos_ids {
        padded_ids.extend_from_slice(eos);
        padded_prosody.extend(std::iter::repeat_n(None, eos.len()));
    }

    (padded_ids, padded_prosody)
}

// ---------------------------------------------------------------------------
// PassthroughPhonemizer
// ---------------------------------------------------------------------------

/// A simple phonemizer that performs character-level tokenization.
///
/// Used for languages without a native Rust phonemizer (en, zh, ko, es, fr, pt).
/// Each character becomes a separate token. Relies on the phoneme_id_map from
/// config.json for ID conversion.
pub struct PassthroughPhonemizer {
    lang_code: String,
}

impl PassthroughPhonemizer {
    /// Create a new passthrough phonemizer for the given language code.
    pub fn new(lang_code: &str) -> Self {
        Self {
            lang_code: lang_code.to_string(),
        }
    }
}

impl Phonemizer for PassthroughPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        let tokens: Vec<String> = text.chars().map(|c| c.to_string()).collect();
        let prosody: Vec<Option<ProsodyInfo>> = vec![None; tokens.len()];
        Ok((tokens, prosody))
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
        default_post_process_ids(ids, prosody, id_map, "$")
    }

    fn language_code(&self) -> &str {
        &self.lang_code
    }
}

// ---------------------------------------------------------------------------
// MultilingualPhonemizer
// ---------------------------------------------------------------------------

/// Phonemizer that handles code-switching between N languages.
///
/// Segments the input text by language using Unicode ranges, delegates to
/// language-specific phonemizers, and concatenates results in a unified
/// phoneme space.
///
/// `last_eos` is set by `phonemize_with_prosody` and read by
/// `post_process_ids`. A `Mutex` provides interior mutability while
/// satisfying the `Send + Sync` bounds required by the `Phonemizer` trait.
pub struct MultilingualPhonemizer {
    languages: Vec<String>,
    default_latin_language: String,
    detector: UnicodeLanguageDetector,
    phonemizers: HashMap<String, Box<dyn Phonemizer>>,
    /// Dynamic EOS token captured during the last `phonemize_with_prosody`
    /// call. Consumed by `post_process_ids`.
    last_eos: Mutex<String>,
}

impl MultilingualPhonemizer {
    /// Create a new multilingual phonemizer.
    ///
    /// `languages` lists the supported language codes (e.g., `["ja", "en"]`).
    /// Each must have a corresponding entry in `phonemizers`.
    ///
    /// `default_latin_language` controls which language Latin-script
    /// characters are assigned to. If not present in `languages`, falls
    /// back to the first language.
    pub fn new(
        languages: Vec<String>,
        mut default_latin_language: String,
        phonemizers: HashMap<String, Box<dyn Phonemizer>>,
    ) -> Self {
        // Validate default_latin_language is in the supported set
        if !languages.contains(&default_latin_language) {
            default_latin_language = languages
                .first()
                .cloned()
                .unwrap_or_else(|| "en".to_string());
        }

        let detector = UnicodeLanguageDetector::new(&languages, &default_latin_language);

        Self {
            languages,
            default_latin_language,
            detector,
            phonemizers,
            last_eos: Mutex::new("$".to_string()),
        }
    }

    /// Return the list of supported language codes.
    pub fn languages(&self) -> &[String] {
        &self.languages
    }

    /// Detect the primary language of the text.
    ///
    /// Returns the language code of the first detected language segment,
    /// or the default_latin_language if no segments are detected.
    pub fn detect_primary_language(&self, text: &str) -> &str {
        let segments = segment_text(text, &self.detector);
        if let Some((lang, _)) = segments.first() {
            // Match against known language codes to return &str with correct lifetime
            for supported in &self.languages {
                if supported == lang {
                    return supported.as_str();
                }
            }
        }
        &self.default_latin_language
    }

    /// Build the set of BOS/EOS-like tokens to strip from individual
    /// segment outputs. Includes PUA-encoded Japanese question markers.
    /// Cached via `OnceLock` to avoid re-constructing the `HashSet` on every call.
    fn bos_eos_tokens() -> &'static HashSet<String> {
        static TOKENS: OnceLock<HashSet<String>> = OnceLock::new();
        TOKENS.get_or_init(|| {
            let mut set = HashSet::new();
            set.insert("^".to_string());
            set.insert("$".to_string());
            set.insert("?".to_string());
            // PUA-encoded question markers (?!, ?., ?~)
            for marker in &["?!", "?.", "?~"] {
                if let Some(pua) = token_to_pua(marker) {
                    set.insert(pua.to_string());
                }
            }
            set
        })
    }

    /// Build the set of EOS-like tokens (subset of BOS/EOS used to track
    /// the last EOS for dynamic post-processing).
    /// Cached via `OnceLock` to avoid re-constructing the `HashSet` on every call.
    fn eos_tokens() -> &'static HashSet<String> {
        static TOKENS: OnceLock<HashSet<String>> = OnceLock::new();
        TOKENS.get_or_init(|| {
            let mut set = HashSet::new();
            set.insert("$".to_string());
            set.insert("?".to_string());
            for marker in &["?!", "?.", "?~"] {
                if let Some(pua) = token_to_pua(marker) {
                    set.insert(pua.to_string());
                }
            }
            set
        })
    }
}

impl Phonemizer for MultilingualPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        let segments = segment_text(text, &self.detector);
        if segments.is_empty() {
            return Ok((Vec::new(), Vec::new()));
        }

        let bos_eos = Self::bos_eos_tokens();
        let eos_set = Self::eos_tokens();

        let mut all_phonemes: Vec<String> = Vec::new();
        let mut all_prosody: Vec<Option<ProsodyInfo>> = Vec::new();
        let mut last_eos = "$".to_string();

        for (lang, segment_text) in &segments {
            let phonemizer = self
                .phonemizers
                .get(lang)
                .ok_or_else(|| PiperError::UnsupportedLanguage { code: lang.clone() })?;

            let (phonemes, prosody_list) = phonemizer.phonemize_with_prosody(segment_text)?;

            // Strip BOS/EOS from individual segments.
            // This includes PUA-encoded question markers from Japanese.
            for (ph, pr) in phonemes.iter().zip(prosody_list.iter()) {
                if bos_eos.contains(ph) {
                    if eos_set.contains(ph) {
                        last_eos = ph.clone();
                    }
                    continue;
                }
                all_phonemes.push(ph.clone());
                all_prosody.push(*pr);
            }
        }

        // Update last_eos via interior mutability (Mutex).
        if let Ok(mut guard) = self.last_eos.lock() {
            *guard = last_eos;
        }

        Ok((all_phonemes, all_prosody))
    }

    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> {
        // Multilingual uses the phoneme_id_map from config.json
        // (the unified multilingual map generated during preprocessing).
        None
    }

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
        let eos = self
            .last_eos
            .lock()
            .map(|g| g.clone())
            .unwrap_or_else(|_| "$".to_string());
        default_post_process_ids(ids, prosody, id_map, &eos)
    }

    fn language_code(&self) -> &str {
        // Return the default Latin language for multi-language mode.
        &self.default_latin_language
    }

    fn detect_primary_language(&self, text: &str) -> &str {
        // Delegate to the inherent method
        MultilingualPhonemizer::detect_primary_language(self, text)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // ===== UnicodeLanguageDetector =====

    fn make_detector(langs: &[&str], default_latin: &str) -> UnicodeLanguageDetector {
        let lang_strings: Vec<String> = langs.iter().map(|s| s.to_string()).collect();
        UnicodeLanguageDetector::new(&lang_strings, default_latin)
    }

    #[test]
    fn test_detect_hiragana_as_ja() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char('\u{3042}', false), Some("ja")); // あ
        assert_eq!(det.detect_char('\u{3093}', false), Some("ja")); // ん
    }

    #[test]
    fn test_detect_katakana_as_ja() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char('\u{30A2}', false), Some("ja")); // ア
        assert_eq!(det.detect_char('\u{30F3}', false), Some("ja")); // ン
    }

    #[test]
    fn test_detect_katakana_phonetic_ext_as_ja() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char('\u{31F0}', false), Some("ja")); // ㇰ
    }

    #[test]
    fn test_detect_hangul_as_ko() {
        let det = make_detector(&["ja", "en", "ko"], "en");
        assert_eq!(det.detect_char('\u{AC00}', false), Some("ko")); // 가
        assert_eq!(det.detect_char('\u{D7AF}', false), Some("ko")); // last hangul syllable
    }

    #[test]
    fn test_detect_hangul_jamo_as_ko() {
        let det = make_detector(&["ko", "en"], "en");
        assert_eq!(det.detect_char('\u{1100}', false), Some("ko")); // ᄀ
        assert_eq!(det.detect_char('\u{3131}', false), Some("ko")); // ㄱ (compat)
    }

    #[test]
    fn test_detect_cjk_as_zh_without_kana() {
        let det = make_detector(&["ja", "en", "zh"], "en");
        // CJK ideograph, no kana context → Chinese
        assert_eq!(det.detect_char('\u{4E16}', false), Some("zh")); // 世
    }

    #[test]
    fn test_detect_cjk_as_ja_with_kana_context() {
        let det = make_detector(&["ja", "en", "zh"], "en");
        // CJK ideograph, kana context → Japanese
        assert_eq!(det.detect_char('\u{4E16}', true), Some("ja")); // 世
    }

    #[test]
    fn test_detect_cjk_ja_only() {
        let det = make_detector(&["ja", "en"], "en");
        // Only JA is available, no ZH → always JA regardless of context
        assert_eq!(det.detect_char('\u{4E16}', false), Some("ja"));
    }

    #[test]
    fn test_detect_cjk_zh_only() {
        let det = make_detector(&["zh", "en"], "en");
        // Only ZH is available → always ZH
        assert_eq!(det.detect_char('\u{4E16}', true), Some("zh"));
    }

    #[test]
    fn test_detect_fullwidth_latin_as_default_latin() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char('\u{FF21}', false), Some("en")); // Ａ
        assert_eq!(det.detect_char('\u{FF5A}', false), Some("en")); // ｚ
    }

    #[test]
    fn test_detect_cjk_punctuation_as_ja() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char('\u{3001}', false), Some("ja")); // 、
        assert_eq!(det.detect_char('\u{3002}', false), Some("ja")); // 。
        assert_eq!(det.detect_char('\u{300C}', false), Some("ja")); // 「
    }

    #[test]
    fn test_detect_latin_as_default_language() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char('H', false), Some("en"));
        assert_eq!(det.detect_char('z', false), Some("en"));
    }

    #[test]
    fn test_detect_accented_latin() {
        let det = make_detector(&["ja", "fr"], "fr");
        assert_eq!(det.detect_char('\u{00E9}', false), Some("fr")); // é
        assert_eq!(det.detect_char('\u{00C0}', false), Some("fr")); // À
    }

    #[test]
    fn test_detect_neutral_characters() {
        let det = make_detector(&["ja", "en"], "en");
        assert_eq!(det.detect_char(' ', false), None);
        assert_eq!(det.detect_char('0', false), None);
        assert_eq!(det.detect_char('!', false), None);
        assert_eq!(det.detect_char('.', false), None);
        assert_eq!(det.detect_char(',', false), None);
    }

    #[test]
    fn test_detect_multiplication_sign_is_neutral() {
        let det = make_detector(&["ja", "en"], "en");
        // U+00D7 (×) is in the range but excluded from Latin
        assert_eq!(det.detect_char('\u{00D7}', false), None);
    }

    #[test]
    fn test_has_kana() {
        let det = make_detector(&["ja", "en"], "en");
        assert!(det.has_kana("こんにちは world"));
        assert!(det.has_kana("アイウ"));
        assert!(!det.has_kana("Hello world"));
        assert!(!det.has_kana("你好世界"));
    }

    // ===== segment_text =====

    #[test]
    fn test_segment_pure_japanese() {
        let det = make_detector(&["ja", "en"], "en");
        let segs = segment_text("こんにちは", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "ja");
        assert_eq!(segs[0].1, "こんにちは");
    }

    #[test]
    fn test_segment_pure_english() {
        let det = make_detector(&["ja", "en"], "en");
        let segs = segment_text("Hello world", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "en");
        assert_eq!(segs[0].1, "Hello world");
    }

    #[test]
    fn test_segment_mixed_ja_en() {
        let det = make_detector(&["ja", "en"], "en");
        let segs = segment_text("今日はgood morningですね", &det);
        assert_eq!(segs.len(), 3);
        assert_eq!(segs[0].0, "ja");
        assert_eq!(segs[0].1, "今日は");
        assert_eq!(segs[1].0, "en");
        assert_eq!(segs[1].1, "good morning");
        assert_eq!(segs[2].0, "ja");
        assert_eq!(segs[2].1, "ですね");
    }

    #[test]
    fn test_segment_neutral_absorbed_into_preceding() {
        let det = make_detector(&["ja", "en"], "en");
        // "Hello, " — comma and space are neutral, absorbed into English
        let segs = segment_text("Hello, こんにちは", &det);
        assert_eq!(segs.len(), 2);
        assert_eq!(segs[0].0, "en");
        assert_eq!(segs[0].1, "Hello, ");
        assert_eq!(segs[1].0, "ja");
        assert_eq!(segs[1].1, "こんにちは");
    }

    #[test]
    fn test_segment_leading_neutral_absorbed_into_first_language() {
        let det = make_detector(&["ja", "en"], "en");
        // Leading "123 " are neutral — no preceding segment, so they get
        // absorbed into whatever language comes first.
        let segs = segment_text("123 Hello", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "en");
        assert_eq!(segs[0].1, "123 Hello");
    }

    #[test]
    fn test_segment_empty_string() {
        let det = make_detector(&["ja", "en"], "en");
        let segs = segment_text("", &det);
        assert!(segs.is_empty());
    }

    #[test]
    fn test_segment_whitespace_only() {
        let det = make_detector(&["ja", "en"], "en");
        let segs = segment_text("   ", &det);
        assert!(segs.is_empty());
    }

    #[test]
    fn test_segment_digits_only_fallback() {
        let det = make_detector(&["ja", "en"], "en");
        // No language-specific characters — falls back to default
        let segs = segment_text("12345", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "en");
        assert_eq!(segs[0].1, "12345");
    }

    #[test]
    fn test_segment_cjk_disambiguation_with_kana() {
        let det = make_detector(&["ja", "en", "zh"], "en");
        // Text with kana + CJK ideographs: the ideographs become JA
        let segs = segment_text("漢字とかな", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "ja");
    }

    #[test]
    fn test_segment_cjk_without_kana_is_zh() {
        let det = make_detector(&["ja", "en", "zh"], "en");
        // Pure CJK ideographs without kana → Chinese
        let segs = segment_text("你好世界", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "zh");
    }

    #[test]
    fn test_segment_mixed_zh_en() {
        let det = make_detector(&["zh", "en"], "en");
        let segs = segment_text("Hello你好", &det);
        assert_eq!(segs.len(), 2);
        assert_eq!(segs[0].0, "en");
        assert_eq!(segs[0].1, "Hello");
        assert_eq!(segs[1].0, "zh");
        assert_eq!(segs[1].1, "你好");
    }

    // ===== default_post_process_ids =====

    fn make_id_map() -> PhonemeIdMap {
        let mut m = HashMap::new();
        m.insert("_".to_string(), vec![0]);
        m.insert("^".to_string(), vec![1]);
        m.insert("$".to_string(), vec![2]);
        m.insert("?".to_string(), vec![3]);
        m
    }

    #[test]
    fn test_post_process_basic_padding() {
        let id_map = make_id_map();
        let ids = vec![10, 11, 12];
        let prosody = vec![None, None, None];
        let (out_ids, out_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");
        // Expected: ^(1) + pad(0) + 10 + pad(0) + 11 + pad(0) + 12 + pad(0) + $(2)
        assert_eq!(out_ids, vec![1, 0, 10, 0, 11, 0, 12, 0, 2]);
        assert_eq!(out_prosody.len(), out_ids.len());
    }

    #[test]
    fn test_post_process_skip_padding_after_pad_token() {
        let id_map = make_id_map();
        // ID 0 is a pad token — should NOT get another pad after it
        let ids = vec![10, 0, 12];
        let prosody = vec![None, None, None];
        let (out_ids, _) = default_post_process_ids(ids, prosody, &id_map, "$");
        // Expected: ^(1) + pad(0) + 10 + pad(0) + 0 (no pad after) + 12 + pad(0) + $(2)
        assert_eq!(out_ids, vec![1, 0, 10, 0, 0, 12, 0, 2]);
    }

    #[test]
    fn test_post_process_with_question_eos() {
        let id_map = make_id_map();
        let ids = vec![10];
        let prosody = vec![None];
        let (out_ids, _) = default_post_process_ids(ids, prosody, &id_map, "?");
        // Expected: ^(1) + pad(0) + 10 + pad(0) + ?(3)
        assert_eq!(out_ids, vec![1, 0, 10, 0, 3]);
    }

    #[test]
    fn test_post_process_eos_fallback_to_dollar() {
        let id_map = make_id_map();
        let ids = vec![10];
        let prosody = vec![None];
        // Request EOS token "nonexistent" — should fall back to "$"
        let (out_ids, _) = default_post_process_ids(ids, prosody, &id_map, "nonexistent");
        // Expected: ^(1) + pad(0) + 10 + pad(0) + $(2)
        assert_eq!(out_ids, vec![1, 0, 10, 0, 2]);
    }

    #[test]
    fn test_post_process_empty_input() {
        let id_map = make_id_map();
        let ids: Vec<i64> = Vec::new();
        let prosody: Vec<Option<ProsodyFeature>> = Vec::new();
        let (out_ids, out_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");
        // Expected: ^(1) + pad(0) + $(2)
        assert_eq!(out_ids, vec![1, 0, 2]);
        assert_eq!(out_prosody.len(), out_ids.len());
    }

    #[test]
    fn test_post_process_prosody_propagated() {
        let id_map = make_id_map();
        let ids = vec![10, 11];
        let prosody = vec![Some([1, 2, 3]), None];
        let (out_ids, out_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");
        // ^=None pad=None 10=Some([1,2,3]) pad=None 11=None pad=None $=None
        assert_eq!(out_ids, vec![1, 0, 10, 0, 11, 0, 2]);
        assert!(out_prosody[0].is_none()); // ^
        assert!(out_prosody[1].is_none()); // pad
        assert_eq!(out_prosody[2], Some([1, 2, 3])); // phoneme 10
        assert!(out_prosody[3].is_none()); // pad
        assert!(out_prosody[4].is_none()); // phoneme 11
        assert!(out_prosody[5].is_none()); // pad
        assert!(out_prosody[6].is_none()); // $
    }

    // ===== BOS/EOS token sets =====

    #[test]
    fn test_bos_eos_tokens_include_pua_markers() {
        let set = MultilingualPhonemizer::bos_eos_tokens();
        assert!(set.contains("^"));
        assert!(set.contains("$"));
        assert!(set.contains("?"));
        // PUA markers for ?!, ?., ?~
        assert!(set.contains(&"\u{E016}".to_string())); // ?!
        assert!(set.contains(&"\u{E017}".to_string())); // ?.
        assert!(set.contains(&"\u{E018}".to_string())); // ?~
    }

    #[test]
    fn test_eos_tokens_subset() {
        let eos_set = MultilingualPhonemizer::eos_tokens();
        let bos_eos_set = MultilingualPhonemizer::bos_eos_tokens();
        // EOS set should be a subset of BOS/EOS set
        for token in eos_set {
            assert!(
                bos_eos_set.contains(token),
                "EOS token {:?} not in BOS/EOS set",
                token
            );
        }
        // BOS (^) should be in bos_eos but NOT in eos
        assert!(!eos_set.contains("^"));
    }

    // ===== Integration: post_process_ids via trait =====

    #[test]
    fn test_post_process_ids_and_prosody_lengths_match() {
        let id_map = make_id_map();
        let ids = vec![5, 6, 7, 8, 9];
        let prosody: Vec<Option<ProsodyFeature>> =
            vec![Some([1, 0, 3]), None, Some([0, 2, 4]), None, None];
        let (out_ids, out_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");
        assert_eq!(
            out_ids.len(),
            out_prosody.len(),
            "IDs ({}) and prosody ({}) length mismatch",
            out_ids.len(),
            out_prosody.len()
        );
    }

    // ===== Swedish detection =====

    #[test]
    fn test_detect_swedish_enabled_when_sv_and_en() {
        let det = make_detector(&["en", "sv", "ja"], "en");
        assert!(det.detect_swedish);
    }

    #[test]
    fn test_detect_swedish_disabled_when_sv_is_only_latin() {
        // Only one Latin-script language → no ambiguity → disabled
        let det = make_detector(&["sv", "ja"], "sv");
        assert!(!det.detect_swedish);
    }

    #[test]
    fn test_detect_swedish_disabled_when_no_sv() {
        let det = make_detector(&["en", "fr"], "en");
        assert!(!det.detect_swedish);
    }

    #[test]
    fn test_segment_swedish_chars_reclassify_segment() {
        // ä/ö/å trigger Swedish reclassification
        let det = make_detector(&["en", "sv", "ja"], "en");
        let segs = segment_text("Jag tycker om räkor", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "sv"); // "räkor" contains ä
    }

    #[test]
    fn test_segment_swedish_function_word_reclassify() {
        // "och" is a Swedish function word
        let det = make_detector(&["en", "sv", "ja"], "en");
        let segs = segment_text("Stockholm och Malmö", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "sv"); // "och" is a function word + "Malmö" has ö
    }

    #[test]
    fn test_segment_pure_english_stays_english() {
        // No Swedish indicators → stays as default Latin (en)
        let det = make_detector(&["en", "sv", "ja"], "en");
        let segs = segment_text("Hello world", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "en");
    }

    #[test]
    fn test_segment_swedish_mixed_with_japanese() {
        let det = make_detector(&["en", "sv", "ja"], "en");
        let segs = segment_text("こんにちはJag tycker om räkor", &det);
        assert_eq!(segs.len(), 2);
        assert_eq!(segs[0].0, "ja");
        assert_eq!(segs[1].0, "sv"); // "räkor" has ä
    }

    #[test]
    fn test_segment_no_swedish_refinement_when_default_is_sv() {
        // When default Latin IS Swedish, refinement is skipped
        let det = make_detector(&["sv", "en", "ja"], "sv");
        let segs = segment_text("Hello world", &det);
        assert_eq!(segs.len(), 1);
        // default is sv, so Latin text goes to sv directly (no refinement needed)
        assert_eq!(segs[0].0, "sv");
    }

    #[test]
    fn test_segment_swedish_function_word_alone() {
        // Single function word "jag" should trigger Swedish
        let det = make_detector(&["en", "sv"], "en");
        let segs = segment_text("jag", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "sv");
    }

    #[test]
    fn test_segment_swedish_uppercase_chars() {
        // Uppercase Ä/Ö/Å should also trigger Swedish
        let det = make_detector(&["en", "sv"], "en");
        let segs = segment_text("ÖVERRASKNING", &det);
        assert_eq!(segs.len(), 1);
        assert_eq!(segs[0].0, "sv"); // Ö triggers it
    }

    #[test]
    fn test_refine_skips_non_default_segments() {
        // Segments already classified as "ja" should not be touched
        let input = vec![
            ("ja".to_string(), "こんにちは".to_string()),
            ("en".to_string(), "och hej".to_string()),
        ];
        let result = refine_latin_segments_for_swedish(input, "en");
        assert_eq!(result[0].0, "ja");
        assert_eq!(result[1].0, "sv"); // "och" is a function word
    }

    #[test]
    fn test_refine_no_indicators_stays_default() {
        let input = vec![("en".to_string(), "Hello world".to_string())];
        let result = refine_latin_segments_for_swedish(input, "en");
        assert_eq!(result[0].0, "en");
    }

    #[test]
    fn test_swedish_function_words_count() {
        // Verify the constant has 45 entries (matching Python)
        assert_eq!(SWEDISH_FUNCTION_WORDS.len(), 45);
    }

    #[test]
    fn test_swedish_chars_count() {
        // 6 characters: ä, ö, å, Ä, Ö, Å
        assert_eq!(SWEDISH_CHARS.len(), 6);
    }
}

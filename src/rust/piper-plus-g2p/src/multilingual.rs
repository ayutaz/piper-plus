//! Multilingual phonemizer for code-switching text across N languages.
//!
//! Generalizes the concept of bilingual phonemization to support arbitrary
//! language combinations. Detects language segments via Unicode ranges,
//! delegates to language-specific phonemizers, and returns unified phoneme IDs.
//!
//! Port of the Python `multilingual.py`.

use std::collections::{HashMap, HashSet};
use std::sync::{LazyLock, Mutex, OnceLock};

use crate::error::G2pError;
use crate::phonemizer::{PhonemeIdMap, Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::token_map::token_to_pua;

// ---------------------------------------------------------------------------
// Swedish per-word LID data (Issue #539)
// ---------------------------------------------------------------------------
// The char-level detector maps å/ä/ö to `default_latin_language` (shared with
// other Latin scripts). A conservative word-level post-pass then re-classifies
// default-Latin segments to Swedish when a STRONG indicator is present:
// the å/Å character, or an exact match in the Swedish function-word set.
// Weak chars ä/ö alone are NOT sufficient (shared with German/Finnish/loanwords).
//
// The function-word list + strong-char set are loaded from the bundled JSON
// data file (byte-for-byte identical to the Python canonical
// `src/python/g2p/piper_plus_g2p/data/sv_function_words.json`; a CI sync gate
// enforces this). We do NOT hardcode them — mirroring the ZH-EN loanword
// pattern (`chinese.rs`).

/// Default Swedish function-word + strong-char data, embedded at compile time.
///
/// Byte-for-byte identical to
/// `src/python/g2p/piper_plus_g2p/data/sv_function_words.json`. `include_str!`
/// bakes the bytes into the binary at compile time, so there is no runtime
/// file dependency (and no `include` entry is needed in `Cargo.toml`).
const SV_FUNCTION_WORDS_JSON: &str = include_str!("../data/sv_function_words.json");

/// Schema for `sv_function_words.json`.
///
/// **Forward-compatible**: unknown top-level fields (e.g. a future
/// `schema_version` bump or added sections) are silently ignored via
/// `#[serde(default)]` + serde's default behaviour of dropping unrecognised
/// keys, so a future payload extension does not break this loader.
#[derive(Debug, Clone, Default, serde::Deserialize)]
struct SvFunctionWordsData {
    /// Strong single-char indicators (conservative policy: å/Å only).
    #[serde(default)]
    strong_chars: Vec<String>,
    /// LID-discriminative Swedish function words.
    #[serde(default)]
    function_words: Vec<String>,
}

/// Parsed `(function_words, strong_chars)`, lazily loaded + cached.
///
/// * `function_words` are lowercased (callers lowercase each word before
///   matching).
/// * `strong_chars` are kept as-is. The uppercase `Å` entry is a *defensive*
///   convention shared with the C#/Go/C++ runtimes (which store the uppercase
///   form too). Since callers lowercase each word first, only the lowercase
///   `å` is strictly needed to match, but the uppercase form is intentionally
///   retained for cross-runtime parity — do not drop it.
///
/// A malformed/empty bundle degrades gracefully to empty sets (the post-pass
/// becomes a no-op) rather than panicking the whole crate at first use.
///
/// Note: `sv_function_words.json` is the LID-discriminative word list (used
/// only for language detection, and deliberately excludes
/// cross-language-ambiguous words like i/en/av/de/du). It is intentionally
/// DISTINCT from `swedish.rs`'s prosody/stress function-word list — do not
/// try to sync the two.
static SV_FUNCTION_WORDS: LazyLock<(HashSet<String>, HashSet<char>)> = LazyLock::new(|| {
    let data: SvFunctionWordsData = match serde_json::from_str(SV_FUNCTION_WORDS_JSON) {
        Ok(d) => d,
        Err(e) => {
            tracing::warn!(
                "Swedish function-word data is malformed ({e}); \
                 per-word Swedish LID will be disabled."
            );
            SvFunctionWordsData::default()
        }
    };

    let function_words: HashSet<String> = data
        .function_words
        .iter()
        .filter(|w| !w.is_empty())
        .map(|w| w.to_lowercase())
        .collect();

    // Each strong "char" entry in the JSON is a single Unicode scalar; expand
    // any (defensively) multi-char string into its chars so the set is a
    // `HashSet<char>` for O(1) membership.
    let strong_chars: HashSet<char> = data.strong_chars.iter().flat_map(|s| s.chars()).collect();

    (function_words, strong_chars)
});

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
    /// Whether the conservative Swedish per-word post-pass is enabled.
    /// True when "sv" is in `languages` AND there are >=2 Latin-script
    /// languages (i.e. a genuine code-switching context, not a Swedish-only
    /// model). See `refine_latin_segments_for_swedish`.
    detect_swedish: bool,
}

impl UnicodeLanguageDetector {
    /// Create a new detector for the given set of languages.
    ///
    /// `default_latin_language` controls which language Latin-script
    /// characters (A-Z, a-z, accented Latin) are assigned to.
    pub fn new(languages: &[String], default_latin_language: &str) -> Self {
        let lang_set: HashSet<String> = languages.iter().cloned().collect();
        let has_sv = lang_set.contains("sv");
        // Latin-script languages in piper-plus.
        let latin_count = ["en", "es", "pt", "fr", "sv"]
            .iter()
            .filter(|l| lang_set.contains(**l))
            .count();
        Self {
            has_ja: lang_set.contains("ja"),
            has_zh: lang_set.contains("zh"),
            has_ko: lang_set.contains("ko"),
            // Conservative gate for the Swedish per-word post-pass (Issue
            // #539): only when Swedish is requested alongside >=2 Latin-script
            // languages.
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

    // Conservative Swedish per-word post-pass (Issue #539): re-classify
    // default-Latin segments containing a strong Swedish indicator to "sv".
    // Gated on `detect_swedish` (sv present + >=2 Latin-script languages).
    if detector.detect_swedish {
        segments = refine_latin_segments_for_swedish(segments, &detector.default_latin_language);
    }

    segments
}

/// Re-classify default-Latin segments as Swedish (conservative; Issue #539).
///
/// For each segment currently assigned to the default Latin language, scan its
/// words for a STRONG Swedish indicator:
///
///   * an exact function-word match (e.g. "och", "jag", "från"), OR
///   * the å/Å character.
///
/// The weak chars ä/ö ALONE are intentionally NOT sufficient — they are shared
/// with German/Finnish/loanwords, so treating them as strong would over-trigger
/// (e.g. German "schön" / "Mädchen"). Function words containing ä/ö (för, när,
/// är, …) still qualify via the exact-match path. If any word is strong, the
/// WHOLE segment is re-classified to "sv" (avoids over-fragmentation from
/// word-by-word splitting). Segments NOT in the default Latin language (ja, zh,
/// ko, …) are left untouched.
fn refine_latin_segments_for_swedish(
    segments: Vec<(String, String)>,
    default_latin: &str,
) -> Vec<(String, String)> {
    // If the default Latin language IS Swedish, Latin text already goes to
    // "sv" directly — no refinement needed.
    if default_latin == "sv" {
        return segments;
    }

    let (func_words, strong_chars) = &*SV_FUNCTION_WORDS;

    segments
        .into_iter()
        .map(|(lang, text)| {
            if lang != default_latin {
                return (lang, text);
            }

            let mut strong = false;
            for word in text.split_whitespace() {
                // The 5-mark strip set (. , ; : ! ?) is PINNED: all runtimes
                // (Python/C#/Go/C++) strip exactly these ASCII marks, and
                // byte-identical tokenization across runtimes is required for
                // parity. Do not broaden it (no Unicode punctuation, no smart
                // quotes, etc.).
                let w = word
                    .trim_matches(|c: char| matches!(c, '.' | ',' | ';' | ':' | '!' | '?'))
                    .to_lowercase();
                if w.is_empty() {
                    continue;
                }
                if func_words.contains(&w) {
                    strong = true;
                    break;
                }
                // `w` is already lowercased here, so the å/Å strong-char set
                // only needs the lowercase `å` to match; the uppercase `Å`
                // entry is kept for cross-runtime parity (see loader docs).
                if w.chars().any(|c| strong_chars.contains(&c)) {
                    strong = true;
                    break;
                }
            }

            if strong {
                ("sv".to_string(), text)
            } else {
                (lang, text)
            }
        })
        .collect()
}

/// A text segment with its detected language.
#[derive(Debug, Clone)]
pub struct TextSegment {
    /// ISO 639-1 language code.
    pub language: String,
    /// The text content of this segment.
    pub text: String,
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
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        let tokens: Vec<String> = text.chars().map(|c| c.to_string()).collect();
        let prosody: Vec<Option<ProsodyInfo>> = vec![None; tokens.len()];
        Ok((tokens, prosody))
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
/// `last_eos` is set by `phonemize_with_prosody` and accessible via
/// `last_eos()`. A `Mutex` provides interior mutability while
/// satisfying the `Send + Sync` bounds required by the `Phonemizer` trait.
pub struct MultilingualPhonemizer {
    languages: Vec<String>,
    default_latin_language: String,
    detector: UnicodeLanguageDetector,
    phonemizers: HashMap<String, Box<dyn Phonemizer>>,
    /// Dynamic EOS token captured during the last `phonemize_with_prosody`
    /// call. Accessible via `last_eos()`.
    last_eos: Mutex<String>,
    /// ZH-EN code-switching dispatch toggle (Issue #384).
    ///
    /// When enabled (default with `chinese` feature), English segments
    /// adjacent to Chinese (`[zh, en, *]` / `[en, zh]` / `[zh, en, zh]`)
    /// are phonemized as Mandarin pinyin via the loanword dictionary
    /// instead of the standard English phonemizer.
    ///
    /// **Two-layer control (TICKET-01 §7 懸念 5)**:
    /// - **Cargo feature `chinese`**: compile-time switch (default-on)
    /// - **`enable_zh_en_dispatch`**: runtime switch (default-on, opt-out)
    enable_zh_en_dispatch: bool,
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
            // Default-on when chinese feature is compiled in (TICKET-01 §7 懸念 5)
            enable_zh_en_dispatch: cfg!(feature = "chinese"),
        }
    }

    /// Toggle ZH-EN code-switching dispatch (default-on with `chinese` feature).
    ///
    /// When `false`, embedded English in Chinese context is routed to the
    /// standard English phonemizer instead of being mapped to Mandarin pinyin
    /// via the loanword dictionary. Useful for callers who want to keep
    /// embedded English pronounced in English voice.
    pub fn enable_zh_en_dispatch(&mut self, enabled: bool) -> &mut Self {
        self.enable_zh_en_dispatch = enabled;
        self
    }

    /// Return whether ZH-EN code-switching dispatch is enabled.
    pub fn is_zh_en_dispatch_enabled(&self) -> bool {
        self.enable_zh_en_dispatch
    }

    /// Replace the phonemizer for a given language.
    ///
    /// Used by WASM external dictionary loading: initially a PassthroughPhonemizer
    /// is used for JA, then replaced with a real JapanesePhonemizer once the
    /// dictionary bytes are available.
    pub fn replace_phonemizer(&mut self, lang: &str, phonemizer: Box<dyn Phonemizer>) {
        self.phonemizers.insert(lang.to_string(), phonemizer);
    }

    /// Return the list of supported language codes.
    pub fn languages(&self) -> &[String] {
        &self.languages
    }

    /// Return the last EOS token captured during `phonemize_with_prosody`.
    ///
    /// Defaults to `"$"`. Japanese segments may produce `"?"`, `"?!"`, etc.
    /// Used by the encoder to pick the correct EOS during ID conversion.
    pub fn last_eos(&self) -> String {
        self.last_eos
            .lock()
            .map(|g| g.clone())
            .unwrap_or_else(|_| "$".to_string())
    }

    /// Segment mixed-language text into per-language chunks.
    ///
    /// Each segment contains contiguous characters of the same detected
    /// language. Neutral characters (whitespace, digits, punctuation) are
    /// absorbed into the preceding segment.
    ///
    /// Returns a list of `TextSegment { language, text }` structs.
    pub fn segment_text_structured(&self, text: &str) -> Vec<TextSegment> {
        segment_text(text, &self.detector)
            .into_iter()
            .map(|(lang, txt)| TextSegment {
                language: lang,
                text: txt,
            })
            .collect()
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

    /// Phonemize text with an explicit language hint.
    ///
    /// When a language hint is provided and the phonemizer for that language
    /// exists, the entire text is routed to that language's phonemizer
    /// (bypassing Unicode-based auto-detection). This is critical for
    /// Latin-script languages (es/fr/pt) which cannot be distinguished from
    /// English by Unicode ranges alone.
    ///
    /// Falls back to auto-detected segmentation if the hint is unknown.
    pub fn phonemize_with_language_hint(
        &self,
        text: &str,
        language: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        if let Some(phonemizer) = self.phonemizers.get(language) {
            let (tokens, prosody) = phonemizer.phonemize_with_prosody(text)?;

            // Strip BOS/EOS tokens from the segment, then re-wrap
            let bos_eos = Self::bos_eos_tokens();
            let eos_set = Self::eos_tokens();
            let mut last_eos = "$".to_string();
            let mut filtered_tokens = Vec::new();
            let mut filtered_prosody = Vec::new();
            for (ph, pr) in tokens.iter().zip(prosody.iter()) {
                if bos_eos.contains(ph) {
                    if eos_set.contains(ph) {
                        last_eos = ph.clone();
                    }
                    continue;
                }
                filtered_tokens.push(ph.clone());
                filtered_prosody.push(*pr);
            }

            if let Ok(mut guard) = self.last_eos.lock() {
                *guard = last_eos;
            }

            Ok((filtered_tokens, filtered_prosody))
        } else {
            // Unknown language hint — fall back to auto-detection
            self.phonemize_with_prosody(text)
        }
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
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        let segments = segment_text(text, &self.detector);
        if segments.is_empty() {
            return Ok((Vec::new(), Vec::new()));
        }

        let bos_eos = Self::bos_eos_tokens();
        let eos_set = Self::eos_tokens();

        let mut all_phonemes: Vec<String> = Vec::new();
        let mut all_prosody: Vec<Option<ProsodyInfo>> = Vec::new();
        let mut last_eos = "$".to_string();

        // Pre-compute whether text contains any zh segment, used for ZH-EN dispatch.
        #[cfg(feature = "chinese")]
        let has_zh_segment = segments.iter().any(|(lang, _)| lang == "zh");

        for (i, (lang, seg_text)) in segments.iter().enumerate() {
            // ZH-EN code-switching: route embedded en (with adjacent zh) through
            // chinese loanword phonemizer. Issue #384, design §2.1.
            #[cfg(feature = "chinese")]
            if self.enable_zh_en_dispatch && lang == "en" && has_zh_segment {
                let prev_is_zh = i > 0 && segments[i - 1].0 == "zh";
                let next_is_zh = i + 1 < segments.len() && segments[i + 1].0 == "zh";
                if prev_is_zh || next_is_zh {
                    let data = crate::chinese::load_default_loanword_data();
                    // Use `*_with_prosody` so each IPA token carries the
                    // syllable's tone in `a1` (matches Python: a2=a3=1
                    // because there is no surrounding chinese_text). Issue
                    // #384 review note R-C1.
                    let (tokens, prosody) =
                        crate::chinese::phonemize_embedded_english_with_prosody(seg_text, data);
                    debug_assert_eq!(tokens.len(), prosody.len());
                    all_phonemes.extend(tokens);
                    all_prosody.extend(prosody);
                    continue;
                }
            }

            let phonemizer = self
                .phonemizers
                .get(lang)
                .ok_or_else(|| G2pError::UnsupportedLanguage { code: lang.clone() })?;

            let (phonemes, prosody_list) = phonemizer.phonemize_with_prosody(seg_text)?;

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

    fn language_code(&self) -> &str {
        // Return the default Latin language for multi-language mode.
        &self.default_latin_language
    }

    fn detect_primary_language(&self, text: &str) -> &str {
        // Delegate to the inherent method
        MultilingualPhonemizer::detect_primary_language(self, text)
    }

    fn set_zh_en_dispatch(&mut self, enabled: bool) {
        // Forward through the inherent setter so trait-object users
        // (e.g. piper-core's `G2pAdapter`) can toggle the dispatch.
        // (Inherent name is `enable_zh_en_dispatch` for ergonomic use.)
        MultilingualPhonemizer::enable_zh_en_dispatch(self, enabled);
    }

    fn is_zh_en_dispatch_enabled(&self) -> bool {
        MultilingualPhonemizer::is_zh_en_dispatch_enabled(self)
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

    // ===== Integration: default_post_process_ids =====

    #[test]
    fn test_default_post_process_ids_and_prosody_lengths_match() {
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

    // ===== replace_phonemizer =====

    #[test]
    fn test_replace_phonemizer() {
        // Setup: create a multilingual phonemizer with 2 languages
        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        phonemizers.insert("ja".to_string(), Box::new(PassthroughPhonemizer::new("ja")));
        phonemizers.insert("en".to_string(), Box::new(PassthroughPhonemizer::new("en")));

        let mut mp = MultilingualPhonemizer::new(
            vec!["ja".to_string(), "en".to_string()],
            "en".to_string(),
            phonemizers,
        );

        // Phonemize Japanese text with passthrough (should produce character-level tokens)
        let (tokens_before, _) = mp.phonemize_with_prosody("あ").unwrap();

        // Replace JA phonemizer with a new passthrough (same type, but proves replacement works)
        mp.replace_phonemizer("ja", Box::new(PassthroughPhonemizer::new("ja")));

        // Phonemize again — should still work after replacement
        let (tokens_after, _) = mp.phonemize_with_prosody("あ").unwrap();
        assert_eq!(
            tokens_before, tokens_after,
            "replacement should produce same results"
        );
    }

    fn make_hint_test_phonemizer() -> MultilingualPhonemizer {
        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        phonemizers.insert("ja".to_string(), Box::new(PassthroughPhonemizer::new("ja")));
        phonemizers.insert("en".to_string(), Box::new(PassthroughPhonemizer::new("en")));
        phonemizers.insert("es".to_string(), Box::new(PassthroughPhonemizer::new("es")));
        MultilingualPhonemizer::new(
            vec!["ja".to_string(), "en".to_string(), "es".to_string()],
            "en".to_string(),
            phonemizers,
        )
    }

    #[test]
    fn test_language_hint_routes_to_correct_phonemizer() {
        let mp = make_hint_test_phonemizer();

        // Without hint: "Hola" is Latin → default_latin (en)
        let (tokens_auto, _) = mp.phonemize_with_prosody("Hola").unwrap();

        // With hint "es": routes directly to es phonemizer
        let (tokens_hint, _) = mp.phonemize_with_language_hint("Hola", "es").unwrap();

        // Both should produce output (not empty)
        assert!(!tokens_auto.is_empty(), "auto-detect should produce tokens");
        assert!(
            !tokens_hint.is_empty(),
            "language hint should produce tokens"
        );
    }

    #[test]
    fn test_language_hint_unknown_falls_back_to_auto() {
        let mp = make_hint_test_phonemizer();

        // Unknown language hint should fall back to auto-detection
        let (tokens, _) = mp.phonemize_with_language_hint("Hello", "xx").unwrap();
        assert!(
            !tokens.is_empty(),
            "unknown hint should fall back to auto-detect"
        );
    }

    #[test]
    fn test_language_hint_ja_matches_auto_detect() {
        let mp = make_hint_test_phonemizer();

        // "あ" with ja hint → JA phonemizer
        let (tokens_hint, _) = mp.phonemize_with_language_hint("あ", "ja").unwrap();
        let (tokens_auto, _) = mp.phonemize_with_prosody("あ").unwrap();

        // Both should produce the same result since auto-detect also detects ja
        assert_eq!(
            tokens_hint, tokens_auto,
            "ja hint should match auto-detected ja"
        );
    }

    // ===== ZH-EN code-switching dispatch (TICKET-01 R3) =====

    #[cfg(feature = "chinese")]
    fn make_zh_en_dispatch_phonemizer() -> MultilingualPhonemizer {
        // ZhEnDispatch only fires when both `zh` and `en` are registered.
        // We use PassthroughPhonemizer for both: zh dispatch is bypassed by
        // the chinese loanword path, but the ZhPhonemizer instance must exist
        // in the registry so the lang segment isn't rejected.
        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        phonemizers.insert("zh".to_string(), Box::new(PassthroughPhonemizer::new("zh")));
        phonemizers.insert("en".to_string(), Box::new(PassthroughPhonemizer::new("en")));
        MultilingualPhonemizer::new(
            vec!["zh".to_string(), "en".to_string()],
            "en".to_string(),
            phonemizers,
        )
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_default_enabled() {
        let mp = make_zh_en_dispatch_phonemizer();
        assert!(mp.is_zh_en_dispatch_enabled());
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_pattern_zh_en_zh() {
        // [zh, en, zh] — embedded English routes to loanword path
        let mp = make_zh_en_dispatch_phonemizer();
        let (tokens_dispatch, _) = mp
            .phonemize_with_prosody("\u{4f60}\u{597d} GPS \u{4e16}\u{754c}")
            .unwrap();
        // tokens contain GPS-mapped pinyin IPA tokens (PUA codepoints in 0xE020-0xE04A range)
        assert!(!tokens_dispatch.is_empty());
        let pua_count = tokens_dispatch
            .iter()
            .filter(|t| {
                t.chars()
                    .next()
                    .is_some_and(|c| (0xE020..=0xE04A).contains(&(c as u32)))
            })
            .count();
        assert!(
            pua_count > 0,
            "expected PUA tone markers from loanword path"
        );
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_pattern_zh_en() {
        // [zh, en] — `en` segment after zh routes to loanword path
        let mp = make_zh_en_dispatch_phonemizer();
        let (tokens, _) = mp
            .phonemize_with_prosody("\u{8bf7}\u{6253}\u{5f00} GPS")
            .unwrap();
        // The `en` segment "GPS" (with leading space absorbed into prior zh segment
        // or its own) should route through the loanword path.
        assert!(!tokens.is_empty());
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_disabled_falls_through_to_english() {
        let mut mp = make_zh_en_dispatch_phonemizer();
        mp.enable_zh_en_dispatch(false);
        assert!(!mp.is_zh_en_dispatch_enabled());
        // With dispatch disabled, "GPS" goes through the (passthrough) english path.
        let (tokens, _) = mp.phonemize_with_prosody("\u{4f60}\u{597d} GPS").unwrap();
        // Passthrough produces character-level tokens like "G", "P", "S" — none of
        // them are PUA tone markers from the loanword path.
        let pua_count = tokens
            .iter()
            .filter(|t| {
                t.chars()
                    .next()
                    .is_some_and(|c| (0xE020..=0xE04A).contains(&(c as u32)))
            })
            .count();
        assert_eq!(
            pua_count, 0,
            "dispatch disabled: no loanword PUA markers expected"
        );
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_pure_zh_unaffected() {
        let mp = make_zh_en_dispatch_phonemizer();
        // Pure zh — no en segment, dispatch doesn't fire.
        let (tokens, _) = mp
            .phonemize_with_prosody("\u{4f60}\u{597d}\u{4e16}\u{754c}")
            .unwrap();
        assert!(!tokens.is_empty());
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_pure_en_unaffected() {
        let mp = make_zh_en_dispatch_phonemizer();
        // Pure en — no zh segment, has_zh_segment is false, dispatch doesn't fire.
        let (tokens, _) = mp.phonemize_with_prosody("Hello GPS world").unwrap();
        let pua_count = tokens
            .iter()
            .filter(|t| {
                t.chars()
                    .next()
                    .is_some_and(|c| (0xE020..=0xE04A).contains(&(c as u32)))
            })
            .count();
        assert_eq!(pua_count, 0, "no zh segment: dispatch must not fire");
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_pattern_en_zh_en() {
        // Review note R-H1: when `en` is at both ends with `zh` in the
        // middle, *both* en segments are adjacent to a zh segment and so
        // both should route through the loanword path.
        let mp = make_zh_en_dispatch_phonemizer();
        let (tokens, _) = mp
            .phonemize_with_prosody("Hello \u{4f60}\u{597d} GPS")
            .unwrap();
        let pua_count = tokens
            .iter()
            .filter(|t| {
                t.chars()
                    .next()
                    .is_some_and(|c| (0xE020..=0xE04A).contains(&(c as u32)))
            })
            .count();
        assert!(
            pua_count > 0,
            "[en, zh, en] pattern: at least one en segment must route to loanword path"
        );
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_carries_prosody_a1_tone() {
        // Review note R-C1: dispatched IPA tokens must carry per-token
        // prosody (a1=tone, a2=a3=1), not None.
        let mp = make_zh_en_dispatch_phonemizer();
        let (tokens, prosody) = mp
            .phonemize_with_prosody("\u{4f60}\u{597d} GPS \u{4e16}\u{754c}")
            .unwrap();
        assert_eq!(tokens.len(), prosody.len(), "shape parity");
        // Find at least one PUA tone marker token from the dispatch path
        // and verify its prosody is `Some` with a valid Mandarin tone.
        let mut found_dispatched_with_tone = false;
        for (tok, p) in tokens.iter().zip(prosody.iter()) {
            let first = tok.chars().next().map(|c| c as u32).unwrap_or(0);
            if (0xE020..=0xE04A).contains(&first) {
                let info = p.as_ref().unwrap_or_else(|| {
                    panic!("dispatched token must carry prosody, got None for {tok:?}")
                });
                if (1..=5).contains(&info.a1) && info.a2 == 1 && info.a3 == 1 {
                    found_dispatched_with_tone = true;
                    break;
                }
            }
        }
        assert!(
            found_dispatched_with_tone,
            "expected at least one dispatched PUA token with (a1=tone, a2=1, a3=1)"
        );
    }

    #[cfg(feature = "chinese")]
    #[test]
    fn test_zh_en_dispatch_via_phonemizer_trait() {
        // R-C3 followup: set_zh_en_dispatch / is_zh_en_dispatch_enabled must
        // round-trip through the Phonemizer trait (dyn dispatch), not just the
        // inherent methods. WASM/Go bindings call through the trait.
        let mut mp: Box<dyn Phonemizer> = Box::new(make_zh_en_dispatch_phonemizer());
        assert!(
            mp.is_zh_en_dispatch_enabled(),
            "default ON under `chinese` feature"
        );
        mp.set_zh_en_dispatch(false);
        assert!(
            !mp.is_zh_en_dispatch_enabled(),
            "set_zh_en_dispatch(false) must propagate through trait"
        );
        mp.set_zh_en_dispatch(true);
        assert!(
            mp.is_zh_en_dispatch_enabled(),
            "set_zh_en_dispatch(true) must propagate through trait"
        );
    }

    #[test]
    fn test_zh_en_dispatch_trait_default_noop_for_other_phonemizers() {
        // R-C3 followup: Phonemizer trait has a default no-op for
        // set/is_zh_en_dispatch_enabled so non-multilingual phonemizers
        // (e.g. PassthroughPhonemizer) silently report "disabled" and ignore
        // toggle calls. This guarantees capability discovery is meaningful.
        let mut p = PassthroughPhonemizer::new("en");
        assert!(
            !p.is_zh_en_dispatch_enabled(),
            "non-multilingual phonemizer default = disabled"
        );
        p.set_zh_en_dispatch(true);
        assert!(
            !p.is_zh_en_dispatch_enabled(),
            "default no-op: set_zh_en_dispatch(true) does not change state"
        );
    }
}

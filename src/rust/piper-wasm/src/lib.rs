//! WASM phonemizer for Piper Plus TTS.
//!
//! Provides `WasmPhonemizer` — a wasm-bindgen API wrapping piper-core's
//! `MultilingualPhonemizer` with bundled NAIST-JDIC dictionary.
//! Replaces the Emscripten OpenJTalk WASM + JS label parsing pipeline.
//!
//! # Feature gates
//!
//! Each language can be individually enabled/disabled via Cargo features:
//! - `ja` — Japanese (enables `piper-plus/naist-jdic`, bundles ~30 MB dictionary)
//! - `ja-external` — Japanese without bundled dictionary (enables `piper-plus/japanese`).
//!   Use `setJapaneseDictionary()` at runtime to load the dictionary from external bytes.
//! - `zh` — Chinese (enables `piper-plus-g2p/chinese`). Pinyin dictionaries must be
//!   loaded at runtime via `setChineseDictionary()`.
//! - `zh-external` — Chinese with runtime dictionary loading (same as `zh` but
//!   semantically indicates external dict loading, like `ja-external`).
//!   Use `setChineseDictionary()` to load pinyin JSON dictionaries.
//! - `ko` — Korean (rule-based, no dictionary needed)
//! - `es` — Spanish (rule-based, no dictionary needed)
//! - `fr` — French (rule-based, no dictionary needed)
//! - `pt` — Portuguese (rule-based, no dictionary needed)
//! - `sv` — Swedish (rule-based, no dictionary needed)
//! - `multilingual` — All languages with bundled JA dictionary + ZH G2P
//! - `multilingual-external` — All languages with `ja-external` + `zh-external`
//!
//! **EN** always uses `PassthroughPhonemizer` (character-level tokenization)
//! inside Rust WASM because its full G2P requires a large pronunciation
//! dictionary (CMU-dict). The JS-side `@piper-plus/g2p` package provides
//! richer EN phonemization separately.
//!
//! All features are off by default. For a JA-only WASM build:
//! ```sh
//! wasm-pack build --no-default-features --features ja
//! ```
//!
//! For a build without the bundled dictionary (external dict loading):
//! ```sh
//! wasm-pack build --no-default-features --features ja-external
//! ```
//!
//! When a language feature is disabled, that language falls back to
//! `PassthroughPhonemizer` (character-level tokenization).

use std::collections::HashMap;
use wasm_bindgen::prelude::*;

// ---------------------------------------------------------------------------
// Structured WASM error support
// ---------------------------------------------------------------------------
// Error codes exposed on the JavaScript `Error.code` property so callers can
// programmatically distinguish error types without parsing message strings.

/// Failed to parse the config.json supplied to the constructor.
const ERROR_CONFIG_PARSE: &str = "CONFIG_PARSE_ERROR";
/// Phonemization pipeline failed (G2P, token-mapping, etc.).
const ERROR_PHONEMIZE: &str = "PHONEMIZE_ERROR";
/// A required language is not present in the model configuration.
const ERROR_UNSUPPORTED_LANGUAGE: &str = "UNSUPPORTED_LANGUAGE";
/// The input text is empty or whitespace-only.
const ERROR_EMPTY_INPUT: &str = "EMPTY_INPUT";
/// Catch-all for unexpected / internal failures.
#[allow(dead_code)]
const ERROR_INTERNAL: &str = "INTERNAL_ERROR";

/// Create a JavaScript `Error` object with an additional `.code` property.
///
/// This preserves backward compatibility (JS `catch` still works, `.message`
/// is still set) while allowing programmatic error handling via `err.code`.
fn create_wasm_error(code: &str, message: &str) -> JsValue {
    let error = js_sys::Error::new(message);
    js_sys::Reflect::set(&error, &"code".into(), &code.into()).ok();
    error.into()
}

/// Called automatically when the WASM module is instantiated.
/// Sets up the panic hook for better error messages in the browser console.
#[wasm_bindgen(start)]
pub fn init_panic_hook() {
    console_error_panic_hook::set_once();
    // Initialize wasm-logger only once (safe to call multiple times).
    wasm_logger::init(wasm_logger::Config::default());
    log::info!("piper-wasm v{} initialized", env!("CARGO_PKG_VERSION"));
}

/// Get the API version string.
#[wasm_bindgen(js_name = getApiVersion)]
pub fn get_api_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

use piper_plus::config::VoiceConfig;
#[cfg(any(feature = "zh", feature = "zh-external"))]
use piper_plus_g2p::chinese::ChinesePhonemizer;
#[cfg(feature = "fr")]
use piper_plus_g2p::french::FrenchPhonemizer;
#[cfg(any(feature = "ja", feature = "ja-external"))]
use piper_plus_g2p::japanese::JapanesePhonemizer;
#[cfg(feature = "ko")]
use piper_plus_g2p::korean::KoreanPhonemizer;
use piper_plus_g2p::multilingual::{MultilingualPhonemizer, PassthroughPhonemizer};
#[cfg(feature = "pt")]
use piper_plus_g2p::portuguese::PortuguesePhonemizer;
#[cfg(feature = "es")]
use piper_plus_g2p::spanish::SpanishPhonemizer;
#[cfg(feature = "sv")]
use piper_plus_g2p::swedish::SwedishPhonemizer;
use piper_plus_g2p::{PhonemeIdMap, Phonemizer, PiperEncoder, UnknownTokenMode};

/// Phonemization result returned to JavaScript.
///
/// Contains `phoneme_ids` (ready for ONNX inference) and
/// `prosody_features` (flattened `[N*3]` array of A1/A2/A3 values).
#[wasm_bindgen]
#[derive(Debug)]
pub struct PhonemizeResult {
    phoneme_ids: Vec<i32>,
    prosody_features: Vec<i32>,
}

#[wasm_bindgen]
impl PhonemizeResult {
    /// phoneme_ids as Int32Array in JavaScript.
    /// Values are in the 0–1000 range so i32 is sufficient.
    #[wasm_bindgen(getter, js_name = phonemeIds)]
    pub fn phoneme_ids(&self) -> Vec<i32> {
        self.phoneme_ids.clone()
    }

    /// Prosody features as Int32Array (flattened [N*3]: a1,a2,a3 repeating).
    #[wasm_bindgen(getter, js_name = prosodyFeatures)]
    pub fn prosody_features(&self) -> Vec<i32> {
        self.prosody_features.clone()
    }

    /// Number of phoneme IDs.
    #[wasm_bindgen(getter, js_name = phonemeCount)]
    pub fn phoneme_count(&self) -> usize {
        self.phoneme_ids.len()
    }
}

/// WASM-compatible 8-language phonemizer with bundled Japanese dictionary.
///
/// Usage from JavaScript:
/// ```js
/// import init, { WasmPhonemizer } from './piper_plus_wasm.js';
/// await init();
/// const phonemizer = new WasmPhonemizer(JSON.stringify(config));
/// const result = phonemizer.phonemize("こんにちは");
/// console.log(result.phonemeIds);       // Int32Array
/// console.log(result.prosodyFeatures);  // Int32Array
/// phonemizer.free(); // optional explicit cleanup
/// ```
#[wasm_bindgen]
pub struct WasmPhonemizer {
    phonemizer: MultilingualPhonemizer,
    phoneme_id_map: PhonemeIdMap,
    encoder: PiperEncoder,
}

impl std::fmt::Debug for WasmPhonemizer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("WasmPhonemizer")
            .field("phoneme_id_map_len", &self.phoneme_id_map.len())
            .finish()
    }
}

/// Helper: create a phonemizer for the given language code.
///
/// When a language feature is enabled, the dedicated phonemizer is used.
/// When disabled (or for EN/unknown), falls back to `PassthroughPhonemizer`.
/// ZH starts as passthrough and is upgraded via `setChineseDictionary()`.
fn create_phonemizer(lang: &str) -> Result<Box<dyn Phonemizer>, String> {
    match lang {
        "ja" => {
            #[cfg(feature = "ja")]
            {
                JapanesePhonemizer::new_bundled()
                    .map(|p| Box::new(p) as Box<dyn Phonemizer>)
                    .map_err(|e| format!("JA init error: {e}"))
            }
            #[cfg(all(not(feature = "ja"), feature = "ja-external"))]
            {
                // External dict mode: start with passthrough, replaced by setJapaneseDictionary()
                Ok(Box::new(PassthroughPhonemizer::new("ja")))
            }
            #[cfg(all(not(feature = "ja"), not(feature = "ja-external")))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("ja")))
            }
        }
        "ko" => {
            #[cfg(feature = "ko")]
            {
                Ok(Box::new(KoreanPhonemizer::new()))
            }
            #[cfg(not(feature = "ko"))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("ko")))
            }
        }
        "es" => {
            #[cfg(feature = "es")]
            {
                Ok(Box::new(SpanishPhonemizer::new()))
            }
            #[cfg(not(feature = "es"))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("es")))
            }
        }
        "fr" => {
            #[cfg(feature = "fr")]
            {
                Ok(Box::new(FrenchPhonemizer::new()))
            }
            #[cfg(not(feature = "fr"))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("fr")))
            }
        }
        "pt" => {
            #[cfg(feature = "pt")]
            {
                Ok(Box::new(PortuguesePhonemizer::new()))
            }
            #[cfg(not(feature = "pt"))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("pt")))
            }
        }
        "sv" => {
            #[cfg(feature = "sv")]
            {
                Ok(Box::new(SwedishPhonemizer::new()))
            }
            #[cfg(not(feature = "sv"))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("sv")))
            }
        }
        "zh" => {
            #[cfg(feature = "zh")]
            {
                // zh feature: dictionaries are bundled but ChinesePhonemizer requires
                // JSON dict bytes -- not yet available at bundle time.
                // For now, start with passthrough; caller can use setChineseDictionary().
                Ok(Box::new(PassthroughPhonemizer::new("zh")))
            }
            #[cfg(all(not(feature = "zh"), feature = "zh-external"))]
            {
                // External dict mode: start with passthrough, replaced by setChineseDictionary()
                Ok(Box::new(PassthroughPhonemizer::new("zh")))
            }
            #[cfg(all(not(feature = "zh"), not(feature = "zh-external")))]
            {
                Ok(Box::new(PassthroughPhonemizer::new("zh")))
            }
        }
        // EN requires a large pronunciation dictionary (CMU-dict) -- handled by the
        // JS-side G2P package (@piper-plus/g2p) which provides EnglishG2P.
        // Unknown languages also fall back to character-level tokenization.
        other => Ok(Box::new(PassthroughPhonemizer::new(other))),
    }
}

#[wasm_bindgen]
impl WasmPhonemizer {
    /// Create a new phonemizer from a config.json string.
    ///
    /// The config must contain `phoneme_id_map` and `language_id_map`.
    ///
    /// # Errors
    ///
    /// Returns a JavaScript `Error` with a `.code` property:
    /// - `CONFIG_PARSE_ERROR` — invalid JSON or missing required fields
    /// - `UNSUPPORTED_LANGUAGE` — a language in `language_id_map` could not be initialised
    /// - `INTERNAL_ERROR` — unexpected failure
    #[wasm_bindgen(constructor)]
    pub fn new(config_json: &str) -> Result<WasmPhonemizer, JsValue> {
        let config: VoiceConfig = serde_json::from_str(config_json).map_err(|e| {
            create_wasm_error(
                ERROR_CONFIG_PARSE,
                &format!(
                    "Failed to parse config.json: {e}. \
                     Ensure the JSON is valid and contains 'phoneme_id_map' and 'language_id_map'."
                ),
            )
        })?;

        // Schema validation (MS3-2)
        config
            .validate()
            .map_err(|e| create_wasm_error(ERROR_CONFIG_PARSE, &format!("Invalid config: {e}")))?;

        let languages: Vec<String> = config.language_id_map.keys().cloned().collect();

        // WASM-specific: at least one language is always required for phonemizer init
        if languages.is_empty() {
            return Err(create_wasm_error(
                ERROR_CONFIG_PARSE,
                "language_id_map is empty in config.json. \
                 At least one language must be defined.",
            ));
        }

        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        for lang in &languages {
            let phonemizer = create_phonemizer(lang.as_str()).map_err(|e| {
                create_wasm_error(
                    ERROR_UNSUPPORTED_LANGUAGE,
                    &format!("Failed to initialise phonemizer for language '{lang}': {e}"),
                )
            })?;
            phonemizers.insert(lang.clone(), phonemizer);
        }

        let default_latin = if languages.contains(&"en".to_string()) {
            "en".to_string()
        } else {
            languages
                .first()
                .cloned()
                .unwrap_or_else(|| "en".to_string())
        };

        let multilingual = MultilingualPhonemizer::new(languages, default_latin, phonemizers);

        let encoder = PiperEncoder::new(config.phoneme_id_map.clone(), UnknownTokenMode::Skip)
            .map_err(|e| {
                create_wasm_error(
                    ERROR_CONFIG_PARSE,
                    &format!("Failed to create encoder: {e}"),
                )
            })?;

        Ok(WasmPhonemizer {
            phonemizer: multilingual,
            phoneme_id_map: config.phoneme_id_map,
            encoder,
        })
    }

    /// Phonemize text and return phoneme IDs + prosody features.
    ///
    /// `language` is an optional language code hint (e.g. `"ja"`, `"en"`).
    /// When provided, a warning is logged if auto-detection yields a different
    /// language. Currently auto-detection is always used for the actual
    /// phonemization; the parameter is reserved for future forced-language
    /// support.
    ///
    /// # Errors
    ///
    /// Returns a JavaScript `Error` with a `.code` property:
    /// - `EMPTY_INPUT` — text is empty or whitespace-only
    /// - `PHONEMIZE_ERROR` — the G2P pipeline failed
    pub fn phonemize(
        &self,
        text: &str,
        language: Option<String>,
    ) -> Result<PhonemizeResult, JsValue> {
        if text.trim().is_empty() {
            return Err(create_wasm_error(
                ERROR_EMPTY_INPUT,
                "Input text is empty or contains only whitespace. \
                 Provide at least one non-whitespace character.",
            ));
        }

        // Step 1: phonemize → raw tokens + prosody
        // When a language hint is provided, route the entire text to that
        // language's phonemizer. This is essential for Latin-script languages
        // (es/fr/pt/sv) which cannot be distinguished from English by Unicode.
        let (tokens, prosody_list) = if let Some(ref hint) = language {
            self.phonemizer
                .phonemize_with_language_hint(text, hint)
                .map_err(|e| {
                    create_wasm_error(
                        ERROR_PHONEMIZE,
                        &format!("Phonemization failed for the provided text: {e}"),
                    )
                })?
        } else {
            self.phonemizer.phonemize_with_prosody(text).map_err(|e| {
                create_wasm_error(
                    ERROR_PHONEMIZE,
                    &format!("Phonemization failed for the provided text: {e}"),
                )
            })?
        };

        // Step 2: encode tokens → IDs with BOS/EOS/PAD + prosody alignment
        let eos = self.phonemizer.last_eos();
        let (final_ids, final_prosody_features) = self
            .encoder
            .encode_with_prosody_and_eos(&tokens, &prosody_list, Some(&eos))
            .map_err(|e| create_wasm_error(ERROR_PHONEMIZE, &format!("Encoding failed: {e}")))?;

        // Step 3: flatten prosody to [N*3]
        let flat_prosody: Vec<i32> = final_prosody_features
            .iter()
            .flat_map(|pf| [pf[0], pf[1], pf[2]])
            .collect();

        // Downcast i64 → i32: phoneme IDs are in the 0–1000 range,
        // so i32 is sufficient and avoids BigInt64Array on the JS side.
        let phoneme_ids_i32: Vec<i32> = final_ids.iter().map(|&id| id as i32).collect();

        Ok(PhonemizeResult {
            phoneme_ids: phoneme_ids_i32,
            prosody_features: flat_prosody,
        })
    }

    /// Detect the primary language of the given text.
    #[wasm_bindgen(js_name = detectLanguage)]
    pub fn detect_language(&self, text: &str) -> String {
        self.phonemizer.detect_primary_language(text).to_string()
    }

    /// Get the list of supported languages.
    ///
    /// Returns the language codes from the model's `language_id_map`
    /// (e.g. `["ja", "en", "zh", ...]`).
    #[wasm_bindgen(js_name = getSupportedLanguages)]
    pub fn get_supported_languages(&self) -> Vec<String> {
        self.phonemizer.languages().to_vec()
    }

    /// Load an external Japanese dictionary from serialized bytes.
    ///
    /// This replaces the initial PassthroughPhonemizer for Japanese with a
    /// full JapanesePhonemizer backed by the provided NAIST-JDIC dictionary.
    ///
    /// The `dict_data` should be a bincode-serialized `Dictionary` blob,
    /// typically fetched from a CDN and cached in IndexedDB.
    ///
    /// # Errors
    ///
    /// Returns `CONFIG_PARSE_ERROR` if the dictionary bytes are invalid.
    #[cfg(feature = "ja-external")]
    #[wasm_bindgen(js_name = setJapaneseDictionary)]
    pub fn set_japanese_dictionary(&mut self, dict_data: &[u8]) -> Result<(), JsValue> {
        let ja_phonemizer =
            JapanesePhonemizer::new_from_serialized_dict(dict_data).map_err(|e| {
                create_wasm_error(
                    ERROR_CONFIG_PARSE,
                    &format!("Failed to load Japanese dictionary: {e}"),
                )
            })?;
        self.phonemizer
            .replace_phonemizer("ja", Box::new(ja_phonemizer));
        Ok(())
    }

    /// Load external Chinese pinyin dictionaries from JSON bytes.
    ///
    /// This replaces the initial PassthroughPhonemizer for Chinese with a
    /// full ChinesePhonemizer backed by the provided pinyin dictionaries.
    ///
    /// - `single_json` — JSON bytes for single-character pinyin dict
    ///   (e.g. `{"19968": "yi1", "19969": "ding1,zheng4", ...}`)
    /// - `phrase_json` — JSON bytes for phrase pinyin dict
    ///   (e.g. `{"一丁不識": [["yī"], ["dīng"], ...], ...}`)
    ///
    /// Typically fetched from a CDN and cached in IndexedDB.
    ///
    /// # Errors
    ///
    /// Returns `CONFIG_PARSE_ERROR` if the dictionary JSON is invalid.
    #[cfg(any(feature = "zh", feature = "zh-external"))]
    #[wasm_bindgen(js_name = setChineseDictionary)]
    pub fn set_chinese_dictionary(
        &mut self,
        single_json: &[u8],
        phrase_json: &[u8],
    ) -> Result<(), JsValue> {
        let zh_phonemizer =
            ChinesePhonemizer::from_json_bytes(single_json, phrase_json).map_err(|e| {
                create_wasm_error(
                    ERROR_CONFIG_PARSE,
                    &format!("Failed to load Chinese dictionary: {e}"),
                )
            })?;
        self.phonemizer
            .replace_phonemizer("zh", Box::new(zh_phonemizer));
        Ok(())
    }
}

// ===========================================================================
// Test helpers (shared by native + WASM test modules)
// ===========================================================================

/// Minimal JA+EN config for basic tests.
#[cfg(test)]
fn make_test_config() -> String {
    serde_json::json!({
        "audio": {"sample_rate": 22050},
        "num_speakers": 1,
        "num_languages": 2,
        "phoneme_type": "espeak",
        "phoneme_id_map": {
            "^": [1],
            "_": [0],
            "$": [2],
            "a": [15],
            "k": [30],
            "o": [40],
            "N": [22],
            "\u{E000}": [45],
            "\u{E001}": [46]
        },
        "language_id_map": {
            "ja": 0,
            "en": 1
        }
    })
    .to_string()
}

/// Full 8-language config with broad character-level phoneme_id_map covering
/// Latin, CJK, Hangul, diacritics, and special tokens used by the various
/// language phonemizers and passthrough tokenization.
#[cfg(test)]
fn make_multilingual_config() -> String {
    let mut id_map = serde_json::Map::new();
    // Special tokens
    id_map.insert("^".into(), serde_json::json!([1]));
    id_map.insert("_".into(), serde_json::json!([0]));
    id_map.insert("$".into(), serde_json::json!([2]));
    // PUA tokens used by JA phonemizer
    id_map.insert("\u{E000}".into(), serde_json::json!([45]));
    id_map.insert("\u{E001}".into(), serde_json::json!([46]));

    // Latin letters (a-z) for EN/ES/FR/PT/SV passthrough and phonemizer output
    for (i, c) in ('a'..='z').enumerate() {
        id_map.insert(c.to_string(), serde_json::json!([100 + i as i64]));
    }
    // Uppercase Latin (A-Z) for passthrough
    for (i, c) in ('A'..='Z').enumerate() {
        id_map.insert(c.to_string(), serde_json::json!([130 + i as i64]));
    }
    // Common punctuation and whitespace
    for (i, c) in [' ', '.', ',', '!', '?', '-', '\'', '"', ':', ';', '(', ')']
        .iter()
        .enumerate()
    {
        id_map.insert(c.to_string(), serde_json::json!([200 + i as i64]));
    }
    // Digits 0-9
    for d in '0'..='9' {
        id_map.insert(
            d.to_string(),
            serde_json::json!([160 + (d as i64 - '0' as i64)]),
        );
    }
    // Common JA phoneme tokens (output of JapanesePhonemizer)
    for (i, tok) in ["k", "o", "N", "n", "i", "ch", "w", "a", "h"]
        .iter()
        .enumerate()
    {
        id_map
            .entry(tok.to_string())
            .or_insert(serde_json::json!([30 + i as i64]));
    }
    // Korean Hangul sample codepoints (KoreanPhonemizer output / passthrough)
    for (i, cp) in ['\u{AC00}', '\u{B098}', '\u{B2E4}', '\u{D55C}', '\u{AE00}']
        .iter()
        .enumerate()
    {
        id_map.insert(cp.to_string(), serde_json::json!([300 + i as i64]));
    }
    // Japanese Hiragana / Katakana / Kanji used in tests (passthrough)
    for (i, cp) in [
        '\u{4ECA}', '\u{65E5}', '\u{306F}', '\u{3067}', '\u{3059}', // 今日はです
        '\u{3053}', '\u{3093}', '\u{306B}', '\u{3061}', // こんにち
        '\u{6771}', '\u{4EAC}', '\u{30BF}', '\u{30EF}', '\u{30FC}', // 東京タワー
    ]
    .iter()
    .enumerate()
    {
        id_map.insert(cp.to_string(), serde_json::json!([250 + i as i64]));
    }
    // Chinese character samples (passthrough)
    for (i, cp) in ['\u{4F60}', '\u{597D}', '\u{5417}'].iter().enumerate() {
        id_map.insert(cp.to_string(), serde_json::json!([350 + i as i64]));
    }
    // Spanish-specific diacritics
    for (i, c) in [
        '\u{00E1}', '\u{00E9}', '\u{00ED}', '\u{00F3}', '\u{00FA}', '\u{00F1}', '\u{00BF}',
        '\u{00A1}',
    ]
    .iter()
    .enumerate()
    {
        id_map.insert(c.to_string(), serde_json::json!([400 + i as i64]));
    }
    // French-specific diacritics
    for (i, c) in [
        '\u{00E0}', '\u{00E8}', '\u{00EA}', '\u{00EB}', '\u{00E7}', '\u{00F9}', '\u{00FB}',
        '\u{00F4}', '\u{00EE}', '\u{00EF}',
    ]
    .iter()
    .enumerate()
    {
        id_map
            .entry(c.to_string())
            .or_insert(serde_json::json!([420 + i as i64]));
    }
    // Portuguese-specific diacritics
    for (i, c) in ['\u{00E3}', '\u{00F5}', '\u{00E2}'].iter().enumerate() {
        id_map
            .entry(c.to_string())
            .or_insert(serde_json::json!([440 + i as i64]));
    }
    // Swedish-specific characters
    for (i, c) in ['\u{00E5}', '\u{00E4}', '\u{00F6}'].iter().enumerate() {
        id_map
            .entry(c.to_string())
            .or_insert(serde_json::json!([460 + i as i64]));
    }

    serde_json::json!({
        "audio": {"sample_rate": 22050},
        "num_speakers": 1,
        "num_languages": 8,
        "phoneme_type": "multilingual",
        "phoneme_id_map": id_map,
        "language_id_map": {
            "ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5, "sv": 6, "ko": 7
        }
    })
    .to_string()
}

// ===========================================================================
// Native tests (run with `cargo test -p piper-plus-wasm`)
// ===========================================================================
// NOTE: Error-path tests that trigger `create_wasm_error()` /
// `js_sys::Error::new()` panic on non-wasm targets and therefore live in
// the `wasm_tests` module below (gated on `target_arch = "wasm32"`).

#[cfg(test)]
mod tests {
    use super::*;

    // -------------------------------------------------------------------
    // Constructor tests
    // -------------------------------------------------------------------

    #[test]
    fn test_constructor_valid_config() {
        let config = make_test_config();
        let result = WasmPhonemizer::new(&config);
        assert!(result.is_ok());
    }

    #[test]
    fn test_constructor_multilingual_config() {
        let config = make_multilingual_config();
        let result = WasmPhonemizer::new(&config);
        assert!(result.is_ok());
        let p = result.unwrap();
        assert_eq!(p.get_supported_languages().len(), 8);
    }

    // -------------------------------------------------------------------
    // Language detection tests
    // -------------------------------------------------------------------

    #[test]
    fn test_detect_language_ja() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("こんにちは"), "ja");
    }

    #[test]
    fn test_detect_language_en() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("Hello world"), "en");
    }

    #[test]
    fn test_detect_language_zh() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("你好世界"), "zh");
    }

    #[test]
    fn test_detect_language_ko() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("한국어 텍스트"), "ko");
    }

    #[test]
    fn test_detect_language_defaults_to_latin() {
        // Purely Latin text falls back to the default Latin language (EN).
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("abc"), "en");
    }

    // -------------------------------------------------------------------
    // Prosody alignment tests
    // -------------------------------------------------------------------

    #[test]
    fn test_phonemize_result_prosody_alignment() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちは", None).unwrap();
        assert_eq!(result.prosody_features.len(), result.phoneme_ids.len() * 3,);
    }

    #[test]
    fn test_phonemize_prosody_divisible_by_three() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Hello", None).unwrap();
        assert_eq!(result.prosody_features.len() % 3, 0);
        assert_eq!(result.prosody_features.len(), result.phoneme_ids.len() * 3,);
    }

    // -------------------------------------------------------------------
    // Supported languages tests
    // -------------------------------------------------------------------

    #[test]
    fn test_get_supported_languages() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let langs = p.get_supported_languages();
        assert_eq!(langs.len(), 2);
        assert!(langs.contains(&"ja".to_string()));
        assert!(langs.contains(&"en".to_string()));
    }

    #[test]
    fn test_get_supported_languages_all_eight() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let langs = p.get_supported_languages();
        assert_eq!(langs.len(), 8);
        for code in &["ja", "en", "zh", "es", "fr", "pt", "sv", "ko"] {
            assert!(
                langs.contains(&code.to_string()),
                "missing language: {code}",
            );
        }
    }

    // -------------------------------------------------------------------
    // Language hint tests
    // -------------------------------------------------------------------

    #[test]
    fn test_phonemize_with_language_hint() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちは", Some("ja".to_string()));
        assert!(result.is_ok());
    }

    // NOTE: test_phonemize_with_mismatched_hint is in the wasm_tests module
    // because a mismatched hint triggers `log::warn!` via wasm-logger which
    // calls into JS — panics on non-wasm targets.

    // -------------------------------------------------------------------
    // Per-language basic phonemization tests
    // -------------------------------------------------------------------

    #[test]
    fn test_phonemize_japanese() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちは", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
        assert!(result.phoneme_ids.len() >= 3); // BOS + content + EOS minimum
    }

    #[test]
    fn test_phonemize_english() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Hello world", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
        assert!(result.phoneme_ids.len() >= 3);
    }

    #[test]
    fn test_phonemize_chinese() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("你好", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    #[test]
    fn test_phonemize_korean() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("한글", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    #[test]
    fn test_phonemize_spanish() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Hola mundo", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    #[test]
    fn test_phonemize_french() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Bonjour le monde", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    #[test]
    fn test_phonemize_portuguese() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Bom dia", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    #[test]
    fn test_phonemize_swedish() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Hej världen", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    // -------------------------------------------------------------------
    // Mixed language text
    // -------------------------------------------------------------------

    #[test]
    fn test_phonemize_mixed_ja_en() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちはWorld", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
        assert_eq!(result.prosody_features.len(), result.phoneme_ids.len() * 3,);
    }

    #[test]
    fn test_phonemize_mixed_ja_zh_en() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("Hello 你好 こんにちは", None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    // -------------------------------------------------------------------
    // Long input tests
    // -------------------------------------------------------------------

    #[test]
    fn test_phonemize_long_input() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let sentence = "This is a test sentence for long input handling. ";
        let long_text: String = sentence.repeat(25); // ~1250 chars
        assert!(long_text.len() > 1000);
        let result = p.phonemize(&long_text, None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
        assert_eq!(result.prosody_features.len(), result.phoneme_ids.len() * 3,);
    }

    #[test]
    fn test_phonemize_long_japanese_input() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let sentence = "これはテストです。";
        let long_text: String = sentence.repeat(120); // ~1080 chars
        assert!(long_text.len() > 1000);
        let result = p.phonemize(&long_text, None).unwrap();
        assert!(!result.phoneme_ids.is_empty());
    }

    // -------------------------------------------------------------------
    // Multiple instances test
    // -------------------------------------------------------------------

    #[test]
    fn test_multiple_instances_independent() {
        let config_a = make_test_config();
        let config_b = make_multilingual_config();
        let p_a = WasmPhonemizer::new(&config_a).unwrap();
        let p_b = WasmPhonemizer::new(&config_b).unwrap();

        assert_eq!(p_a.get_supported_languages().len(), 2);
        assert_eq!(p_b.get_supported_languages().len(), 8);

        let result_a = p_a.phonemize("こんにちは", None).unwrap();
        let result_b = p_b.phonemize("こんにちは", None).unwrap();
        assert!(!result_a.phoneme_ids.is_empty());
        assert!(!result_b.phoneme_ids.is_empty());
    }

    // -------------------------------------------------------------------
    // PhonemizeResult accessor tests
    // -------------------------------------------------------------------

    #[test]
    fn test_phonemize_result_accessors() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちは", None).unwrap();
        assert_eq!(result.phoneme_count(), result.phoneme_ids().len());
        // Getters return cloned data — calling twice yields equal results
        let ids_1 = result.phoneme_ids();
        let ids_2 = result.phoneme_ids();
        assert_eq!(ids_1, ids_2);
    }

    // -------------------------------------------------------------------
    // API version test
    // -------------------------------------------------------------------

    #[test]
    fn test_get_api_version() {
        let version = get_api_version();
        assert!(!version.is_empty());
        assert!(
            version.contains('.'),
            "version string should be semver: {version}",
        );
    }

    // -------------------------------------------------------------------
    // Golden-file phoneme accuracy tests
    // -------------------------------------------------------------------
    // These tests pin the current phonemization output so that regressions
    // in G2P, token mapping, or post-processing are caught immediately.

    #[test]
    fn test_golden_japanese_konnichiwa() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p
            .phonemize("\u{3053}\u{3093}\u{306B}\u{3061}\u{306F}", None)
            .unwrap();
        let ids = result.phoneme_ids();
        assert!(
            ids.len() >= 3,
            "Expected at least BOS + phoneme + EOS, got {}",
            ids.len()
        );
        assert_eq!(ids[0], 1, "First ID should be BOS (^)");
        assert_eq!(ids[ids.len() - 1], 2, "Last ID should be EOS ($)");
        // Verify determinism: phonemizing the same input twice yields identical IDs
        let result2 = p
            .phonemize("\u{3053}\u{3093}\u{306B}\u{3061}\u{306F}", None)
            .unwrap();
        assert_eq!(
            ids,
            result2.phoneme_ids(),
            "Phonemization should be deterministic"
        );
    }

    #[test]
    fn test_golden_japanese_tokyo_tower() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p
            .phonemize("\u{6771}\u{4EAC}\u{30BF}\u{30EF}\u{30FC}", None)
            .unwrap();
        let ids = result.phoneme_ids();
        assert!(
            ids.len() >= 3,
            "Expected at least BOS + phoneme + EOS, got {}",
            ids.len()
        );
        assert_eq!(ids[0], 1, "First ID should be BOS (^)");
        assert_eq!(ids[ids.len() - 1], 2, "Last ID should be EOS ($)");
        // Tokyo Tower is longer than konnichiwa — verify it produces more tokens
        let konnichiwa = p
            .phonemize("\u{3053}\u{3093}\u{306B}\u{3061}\u{306F}", None)
            .unwrap();
        assert!(
            ids.len() >= konnichiwa.phoneme_ids().len(),
            "Tokyo Tower ({} tokens) should produce at least as many tokens as konnichiwa ({})",
            ids.len(),
            konnichiwa.phoneme_ids().len(),
        );
    }

    #[test]
    fn test_golden_english_hello() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("hello", None).unwrap();
        let ids = result.phoneme_ids();
        assert!(
            ids.len() >= 3,
            "Expected at least BOS + phoneme + EOS, got {}",
            ids.len()
        );
        assert_eq!(ids[0], 1, "First ID should be BOS (^)");
        assert_eq!(ids[ids.len() - 1], 2, "Last ID should be EOS ($)");
        // Determinism check
        let result2 = p.phonemize("hello", None).unwrap();
        assert_eq!(
            ids,
            result2.phoneme_ids(),
            "Phonemization should be deterministic"
        );
    }

    #[test]
    fn test_golden_mixed_ja_en() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        // "今日はgood dayです" — mixed JA + EN text
        let result = p
            .phonemize("\u{4ECA}\u{65E5}\u{306F}good day\u{3067}\u{3059}", None)
            .unwrap();
        let ids = result.phoneme_ids();
        assert!(
            ids.len() >= 3,
            "Expected at least BOS + phoneme + EOS, got {}",
            ids.len()
        );
        assert_eq!(ids[0], 1, "First ID should be BOS (^)");
        assert_eq!(ids[ids.len() - 1], 2, "Last ID should be EOS ($)");
        // Mixed text should produce more tokens than pure JA or pure EN alone
        let ja_only = p.phonemize("\u{4ECA}\u{65E5}\u{306F}", None).unwrap();
        let en_only = p.phonemize("good day", None).unwrap();
        assert!(
            ids.len() > ja_only.phoneme_ids().len(),
            "Mixed text ({} tokens) should be longer than JA-only ({})",
            ids.len(),
            ja_only.phoneme_ids().len(),
        );
        assert!(
            ids.len() > en_only.phoneme_ids().len(),
            "Mixed text ({} tokens) should be longer than EN-only ({})",
            ids.len(),
            en_only.phoneme_ids().len(),
        );
    }

    // NOTE: Empty-string and whitespace-only error tests live in the
    // `wasm_tests` module because the error path calls `js_sys::Error::new()`
    // which panics on non-wasm targets.

    #[test]
    fn test_golden_prosody_alignment_invariant() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        // Verify the prosody_features.len() == phoneme_ids.len() * 3 invariant
        // across multiple languages and inputs.
        let cases = vec![
            "\u{3053}\u{3093}\u{306B}\u{3061}\u{306F}", // Japanese
            "hello",                                    // English
            "\u{4ECA}\u{65E5}\u{306F}good day\u{3067}\u{3059}", // Mixed JA+EN
            "\u{6771}\u{4EAC}\u{30BF}\u{30EF}\u{30FC}", // Japanese (katakana)
            "Hola mundo",                               // Spanish
            "Bonjour",                                  // French
        ];
        for text in &cases {
            let result = p.phonemize(text, None).unwrap();
            assert_eq!(
                result.prosody_features().len(),
                result.phoneme_ids().len() * 3,
                "Prosody alignment violated for input '{}': prosody={} != ids*3={}",
                text,
                result.prosody_features().len(),
                result.phoneme_ids().len() * 3,
            );
        }
    }

    // -------------------------------------------------------------------
    // External dictionary tests (ja-external feature)
    // -------------------------------------------------------------------

    #[cfg(feature = "ja-external")]
    #[test]
    fn test_ja_external_starts_with_passthrough() {
        // With ja-external (not ja), JA starts as PassthroughPhonemizer.
        // Phonemizing JA text should still work (character-level fallback).
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("あ", None).unwrap();
        assert!(
            !result.phoneme_ids.is_empty(),
            "passthrough should produce some IDs"
        );
    }

    #[cfg(feature = "ja-external")]
    #[test]
    fn test_set_japanese_dictionary_invalid_data() {
        // set_japanese_dictionary with invalid data should return Err.
        // Note: This test only works in native mode because create_wasm_error panics on non-wasm.
        // We test the underlying deserialization directly.
        use piper_plus_g2p::japanese::JapanesePhonemizer;
        let result = JapanesePhonemizer::new_from_serialized_dict(b"invalid bincode data");
        assert!(result.is_err(), "invalid dict data should fail");
    }
}

// ===========================================================================
// WASM-bindgen tests (run with `wasm-pack test --headless --chrome`)
// ===========================================================================
// These tests execute in a real WASM runtime and exercise the full
// wasm-bindgen boundary including `js_sys::Error` creation, the `.code`
// property on error objects, and `log::warn!` via wasm-logger.
//
// `js_sys::Error::new()` panics on non-wasm targets, so all error-path
// tests live here under the `target_arch = "wasm32"` gate.

#[cfg(test)]
#[cfg(target_arch = "wasm32")]
mod wasm_tests {
    use super::*;
    use wasm_bindgen_test::*;

    // NOTE: run_in_browser is NOT set — these tests run in Node.js via
    // `wasm-pack test --node`, which avoids WebDriver/chromedriver issues.
    // None of these tests use browser-specific APIs (DOM, fetch, etc.).

    // -------------------------------------------------------------------
    // Constructor tests
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_phonemizer_valid_config() {
        let config = make_test_config();
        let result = WasmPhonemizer::new(&config);
        assert!(
            result.is_ok(),
            "constructor should succeed with valid config"
        );
    }

    #[wasm_bindgen_test]
    fn test_wasm_phonemizer_invalid_json() {
        let result = WasmPhonemizer::new("{invalid json!!!}");
        assert!(result.is_err(), "constructor should fail on invalid JSON");
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "CONFIG_PARSE_ERROR");
    }

    #[wasm_bindgen_test]
    fn test_wasm_phonemizer_empty_language_map() {
        let config = serde_json::json!({
            "audio": {"sample_rate": 22050},
            "phoneme_id_map": {"^": [1], "_": [0], "$": [2]},
            "language_id_map": {}
        })
        .to_string();
        let result = WasmPhonemizer::new(&config);
        assert!(result.is_err(), "empty language_id_map should error");
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "CONFIG_PARSE_ERROR");
    }

    #[wasm_bindgen_test]
    fn test_wasm_phonemizer_missing_phoneme_id_map() {
        // phoneme_id_map defaults to empty HashMap via serde; validate() now
        // rejects this because required markers (^, _, $) are missing.
        let config = serde_json::json!({
            "audio": {"sample_rate": 22050},
            "language_id_map": {"ja": 0}
        })
        .to_string();
        let result = WasmPhonemizer::new(&config);
        assert!(
            result.is_err(),
            "empty phoneme_id_map should error after validate()"
        );
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "CONFIG_PARSE_ERROR");
    }

    // -------------------------------------------------------------------
    // Phonemize success tests
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_phonemize_japanese() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちは", None);
        assert!(result.is_ok(), "JA phonemization should succeed");
        let r = result.unwrap();
        assert!(!r.phoneme_ids.is_empty(), "phoneme_ids should not be empty");
        assert!(
            r.phoneme_ids.len() >= 3,
            "should have at least BOS + content + EOS",
        );
    }

    // -------------------------------------------------------------------
    // Phonemize error tests
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_phonemize_empty_text() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("", None);
        assert!(result.is_err(), "empty text should fail");
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "EMPTY_INPUT");
    }

    #[wasm_bindgen_test]
    fn test_wasm_phonemize_whitespace_only() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("   \t\n  ", None);
        assert!(result.is_err());
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "EMPTY_INPUT");
    }

    // -------------------------------------------------------------------
    // Prosody alignment test
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_prosody_alignment() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("こんにちは", None).unwrap();
        assert_eq!(
            result.prosody_features.len(),
            result.phoneme_ids.len() * 3,
            "prosody_features length must equal phoneme_count * 3",
        );
    }

    // -------------------------------------------------------------------
    // Language detection tests
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_detect_language() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("こんにちは"), "ja");
        assert_eq!(p.detect_language("Hello world"), "en");
    }

    #[wasm_bindgen_test]
    fn test_wasm_detect_language_multilingual() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        assert_eq!(p.detect_language("你好"), "zh");
        assert_eq!(p.detect_language("한국어"), "ko");
        assert_eq!(p.detect_language("こんにちは"), "ja");
    }

    // -------------------------------------------------------------------
    // Supported languages test
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_supported_languages() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let langs = p.get_supported_languages();
        assert_eq!(langs.len(), 8);
        for code in &["ja", "en", "zh", "es", "fr", "pt", "sv", "ko"] {
            assert!(
                langs.contains(&code.to_string()),
                "missing language: {code}",
            );
        }
    }

    // -------------------------------------------------------------------
    // Multiple instances test
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_multiple_instances() {
        let config_a = make_test_config();
        let config_b = make_multilingual_config();
        let p_a = WasmPhonemizer::new(&config_a).unwrap();
        let p_b = WasmPhonemizer::new(&config_b).unwrap();

        assert_eq!(p_a.get_supported_languages().len(), 2);
        assert_eq!(p_b.get_supported_languages().len(), 8);

        let r_a = p_a.phonemize("こんにちは", None).unwrap();
        let r_b = p_b.phonemize("こんにちは", None).unwrap();
        assert!(!r_a.phoneme_ids.is_empty());
        assert!(!r_b.phoneme_ids.is_empty());
    }

    // -------------------------------------------------------------------
    // Language hint tests
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_language_hint() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();

        // Matching hint: succeeds
        let result = p.phonemize("こんにちは", Some("ja".to_string()));
        assert!(result.is_ok());

        // Mismatched hint: still succeeds (logs a console warning)
        let result = p.phonemize("こんにちは", Some("en".to_string()));
        assert!(result.is_ok());
    }

    // -------------------------------------------------------------------
    // API version test
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_api_version() {
        let version = get_api_version();
        assert!(!version.is_empty());
        assert!(version.contains('.'), "version should be semver-like");
    }

    // -------------------------------------------------------------------
    // Error structure tests (WASM-only: require real JS Error objects)
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_error_has_message_and_code() {
        let result = WasmPhonemizer::new("<<<not json>>>");
        let err = result.unwrap_err();

        // .code property
        let code = js_sys::Reflect::get(&err, &"code".into()).unwrap();
        assert_eq!(code.as_string().unwrap(), "CONFIG_PARSE_ERROR");

        // .message property (inherited from Error)
        let message = js_sys::Reflect::get(&err, &"message".into()).unwrap();
        let msg_str = message.as_string().unwrap();
        assert!(
            msg_str.contains("config.json"),
            "message should mention config.json: {msg_str}",
        );
    }

    #[wasm_bindgen_test]
    fn test_wasm_empty_input_error_code() {
        let config = make_test_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("", None);
        let err = result.unwrap_err();
        let code = js_sys::Reflect::get(&err, &"code".into()).unwrap();
        assert_eq!(code.as_string().unwrap(), "EMPTY_INPUT");
    }

    // -------------------------------------------------------------------
    // Golden-file error tests (WASM-only: error path uses js_sys::Error)
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_golden_empty_string_error() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("", None);
        assert!(result.is_err(), "Empty string should produce an error");
        let err = result.unwrap_err();
        let code = js_sys::Reflect::get(&err, &"code".into()).unwrap();
        assert_eq!(code.as_string().unwrap(), "EMPTY_INPUT");
    }

    #[wasm_bindgen_test]
    fn test_golden_whitespace_only_error() {
        let config = make_multilingual_config();
        let p = WasmPhonemizer::new(&config).unwrap();
        let result = p.phonemize("   ", None);
        assert!(
            result.is_err(),
            "Whitespace-only string should produce an error"
        );
        let err = result.unwrap_err();
        let code = js_sys::Reflect::get(&err, &"code".into()).unwrap();
        assert_eq!(code.as_string().unwrap(), "EMPTY_INPUT");
    }

    // -------------------------------------------------------------------
    // MS3-3: Config validation tests (validate() integration)
    // -------------------------------------------------------------------

    #[wasm_bindgen_test]
    fn test_wasm_new_invalid_config() {
        // BOS marker (^) missing — validate() should reject
        let config = serde_json::json!({
            "audio": {"sample_rate": 22050},
            "phoneme_id_map": {"_": [0], "$": [2], "a": [15]},
            "language_id_map": {"ja": 0, "en": 1}
        })
        .to_string();
        let result = WasmPhonemizer::new(&config);
        assert!(result.is_err(), "missing BOS should fail validation");
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "CONFIG_PARSE_ERROR");
    }

    #[wasm_bindgen_test]
    fn test_wasm_new_valid_config() {
        // Fully valid config with all required markers
        let config = make_test_config();
        let result = WasmPhonemizer::new(&config);
        assert!(result.is_ok(), "valid config should succeed");
        let p = result.unwrap();
        assert_eq!(p.get_supported_languages().len(), 2);
    }

    // -------------------------------------------------------------------
    // External dictionary tests (ja-external feature)
    // -------------------------------------------------------------------

    #[cfg(feature = "ja-external")]
    #[wasm_bindgen_test]
    fn test_wasm_set_japanese_dictionary_invalid_data() {
        let config = make_test_config();
        let mut p = WasmPhonemizer::new(&config).unwrap();
        let result = p.set_japanese_dictionary(&[0, 1, 2, 3]);
        assert!(result.is_err(), "invalid dict data should return error");
        let err = result.unwrap_err();
        let code =
            js_sys::Reflect::get(&err, &"code".into()).expect("error should have a code property");
        assert_eq!(code.as_string().unwrap(), "CONFIG_PARSE_ERROR");
    }

    #[cfg(feature = "ja-external")]
    #[wasm_bindgen_test]
    fn test_wasm_set_japanese_dictionary_empty_data() {
        let config = make_test_config();
        let mut p = WasmPhonemizer::new(&config).unwrap();
        let result = p.set_japanese_dictionary(&[]);
        assert!(result.is_err(), "empty dict data should return error");
    }
}

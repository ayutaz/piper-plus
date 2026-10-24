//! C FFI for piper-plus-g2p — foundation for mobile (UniFFI) bindings.

use std::collections::HashMap;
use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::panic::AssertUnwindSafe;
use std::ptr;
use std::sync::Arc;

use crate::G2pError;
use crate::multilingual::MultilingualPhonemizer;
use crate::phonemizer::{Phonemizer, ProsodyInfo};

/// Opaque handle to a multilingual phonemizer over the registered languages.
pub struct PiperG2pHandle {
    phonemizer: MultilingualPhonemizer,
    /// The Japanese phonemizer of `phonemizer`, which reads Japanese text
    /// whole: the multilingual phonemizer would drop its question-type EOS
    /// ("?", "?!", ...) and read kanji without kana as Chinese.
    japanese: Option<Arc<dyn Phonemizer>>,
}

/// A phonemizer the handle shares with its multilingual phonemizer.
struct SharedPhonemizer(Arc<dyn Phonemizer>);

impl Phonemizer for SharedPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        self.0.phonemize_with_prosody(text)
    }

    fn language_code(&self) -> &str {
        self.0.language_code()
    }
}

/// Create a new G2P handle. Returns NULL on failure.
///
/// # Safety
/// `languages` must be a valid null-terminated UTF-8 string or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_plus_g2p_create(languages: *const c_char) -> *mut PiperG2pHandle {
    let result = std::panic::catch_unwind(|| {
        let langs: Vec<&str> = if languages.is_null() {
            default_languages()
        } else {
            match unsafe { CStr::from_ptr(languages) }.to_str() {
                Ok("") => default_languages(),
                Ok(s) => s.split(',').map(str::trim).collect(),
                Err(_) => return ptr::null_mut(),
            }
        };
        let mut registered: Vec<String> = Vec::new();
        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        let mut japanese = None;
        for lang in langs {
            if phonemizers.contains_key(lang) {
                continue;
            }
            let Ok(mut p) = new_phonemizer(lang) else {
                continue;
            };
            if lang == "ja" {
                let shared: Arc<dyn Phonemizer> = Arc::from(p);
                japanese = Some(Arc::clone(&shared));
                p = Box::new(SharedPhonemizer(shared));
            }
            registered.push(lang.to_string());
            phonemizers.insert(lang.to_string(), p);
        }
        // Latin letters in text of a non-Latin language go to English, or to
        // the first registered language without it, as in Python.
        let phonemizer = MultilingualPhonemizer::new(registered, "en".into(), phonemizers);
        Box::into_raw(Box::new(PiperG2pHandle {
            phonemizer,
            japanese,
        }))
    });
    result.unwrap_or(ptr::null_mut())
}

/// Phonemize text, returning JSON: `{"tokens":[...],"language":".."}`.
/// Caller must free result with `piper_plus_g2p_free_string`.
///
/// # Safety
/// All pointer args must be valid null-terminated UTF-8 or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_plus_g2p_phonemize(
    handle: *const PiperG2pHandle,
    text: *const c_char,
    language: *const c_char,
) -> *mut c_char {
    if handle.is_null() || text.is_null() {
        return ptr::null_mut();
    }
    let result = std::panic::catch_unwind(AssertUnwindSafe(|| {
        let h = unsafe { &*handle };
        let text = unsafe { CStr::from_ptr(text) }.to_str().ok()?;
        let lang = if language.is_null() {
            "en"
        } else {
            unsafe { CStr::from_ptr(language) }.to_str().ok()?
        };
        if !h.phonemizer.languages().iter().any(|l| l == lang) {
            return None;
        }
        // Japanese text goes whole to the Japanese phonemizer (see
        // `PiperG2pHandle::japanese`). Other languages are split by script as
        // in Python's MultilingualPhonemizer, with Latin letters read as
        // `lang` when it is a Latin-script language. Latin letters next to Chinese are read as
        // pinyin when English is registered (Issue #827), and CJK punctuation
        // in a Latin-script segment is read as ASCII (Issue #823).
        let (tokens, _) = match (&h.japanese, lang) {
            (Some(japanese), "ja") => japanese.phonemize_with_prosody(text),
            _ => h.phonemizer.phonemize_with_language(text, lang),
        }
        .ok()?;
        let json = serde_json::json!({"tokens": tokens, "language": lang});
        CString::new(json.to_string()).ok()
    }));
    match result {
        Ok(Some(s)) => s.into_raw(),
        _ => ptr::null_mut(),
    }
}

/// Free a string from piper_plus_g2p functions.
/// # Safety
/// `ptr` must be from a piper_plus_g2p function, or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_plus_g2p_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        unsafe {
            drop(CString::from_raw(ptr));
        }
    }
}

/// Destroy a G2P handle.
/// # Safety
/// `handle` must be from `piper_plus_g2p_create`, or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_plus_g2p_free(handle: *mut PiperG2pHandle) {
    if !handle.is_null() {
        unsafe {
            drop(Box::from_raw(handle));
        }
    }
}

/// Get available languages as comma-separated string.
/// # Safety
/// `handle` must be valid or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_plus_g2p_available_languages(
    handle: *const PiperG2pHandle,
) -> *mut c_char {
    if handle.is_null() {
        return ptr::null_mut();
    }
    let result = std::panic::catch_unwind(AssertUnwindSafe(|| {
        let h = unsafe { &*handle };
        let joined = h.phonemizer.languages().join(",");
        CString::new(joined).ok()
    }));
    match result {
        Ok(Some(s)) => s.into_raw(),
        _ => ptr::null_mut(),
    }
}

/// Default languages for `piper_plus_g2p_create(NULL)`.
///
/// Always includes rule-based languages (`es`, `fr`, `pt`, `sv`).
/// `en` is included whenever the `english` feature is on (file lookup
/// without `bundled-dicts`, embedded JSON with it).
/// `ko` (rule-based) is included when `korean` is on.
/// `zh` is included only when both `chinese` and `bundled-dicts` are on,
/// because path-based init would otherwise fail at runtime on iOS.
/// `ja` requires either `naist-jdic` (bundled NAIST-JDIC) or
/// `japanese` + `bundled-dicts`.
#[allow(unused_mut, clippy::vec_init_then_push)]
fn default_languages() -> Vec<&'static str> {
    let mut langs: Vec<&'static str> = Vec::new();
    #[cfg(feature = "english")]
    langs.push("en");
    #[cfg(feature = "spanish")]
    langs.push("es");
    #[cfg(feature = "french")]
    langs.push("fr");
    #[cfg(feature = "portuguese")]
    langs.push("pt");
    #[cfg(feature = "swedish")]
    langs.push("sv");
    #[cfg(feature = "korean")]
    langs.push("ko");
    #[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
    langs.push("zh");
    #[cfg(any(
        feature = "naist-jdic",
        all(feature = "japanese", feature = "bundled-dicts")
    ))]
    langs.push("ja");
    langs
}

fn new_phonemizer(lang: &str) -> Result<Box<dyn Phonemizer>, G2pError> {
    Ok(match lang {
        #[cfg(all(feature = "english", feature = "bundled-dicts"))]
        "en" => Box::new(crate::english::EnglishPhonemizer::new_bundled()?),
        #[cfg(all(feature = "english", not(feature = "bundled-dicts")))]
        "en" => Box::new(crate::english::EnglishPhonemizer::new()?),
        #[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
        "zh" => Box::new(crate::chinese::ChinesePhonemizer::new_bundled()?),
        #[cfg(all(feature = "chinese", not(feature = "bundled-dicts")))]
        "zh" => {
            return Err(G2pError::Phonemize(
                "Chinese requires bundled-dicts feature or use from_dicts() directly".into(),
            ));
        }
        #[cfg(feature = "korean")]
        "ko" => Box::new(crate::korean::KoreanPhonemizer::new()),
        #[cfg(feature = "spanish")]
        "es" => Box::new(crate::spanish::SpanishPhonemizer::new()),
        #[cfg(feature = "french")]
        "fr" => Box::new(crate::french::FrenchPhonemizer::new()),
        #[cfg(feature = "portuguese")]
        "pt" => Box::new(crate::portuguese::PortuguesePhonemizer::new()),
        #[cfg(feature = "swedish")]
        "sv" => Box::new(crate::swedish::SwedishPhonemizer::new()),
        #[cfg(feature = "naist-jdic")]
        "ja" => Box::new(crate::japanese::JapanesePhonemizer::new_bundled()?),
        #[cfg(all(feature = "japanese", not(feature = "naist-jdic")))]
        "ja" => Box::new(crate::japanese::JapanesePhonemizer::new()?),
        _ => {
            return Err(G2pError::UnsupportedLanguage {
                code: lang.to_string(),
            });
        }
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::{CStr, CString};

    // -----------------------------------------------------------------------
    // Chinese FFI tests (bundled-dicts feature)
    // -----------------------------------------------------------------------

    #[test]
    #[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
    fn test_ffi_create_with_chinese_bundled() {
        let lang = CString::new("zh").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(
                !handle.is_null(),
                "handle should not be NULL for 'zh' with bundled-dicts"
            );
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
    fn test_ffi_phonemize_chinese_bundled() {
        let lang = CString::new("zh").unwrap();
        let text = CString::new("你好").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null(), "phonemize result should not be NULL");

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(s.contains("\"tokens\""));
            assert!(s.contains("\"language\":\"zh\""));

            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(all(feature = "english", feature = "bundled-dicts"))]
    fn test_ffi_phonemize_english_bundled() {
        let lang = CString::new("en").unwrap();
        let text = CString::new("Hello").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(
                !result.is_null(),
                "english phonemize with bundled-dicts must succeed"
            );

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(s.contains("\"language\":\"en\""));

            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
        }
    }

    /// Tokens JSON of `piper_plus_g2p_phonemize(text, lang)`.
    #[cfg(any(
        feature = "spanish",
        all(feature = "english", feature = "bundled-dicts")
    ))]
    fn ffi_tokens(lang: &str, text: &str) -> String {
        let lang = CString::new(lang).unwrap();
        let text = CString::new(text).unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null());
            let s = CStr::from_ptr(result).to_str().unwrap().to_owned();
            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
            s
        }
    }

    // CJK punctuation in text of a Latin-script language is read as ASCII
    // (Issue #823, docs/spec/cjk-punctuation-contract.toml). Swift's
    // PiperPlusG2P uses the FFI.
    #[test]
    #[cfg(all(feature = "english", feature = "bundled-dicts"))]
    fn test_ffi_english_reads_cjk_punctuation_like_ascii() {
        assert_eq!(
            ffi_tokens("en", "Hello，world"),
            ffi_tokens("en", "Hello,world")
        );
        assert_eq!(
            ffi_tokens("en", "Hello、world。"),
            ffi_tokens("en", "Hello,world.")
        );
        assert_eq!(
            ffi_tokens("en", "I have ３ cats．"),
            ffi_tokens("en", "I have 3 cats.")
        );
    }

    #[test]
    #[cfg(feature = "spanish")]
    fn test_ffi_spanish_reads_cjk_punctuation_like_ascii() {
        assert_eq!(
            ffi_tokens("es", "Hola，amigo！"),
            ffi_tokens("es", "Hola,amigo!")
        );
    }

    /// Tokens of `piper_plus_g2p_phonemize(text, lang)` on a handle created
    /// with `languages`.
    #[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
    fn ffi_token_list(languages: &str, lang: &str, text: &str) -> Vec<String> {
        let languages = CString::new(languages).unwrap();
        let lang = CString::new(lang).unwrap();
        let text = CString::new(text).unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(languages.as_ptr());
            assert!(!handle.is_null());
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null());
            let json: serde_json::Value =
                serde_json::from_str(CStr::from_ptr(result).to_str().unwrap()).unwrap();
            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
            json["tokens"]
                .as_array()
                .unwrap()
                .iter()
                .map(|t| t.as_str().unwrap().to_owned())
                .collect()
        }
    }

    // Latin letters in Chinese text are read as Python's
    // MultilingualPhonemizer reads them: as pinyin when English is registered
    // (ZH-EN dispatch, Issue #384), not as the letters themselves (Issue
    // #827). Swift's PiperPlusG2P names one language per call.
    #[test]
    #[cfg(all(feature = "english", feature = "chinese", feature = "bundled-dicts"))]
    fn test_ffi_chinese_reads_english_letters_as_pinyin_when_english_is_registered() {
        let golden = "aɪ tone1 tʂʰ ɻ̩ tone4 i tone1 aɪ tone1 ɚ tone2 aɪ tone1 ɚ tone2 oʊ tone1 \
                      n i tone2 x aʊ tone3";
        let expected: Vec<String> = golden
            .split(' ')
            .map(|t| crate::token_map::token_to_pua(t).map_or_else(|| t.to_owned(), String::from))
            .collect();
        assert_eq!(ffi_token_list("en,zh", "zh", "Hello你好"), expected);
    }

    // Without English, Python leaves the letters as they are.
    #[test]
    #[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
    fn test_ffi_chinese_keeps_english_letters_when_english_is_not_registered() {
        let tokens = ffi_token_list("zh", "zh", "Hello你好");
        assert_eq!(tokens[..5], ["H", "e", "l", "l", "o"]);
    }

    // Japanese text is read whole by the Japanese phonemizer: it keeps the
    // question-type EOS (Swift's GoldenPhonemeTests checks it), and kanji
    // without kana stay Japanese when Chinese is registered too.
    #[test]
    #[cfg(all(feature = "naist-jdic", feature = "chinese", feature = "bundled-dicts"))]
    fn test_ffi_japanese_is_read_by_the_japanese_phonemizer() {
        let tokens = ffi_token_list("en,ja,zh", "ja", "これは何ですか？");
        assert_eq!(tokens.first().map(String::as_str), Some("^"));
        assert_eq!(tokens.last().map(String::as_str), Some("?"));
        assert_eq!(
            ffi_token_list("en,ja,zh", "ja", "日本語"),
            ffi_token_list("ja", "ja", "日本語")
        );
    }

    // A language the handle has not registered is still refused, even though
    // the multilingual phonemizer could read the text by its script.
    #[test]
    #[cfg(all(feature = "english", feature = "chinese", feature = "bundled-dicts"))]
    fn test_ffi_phonemize_unregistered_language_with_other_languages_registered() {
        let languages = CString::new("en,zh").unwrap();
        let text = CString::new("你好").unwrap();
        let lang = CString::new("es").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(languages.as_ptr());
            assert!(!handle.is_null());
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(result.is_null(), "unregistered 'es' should return NULL");
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(all(feature = "naist-jdic", feature = "bundled-dicts"))]
    fn test_ffi_phonemize_japanese_bundled() {
        let lang = CString::new("ja").unwrap();
        let text = CString::new("こんにちは").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null());

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(s.contains("\"language\":\"ja\""));

            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // Korean FFI tests
    // -----------------------------------------------------------------------

    #[test]
    #[cfg(feature = "korean")]
    fn test_ffi_create_with_korean() {
        let lang = CString::new("ko").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null(), "handle should not be NULL for 'ko'");
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "korean")]
    fn test_ffi_phonemize_korean() {
        let lang = CString::new("ko").unwrap();
        let text = CString::new("가").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null(), "phonemize result should not be NULL");

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(!s.is_empty(), "phonemize result should not be empty");
            // Result is JSON with "tokens" and "language" keys
            assert!(s.contains("\"tokens\""), "result should contain tokens key");
            assert!(
                s.contains("\"language\""),
                "result should contain language key"
            );

            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "korean")]
    fn test_ffi_korean_available_languages() {
        let lang = CString::new("ko").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let langs_ptr = piper_plus_g2p_available_languages(handle);
            assert!(!langs_ptr.is_null());

            let langs_str = CStr::from_ptr(langs_ptr).to_str().unwrap();
            let langs: Vec<&str> = langs_str.split(',').collect();
            assert!(
                langs.contains(&"ko"),
                "available languages should contain 'ko', got: {langs_str}"
            );

            piper_plus_g2p_free_string(langs_ptr);
            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // Swedish FFI tests
    // -----------------------------------------------------------------------

    #[test]
    #[cfg(feature = "swedish")]
    fn test_ffi_create_with_swedish() {
        let lang = CString::new("sv").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null(), "handle should not be NULL for 'sv'");
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "swedish")]
    fn test_ffi_phonemize_swedish() {
        let lang = CString::new("sv").unwrap();
        let text = CString::new("hej").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null(), "phonemize result should not be NULL");

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(!s.is_empty(), "phonemize result should not be empty");
            assert!(s.contains("\"tokens\""), "result should contain tokens key");
            assert!(
                s.contains("\"language\""),
                "result should contain language key"
            );

            piper_plus_g2p_free_string(result);
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "swedish")]
    fn test_ffi_swedish_available_languages() {
        let lang = CString::new("sv").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let langs_ptr = piper_plus_g2p_available_languages(handle);
            assert!(!langs_ptr.is_null());

            let langs_str = CStr::from_ptr(langs_ptr).to_str().unwrap();
            let langs: Vec<&str> = langs_str.split(',').collect();
            assert!(
                langs.contains(&"sv"),
                "available languages should contain 'sv', got: {langs_str}"
            );

            piper_plus_g2p_free_string(langs_ptr);
            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // NULL pointer tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_ffi_create_null_languages() {
        // NULL languages pointer should succeed (uses default language set)
        unsafe {
            let handle = piper_plus_g2p_create(ptr::null());
            assert!(
                !handle.is_null(),
                "NULL languages should create a handle with defaults"
            );
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    fn test_ffi_phonemize_null_text() {
        let lang = CString::new("en").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            // NULL text should return NULL without crashing
            let result = piper_plus_g2p_phonemize(handle, ptr::null(), lang.as_ptr());
            assert!(result.is_null(), "NULL text should return NULL");

            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    fn test_ffi_phonemize_null_handle() {
        let text = CString::new("hello").unwrap();
        let lang = CString::new("en").unwrap();
        unsafe {
            // NULL handle should return NULL without crashing
            let result = piper_plus_g2p_phonemize(ptr::null(), text.as_ptr(), lang.as_ptr());
            assert!(result.is_null(), "NULL handle should return NULL");
        }
    }

    #[test]
    fn test_ffi_phonemize_null_language() {
        // NULL language defaults to "en" inside piper_plus_g2p_phonemize.
        // Register "en" (plus "es" as fallback) so the test works in environments
        // where the CMU dictionary is available. If "en" fails to register
        // (no dictionary), the result will be NULL — which is still safe.
        let langs = CString::new("en,es").unwrap();
        let text = CString::new("hello").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(langs.as_ptr());
            assert!(!handle.is_null());

            // NULL language triggers the default "en" path — must not crash
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), ptr::null());
            if !result.is_null() {
                let s = CStr::from_ptr(result).to_str().unwrap();
                assert!(
                    s.contains("\"language\":\"en\""),
                    "should default to 'en', got: {s}"
                );
                piper_plus_g2p_free_string(result);
            }
            // If result is NULL, "en" was not registered (no CMU dict) — still safe

            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // Invalid language code tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_ffi_phonemize_unsupported_language() {
        // Create handle with defaults, then try to phonemize with unsupported language
        let lang = CString::new("en").unwrap();
        let text = CString::new("hello").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let unsupported = CString::new("xx").unwrap();
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), unsupported.as_ptr());
            assert!(
                result.is_null(),
                "unsupported language 'xx' should return NULL"
            );

            let invalid = CString::new("invalid").unwrap();
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), invalid.as_ptr());
            assert!(
                result.is_null(),
                "unsupported language 'invalid' should return NULL"
            );

            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    fn test_ffi_create_unsupported_language() {
        // Creating with an unsupported language should still return a handle
        // (new_phonemizer fails for unknown languages and they are skipped)
        let lang = CString::new("xx").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(
                !handle.is_null(),
                "handle should be non-NULL even if language is unsupported"
            );

            // The handle should have no registered languages
            let avail_ptr = piper_plus_g2p_available_languages(handle);
            assert!(!avail_ptr.is_null());
            let avail_str = CStr::from_ptr(avail_ptr).to_str().unwrap();
            assert!(
                avail_str.is_empty(),
                "no languages should be registered, got: {avail_str}"
            );

            piper_plus_g2p_free_string(avail_ptr);
            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    fn test_ffi_phonemize_empty_language() {
        // Empty language string in phonemize should fail (not registered)
        let lang = CString::new("en").unwrap();
        let text = CString::new("hello").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let empty_lang = CString::new("").unwrap();
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), empty_lang.as_ptr());
            assert!(result.is_null(), "empty language code should return NULL");

            piper_plus_g2p_free(handle);
        }
    }

    #[test]
    fn test_ffi_create_empty_language() {
        // Empty string for languages in create should use defaults
        let lang = CString::new("").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(
                !handle.is_null(),
                "empty languages string should use defaults"
            );

            let avail_ptr = piper_plus_g2p_available_languages(handle);
            assert!(!avail_ptr.is_null());
            let avail_str = CStr::from_ptr(avail_ptr).to_str().unwrap();
            assert!(
                !avail_str.is_empty(),
                "defaults should register at least one language"
            );

            piper_plus_g2p_free_string(avail_ptr);
            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // Empty string input tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_ffi_phonemize_empty_text() {
        let lang = CString::new("en").unwrap();
        let text = CString::new("").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            // Empty text: the phonemizer may return NULL or an empty tokens result.
            // Either way it must not crash.
            let result = piper_plus_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            if !result.is_null() {
                piper_plus_g2p_free_string(result);
            }

            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // Memory safety tests (NULL to free functions)
    // -----------------------------------------------------------------------

    #[test]
    fn test_ffi_free_string_null() {
        // Passing NULL to free_string should be a no-op, not crash
        unsafe {
            piper_plus_g2p_free_string(ptr::null_mut());
        }
    }

    #[test]
    fn test_ffi_free_null_handle() {
        // Passing NULL to free should be a no-op, not crash
        unsafe {
            piper_plus_g2p_free(ptr::null_mut());
        }
    }

    #[test]
    fn test_ffi_available_languages_null_handle() {
        // NULL handle should return NULL, not crash
        unsafe {
            let result = piper_plus_g2p_available_languages(ptr::null());
            assert!(
                result.is_null(),
                "NULL handle should return NULL from available_languages"
            );
        }
    }

    // -----------------------------------------------------------------------
    // Combined test
    // -----------------------------------------------------------------------

    #[test]
    #[cfg(all(feature = "korean", feature = "swedish"))]
    fn test_ffi_create_multilingual() {
        let langs = CString::new("ko,sv").unwrap();
        unsafe {
            let handle = piper_plus_g2p_create(langs.as_ptr());
            assert!(!handle.is_null(), "handle should not be NULL for 'ko,sv'");

            let avail_ptr = piper_plus_g2p_available_languages(handle);
            assert!(!avail_ptr.is_null());

            let avail_str = CStr::from_ptr(avail_ptr).to_str().unwrap();
            let avail: Vec<&str> = avail_str.split(',').collect();
            assert!(
                avail.contains(&"ko"),
                "should contain 'ko', got: {avail_str}"
            );
            assert!(
                avail.contains(&"sv"),
                "should contain 'sv', got: {avail_str}"
            );

            // Phonemize Korean text
            let ko_text = CString::new("가").unwrap();
            let ko_lang = CString::new("ko").unwrap();
            let ko_result = piper_plus_g2p_phonemize(handle, ko_text.as_ptr(), ko_lang.as_ptr());
            assert!(!ko_result.is_null(), "Korean phonemize should succeed");
            piper_plus_g2p_free_string(ko_result);

            // Phonemize Swedish text
            let sv_text = CString::new("hej").unwrap();
            let sv_lang = CString::new("sv").unwrap();
            let sv_result = piper_plus_g2p_phonemize(handle, sv_text.as_ptr(), sv_lang.as_ptr());
            assert!(!sv_result.is_null(), "Swedish phonemize should succeed");
            piper_plus_g2p_free_string(sv_result);

            piper_plus_g2p_free_string(avail_ptr);
            piper_plus_g2p_free(handle);
        }
    }

    // -----------------------------------------------------------------------
    // default_languages() — feature-gated default set (commit 44008b8)
    // -----------------------------------------------------------------------

    #[test]
    #[cfg(all(
        feature = "all-languages",
        feature = "naist-jdic",
        feature = "bundled-dicts"
    ))]
    fn test_default_languages_full_feature_set() {
        // With all-languages + naist-jdic + bundled-dicts (the iOS xcframework
        // build configuration), default_languages() must return all 8.
        let langs = default_languages();
        assert_eq!(
            langs.len(),
            8,
            "expected 8 default languages with full feature set, got {langs:?}"
        );
        for expected in &["en", "es", "fr", "pt", "sv", "ko", "zh", "ja"] {
            assert!(
                langs.contains(expected),
                "default_languages() missing {expected}: {langs:?}"
            );
        }
    }

    #[test]
    #[cfg(any(feature = "english", feature = "spanish"))]
    fn test_default_languages_includes_rule_based_when_features_on() {
        // Whatever subset of features is enabled, the rule-based languages
        // present in the build must appear in defaults (no path lookup needed).
        let langs = default_languages();
        #[cfg(feature = "english")]
        assert!(langs.contains(&"en"), "en missing: {langs:?}");
        #[cfg(feature = "spanish")]
        assert!(langs.contains(&"es"), "es missing: {langs:?}");
        #[cfg(feature = "french")]
        assert!(langs.contains(&"fr"), "fr missing: {langs:?}");
        #[cfg(feature = "portuguese")]
        assert!(langs.contains(&"pt"), "pt missing: {langs:?}");
        #[cfg(feature = "swedish")]
        assert!(langs.contains(&"sv"), "sv missing: {langs:?}");
        #[cfg(feature = "korean")]
        assert!(langs.contains(&"ko"), "ko missing: {langs:?}");
    }

    #[test]
    #[cfg(all(feature = "chinese", not(feature = "bundled-dicts")))]
    fn test_default_languages_excludes_zh_without_bundled_dicts() {
        // Without bundled-dicts, ChinesePhonemizer cannot self-init from a
        // path on iOS. default_languages() must NOT include "zh" so that
        // piper_plus_g2p_create(NULL) does not return NULL on every iOS app.
        let langs = default_languages();
        assert!(
            !langs.contains(&"zh"),
            "zh must not be in default without bundled-dicts: {langs:?}"
        );
    }

    // -----------------------------------------------------------------------
    // new_phonemizer() — error paths (commit 44008b8 added cfg gating)
    // -----------------------------------------------------------------------

    #[test]
    fn test_new_phonemizer_unsupported_language() {
        let Err(err) = new_phonemizer("xx") else {
            panic!("xx must fail");
        };
        match err {
            crate::G2pError::UnsupportedLanguage { code } => {
                assert_eq!(code, "xx");
            }
            other => panic!("expected UnsupportedLanguage, got {other:?}"),
        }
    }

    #[test]
    #[cfg(all(feature = "chinese", not(feature = "bundled-dicts")))]
    fn test_new_phonemizer_zh_without_bundled_dicts_returns_phonemize_error() {
        // The path-based zh path is intentionally an error in new_phonemizer
        // because we cannot reasonably ship JSON files alongside an iOS app.
        let Err(err) = new_phonemizer("zh") else {
            panic!("zh without bundled-dicts must fail");
        };
        assert!(matches!(err, crate::G2pError::Phonemize(_)));
    }

    #[test]
    #[cfg(feature = "english")]
    fn test_new_phonemizer_en_succeeds() {
        let p = new_phonemizer("en").expect("en must register");
        assert_eq!(p.language_code(), "en");
    }

    #[test]
    #[cfg(feature = "korean")]
    fn test_new_phonemizer_ko_rule_based_succeeds() {
        // ko is rule-based, no dict needed — must always work when the
        // korean feature is enabled.
        let p = new_phonemizer("ko").expect("ko must register");
        assert_eq!(p.language_code(), "ko");
    }

    #[test]
    #[cfg(all(feature = "naist-jdic", feature = "bundled-dicts"))]
    fn test_new_phonemizer_ja_with_naist_jdic_succeeds() {
        let p = new_phonemizer("ja").expect("ja must register with naist-jdic");
        assert_eq!(p.language_code(), "ja");
    }

    // -----------------------------------------------------------------------
    // create(NULL) returns the same set as default_languages()
    // -----------------------------------------------------------------------

    #[test]
    fn test_create_null_yields_default_set() {
        unsafe {
            let handle = piper_plus_g2p_create(std::ptr::null());
            assert!(
                !handle.is_null(),
                "NULL languages should yield default handle"
            );
            let avail_ptr = piper_plus_g2p_available_languages(handle);
            assert!(!avail_ptr.is_null());
            let avail = CStr::from_ptr(avail_ptr).to_str().unwrap();
            let avail_set: Vec<&str> = avail.split(',').filter(|s| !s.is_empty()).collect();
            let expected = default_languages();
            assert_eq!(
                avail_set.len(),
                expected.len(),
                "available langs ({avail_set:?}) must match default_languages() ({expected:?})"
            );
            for lang in &expected {
                assert!(
                    avail_set.contains(lang),
                    "available langs missing {lang}: {avail:?}"
                );
            }
            piper_plus_g2p_free_string(avail_ptr);
            piper_plus_g2p_free(handle);
        }
    }
}

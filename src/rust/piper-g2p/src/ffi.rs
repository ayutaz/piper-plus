//! C FFI for piper-g2p — foundation for mobile (UniFFI) bindings.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::panic::AssertUnwindSafe;
use std::ptr;

use crate::phonemizer::PhonemizerRegistry;

/// Opaque handle to a PhonemizerRegistry.
pub struct PiperG2pHandle {
    registry: PhonemizerRegistry,
}

/// Create a new G2P handle. Returns NULL on failure.
///
/// # Safety
/// `languages` must be a valid null-terminated UTF-8 string or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_g2p_create(languages: *const c_char) -> *mut PiperG2pHandle {
    let result = std::panic::catch_unwind(|| {
        let mut registry = PhonemizerRegistry::new();
        let langs: Vec<&str> = if languages.is_null() {
            vec!["en", "es", "fr", "pt", "sv"]
        } else {
            match unsafe { CStr::from_ptr(languages) }.to_str() {
                Ok("") => vec!["en", "es", "fr", "pt", "sv"],
                Ok(s) => s.split(',').map(str::trim).collect(),
                Err(_) => return ptr::null_mut(),
            }
        };
        for lang in &langs {
            let _ = register_one(&mut registry, lang);
        }
        Box::into_raw(Box::new(PiperG2pHandle { registry }))
    });
    result.unwrap_or(ptr::null_mut())
}

/// Phonemize text, returning JSON: `{"tokens":[...],"language":".."}`.
/// Caller must free result with `piper_g2p_free_string`.
///
/// # Safety
/// All pointer args must be valid null-terminated UTF-8 or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_g2p_phonemize(
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
        let p = h.registry.get(lang)?;
        let (tokens, _) = p.phonemize_with_prosody(text).ok()?;
        let json = serde_json::json!({"tokens": tokens, "language": lang});
        CString::new(json.to_string()).ok()
    }));
    match result {
        Ok(Some(s)) => s.into_raw(),
        _ => ptr::null_mut(),
    }
}

/// Free a string from piper_g2p functions.
/// # Safety
/// `ptr` must be from a piper_g2p function, or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_g2p_free_string(ptr: *mut c_char) {
    if !ptr.is_null() {
        unsafe {
            drop(CString::from_raw(ptr));
        }
    }
}

/// Destroy a G2P handle.
/// # Safety
/// `handle` must be from `piper_g2p_create`, or NULL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn piper_g2p_free(handle: *mut PiperG2pHandle) {
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
pub unsafe extern "C" fn piper_g2p_available_languages(
    handle: *const PiperG2pHandle,
) -> *mut c_char {
    if handle.is_null() {
        return ptr::null_mut();
    }
    let result = std::panic::catch_unwind(AssertUnwindSafe(|| {
        let h = unsafe { &*handle };
        let joined = h.registry.available_languages().join(",");
        CString::new(joined).ok()
    }));
    match result {
        Ok(Some(s)) => s.into_raw(),
        _ => ptr::null_mut(),
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::{CStr, CString};

    // -----------------------------------------------------------------------
    // Korean FFI tests
    // -----------------------------------------------------------------------

    #[test]
    #[cfg(feature = "korean")]
    fn test_ffi_create_with_korean() {
        let lang = CString::new("ko").unwrap();
        unsafe {
            let handle = piper_g2p_create(lang.as_ptr());
            assert!(!handle.is_null(), "handle should not be NULL for 'ko'");
            piper_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "korean")]
    fn test_ffi_phonemize_korean() {
        let lang = CString::new("ko").unwrap();
        let text = CString::new("가").unwrap();
        unsafe {
            let handle = piper_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null(), "phonemize result should not be NULL");

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(!s.is_empty(), "phonemize result should not be empty");
            // Result is JSON with "tokens" and "language" keys
            assert!(s.contains("\"tokens\""), "result should contain tokens key");
            assert!(s.contains("\"language\""), "result should contain language key");

            piper_g2p_free_string(result);
            piper_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "korean")]
    fn test_ffi_korean_available_languages() {
        let lang = CString::new("ko").unwrap();
        unsafe {
            let handle = piper_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let langs_ptr = piper_g2p_available_languages(handle);
            assert!(!langs_ptr.is_null());

            let langs_str = CStr::from_ptr(langs_ptr).to_str().unwrap();
            let langs: Vec<&str> = langs_str.split(',').collect();
            assert!(langs.contains(&"ko"), "available languages should contain 'ko', got: {langs_str}");

            piper_g2p_free_string(langs_ptr);
            piper_g2p_free(handle);
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
            let handle = piper_g2p_create(lang.as_ptr());
            assert!(!handle.is_null(), "handle should not be NULL for 'sv'");
            piper_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "swedish")]
    fn test_ffi_phonemize_swedish() {
        let lang = CString::new("sv").unwrap();
        let text = CString::new("hej").unwrap();
        unsafe {
            let handle = piper_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let result = piper_g2p_phonemize(handle, text.as_ptr(), lang.as_ptr());
            assert!(!result.is_null(), "phonemize result should not be NULL");

            let s = CStr::from_ptr(result).to_str().unwrap();
            assert!(!s.is_empty(), "phonemize result should not be empty");
            assert!(s.contains("\"tokens\""), "result should contain tokens key");
            assert!(s.contains("\"language\""), "result should contain language key");

            piper_g2p_free_string(result);
            piper_g2p_free(handle);
        }
    }

    #[test]
    #[cfg(feature = "swedish")]
    fn test_ffi_swedish_available_languages() {
        let lang = CString::new("sv").unwrap();
        unsafe {
            let handle = piper_g2p_create(lang.as_ptr());
            assert!(!handle.is_null());

            let langs_ptr = piper_g2p_available_languages(handle);
            assert!(!langs_ptr.is_null());

            let langs_str = CStr::from_ptr(langs_ptr).to_str().unwrap();
            let langs: Vec<&str> = langs_str.split(',').collect();
            assert!(langs.contains(&"sv"), "available languages should contain 'sv', got: {langs_str}");

            piper_g2p_free_string(langs_ptr);
            piper_g2p_free(handle);
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
            let handle = piper_g2p_create(langs.as_ptr());
            assert!(!handle.is_null(), "handle should not be NULL for 'ko,sv'");

            let avail_ptr = piper_g2p_available_languages(handle);
            assert!(!avail_ptr.is_null());

            let avail_str = CStr::from_ptr(avail_ptr).to_str().unwrap();
            let avail: Vec<&str> = avail_str.split(',').collect();
            assert!(avail.contains(&"ko"), "should contain 'ko', got: {avail_str}");
            assert!(avail.contains(&"sv"), "should contain 'sv', got: {avail_str}");

            // Phonemize Korean text
            let ko_text = CString::new("가").unwrap();
            let ko_lang = CString::new("ko").unwrap();
            let ko_result = piper_g2p_phonemize(handle, ko_text.as_ptr(), ko_lang.as_ptr());
            assert!(!ko_result.is_null(), "Korean phonemize should succeed");
            piper_g2p_free_string(ko_result);

            // Phonemize Swedish text
            let sv_text = CString::new("hej").unwrap();
            let sv_lang = CString::new("sv").unwrap();
            let sv_result = piper_g2p_phonemize(handle, sv_text.as_ptr(), sv_lang.as_ptr());
            assert!(!sv_result.is_null(), "Swedish phonemize should succeed");
            piper_g2p_free_string(sv_result);

            piper_g2p_free_string(avail_ptr);
            piper_g2p_free(handle);
        }
    }
}

fn register_one(registry: &mut PhonemizerRegistry, lang: &str) -> Result<(), crate::G2pError> {
    match lang {
        #[cfg(feature = "english")]
        "en" => {
            registry.register("en", Box::new(crate::english::EnglishPhonemizer::new()?));
        }
        #[cfg(feature = "chinese")]
        "zh" => {
            // ChinesePhonemizer requires dictionary file paths;
            // skip registration when paths are not available via FFI.
            return Err(crate::G2pError::Phonemize(
                "Chinese requires dictionary paths; use from_dicts() instead".into(),
            ));
        }
        #[cfg(feature = "korean")]
        "ko" => {
            registry.register("ko", Box::new(crate::korean::KoreanPhonemizer::new()));
        }
        #[cfg(feature = "spanish")]
        "es" => {
            registry.register("es", Box::new(crate::spanish::SpanishPhonemizer::new()));
        }
        #[cfg(feature = "french")]
        "fr" => {
            registry.register("fr", Box::new(crate::french::FrenchPhonemizer::new()));
        }
        #[cfg(feature = "portuguese")]
        "pt" => {
            registry.register(
                "pt",
                Box::new(crate::portuguese::PortuguesePhonemizer::new()),
            );
        }
        #[cfg(feature = "swedish")]
        "sv" => {
            registry.register("sv", Box::new(crate::swedish::SwedishPhonemizer::new()));
        }
        #[cfg(feature = "japanese")]
        "ja" => {
            registry.register("ja", Box::new(crate::japanese::JapanesePhonemizer::new()?));
        }
        _ => {
            return Err(crate::G2pError::UnsupportedLanguage {
                code: lang.to_string(),
            });
        }
    }
    Ok(())
}

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

//! OpenJTalk dictionary download manager.
//!
//! Automatically searches for or downloads the OpenJTalk UTF-8 dictionary
//! (MeCab binary format), mirroring the C++ `openjtalk_dictionary_manager.c` behavior.
//!
//! **Note:** This module downloads the OpenJTalk MeCab-format dictionary which is
//! used by C++ and C# implementations. The Rust `jpreprocess` library uses a
//! different binary format (lindera). When the `naist-jdic` feature is enabled
//! (default), jpreprocess bundles its own dictionary and this module is not used
//! for Japanese phonemization. This module is primarily used by the C# CLI's
//! `DictionaryManager` equivalent.
//!
//! ## Dictionary search order
//!
//! 1. `OPENJTALK_DICTIONARY_PATH` environment variable
//! 2. Executable-relative: `<exe_dir>/../share/open_jtalk/dic`
//! 3. System paths (platform-dependent)
//! 4. Data directory: `<data_dir>/open_jtalk_dic_utf_8-1.11`
//!
//! ## Control flags
//!
//! - `PIPER_OFFLINE_MODE=1` — disable all downloads
//! - `PIPER_AUTO_DOWNLOAD_DICT=0` — disable dictionary auto-download

use std::path::{Path, PathBuf};

use crate::error::PiperError;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Download URL for the OpenJTalk UTF-8 dictionary tar.gz archive.
#[cfg(feature = "dict-download")]
const DICTIONARY_URL: &str =
    "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz";

/// Expected directory name after extraction.
const DICTIONARY_DIR_NAME: &str = "open_jtalk_dic_utf_8-1.11";

/// SHA-256 hash of the tar.gz archive for integrity verification.
#[cfg(feature = "dict-download")]
const DICTIONARY_SHA256: &str = "fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a";

/// Sentinel file placed inside the dictionary directory after successful
/// download and extraction. Used to distinguish a fully extracted dictionary
/// from a partially extracted one.
#[cfg(feature = "dict-download")]
const SENTINEL_FILE: &str = ".piper_dict_ok";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Search for an existing OpenJTalk dictionary without downloading.
///
/// Returns `Some(path)` if found, `None` otherwise.
pub fn find_dictionary() -> Option<PathBuf> {
    // 1. Environment variable override
    if let Ok(path) = std::env::var("OPENJTALK_DICTIONARY_PATH") {
        let p = PathBuf::from(&path);
        if is_valid_dictionary(&p) {
            return Some(p);
        }
    }

    // 2. Executable-relative path: <exe_dir>/../share/open_jtalk/dic
    if let Some(p) = exe_relative_dict_path()
        && is_valid_dictionary(&p)
    {
        return Some(p);
    }

    // 3. System paths
    for p in system_dict_paths() {
        if is_valid_dictionary(&p) {
            return Some(p);
        }
    }

    // 4. Data directory
    let data_dict = get_data_dir().join(DICTIONARY_DIR_NAME);
    if is_valid_dictionary(&data_dict) {
        return Some(data_dict);
    }

    None
}

/// Ensure the OpenJTalk dictionary is available, downloading if necessary.
///
/// Search order matches [`find_dictionary`]. If no existing dictionary is
/// found and downloading is permitted, the dictionary is downloaded to the
/// data directory and its SHA-256 hash is verified before extraction.
///
/// ## Errors
///
/// Returns `PiperError::DictionaryLoad` when:
/// - The dictionary cannot be found and downloading is disabled.
/// - The download, hash verification, or extraction fails.
pub fn ensure_dictionary() -> Result<PathBuf, PiperError> {
    // Try to find an existing dictionary first.
    if let Some(p) = find_dictionary() {
        return Ok(p);
    }

    // Check control flags before attempting download.
    if is_offline_mode() {
        return Err(PiperError::DictionaryLoad {
            path: "OpenJTalk dictionary not found and PIPER_OFFLINE_MODE=1 is set".to_string(),
        });
    }

    if !is_auto_download_enabled() {
        return Err(PiperError::DictionaryLoad {
            path: "OpenJTalk dictionary not found and PIPER_AUTO_DOWNLOAD_DICT=0 is set. \
                   Set OPENJTALK_DICTIONARY_PATH or enable auto-download"
                .to_string(),
        });
    }

    // Download to data directory.
    download_and_extract()
}

// ---------------------------------------------------------------------------
// Data directory resolution
// ---------------------------------------------------------------------------

/// Resolve the data directory for storing downloaded dictionaries.
///
/// Search order:
/// - `OPENJTALK_DATA_DIR` environment variable
/// - Windows: `%APPDATA%\piper`
/// - Unix: `$XDG_DATA_HOME/piper` → `$HOME/.local/share/piper` → `/tmp/piper`
fn get_data_dir() -> PathBuf {
    // 1. Explicit override
    if let Ok(dir) = std::env::var("OPENJTALK_DATA_DIR") {
        return PathBuf::from(dir);
    }

    // 2. Platform-specific default
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return PathBuf::from(appdata).join("piper");
        }
        // Fallback: current directory
        PathBuf::from(".").join("data")
    }

    #[cfg(not(target_os = "windows"))]
    {
        // XDG_DATA_HOME/piper
        if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
            return PathBuf::from(xdg).join("piper");
        }
        // $HOME/.local/share/piper
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("piper");
        }
        // Last resort
        PathBuf::from("/tmp/piper")
    }
}

// ---------------------------------------------------------------------------
// Dictionary path helpers
// ---------------------------------------------------------------------------

/// Executable-relative dictionary path: `<exe_dir>/../share/open_jtalk/dic`
fn exe_relative_dict_path() -> Option<PathBuf> {
    std::env::current_exe().ok().and_then(|exe| {
        exe.parent()
            .and_then(|dir| dir.parent())
            .map(|prefix| prefix.join("share").join("open_jtalk").join("dic"))
    })
}

/// Platform-specific system dictionary paths.
fn system_dict_paths() -> Vec<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        vec![
            PathBuf::from(r"C:\Program Files\open_jtalk\dic"),
            PathBuf::from(r"C:\Program Files (x86)\open_jtalk\dic"),
        ]
    }

    #[cfg(not(target_os = "windows"))]
    {
        vec![
            PathBuf::from("/usr/share/open_jtalk/dic"),
            PathBuf::from("/usr/local/share/open_jtalk/dic"),
            PathBuf::from("/opt/open_jtalk/dic"),
        ]
    }
}

/// Check if a directory looks like a valid OpenJTalk dictionary.
///
/// A valid dictionary directory must exist and contain at least one
/// `.bin` file (the compiled MeCab dictionary entries).
fn is_valid_dictionary(path: &Path) -> bool {
    if !path.is_dir() {
        return false;
    }
    // Check for at least one *.bin file (sys.dic, unk.dic, etc.)
    if let Ok(entries) = std::fs::read_dir(path) {
        for entry in entries.flatten() {
            if let Some(ext) = entry.path().extension()
                && (ext == "bin" || ext == "dic")
            {
                return true;
            }
        }
    }
    false
}

// ---------------------------------------------------------------------------
// Control flags
// ---------------------------------------------------------------------------

/// Returns `true` if offline mode is enabled (`PIPER_OFFLINE_MODE=1`).
fn is_offline_mode() -> bool {
    std::env::var("PIPER_OFFLINE_MODE")
        .map(|v| v == "1")
        .unwrap_or(false)
}

/// Returns `true` if auto-download is enabled (default: true).
///
/// Disabled when `PIPER_AUTO_DOWNLOAD_DICT=0`.
fn is_auto_download_enabled() -> bool {
    std::env::var("PIPER_AUTO_DOWNLOAD_DICT")
        .map(|v| v != "0")
        .unwrap_or(true)
}

// ---------------------------------------------------------------------------
// Download and extraction (feature-gated)
// ---------------------------------------------------------------------------

/// Download, verify, and extract the dictionary archive.
///
/// Returns the path to the extracted dictionary directory.
#[cfg(feature = "dict-download")]
fn download_and_extract() -> Result<PathBuf, PiperError> {
    let data_dir = get_data_dir();
    let dict_dir = data_dir.join(DICTIONARY_DIR_NAME);
    let archive_path = data_dir.join("open_jtalk_dic_utf_8-1.11.tar.gz");

    // Create parent directory
    std::fs::create_dir_all(&data_dir).map_err(|e| PiperError::DictionaryLoad {
        path: format!(
            "failed to create data directory {}: {e}",
            data_dir.display()
        ),
    })?;

    // Check if a previous download left a valid directory
    if is_valid_dictionary(&dict_dir) && dict_dir.join(SENTINEL_FILE).exists() {
        return Ok(dict_dir);
    }

    eprintln!(
        "[piper] Downloading OpenJTalk dictionary from {}",
        DICTIONARY_URL
    );

    // 1. Download
    download_archive(&archive_path)?;

    // 2. Verify SHA-256
    eprintln!("[piper] Verifying SHA-256 checksum...");
    verify_sha256(&archive_path)?;

    // 3. Extract
    eprintln!("[piper] Extracting dictionary to {}...", data_dir.display());
    extract_tar_gz(&archive_path, &data_dir)?;

    // 4. Write sentinel file
    if dict_dir.is_dir() {
        let _ = std::fs::write(dict_dir.join(SENTINEL_FILE), "ok");
    }

    // 5. Delete archive
    if archive_path.exists() {
        let _ = std::fs::remove_file(&archive_path);
    }

    if is_valid_dictionary(&dict_dir) {
        eprintln!("[piper] Dictionary ready: {}", dict_dir.display());
        Ok(dict_dir)
    } else {
        Err(PiperError::DictionaryLoad {
            path: format!(
                "extraction succeeded but dictionary not found at {}",
                dict_dir.display()
            ),
        })
    }
}

/// Download the archive using `reqwest::blocking`.
#[cfg(feature = "dict-download")]
fn download_archive(dest: &Path) -> Result<(), PiperError> {
    use std::io::{Read as _, Write};

    let client = reqwest::blocking::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(30))
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| PiperError::Download(format!("HTTP client error: {e}")))?;

    let mut response = client
        .get(DICTIONARY_URL)
        .send()
        .map_err(|e| PiperError::Download(format!("dictionary download failed: {e}")))?;

    if !response.status().is_success() {
        return Err(PiperError::Download(format!(
            "HTTP {} downloading dictionary from {}",
            response.status(),
            DICTIONARY_URL
        )));
    }

    let total_bytes = response.content_length();
    let mut bytes_downloaded: u64 = 0;
    let mut last_pct: u64 = 0;

    let file = std::fs::File::create(dest).map_err(|e| PiperError::DictionaryLoad {
        path: format!("failed to create {}: {e}", dest.display()),
    })?;
    let mut writer = std::io::BufWriter::with_capacity(256 * 1024, file);
    let mut buf = [0u8; 64 * 1024];

    loop {
        let n = response
            .read(&mut buf)
            .map_err(|e| PiperError::Download(format!("read error: {e}")))?;
        if n == 0 {
            break;
        }
        writer
            .write_all(&buf[..n])
            .map_err(|e| PiperError::DictionaryLoad {
                path: format!("write error: {e}"),
            })?;
        bytes_downloaded += n as u64;

        // Print progress every 10%
        if let Some(total) = total_bytes
            && total > 0
        {
            let pct = (bytes_downloaded * 100) / total;
            if pct >= last_pct + 10 {
                eprintln!(
                    "[piper] Downloaded {:.1} / {:.1} MB ({}%)",
                    bytes_downloaded as f64 / 1_048_576.0,
                    total as f64 / 1_048_576.0,
                    pct
                );
                last_pct = pct;
            }
        }
    }

    writer.flush().map_err(|e| PiperError::DictionaryLoad {
        path: format!("flush error: {e}"),
    })?;

    eprintln!(
        "[piper] Download complete ({:.1} MB)",
        bytes_downloaded as f64 / 1_048_576.0
    );

    Ok(())
}

/// Verify SHA-256 hash of the downloaded archive.
#[cfg(feature = "dict-download")]
fn verify_sha256(path: &Path) -> Result<(), PiperError> {
    use sha2::{Digest, Sha256};
    use std::io::Read as _;

    let mut file = std::fs::File::open(path).map_err(|e| PiperError::DictionaryLoad {
        path: format!("failed to open {}: {e}", path.display()),
    })?;

    let mut hasher = Sha256::new();
    let mut buf = [0u8; 64 * 1024];
    loop {
        let n = file
            .read(&mut buf)
            .map_err(|e| PiperError::DictionaryLoad {
                path: format!("read error during hash: {e}"),
            })?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }

    let hash = format!("{:x}", hasher.finalize());

    if hash != DICTIONARY_SHA256 {
        // Remove corrupt archive
        let _ = std::fs::remove_file(path);
        return Err(PiperError::DictionaryLoad {
            path: format!(
                "SHA-256 mismatch for {}: expected {}, got {}",
                path.display(),
                DICTIONARY_SHA256,
                hash
            ),
        });
    }

    Ok(())
}

/// Extract a `.tar.gz` archive into `dest_dir`.
#[cfg(feature = "dict-download")]
fn extract_tar_gz(archive_path: &Path, dest_dir: &Path) -> Result<(), PiperError> {
    use flate2::read::GzDecoder;
    use tar::Archive;

    let file = std::fs::File::open(archive_path).map_err(|e| PiperError::DictionaryLoad {
        path: format!("failed to open archive {}: {e}", archive_path.display()),
    })?;

    let decoder = GzDecoder::new(file);
    let mut archive = Archive::new(decoder);

    archive
        .unpack(dest_dir)
        .map_err(|e| PiperError::DictionaryLoad {
            path: format!(
                "failed to extract {} to {}: {e}",
                archive_path.display(),
                dest_dir.display()
            ),
        })?;

    Ok(())
}

/// Stub when the `dict-download` feature is not enabled.
#[cfg(not(feature = "dict-download"))]
fn download_and_extract() -> Result<PathBuf, PiperError> {
    Err(PiperError::DictionaryLoad {
        path: "OpenJTalk dictionary not found. Auto-download requires the \
               \"dict-download\" feature; rebuild with `--features dict-download` \
               or set OPENJTALK_DICTIONARY_PATH"
            .to_string(),
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // Pure-logic tests (no env var mutation, safe for parallel execution)
    // -----------------------------------------------------------------------

    #[test]
    fn test_is_valid_dictionary_nonexistent() {
        assert!(!is_valid_dictionary(Path::new("/nonexistent/path/12345")));
    }

    #[test]
    fn test_is_valid_dictionary_empty_dir() {
        let dir = tempfile::tempdir().unwrap();
        assert!(!is_valid_dictionary(dir.path()));
    }

    #[test]
    fn test_is_valid_dictionary_with_dic_file() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("sys.dic"), b"fake").unwrap();
        assert!(is_valid_dictionary(dir.path()));
    }

    #[test]
    fn test_is_valid_dictionary_with_bin_extension() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("matrix.bin"), b"fake").unwrap();
        assert!(is_valid_dictionary(dir.path()));
    }

    #[test]
    fn test_is_valid_dictionary_ignores_txt_files() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("readme.txt"), b"hello").unwrap();
        assert!(!is_valid_dictionary(dir.path()));
    }

    #[test]
    fn test_system_dict_paths_not_empty() {
        let paths = system_dict_paths();
        assert!(!paths.is_empty());
        // All paths should be absolute
        for p in &paths {
            assert!(p.is_absolute(), "system path should be absolute: {p:?}");
        }
    }

    #[test]
    fn test_exe_relative_dict_path_returns_some() {
        let result = exe_relative_dict_path();
        assert!(result.is_some());
        let p = result.unwrap();
        assert!(p.ends_with("dic"));
    }

    #[test]
    fn test_constants_dir_name() {
        assert_eq!(DICTIONARY_DIR_NAME, "open_jtalk_dic_utf_8-1.11");
    }

    #[cfg(feature = "dict-download")]
    #[test]
    fn test_constants_download() {
        assert!(DICTIONARY_URL.starts_with("https://"));
        assert!(DICTIONARY_URL.ends_with(".tar.gz"));
        assert!(DICTIONARY_URL.contains("open_jtalk_dic_utf_8"));
        assert_eq!(DICTIONARY_SHA256.len(), 64); // SHA-256 hex string
        // All hex characters
        assert!(DICTIONARY_SHA256.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn test_get_data_dir_returns_non_empty() {
        // get_data_dir() always returns a non-empty path regardless of env
        let dir = get_data_dir();
        assert!(!dir.as_os_str().is_empty());
    }

    #[test]
    fn test_find_dictionary_returns_valid_or_none() {
        // Acquire ENV_MUTEX: concurrent env var tests may set
        // OPENJTALK_DICTIONARY_PATH to a temp dir that gets cleaned up
        // before we validate it, causing a spurious failure.
        let _lock = ENV_MUTEX.lock().unwrap_or_else(|e| e.into_inner());
        // find_dictionary() should return either None or a valid dictionary
        if let Some(p) = find_dictionary() {
            assert!(
                is_valid_dictionary(&p),
                "find_dictionary returned invalid path: {p:?}"
            );
        }
    }

    // -----------------------------------------------------------------------
    // SHA-256 verification tests (feature-gated, no env mutation)
    // -----------------------------------------------------------------------

    #[cfg(feature = "dict-download")]
    #[test]
    fn test_verify_sha256_bad_hash() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("test_archive.tar.gz");
        std::fs::write(&path, b"not a real archive").unwrap();
        let result = verify_sha256(&path);
        assert!(result.is_err());
        let err = format!("{}", result.unwrap_err());
        assert!(err.contains("SHA-256 mismatch"));
        // Archive should be deleted on mismatch
        assert!(!path.exists());
    }

    #[cfg(feature = "dict-download")]
    #[test]
    fn test_verify_sha256_missing_file() {
        let result = verify_sha256(Path::new("/nonexistent/file.tar.gz"));
        assert!(result.is_err());
    }

    #[cfg(feature = "dict-download")]
    #[test]
    fn test_verify_sha256_known_hash() {
        // Verify SHA-256 computation with a known input
        use sha2::{Digest, Sha256};
        let data = b"hello world";
        let expected = format!("{:x}", Sha256::digest(data));

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("known_hash_test.bin");
        std::fs::write(&path, data).unwrap();

        // This will fail because the hash doesn't match DICTIONARY_SHA256,
        // but the error message should contain the actual hash
        let result = verify_sha256(&path);
        assert!(result.is_err());
        let err = format!("{}", result.unwrap_err());
        assert!(
            err.contains(&expected),
            "error should contain actual hash: {err}"
        );
    }

    // -----------------------------------------------------------------------
    // Extraction test (feature-gated, no env mutation)
    // -----------------------------------------------------------------------

    #[cfg(feature = "dict-download")]
    #[test]
    fn test_extract_tar_gz_valid() {
        use flate2::Compression;
        use flate2::write::GzEncoder;
        use std::io::Write;

        let dir = tempfile::tempdir().unwrap();
        let archive_path = dir.path().join("test.tar.gz");

        // Create a minimal tar.gz containing a single file.
        // The builder must be explicitly finished and the GzEncoder flushed
        // before the file handle is dropped.
        {
            let file = std::fs::File::create(&archive_path).unwrap();
            let encoder = GzEncoder::new(file, Compression::default());
            let mut builder = tar::Builder::new(encoder);

            let data = b"test dictionary content";
            let mut header = tar::Header::new_gnu();
            header.set_size(data.len() as u64);
            header.set_mode(0o644);
            header.set_cksum();
            builder
                .append_data(&mut header, "test_dict/sys.dic", &data[..])
                .unwrap();

            // into_inner() finalises the tar archive and returns the GzEncoder.
            let mut gz = builder.into_inner().unwrap();
            gz.flush().unwrap();
            // Drop gz to call finish() on the GzEncoder.
            gz.finish().unwrap();
        }

        // Extract
        let extract_dir = dir.path().join("extracted");
        std::fs::create_dir_all(&extract_dir).unwrap();
        let result = extract_tar_gz(&archive_path, &extract_dir);
        assert!(result.is_ok(), "extraction failed: {result:?}");

        // Verify extracted content
        let extracted_file = extract_dir.join("test_dict").join("sys.dic");
        assert!(extracted_file.exists(), "extracted file should exist");
        let content = std::fs::read(&extracted_file).unwrap();
        assert_eq!(content, b"test dictionary content");
    }

    #[cfg(feature = "dict-download")]
    #[test]
    fn test_extract_tar_gz_invalid_archive() {
        let dir = tempfile::tempdir().unwrap();
        let archive_path = dir.path().join("bad.tar.gz");
        std::fs::write(&archive_path, b"not a tar.gz file").unwrap();

        let result = extract_tar_gz(&archive_path, dir.path());
        assert!(result.is_err());
    }

    // -----------------------------------------------------------------------
    // download_and_extract stub test (without dict-download feature)
    // -----------------------------------------------------------------------

    #[test]
    fn test_download_and_extract_stub() {
        // download_and_extract() is an internal function, but we can test it
        // indirectly: if no dictionary is found and flags allow download,
        // ensure_dictionary() will call download_and_extract().
        // On CI without a real dictionary, this tests the error path.
        let result = ensure_dictionary();
        // Result depends on whether a dictionary exists on this machine.
        // We just verify it doesn't panic.
        let _ = result;
    }

    // -----------------------------------------------------------------------
    // Environment-variable tests (serialized via ENV_MUTEX)
    //
    // `std::env::set_var` / `remove_var` mutate process-wide state and are
    // `unsafe` in Rust 2024 edition.  A shared mutex prevents concurrent
    // env mutations across test threads from racing.
    // -----------------------------------------------------------------------

    use std::sync::Mutex;

    /// Mutex that serializes all env-var-mutating tests so they don't race.
    static ENV_MUTEX: Mutex<()> = Mutex::new(());

    #[test]
    fn test_find_dictionary_env_var_valid() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // Create a temp dir with a .dic file to make it "valid"
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("sys.dic"), b"test").unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("OPENJTALK_DICTIONARY_PATH", dir.path());
        }
        let result = find_dictionary();
        unsafe {
            std::env::remove_var("OPENJTALK_DICTIONARY_PATH");
        }

        assert_eq!(result, Some(dir.path().to_path_buf()));
    }

    #[test]
    fn test_find_dictionary_env_var_invalid_skipped() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // Set env var to nonexistent path - should be skipped
        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("OPENJTALK_DICTIONARY_PATH", "/nonexistent/path/dict");
        }
        let result = find_dictionary();
        unsafe {
            std::env::remove_var("OPENJTALK_DICTIONARY_PATH");
        }

        // Should NOT return the invalid path (returns None or another valid path)
        assert_ne!(
            result,
            Some(std::path::PathBuf::from("/nonexistent/path/dict"))
        );
    }

    // -----------------------------------------------------------------------
    // Control flag tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_offline_mode_enabled() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("PIPER_OFFLINE_MODE", "1");
        }
        assert!(is_offline_mode());
        unsafe {
            std::env::remove_var("PIPER_OFFLINE_MODE");
        }
    }

    #[test]
    fn test_offline_mode_disabled_by_default() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::remove_var("PIPER_OFFLINE_MODE");
        }
        assert!(!is_offline_mode());
    }

    #[test]
    fn test_offline_mode_other_values_not_offline() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("PIPER_OFFLINE_MODE", "0");
        }
        assert!(!is_offline_mode());
        unsafe {
            std::env::set_var("PIPER_OFFLINE_MODE", "true");
        }
        assert!(!is_offline_mode());
        unsafe {
            std::env::remove_var("PIPER_OFFLINE_MODE");
        }
    }

    #[test]
    fn test_auto_download_enabled_by_default() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::remove_var("PIPER_AUTO_DOWNLOAD_DICT");
        }
        assert!(is_auto_download_enabled());
    }

    #[test]
    fn test_auto_download_disabled() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("PIPER_AUTO_DOWNLOAD_DICT", "0");
        }
        assert!(!is_auto_download_enabled());
        unsafe {
            std::env::remove_var("PIPER_AUTO_DOWNLOAD_DICT");
        }
    }

    #[test]
    fn test_auto_download_other_values_enabled() {
        let _lock = ENV_MUTEX.lock().unwrap();

        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("PIPER_AUTO_DOWNLOAD_DICT", "1");
        }
        assert!(is_auto_download_enabled());
        unsafe {
            std::env::set_var("PIPER_AUTO_DOWNLOAD_DICT", "false");
        }
        assert!(is_auto_download_enabled());
        unsafe {
            std::env::remove_var("PIPER_AUTO_DOWNLOAD_DICT");
        }
    }

    // -----------------------------------------------------------------------
    // Data directory resolution tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_get_data_dir_env_override() {
        let _lock = ENV_MUTEX.lock().unwrap();

        let dir = tempfile::tempdir().unwrap();
        // SAFETY: serialized by ENV_MUTEX; restored immediately.
        unsafe {
            std::env::set_var("OPENJTALK_DATA_DIR", dir.path());
        }
        let result = get_data_dir();
        unsafe {
            std::env::remove_var("OPENJTALK_DATA_DIR");
        }

        assert_eq!(result, dir.path().to_path_buf());
    }
}

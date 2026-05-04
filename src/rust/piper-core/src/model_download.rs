//! Model download and management utilities.
//!
//! Download ONNX models and config files from HuggingFace or direct URLs.
//! Feature-gated behind "download" feature (requires reqwest).

use std::path::{Path, PathBuf};

use crate::error::PiperError;

/// Model metadata for a downloadable voice.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ModelInfo {
    pub name: String,
    pub language: String,
    /// Quality tier: "low", "medium", or "high".
    pub quality: String,
    pub description: String,
    pub model_url: String,
    pub config_url: String,
    pub size_bytes: Option<u64>,
}

/// Download progress callback.
pub type ProgressCallback = Box<dyn Fn(DownloadProgress) + Send>;

/// Download progress information.
#[derive(Debug, Clone)]
pub struct DownloadProgress {
    pub bytes_downloaded: u64,
    pub total_bytes: Option<u64>,
    pub percentage: Option<f64>,
}

/// Default model directory based on the current platform.
///
/// - Linux: `~/.local/share/piper-plus/models/`
/// - macOS: `~/Library/Application Support/piper-plus/models/`
/// - Windows: `%APPDATA%/piper-plus/models/`
///
/// Falls back to `~/.piper-plus/models/` if the home directory cannot be
/// determined through standard means.
pub fn default_model_dir() -> PathBuf {
    if let Some(dir) = platform_data_dir() {
        return dir.join("piper-plus").join("models");
    }

    // Fallback: try HOME environment variable directly.
    if let Ok(home) = std::env::var("HOME") {
        return PathBuf::from(home).join(".piper-plus").join("models");
    }

    // Last resort on Windows.
    if let Ok(profile) = std::env::var("USERPROFILE") {
        return PathBuf::from(profile).join(".piper-plus").join("models");
    }

    PathBuf::from(".piper-plus").join("models")
}

/// Platform-specific data directory without pulling in the `dirs` crate.
fn platform_data_dir() -> Option<PathBuf> {
    #[cfg(target_os = "linux")]
    {
        // XDG_DATA_HOME or ~/.local/share
        if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
            return Some(PathBuf::from(xdg));
        }
        std::env::var("HOME")
            .ok()
            .map(|h| PathBuf::from(h).join(".local").join("share"))
    }

    #[cfg(target_os = "macos")]
    {
        std::env::var("HOME")
            .ok()
            .map(|h| PathBuf::from(h).join("Library").join("Application Support"))
    }

    #[cfg(target_os = "windows")]
    {
        std::env::var("APPDATA").ok().map(PathBuf::from)
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
    {
        None
    }
}

/// Download a file from `url` to `dest`, calling `progress` periodically.
///
/// This is the feature-gated implementation that requires the `download`
/// Cargo feature (which brings in `reqwest`).
#[cfg(feature = "download")]
pub fn download_file(
    url: &str,
    dest: &Path,
    progress: Option<ProgressCallback>,
) -> Result<(), PiperError> {
    use std::io::{BufWriter, Read as _, Write};

    // Ensure the parent directory exists.
    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent).map_err(|e| {
            PiperError::ModelLoad(format!(
                "failed to create directory {}: {e}",
                parent.display()
            ))
        })?;
    }

    let client = reqwest::blocking::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(30))
        .timeout(std::time::Duration::from_secs(600)) // 10 min for large models
        .build()
        .map_err(|e| PiperError::Download(format!("HTTP client error: {e}")))?;

    let mut response = client
        .get(url)
        .send()
        .map_err(|e| PiperError::Download(format!("download failed: {e}")))?;

    if !response.status().is_success() {
        return Err(PiperError::ModelLoad(format!(
            "HTTP {} for {url}",
            response.status()
        )));
    }

    let total_bytes = response.content_length();
    let mut bytes_downloaded: u64 = 0;
    // ~100 KB progress granularity.
    const PROGRESS_INTERVAL: u64 = 100 * 1024;
    let mut next_report = PROGRESS_INTERVAL;

    let file = std::fs::File::create(dest).map_err(|e| {
        PiperError::ModelLoad(format!("failed to create file {}: {e}", dest.display()))
    })?;
    let mut file = BufWriter::with_capacity(256 * 1024, file); // 256KB buffer

    // Stream directly from the response to disk to avoid loading
    // the entire body into memory.
    let mut buf = [0u8; 64 * 1024];
    loop {
        let n = response.read(&mut buf).map_err(|e| {
            PiperError::ModelLoad(format!("failed to read response body from {url}: {e}"))
        })?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n]).map_err(|e| {
            PiperError::ModelLoad(format!("failed to write to {}: {e}", dest.display()))
        })?;
        bytes_downloaded += n as u64;

        if let Some(ref cb) = progress
            && (bytes_downloaded >= next_report || (total_bytes == Some(bytes_downloaded)))
        {
            let percentage = total_bytes.map(|t| {
                if t == 0 {
                    100.0
                } else {
                    (bytes_downloaded as f64 / t as f64) * 100.0
                }
            });
            cb(DownloadProgress {
                bytes_downloaded,
                total_bytes,
                percentage,
            });
            next_report = bytes_downloaded + PROGRESS_INTERVAL;
        }
    }

    file.flush()
        .map_err(|e| PiperError::ModelLoad(format!("failed to flush {}: {e}", dest.display())))?;

    Ok(())
}

/// Stub when the `download` feature is not enabled.
///
/// Returns an error indicating that the feature must be enabled.
#[cfg(not(feature = "download"))]
pub fn download_file(
    _url: &str,
    _dest: &Path,
    _progress: Option<ProgressCallback>,
) -> Result<(), PiperError> {
    Err(PiperError::ModelLoad(
        "the \"download\" feature is required for download_file; \
         rebuild with `--features download`"
            .to_string(),
    ))
}

/// Download a model (ONNX + config.json) from HuggingFace.
///
/// Creates `dest_dir` if it does not exist. Returns `(model_path, config_path)`.
#[cfg(feature = "download")]
pub fn download_model(
    model_info: &ModelInfo,
    dest_dir: &Path,
    progress: Option<ProgressCallback>,
) -> Result<(PathBuf, PathBuf), PiperError> {
    std::fs::create_dir_all(dest_dir).map_err(|e| {
        PiperError::ModelLoad(format!(
            "failed to create model directory {}: {e}",
            dest_dir.display()
        ))
    })?;

    let model_filename =
        url_filename(&model_info.model_url).unwrap_or_else(|| format!("{}.onnx", model_info.name));
    let config_filename =
        url_filename(&model_info.config_url).unwrap_or_else(|| "config.json".to_string());

    let model_path = dest_dir.join(&model_filename);
    let config_path = dest_dir.join(&config_filename);

    // Download model file (with progress).
    download_file(&model_info.model_url, &model_path, progress)?;

    // Download config file (no progress -- typically tiny).
    download_file(&model_info.config_url, &config_path, None)?;

    Ok((model_path, config_path))
}

/// Stub when the `download` feature is not enabled.
#[cfg(not(feature = "download"))]
pub fn download_model(
    _model_info: &ModelInfo,
    _dest_dir: &Path,
    _progress: Option<ProgressCallback>,
) -> Result<(PathBuf, PathBuf), PiperError> {
    Err(PiperError::ModelLoad(
        "the \"download\" feature is required for download_model; \
         rebuild with `--features download`"
            .to_string(),
    ))
}

/// Construct a HuggingFace download URL from a repo identifier and filename.
///
/// Format: `https://huggingface.co/{repo}/resolve/main/{filename}`
///
/// # Examples
///
/// ```
/// # use piper_plus::model_download::huggingface_url;
/// let url = huggingface_url("ayousanz/piper-plus-tsukuyomi-chan", "model.onnx");
/// assert_eq!(url, "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/model.onnx");
/// ```
pub fn huggingface_url(repo: &str, filename: &str) -> String {
    format!("https://huggingface.co/{repo}/resolve/main/{filename}")
}

/// Parse a model registry from a JSON string.
///
/// The JSON should be an array of [`ModelInfo`] objects.
pub fn parse_model_registry(json_str: &str) -> Result<Vec<ModelInfo>, PiperError> {
    let models: Vec<ModelInfo> = serde_json::from_str(json_str)?;
    Ok(models)
}

/// Check whether a model named `model_name` is already cached in `model_dir`.
///
/// A model is considered cached when both `{model_name}.onnx` and
/// `{model_name}.onnx.json` (or `config.json`) exist inside the directory.
pub fn is_model_cached(model_name: &str, model_dir: &Path) -> bool {
    let onnx = model_dir.join(format!("{model_name}.onnx"));
    let onnx_json = model_dir.join(format!("{model_name}.onnx.json"));
    let config_json = model_dir.join("config.json");

    onnx.exists() && (onnx_json.exists() || config_json.exists())
}

/// Built-in model registry with known Piper-Plus models.
///
/// The registry is lazily initialised once and then shared for the lifetime
/// of the process, avoiding repeated heap allocations on every call.
pub fn builtin_registry() -> &'static [ModelInfo] {
    use std::sync::OnceLock;
    static REGISTRY: OnceLock<Vec<ModelInfo>> = OnceLock::new();
    REGISTRY.get_or_init(|| {
        vec![
            ModelInfo {
                name: "tsukuyomi-6lang-v2".to_string(),
                language: "ja-en-zh-es-fr-pt".to_string(),
                quality: "medium".to_string(),
                description: "Tsukuyomi-chan 6-language model (JA/EN/ZH/ES/FR/PT, MB-iSTFT)"
                    .to_string(),
                model_url: huggingface_url(
                    "ayousanz/piper-plus-tsukuyomi-chan",
                    "tsukuyomi-chan-6lang-fp16.onnx",
                ),
                config_url: huggingface_url("ayousanz/piper-plus-tsukuyomi-chan", "config.json"),
                size_bytes: Some(39_652_717),
            },
            ModelInfo {
                name: "css10-6lang".to_string(),
                language: "ja-en-zh-es-fr-pt".to_string(),
                quality: "medium".to_string(),
                description:
                    "CSS10 Japanese 6-language model fine-tuned from multilingual base (FP16, MB-iSTFT)"
                        .to_string(),
                model_url: huggingface_url(
                    "ayousanz/piper-plus-css10-ja-6lang",
                    "css10-ja-6lang-fp16.onnx",
                ),
                config_url: huggingface_url("ayousanz/piper-plus-css10-ja-6lang", "config.json"),
                size_bytes: Some(39_652_717),
            },
        ]
    })
}

/// Find a model by name or alias in the built-in registry.
///
/// Supports exact name match, unique partial match (contains), and unique
/// description match (case-insensitive).
pub fn find_model(query: &str) -> Option<&'static ModelInfo> {
    let registry = builtin_registry();

    // 1. Exact name match
    if let Some(m) = registry.iter().find(|m| m.name == query) {
        return Some(m);
    }

    // 2. Partial name match (contains)
    let matches: Vec<_> = registry.iter().filter(|m| m.name.contains(query)).collect();
    if matches.len() == 1 {
        return Some(matches[0]);
    }

    // 3. Check if query matches any part of the description
    let query_lower = query.to_lowercase();
    let desc_matches: Vec<_> = registry
        .iter()
        .filter(|m| m.description.to_lowercase().contains(&query_lower))
        .collect();
    if desc_matches.len() == 1 {
        return Some(desc_matches[0]);
    }

    None
}

/// Resolve a model path from a name, alias, or file path.
///
/// 1. If the string is a path to an existing file, return it directly.
/// 2. If it matches a model name in the registry, look in `model_dir` for a
///    cached copy.
/// 3. If not cached, auto-download when the `download` feature is enabled.
pub fn resolve_model_path(
    model_str: &str,
    model_dir: Option<&Path>,
) -> Result<PathBuf, PiperError> {
    let path = PathBuf::from(model_str);

    // 1. Direct file path
    if path.is_file() {
        return Ok(path);
    } else if path.is_dir() {
        return Err(PiperError::ModelLoad(format!(
            "Path '{}' is a directory. Please provide a model file path or a model name.",
            path.display()
        )));
    }

    // 2. Try as model name
    let model_info = find_model(model_str).ok_or_else(|| {
        PiperError::ModelLoad(format!(
            "Model '{}' not found. Use --list-models to see available models, or specify a file path.",
            model_str
        ))
    })?;

    let dir = model_dir
        .map(PathBuf::from)
        .unwrap_or_else(default_model_dir);

    // Check if already cached
    if is_model_cached(&model_info.name, &dir) {
        let model_path = dir.join(format!("{}.onnx", model_info.name));
        return Ok(model_path);
    }

    // 3. Auto-download
    #[cfg(feature = "download")]
    {
        eprintln!(
            "Model '{}' not found locally. Downloading...",
            model_info.name
        );
        let (model_path, _config_path) = download_model(
            model_info,
            &dir,
            Some(Box::new(|progress| {
                if let Some(pct) = progress.percentage {
                    eprint!("\r  Downloading... {:.1}%", pct);
                }
            })),
        )?;
        eprintln!();
        eprintln!("Model downloaded to: {}", model_path.display());
        Ok(model_path)
    }

    #[cfg(not(feature = "download"))]
    {
        Err(PiperError::ModelLoad(format!(
            "Model '{}' not cached. Download it with: --download-model {}",
            model_str, model_info.name
        )))
    }
}

/// Extract the filename component from a URL path.
///
/// Returns `None` if the URL has no path segments or the last segment is empty.
#[cfg(any(feature = "download", test))]
fn url_filename(url: &str) -> Option<String> {
    let path = url.split('?').next().unwrap_or(url);
    let path = path.split('#').next().unwrap_or(path);
    path.rsplit('/')
        .next()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;

    // -- huggingface_url construction -----------------------------------------

    #[test]
    fn test_huggingface_url_basic() {
        let url = huggingface_url("owner/repo", "model.onnx");
        assert_eq!(
            url,
            "https://huggingface.co/owner/repo/resolve/main/model.onnx"
        );
    }

    #[test]
    fn test_huggingface_url_with_subdirectory_filename() {
        let url = huggingface_url("ayousanz/piper-plus-tsukuyomi-chan", "models/v2.onnx");
        assert_eq!(
            url,
            "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/models/v2.onnx"
        );
    }

    // -- parse_model_registry -------------------------------------------------

    #[test]
    fn test_parse_model_registry_valid() {
        let json = r#"[
            {
                "name": "test-model",
                "language": "ja",
                "quality": "medium",
                "description": "A test model",
                "model_url": "https://example.com/model.onnx",
                "config_url": "https://example.com/config.json",
                "size_bytes": 1024
            }
        ]"#;
        let models = parse_model_registry(json).unwrap();
        assert_eq!(models.len(), 1);
        assert_eq!(models[0].name, "test-model");
        assert_eq!(models[0].size_bytes, Some(1024));
    }

    #[test]
    fn test_parse_model_registry_empty_array() {
        let models = parse_model_registry("[]").unwrap();
        assert!(models.is_empty());
    }

    #[test]
    fn test_parse_model_registry_invalid_json() {
        let result = parse_model_registry("not valid json");
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_model_registry_missing_required_fields() {
        let json = r#"[{"name": "incomplete"}]"#;
        let result = parse_model_registry(json);
        assert!(result.is_err());
    }

    // -- is_model_cached ------------------------------------------------------

    #[test]
    fn test_is_model_cached_with_onnx_json() {
        let dir = tempfile::tempdir().unwrap();
        let dir_path = dir.path();

        // Neither file exists -- not cached.
        assert!(!is_model_cached("voice", dir_path));

        // Only ONNX -- still not cached.
        std::fs::write(dir_path.join("voice.onnx"), b"fake").unwrap();
        assert!(!is_model_cached("voice", dir_path));

        // ONNX + onnx.json -- cached.
        std::fs::write(dir_path.join("voice.onnx.json"), b"{}").unwrap();
        assert!(is_model_cached("voice", dir_path));
    }

    #[test]
    fn test_is_model_cached_with_config_json() {
        let dir = tempfile::tempdir().unwrap();
        let dir_path = dir.path();

        std::fs::write(dir_path.join("voice.onnx"), b"fake").unwrap();
        std::fs::write(dir_path.join("config.json"), b"{}").unwrap();
        assert!(is_model_cached("voice", dir_path));
    }

    #[test]
    fn test_is_model_cached_missing_onnx() {
        let dir = tempfile::tempdir().unwrap();
        let dir_path = dir.path();

        // Config exists but ONNX does not -- not cached.
        std::fs::write(dir_path.join("config.json"), b"{}").unwrap();
        assert!(!is_model_cached("voice", dir_path));
    }

    // -- default_model_dir ----------------------------------------------------

    #[test]
    fn test_default_model_dir_is_non_empty() {
        let dir = default_model_dir();
        assert!(
            !dir.as_os_str().is_empty(),
            "default_model_dir must not be empty"
        );
        // Should always end with "models".
        assert_eq!(
            dir.file_name().and_then(|s| s.to_str()),
            Some("models"),
            "expected path to end with 'models', got: {dir:?}"
        );
    }

    // -- ModelInfo serialization roundtrip -------------------------------------

    #[test]
    fn test_model_info_roundtrip() {
        let info = ModelInfo {
            name: "roundtrip-test".to_string(),
            language: "en".to_string(),
            quality: "high".to_string(),
            description: "Roundtrip test model".to_string(),
            model_url: "https://example.com/m.onnx".to_string(),
            config_url: "https://example.com/c.json".to_string(),
            size_bytes: Some(42),
        };

        let json = serde_json::to_string(&info).unwrap();
        let deserialized: ModelInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.name, info.name);
        assert_eq!(deserialized.language, info.language);
        assert_eq!(deserialized.quality, info.quality);
        assert_eq!(deserialized.description, info.description);
        assert_eq!(deserialized.model_url, info.model_url);
        assert_eq!(deserialized.config_url, info.config_url);
        assert_eq!(deserialized.size_bytes, info.size_bytes);
    }

    #[test]
    fn test_model_info_size_bytes_optional() {
        let json = r#"{
            "name": "n",
            "language": "ja",
            "quality": "low",
            "description": "d",
            "model_url": "https://example.com/m.onnx",
            "config_url": "https://example.com/c.json",
            "size_bytes": null
        }"#;
        let info: ModelInfo = serde_json::from_str(json).unwrap();
        assert!(info.size_bytes.is_none());
    }

    // -- builtin_registry -----------------------------------------------------

    #[test]
    fn test_builtin_registry_non_empty() {
        let models = builtin_registry();
        assert!(
            models.len() >= 2,
            "builtin registry should contain at least 2 models"
        );
        // Every entry should have valid-looking URLs.
        for m in models {
            assert!(
                m.model_url.starts_with("https://"),
                "bad model_url: {}",
                m.model_url
            );
            assert!(
                m.config_url.starts_with("https://"),
                "bad config_url: {}",
                m.config_url
            );
            assert!(!m.name.is_empty());
        }
    }

    // -- DownloadProgress percentage ------------------------------------------

    #[test]
    fn test_download_progress_percentage() {
        let progress = DownloadProgress {
            bytes_downloaded: 50,
            total_bytes: Some(200),
            percentage: Some(25.0),
        };
        assert_eq!(progress.percentage, Some(25.0));
        assert_eq!(progress.bytes_downloaded, 50);
        assert_eq!(progress.total_bytes, Some(200));
    }

    #[test]
    fn test_download_progress_unknown_total() {
        let progress = DownloadProgress {
            bytes_downloaded: 1024,
            total_bytes: None,
            percentage: None,
        };
        assert!(progress.total_bytes.is_none());
        assert!(progress.percentage.is_none());
    }

    // -- url_filename (internal helper) ---------------------------------------

    #[test]
    fn test_url_filename_extraction() {
        assert_eq!(
            url_filename("https://example.com/path/to/model.onnx"),
            Some("model.onnx".to_string())
        );
        assert_eq!(url_filename("https://example.com/"), None);
        assert_eq!(url_filename("model.onnx"), Some("model.onnx".to_string()));
    }

    #[test]
    fn test_url_filename_strips_query_string() {
        assert_eq!(
            url_filename("https://example.com/model.onnx?token=abc123"),
            Some("model.onnx".to_string()),
        );
    }

    #[test]
    fn test_url_filename_strips_fragment() {
        assert_eq!(
            url_filename("https://example.com/model.onnx#section"),
            Some("model.onnx".to_string()),
        );
    }

    #[test]
    fn test_url_filename_strips_query_and_fragment() {
        assert_eq!(
            url_filename("https://example.com/model.onnx?v=2#top"),
            Some("model.onnx".to_string()),
        );
    }

    // -- download_file stub (non-download feature) ----------------------------

    #[cfg(not(feature = "download"))]
    #[test]
    fn test_download_file_stub_returns_error() {
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("out.onnx");
        let result = download_file("https://example.com/model.onnx", &dest, None);
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(
            msg.contains("download"),
            "error should mention the download feature: {msg}"
        );
    }

    #[cfg(not(feature = "download"))]
    #[test]
    fn test_download_model_stub_returns_error() {
        let dir = tempfile::tempdir().unwrap();
        let info = ModelInfo {
            name: "test".to_string(),
            language: "en".to_string(),
            quality: "medium".to_string(),
            description: "test".to_string(),
            model_url: "https://example.com/m.onnx".to_string(),
            config_url: "https://example.com/c.json".to_string(),
            size_bytes: None,
        };
        let result = download_model(&info, dir.path(), None);
        assert!(result.is_err());
    }

    // -- TDD additions: feature-gated paths & error handling ------------------

    #[test]
    fn test_download_progress_percentage_zero_total() {
        // When total_bytes is Some(0) the percentage calculation in
        // download_file uses `if t == 0 { 100.0 }`.  Verify the same
        // convention works when constructing DownloadProgress manually
        // (i.e. no division-by-zero panic).
        let total: Option<u64> = Some(0);
        let percentage = total.map(|t| {
            if t == 0 {
                100.0
            } else {
                (50_f64 / t as f64) * 100.0
            }
        });
        let progress = DownloadProgress {
            bytes_downloaded: 50,
            total_bytes: total,
            percentage,
        };
        assert_eq!(progress.percentage, Some(100.0));
        assert_eq!(progress.total_bytes, Some(0));
    }

    #[test]
    fn test_model_info_empty_fields() {
        // All-empty strings are structurally valid — no runtime panic.
        let info = ModelInfo {
            name: String::new(),
            language: String::new(),
            quality: String::new(),
            description: String::new(),
            model_url: String::new(),
            config_url: String::new(),
            size_bytes: None,
        };
        assert!(info.name.is_empty());
        assert!(info.size_bytes.is_none());

        // Roundtrip through JSON should also succeed.
        let json = serde_json::to_string(&info).unwrap();
        let back: ModelInfo = serde_json::from_str(&json).unwrap();
        assert!(back.name.is_empty());
    }

    #[test]
    fn test_huggingface_url_special_chars() {
        // Repo names with spaces or special characters — the function does
        // plain string interpolation so they must appear verbatim in the URL.
        let url = huggingface_url("owner/repo with spaces", "model (v2).onnx");
        assert!(url.starts_with("https://huggingface.co/"));
        assert!(url.contains("repo with spaces"));
        assert!(url.contains("model (v2).onnx"));

        // Unicode characters in repo name.
        let url2 = huggingface_url("user/日本語モデル", "model.onnx");
        assert!(url2.contains("日本語モデル"));
    }

    #[test]
    fn test_is_model_cached_empty_model_name() {
        let dir = tempfile::tempdir().unwrap();
        let dir_path = dir.path();

        // Empty model name produces ".onnx" and ".onnx.json" lookups.
        // Nothing exists so it must return false without panicking.
        assert!(!is_model_cached("", dir_path));

        // Even if we create the degenerate files, the logic should work.
        std::fs::write(dir_path.join(".onnx"), b"fake").unwrap();
        std::fs::write(dir_path.join(".onnx.json"), b"{}").unwrap();
        assert!(is_model_cached("", dir_path));
    }

    #[test]
    fn test_is_model_cached_with_subdirectory() {
        // A model_dir that does not exist on disk should return false,
        // never panic.
        let nonexistent = PathBuf::from("/tmp/piper_test_nonexistent_dir_12345");
        assert!(!is_model_cached("some-model", &nonexistent));
    }

    #[test]
    fn test_parse_model_registry_extra_fields() {
        // serde by default ignores unknown fields (no deny_unknown_fields).
        let json = r#"[
            {
                "name": "test",
                "language": "en",
                "quality": "medium",
                "description": "desc",
                "model_url": "https://example.com/m.onnx",
                "config_url": "https://example.com/c.json",
                "size_bytes": null,
                "author": "someone",
                "license": "MIT",
                "extra_nested": {"a": 1}
            }
        ]"#;
        let models = parse_model_registry(json).unwrap();
        assert_eq!(models.len(), 1);
        assert_eq!(models[0].name, "test");
    }

    #[test]
    fn test_parse_model_registry_unicode() {
        // Japanese/Chinese characters in name and description.
        let json = r#"[
            {
                "name": "つくよみちゃん",
                "language": "ja",
                "quality": "medium",
                "description": "高品質な日本語音声合成 — 中文描述也可以",
                "model_url": "https://example.com/model.onnx",
                "config_url": "https://example.com/config.json",
                "size_bytes": 999
            }
        ]"#;
        let models = parse_model_registry(json).unwrap();
        assert_eq!(models[0].name, "つくよみちゃん");
        assert!(models[0].description.contains("中文"));
    }

    #[test]
    fn test_builtin_registry_urls_format() {
        // Every URL in the builtin registry must start with https://
        // and reference huggingface.co.
        for m in builtin_registry() {
            assert!(
                m.model_url.starts_with("https://") && m.model_url.contains("huggingface"),
                "model_url must be an HTTPS HuggingFace URL, got: {}",
                m.model_url,
            );
            assert!(
                m.config_url.starts_with("https://") && m.config_url.contains("huggingface"),
                "config_url must be an HTTPS HuggingFace URL, got: {}",
                m.config_url,
            );
        }
    }

    #[test]
    fn test_default_model_dir_consistent() {
        // Calling twice must return the exact same path — no randomness
        // or time-dependent components.
        let a = default_model_dir();
        let b = default_model_dir();
        assert_eq!(a, b, "default_model_dir should be deterministic");
    }

    // -- find_model -----------------------------------------------------------

    #[test]
    fn test_find_model_exact_name() {
        let m = find_model("tsukuyomi-6lang-v2");
        assert!(m.is_some());
        assert_eq!(m.unwrap().name, "tsukuyomi-6lang-v2");
    }

    #[test]
    fn test_find_model_partial_name() {
        // "css10" is a unique substring across all model names.
        let m = find_model("css10");
        assert!(m.is_some());
        assert!(
            m.unwrap().name.contains("css10"),
            "partial name match should return a model containing the query string"
        );
    }

    #[test]
    fn test_find_model_description_match() {
        // "Tsukuyomi" appears only in one model's description.
        let m = find_model("Tsukuyomi");
        assert!(m.is_some());
        assert!(
            m.unwrap().description.to_lowercase().contains("tsukuyomi"),
            "description match should return a model whose description contains the query"
        );
    }

    #[test]
    fn test_find_model_case_insensitive_description() {
        let m = find_model("tsukuyomi");
        assert!(m.is_some());
        assert!(
            m.unwrap().description.to_lowercase().contains("tsukuyomi"),
            "case-insensitive description match should find a model"
        );
    }

    #[test]
    fn test_find_model_no_match() {
        let m = find_model("nonexistent-model-xyz");
        assert!(m.is_none());
    }

    #[test]
    fn test_find_model_ambiguous_returns_none() {
        // "6lang" appears in both model names, so partial match is ambiguous.
        let m = find_model("6lang");
        assert!(m.is_none(), "ambiguous partial match should return None");
    }

    // -- resolve_model_path ---------------------------------------------------

    #[test]
    fn test_resolve_model_path_existing_file() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("my-model.onnx");
        std::fs::write(&file, b"fake onnx").unwrap();

        let resolved = resolve_model_path(file.to_str().unwrap(), None).unwrap();
        assert_eq!(resolved, file);
    }

    #[test]
    fn test_resolve_model_path_cached_model() {
        let dir = tempfile::tempdir().unwrap();
        let dir_path = dir.path();

        // Create cached files for tsukuyomi-6lang-v2
        std::fs::write(dir_path.join("tsukuyomi-6lang-v2.onnx"), b"fake").unwrap();
        std::fs::write(dir_path.join("tsukuyomi-6lang-v2.onnx.json"), b"{}").unwrap();

        let resolved = resolve_model_path("tsukuyomi-6lang-v2", Some(dir_path)).unwrap();
        assert_eq!(resolved, dir_path.join("tsukuyomi-6lang-v2.onnx"));
    }

    #[test]
    fn test_resolve_model_path_cached_via_alias() {
        let dir = tempfile::tempdir().unwrap();
        let dir_path = dir.path();

        // "css10" partial match resolves to "css10-6lang"
        std::fs::write(dir_path.join("css10-6lang.onnx"), b"fake").unwrap();
        std::fs::write(dir_path.join("css10-6lang.onnx.json"), b"{}").unwrap();

        let resolved = resolve_model_path("css10", Some(dir_path)).unwrap();
        assert_eq!(resolved, dir_path.join("css10-6lang.onnx"));
    }

    #[test]
    fn test_resolve_model_path_unknown_model_error() {
        let result = resolve_model_path("nonexistent-model-xyz", None);
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(msg.contains("not found"), "error message: {msg}");
    }
}

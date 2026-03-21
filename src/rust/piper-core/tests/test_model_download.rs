use piper_plus::model_download::{
    DownloadProgress, ModelInfo, builtin_registry, default_model_dir, huggingface_url,
    is_model_cached, parse_model_registry,
};
use std::path::Path;

// ---------------------------------------------------------------------------
// huggingface_url construction
// ---------------------------------------------------------------------------

#[test]
fn test_huggingface_url_basic() {
    let url = huggingface_url("user/repo", "model.onnx");
    assert_eq!(
        url,
        "https://huggingface.co/user/repo/resolve/main/model.onnx"
    );
}

#[test]
fn test_huggingface_url_with_subdirectory() {
    let url = huggingface_url("user/repo", "subdir/model.onnx");
    assert_eq!(
        url,
        "https://huggingface.co/user/repo/resolve/main/subdir/model.onnx"
    );
}

#[test]
fn test_huggingface_url_empty_filename() {
    let url = huggingface_url("user/repo", "");
    assert_eq!(url, "https://huggingface.co/user/repo/resolve/main/");
}

#[test]
fn test_huggingface_url_real_repo() {
    let url = huggingface_url(
        "ayousanz/piper-plus-tsukuyomi-chan",
        "tsukuyomi-chan-6lang-fp16.onnx",
    );
    assert_eq!(
        url,
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx"
    );
}

// ---------------------------------------------------------------------------
// default_model_dir
// ---------------------------------------------------------------------------

#[test]
fn test_default_model_dir_returns_non_empty_path() {
    let dir = default_model_dir();
    assert!(
        !dir.as_os_str().is_empty(),
        "default_model_dir must not return an empty path"
    );
}

#[test]
fn test_default_model_dir_is_absolute() {
    let dir = default_model_dir();
    assert!(
        dir.is_absolute(),
        "default_model_dir should return an absolute path, got: {dir:?}"
    );
}

#[test]
fn test_default_model_dir_contains_piper() {
    let dir = default_model_dir();
    let path_str = dir.to_string_lossy();
    assert!(
        path_str.contains("piper"),
        "default_model_dir should contain 'piper' in the path, got: {path_str}"
    );
}

#[test]
fn test_default_model_dir_ends_with_models() {
    let dir = default_model_dir();
    assert_eq!(
        dir.file_name().and_then(|s| s.to_str()),
        Some("models"),
        "expected path to end with 'models', got: {dir:?}"
    );
}

// ---------------------------------------------------------------------------
// parse_model_registry
// ---------------------------------------------------------------------------

#[test]
fn test_parse_model_registry_valid_single_model() {
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
    assert_eq!(models[0].language, "ja");
    assert_eq!(models[0].quality, "medium");
    assert_eq!(models[0].description, "A test model");
    assert_eq!(models[0].model_url, "https://example.com/model.onnx");
    assert_eq!(models[0].config_url, "https://example.com/config.json");
    assert_eq!(models[0].size_bytes, Some(1024));
}

#[test]
fn test_parse_model_registry_multiple_models() {
    let json = r#"[
        {
            "name": "model-a",
            "language": "ja",
            "quality": "low",
            "description": "Model A",
            "model_url": "https://example.com/a.onnx",
            "config_url": "https://example.com/a.json",
            "size_bytes": null
        },
        {
            "name": "model-b",
            "language": "en",
            "quality": "high",
            "description": "Model B",
            "model_url": "https://example.com/b.onnx",
            "config_url": "https://example.com/b.json",
            "size_bytes": 2048
        }
    ]"#;
    let models = parse_model_registry(json).unwrap();
    assert_eq!(models.len(), 2);
    assert_eq!(models[0].name, "model-a");
    assert_eq!(models[1].name, "model-b");
    assert!(models[0].size_bytes.is_none());
    assert_eq!(models[1].size_bytes, Some(2048));
}

#[test]
fn test_parse_model_registry_empty_array() {
    let models = parse_model_registry("[]").unwrap();
    assert!(models.is_empty());
}

#[test]
fn test_parse_model_registry_invalid_json() {
    let result = parse_model_registry("not valid json at all");
    assert!(result.is_err());
}

#[test]
fn test_parse_model_registry_missing_required_fields() {
    let json = r#"[{"name": "incomplete"}]"#;
    let result = parse_model_registry(json);
    assert!(result.is_err());
}

#[test]
fn test_parse_model_registry_missing_name_field() {
    let json = r#"[{
        "language": "ja",
        "quality": "medium",
        "description": "no name",
        "model_url": "https://example.com/m.onnx",
        "config_url": "https://example.com/c.json",
        "size_bytes": null
    }]"#;
    let result = parse_model_registry(json);
    assert!(result.is_err());
}

// ---------------------------------------------------------------------------
// is_model_cached
// ---------------------------------------------------------------------------

#[test]
fn test_is_model_cached_nonexistent_directory() {
    assert!(!is_model_cached(
        "model",
        Path::new("/nonexistent/path/that/does/not/exist")
    ));
}

#[test]
fn test_is_model_cached_empty_directory() {
    let dir = tempfile::tempdir().unwrap();
    assert!(!is_model_cached("voice", dir.path()));
}

#[test]
fn test_is_model_cached_onnx_only_not_cached() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("voice.onnx"), b"fake onnx data").unwrap();
    assert!(
        !is_model_cached("voice", dir.path()),
        "model with only .onnx file (no config) should not be considered cached"
    );
}

#[test]
fn test_is_model_cached_with_onnx_json() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("voice.onnx"), b"fake onnx data").unwrap();
    std::fs::write(dir.path().join("voice.onnx.json"), b"{}").unwrap();
    assert!(
        is_model_cached("voice", dir.path()),
        "model with .onnx and .onnx.json should be considered cached"
    );
}

#[test]
fn test_is_model_cached_with_config_json() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("voice.onnx"), b"fake onnx data").unwrap();
    std::fs::write(dir.path().join("config.json"), b"{}").unwrap();
    assert!(
        is_model_cached("voice", dir.path()),
        "model with .onnx and config.json should be considered cached"
    );
}

#[test]
fn test_is_model_cached_config_only_not_cached() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("config.json"), b"{}").unwrap();
    assert!(
        !is_model_cached("voice", dir.path()),
        "config.json without .onnx should not be considered cached"
    );
}

#[test]
fn test_is_model_cached_wrong_model_name() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("other.onnx"), b"fake").unwrap();
    std::fs::write(dir.path().join("config.json"), b"{}").unwrap();
    assert!(
        !is_model_cached("voice", dir.path()),
        "cached files for 'other' should not match lookup for 'voice'"
    );
}

// ---------------------------------------------------------------------------
// builtin_registry
// ---------------------------------------------------------------------------

#[test]
fn test_builtin_registry_non_empty() {
    let models = builtin_registry();
    assert!(
        !models.is_empty(),
        "builtin registry should contain at least one model"
    );
}

#[test]
fn test_builtin_registry_all_have_non_empty_name() {
    let models = builtin_registry();
    for m in models {
        assert!(
            !m.name.is_empty(),
            "every model in builtin registry must have a non-empty name"
        );
    }
}

#[test]
fn test_builtin_registry_all_have_valid_urls() {
    let models = builtin_registry();
    for m in models {
        assert!(
            m.model_url.starts_with("https://"),
            "model_url should start with https://, got: {}",
            m.model_url
        );
        assert!(
            m.config_url.starts_with("https://"),
            "config_url should start with https://, got: {}",
            m.config_url
        );
    }
}

#[test]
fn test_builtin_registry_urls_contain_huggingface() {
    let models = builtin_registry();
    for m in models {
        assert!(
            m.model_url.contains("huggingface.co"),
            "model_url should reference huggingface.co, got: {}",
            m.model_url
        );
        assert!(
            m.config_url.contains("huggingface.co"),
            "config_url should reference huggingface.co, got: {}",
            m.config_url
        );
    }
}

#[test]
fn test_builtin_registry_all_have_non_empty_language() {
    let models = builtin_registry();
    for m in models {
        assert!(
            !m.language.is_empty(),
            "every model in builtin registry must have a non-empty language, model: {}",
            m.name
        );
    }
}

// ---------------------------------------------------------------------------
// ModelInfo — serialization, Clone, Debug
// ---------------------------------------------------------------------------

#[test]
fn test_model_info_serialization_roundtrip() {
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
fn test_model_info_size_bytes_none_roundtrip() {
    let info = ModelInfo {
        name: "no-size".to_string(),
        language: "ja".to_string(),
        quality: "low".to_string(),
        description: "d".to_string(),
        model_url: "https://example.com/m.onnx".to_string(),
        config_url: "https://example.com/c.json".to_string(),
        size_bytes: None,
    };

    let json = serde_json::to_string(&info).unwrap();
    let deserialized: ModelInfo = serde_json::from_str(&json).unwrap();
    assert!(deserialized.size_bytes.is_none());
}

#[test]
fn test_model_info_clone() {
    let original = ModelInfo {
        name: "clone-test".to_string(),
        language: "zh".to_string(),
        quality: "medium".to_string(),
        description: "Clone test model".to_string(),
        model_url: "https://example.com/m.onnx".to_string(),
        config_url: "https://example.com/c.json".to_string(),
        size_bytes: Some(999),
    };

    let cloned = original.clone();

    assert_eq!(cloned.name, original.name);
    assert_eq!(cloned.language, original.language);
    assert_eq!(cloned.quality, original.quality);
    assert_eq!(cloned.description, original.description);
    assert_eq!(cloned.model_url, original.model_url);
    assert_eq!(cloned.config_url, original.config_url);
    assert_eq!(cloned.size_bytes, original.size_bytes);
}

#[test]
fn test_model_info_debug_formatting() {
    let info = ModelInfo {
        name: "debug-test".to_string(),
        language: "fr".to_string(),
        quality: "high".to_string(),
        description: "Debug test".to_string(),
        model_url: "https://example.com/m.onnx".to_string(),
        config_url: "https://example.com/c.json".to_string(),
        size_bytes: Some(100),
    };

    let debug_str = format!("{:?}", info);
    assert!(
        debug_str.contains("debug-test"),
        "Debug output should contain the model name, got: {debug_str}"
    );
    assert!(
        debug_str.contains("ModelInfo"),
        "Debug output should contain the struct name, got: {debug_str}"
    );
}

// ---------------------------------------------------------------------------
// DownloadProgress
// ---------------------------------------------------------------------------

#[test]
fn test_download_progress_with_known_total() {
    let progress = DownloadProgress {
        bytes_downloaded: 50,
        total_bytes: Some(200),
        percentage: Some(25.0),
    };
    assert_eq!(progress.bytes_downloaded, 50);
    assert_eq!(progress.total_bytes, Some(200));
    assert_eq!(progress.percentage, Some(25.0));
}

#[test]
fn test_download_progress_unknown_total_bytes() {
    let progress = DownloadProgress {
        bytes_downloaded: 1024,
        total_bytes: None,
        percentage: None,
    };
    assert_eq!(progress.bytes_downloaded, 1024);
    assert!(progress.total_bytes.is_none());
    assert!(progress.percentage.is_none());
}

#[test]
fn test_download_progress_clone() {
    let progress = DownloadProgress {
        bytes_downloaded: 500,
        total_bytes: Some(1000),
        percentage: Some(50.0),
    };

    let cloned = progress.clone();
    assert_eq!(cloned.bytes_downloaded, progress.bytes_downloaded);
    assert_eq!(cloned.total_bytes, progress.total_bytes);
    assert_eq!(cloned.percentage, progress.percentage);
}

#[test]
fn test_download_progress_debug_formatting() {
    let progress = DownloadProgress {
        bytes_downloaded: 42,
        total_bytes: Some(100),
        percentage: Some(42.0),
    };

    let debug_str = format!("{:?}", progress);
    assert!(
        debug_str.contains("DownloadProgress"),
        "Debug output should contain the struct name, got: {debug_str}"
    );
    assert!(
        debug_str.contains("42"),
        "Debug output should contain bytes_downloaded value, got: {debug_str}"
    );
}

#[test]
fn test_download_progress_complete() {
    let progress = DownloadProgress {
        bytes_downloaded: 1000,
        total_bytes: Some(1000),
        percentage: Some(100.0),
    };
    assert_eq!(progress.percentage, Some(100.0));
    assert_eq!(progress.bytes_downloaded, progress.total_bytes.unwrap());
}

#[test]
fn test_download_progress_zero_bytes() {
    let progress = DownloadProgress {
        bytes_downloaded: 0,
        total_bytes: Some(500),
        percentage: Some(0.0),
    };
    assert_eq!(progress.bytes_downloaded, 0);
    assert_eq!(progress.percentage, Some(0.0));
}

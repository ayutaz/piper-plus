use piper_plus::PiperError;

// --- 1. ConfigNotFound ---
#[test]
fn test_config_not_found() {
    let err = PiperError::ConfigNotFound {
        path: "/foo/bar".to_string(),
    };
    let msg = format!("{}", err);
    assert!(msg.contains("/foo/bar"), "Display should contain path");
    assert!(msg.contains("config"), "Display should mention config");
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty(), "Debug should produce output");
    match err {
        PiperError::ConfigNotFound { path } => assert_eq!(path, "/foo/bar"),
        _ => panic!("wrong variant"),
    }
}

// --- 2. InvalidConfig ---
#[test]
fn test_invalid_config() {
    let err = PiperError::InvalidConfig {
        reason: "missing field".to_string(),
    };
    let msg = format!("{}", err);
    assert!(
        msg.contains("missing field"),
        "Display should contain reason"
    );
    assert!(
        msg.contains("invalid config"),
        "Display should mention invalid config"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::InvalidConfig { reason } => assert_eq!(reason, "missing field"),
        _ => panic!("wrong variant"),
    }
}

// --- 3. ModelLoad ---
#[test]
fn test_model_load() {
    let err = PiperError::ModelLoad("onnx init failed".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("onnx init failed"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("model load"),
        "Display should mention model load"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::ModelLoad(s) => assert_eq!(s, "onnx init failed"),
        _ => panic!("wrong variant"),
    }
}

// --- 4. UnsupportedLanguage ---
#[test]
fn test_unsupported_language() {
    let err = PiperError::UnsupportedLanguage {
        code: "xx".to_string(),
    };
    let msg = format!("{}", err);
    assert!(msg.contains("xx"), "Display should contain language code");
    assert!(
        msg.contains("unsupported language"),
        "Display should mention unsupported language"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::UnsupportedLanguage { code } => assert_eq!(code, "xx"),
        _ => panic!("wrong variant"),
    }
}

// --- 5. UnknownPhoneme ---
#[test]
fn test_unknown_phoneme() {
    let err = PiperError::UnknownPhoneme {
        phoneme: "zz".to_string(),
    };
    let msg = format!("{}", err);
    assert!(msg.contains("zz"), "Display should contain phoneme");
    assert!(
        msg.contains("unknown phoneme"),
        "Display should mention unknown phoneme"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::UnknownPhoneme { phoneme } => assert_eq!(phoneme, "zz"),
        _ => panic!("wrong variant"),
    }
}

// --- 6. Inference ---
#[test]
fn test_inference() {
    let err = PiperError::Inference("session run failed".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("session run failed"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("inference failed"),
        "Display should mention inference"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Inference(s) => assert_eq!(s, "session run failed"),
        _ => panic!("wrong variant"),
    }
}

// --- 7. AudioOutput ---
#[test]
fn test_audio_output() {
    let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "file missing");
    let err = PiperError::AudioOutput(io_err);
    let msg = format!("{}", err);
    assert!(
        msg.contains("file missing"),
        "Display should contain io error message"
    );
    assert!(
        msg.contains("audio output"),
        "Display should mention audio output"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match &err {
        PiperError::AudioOutput(e) => assert_eq!(e.kind(), std::io::ErrorKind::NotFound),
        _ => panic!("wrong variant"),
    }
}

// --- 8. JsonParse ---
#[test]
fn test_json_parse() {
    let json_err = serde_json::from_str::<serde_json::Value>("not json").unwrap_err();
    let expected_msg = json_err.to_string();
    let err = PiperError::JsonParse(json_err);
    let msg = format!("{}", err);
    assert!(
        msg.contains(&expected_msg),
        "Display should contain serde_json error message"
    );
    assert!(
        msg.contains("JSON parse"),
        "Display should mention JSON parse"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match &err {
        PiperError::JsonParse(_) => {}
        _ => panic!("wrong variant"),
    }
}

// --- 9. WavWrite ---
#[test]
fn test_wav_write() {
    let err = PiperError::WavWrite("header corrupt".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("header corrupt"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("WAV write"),
        "Display should mention WAV write"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::WavWrite(s) => assert_eq!(s, "header corrupt"),
        _ => panic!("wrong variant"),
    }
}

// --- 10. Phonemize ---
#[test]
fn test_phonemize() {
    let err = PiperError::Phonemize("g2p failed".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("g2p failed"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("phonemization"),
        "Display should mention phonemization"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Phonemize(s) => assert_eq!(s, "g2p failed"),
        _ => panic!("wrong variant"),
    }
}

// --- 11. DictionaryLoad ---
#[test]
fn test_dictionary_load() {
    let err = PiperError::DictionaryLoad {
        path: "/dict/custom.txt".to_string(),
    };
    let msg = format!("{}", err);
    assert!(
        msg.contains("/dict/custom.txt"),
        "Display should contain path"
    );
    assert!(
        msg.contains("dictionary load"),
        "Display should mention dictionary load"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::DictionaryLoad { path } => assert_eq!(path, "/dict/custom.txt"),
        _ => panic!("wrong variant"),
    }
}

// --- 12. JPreprocessInit ---
#[test]
fn test_jpreprocess_init() {
    let err = PiperError::JPreprocessInit("dict not found".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("dict not found"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("jpreprocess"),
        "Display should mention jpreprocess"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::JPreprocessInit(s) => assert_eq!(s, "dict not found"),
        _ => panic!("wrong variant"),
    }
}

// --- 13. LabelParse ---
#[test]
fn test_label_parse() {
    let err = PiperError::LabelParse("bad format".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("bad format"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("label parse"),
        "Display should mention label parse"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::LabelParse(s) => assert_eq!(s, "bad format"),
        _ => panic!("wrong variant"),
    }
}

// --- 14. PhonemeIdNotFound ---
#[test]
fn test_phoneme_id_not_found() {
    let err = PiperError::PhonemeIdNotFound {
        phoneme: "ky".to_string(),
    };
    let msg = format!("{}", err);
    assert!(msg.contains("ky"), "Display should contain phoneme");
    assert!(
        msg.contains("phoneme ID not found"),
        "Display should mention phoneme ID not found"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::PhonemeIdNotFound { phoneme } => assert_eq!(phoneme, "ky"),
        _ => panic!("wrong variant"),
    }
}

// --- 15. Streaming ---
#[test]
fn test_streaming() {
    let err = PiperError::Streaming("channel closed".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("channel closed"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("streaming"),
        "Display should mention streaming"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Streaming(s) => assert_eq!(s, "channel closed"),
        _ => panic!("wrong variant"),
    }
}

// --- 16. Playback ---
#[test]
fn test_playback() {
    let err = PiperError::Playback("no audio device".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("no audio device"),
        "Display should contain inner message"
    );
    assert!(msg.contains("playback"), "Display should mention playback");
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Playback(s) => assert_eq!(s, "no audio device"),
        _ => panic!("wrong variant"),
    }
}

// --- 17. Timing ---
#[test]
fn test_timing() {
    let err = PiperError::Timing("alignment mismatch".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("alignment mismatch"),
        "Display should contain inner message"
    );
    assert!(msg.contains("timing"), "Display should mention timing");
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Timing(s) => assert_eq!(s, "alignment mismatch"),
        _ => panic!("wrong variant"),
    }
}

// --- 18. Download ---
#[test]
fn test_download() {
    let err = PiperError::Download("404 not found".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("404 not found"),
        "Display should contain inner message"
    );
    assert!(msg.contains("download"), "Display should mention download");
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Download(s) => assert_eq!(s, "404 not found"),
        _ => panic!("wrong variant"),
    }
}

// --- 19. Resample ---
#[test]
fn test_resample() {
    let err = PiperError::Resample("unsupported rate".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("unsupported rate"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("resampling"),
        "Display should mention resampling"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Resample(s) => assert_eq!(s, "unsupported rate"),
        _ => panic!("wrong variant"),
    }
}

// --- 20. Device ---
#[test]
fn test_device() {
    let err = PiperError::Device("GPU unavailable".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("GPU unavailable"),
        "Display should contain inner message"
    );
    assert!(msg.contains("device"), "Display should mention device");
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Device(s) => assert_eq!(s, "GPU unavailable"),
        _ => panic!("wrong variant"),
    }
}

// --- 21. Batch ---
#[test]
fn test_batch() {
    let err = PiperError::Batch("empty input".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("empty input"),
        "Display should contain inner message"
    );
    assert!(
        msg.contains("batch processing"),
        "Display should mention batch processing"
    );
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Batch(s) => assert_eq!(s, "empty input"),
        _ => panic!("wrong variant"),
    }
}

// --- 22. Wasm ---
#[test]
fn test_wasm() {
    let err = PiperError::Wasm("wasm memory limit".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("wasm memory limit"),
        "Display should contain inner message"
    );
    assert!(msg.contains("WASM"), "Display should mention WASM");
    let dbg = format!("{:?}", err);
    assert!(!dbg.is_empty());
    match err {
        PiperError::Wasm(s) => assert_eq!(s, "wasm memory limit"),
        _ => panic!("wrong variant"),
    }
}

// --- 23. From<std::io::Error> -> AudioOutput ---
#[test]
fn test_from_io_error() {
    let io_err = std::io::Error::new(std::io::ErrorKind::PermissionDenied, "access denied");
    let err: PiperError = PiperError::from(io_err);
    match &err {
        PiperError::AudioOutput(e) => {
            assert_eq!(e.kind(), std::io::ErrorKind::PermissionDenied);
            assert!(e.to_string().contains("access denied"));
        }
        _ => panic!("From<io::Error> should produce AudioOutput, got: {:?}", err),
    }
}

// --- 24. From<serde_json::Error> -> JsonParse ---
#[test]
fn test_from_serde_json_error() {
    let json_err = serde_json::from_str::<serde_json::Value>("{invalid").unwrap_err();
    let expected_msg = json_err.to_string();
    let err: PiperError = PiperError::from(json_err);
    match &err {
        PiperError::JsonParse(e) => {
            assert_eq!(e.to_string(), expected_msg);
        }
        _ => panic!(
            "From<serde_json::Error> should produce JsonParse, got: {:?}",
            err
        ),
    }
}

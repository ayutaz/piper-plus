#![cfg(feature = "onnx")]

use piper_plus::PiperVoice;
use std::path::PathBuf;

#[test]
fn test_load_missing_model_fails() {
    let result = PiperVoice::load(&PathBuf::from("/nonexistent/model.onnx"), None, "cpu");
    assert!(result.is_err());
}

#[test]
fn test_load_missing_config_fails() {
    // Create a temp dir with no config.json
    let dir = tempfile::tempdir().unwrap();
    let model_path = dir.path().join("model.onnx");
    std::fs::write(&model_path, b"fake model data").unwrap();

    let result = PiperVoice::load(&model_path, None, "cpu");
    assert!(result.is_err());
}

// Additional tests for phoneme_converter integration
use piper_plus_g2p::ProsodyInfo;
use piper_plus_g2p::encode as phoneme_converter;
use std::collections::HashMap;

#[test]
fn test_prosody_to_features_preserves_values() {
    let prosody = vec![
        Some(ProsodyInfo {
            a1: -3,
            a2: 2,
            a3: 7,
        }),
        None,
        Some(ProsodyInfo {
            a1: 0,
            a2: 1,
            a3: 3,
        }),
    ];
    let features = phoneme_converter::prosody_to_features(&prosody);
    assert_eq!(features.len(), 3);
    assert_eq!(features[0], [-3, 2, 7]);
    assert_eq!(features[1], [0, 0, 0]); // None → zeros
    assert_eq!(features[2], [0, 1, 3]);
}

#[test]
fn test_tokens_to_ids_with_config_map() {
    let mut map: HashMap<String, Vec<i64>> = HashMap::new();
    map.insert("^".to_string(), vec![1]);
    map.insert("a".to_string(), vec![10]);
    map.insert("$".to_string(), vec![2]);

    let tokens: Vec<String> = ["^", "a", "$"].iter().map(|s| s.to_string()).collect();
    let ids = phoneme_converter::tokens_to_ids(&tokens, &map).unwrap();
    assert_eq!(ids, vec![1, 10, 2]);
}

#[test]
fn test_tokens_to_ids_error_on_unknown() {
    let map: HashMap<String, Vec<i64>> = HashMap::new();
    let tokens: Vec<String> = ["unknown"].iter().map(|s| s.to_string()).collect();
    let result = phoneme_converter::tokens_to_ids(&tokens, &map);
    assert!(result.is_err());
}

//! Phoneme token-to-ID conversion.
//!
//! Converts phoneme token strings to phoneme_id integers using the
//! phoneme_id_map from config.json, and builds `SynthesisRequest` structs
//! ready for ONNX inference.

use crate::config::PhonemeIdMap;
use crate::error::PiperError;

use super::ProsodyFeature;
use super::ProsodyInfo;

/// Convert a sequence of phoneme token strings to phoneme IDs.
///
/// Each token is a single character (regular or PUA). The token is looked up
/// in the phoneme_id_map to get the corresponding integer ID(s).
pub fn tokens_to_ids(
    tokens: &[String],
    phoneme_id_map: &PhonemeIdMap,
) -> Result<Vec<i64>, PiperError> {
    let mut ids = Vec::with_capacity(tokens.len() * 2);
    for token in tokens {
        match phoneme_id_map.get(token) {
            Some(id_list) => ids.extend(id_list.iter().copied()),
            None => {
                return Err(PiperError::PhonemeIdNotFound {
                    phoneme: token.clone(),
                });
            }
        }
    }
    Ok(ids)
}

/// Convert prosody info list to prosody features array (for ONNX input).
/// Each `ProsodyInfo` becomes `[a1, a2, a3]`. `None` becomes `[0, 0, 0]`.
pub fn prosody_to_features(prosody: &[Option<ProsodyInfo>]) -> Vec<ProsodyFeature> {
    prosody
        .iter()
        .map(|p| match p {
            Some(info) => [info.a1, info.a2, info.a3],
            None => [0, 0, 0],
        })
        .collect()
}

/// Build a complete `SynthesisRequest` from tokens, prosody, and config.
///
/// This is the final step before ONNX inference: it resolves token strings
/// to integer IDs and packs everything into the request struct.
pub fn build_synthesis_request(
    tokens: &[String],
    prosody: &[Option<ProsodyInfo>],
    phoneme_id_map: &PhonemeIdMap,
    speaker_id: Option<i64>,
    language_id: Option<i64>,
    noise_scale: f32,
    length_scale: f32,
    noise_w: f32,
) -> Result<crate::engine::SynthesisRequest, PiperError> {
    let ids = tokens_to_ids(tokens, phoneme_id_map)?;
    let features = prosody_to_features(prosody);

    Ok(crate::engine::SynthesisRequest {
        phoneme_ids: ids,
        prosody_features: Some(features),
        speaker_id,
        language_id,
        noise_scale,
        length_scale,
        noise_w,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    /// Helper: build a PhonemeIdMap from (key, ids) pairs.
    fn make_map(entries: &[(&str, &[i64])]) -> PhonemeIdMap {
        let mut map = HashMap::new();
        for (key, ids) in entries {
            map.insert(key.to_string(), ids.to_vec());
        }
        map
    }

    #[test]
    fn test_basic_token_to_id() {
        let map = make_map(&[
            ("^", &[1]),
            ("_", &[0]),
            ("$", &[2]),
            ("a", &[15]),
            ("k", &[30]),
        ]);
        let tokens: Vec<String> = vec!["^", "a", "_", "k", "$"]
            .into_iter()
            .map(String::from)
            .collect();

        let ids = tokens_to_ids(&tokens, &map).unwrap();
        assert_eq!(ids, vec![1, 15, 0, 30, 2]);
    }

    #[test]
    fn test_pua_character_conversion() {
        // PUA char U+E000 represents "a:" (long vowel)
        let map = make_map(&[
            ("^", &[1]),
            ("\u{E000}", &[45]),
            ("$", &[2]),
        ]);
        let tokens: Vec<String> = vec!["^", "\u{E000}", "$"]
            .into_iter()
            .map(String::from)
            .collect();

        let ids = tokens_to_ids(&tokens, &map).unwrap();
        assert_eq!(ids, vec![1, 45, 2]);
    }

    #[test]
    fn test_unknown_phoneme_error() {
        let map = make_map(&[("a", &[15])]);
        let tokens: Vec<String> = vec!["a", "Z"]
            .into_iter()
            .map(String::from)
            .collect();

        let result = tokens_to_ids(&tokens, &map);
        assert!(result.is_err());
        let err = result.unwrap_err();
        let msg = format!("{err}");
        assert!(
            msg.contains("Z"),
            "error message should contain the unknown phoneme 'Z', got: {msg}"
        );
    }

    #[test]
    fn test_prosody_conversion() {
        let prosody = vec![
            Some(ProsodyInfo {
                a1: -2,
                a2: 1,
                a3: 5,
            }),
            None,
            Some(ProsodyInfo {
                a1: 0,
                a2: 3,
                a3: 4,
            }),
        ];

        let features = prosody_to_features(&prosody);
        assert_eq!(features.len(), 3);
        assert_eq!(features[0], [-2, 1, 5]);
        assert_eq!(features[1], [0, 0, 0]);
        assert_eq!(features[2], [0, 3, 4]);
    }

    #[test]
    fn test_build_synthesis_request() {
        let map = make_map(&[
            ("^", &[1]),
            ("a", &[15]),
            ("$", &[2]),
        ]);
        let tokens: Vec<String> = vec!["^", "a", "$"]
            .into_iter()
            .map(String::from)
            .collect();
        let prosody = vec![
            None,
            Some(ProsodyInfo {
                a1: -1,
                a2: 2,
                a3: 3,
            }),
            None,
        ];

        let req = build_synthesis_request(
            &tokens,
            &prosody,
            &map,
            Some(5),
            Some(1),
            0.667,
            1.0,
            0.8,
        )
        .unwrap();

        assert_eq!(req.phoneme_ids, vec![1, 15, 2]);
        assert_eq!(req.speaker_id, Some(5));
        assert_eq!(req.language_id, Some(1));
        assert!((req.noise_scale - 0.667).abs() < 1e-6);
        assert!((req.length_scale - 1.0).abs() < 1e-6);
        assert!((req.noise_w - 0.8).abs() < 1e-6);

        let features = req.prosody_features.unwrap();
        assert_eq!(features.len(), 3);
        assert_eq!(features[0], [0, 0, 0]);
        assert_eq!(features[1], [-1, 2, 3]);
        assert_eq!(features[2], [0, 0, 0]);
    }

    #[test]
    fn test_multi_id_mapping() {
        // Some phoneme_id_map entries map to multiple IDs
        let map = make_map(&[("a", &[10, 11]), ("b", &[20])]);
        let tokens: Vec<String> = vec!["a", "b"]
            .into_iter()
            .map(String::from)
            .collect();

        let ids = tokens_to_ids(&tokens, &map).unwrap();
        assert_eq!(ids, vec![10, 11, 20]);
    }

    #[test]
    fn test_empty_tokens() {
        let map = make_map(&[("a", &[1])]);
        let tokens: Vec<String> = vec![];

        let ids = tokens_to_ids(&tokens, &map).unwrap();
        assert!(ids.is_empty());
    }
}

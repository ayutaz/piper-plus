//! Phoneme token-to-ID conversion.
//!
//! Converts phoneme token strings to phoneme_id integers using the
//! phoneme_id_map from config.json.

use crate::phonemizer::PhonemeIdMap;
use crate::error::G2pError;

use crate::phonemizer::ProsodyFeature;
use crate::phonemizer::ProsodyInfo;

/// Convert a sequence of phoneme token strings to phoneme IDs.
///
/// Each token is a single character (regular or PUA). The token is looked up
/// in the phoneme_id_map to get the corresponding integer ID(s).
pub fn tokens_to_ids(
    tokens: &[String],
    phoneme_id_map: &PhonemeIdMap,
) -> Result<Vec<i64>, G2pError> {
    let mut ids = Vec::with_capacity(tokens.len() * 2);
    for token in tokens {
        match phoneme_id_map.get(token) {
            Some(id_list) => ids.extend(id_list.iter().copied()),
            None => {
                return Err(G2pError::PhonemeIdNotFound {
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
        let map = make_map(&[("^", &[1]), ("\u{E000}", &[45]), ("$", &[2])]);
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
        let tokens: Vec<String> = vec!["a", "Z"].into_iter().map(String::from).collect();

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
    fn test_multi_id_mapping() {
        // Some phoneme_id_map entries map to multiple IDs
        let map = make_map(&[("a", &[10, 11]), ("b", &[20])]);
        let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();

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

//! Phoneme token-to-ID conversion.
//!
//! Converts phoneme token strings to phoneme_id integers using the
//! phoneme_id_map from config.json.

use crate::error::G2pError;
use crate::phonemizer::PhonemeIdMap;

use crate::phonemizer::ProsodyFeature;
use crate::phonemizer::ProsodyInfo;
use crate::token_map::token_to_pua;

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

/// Encoding mode for handling unknown tokens.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum UnknownTokenMode {
    /// Raise an error on unknown tokens (strict mode).
    Strict,
    /// Skip unknown tokens with a warning log (default).
    #[default]
    Skip,
}

/// High-level encoder that converts IPA token sequences into
/// Piper-compatible phoneme ID arrays with BOS/EOS/PAD insertion.
pub struct PiperEncoder {
    id_map: PhonemeIdMap,
    mode: UnknownTokenMode,
    bos_id: i64,
    eos_id: i64,
    pad_id: i64,
}

impl PiperEncoder {
    /// Create a new encoder from a phoneme ID map.
    pub fn new(id_map: PhonemeIdMap, mode: UnknownTokenMode) -> Result<Self, G2pError> {
        let bos_id = id_map
            .get("^")
            .and_then(|ids| ids.first().copied())
            .ok_or_else(|| G2pError::Phonemize("phoneme_id_map missing '^' (BOS)".into()))?;
        let eos_id = id_map
            .get("$")
            .and_then(|ids| ids.first().copied())
            .ok_or_else(|| G2pError::Phonemize("phoneme_id_map missing '$' (EOS)".into()))?;
        let pad_id = id_map
            .get("_")
            .and_then(|ids| ids.first().copied())
            .ok_or_else(|| G2pError::Phonemize("phoneme_id_map missing '_' (PAD)".into()))?;
        Ok(Self {
            id_map,
            mode,
            bos_id,
            eos_id,
            pad_id,
        })
    }

    /// Resolve the EOS phoneme ID for the given token.
    ///
    /// - `None` → default EOS (`"$"`)
    /// - `Some(token)` → look up the token in the id_map (direct, then PUA)
    fn resolve_eos_id(&self, eos_token: Option<&str>) -> Result<i64, G2pError> {
        match eos_token {
            None => Ok(self.eos_id),
            Some(token) => {
                // Try direct lookup first
                if let Some(&id) = self.id_map.get(token).and_then(|ids| ids.first()) {
                    return Ok(id);
                }
                // Try PUA mapping
                if let Some(pua_char) = token_to_pua(token) {
                    let pua_str = pua_char.to_string();
                    if let Some(&id) = self.id_map.get(&pua_str).and_then(|ids| ids.first()) {
                        return Ok(id);
                    }
                }
                Err(G2pError::PhonemeIdNotFound {
                    phoneme: token.to_string(),
                })
            }
        }
    }

    /// Encode IPA tokens to phoneme IDs with BOS/EOS/PAD insertion.
    pub fn encode(&self, tokens: &[String]) -> Result<Vec<i64>, G2pError> {
        self.encode_with_eos(tokens, None)
    }

    /// Encode IPA tokens with a custom EOS token.
    ///
    /// - `eos_token = None` → default EOS (`"$"`)
    /// - `eos_token = Some("?")` → look up `"?"` in id_map
    /// - `eos_token = Some("?!")` → look up PUA-mapped `"?!"` in id_map
    pub fn encode_with_eos(
        &self,
        tokens: &[String],
        eos_token: Option<&str>,
    ) -> Result<Vec<i64>, G2pError> {
        let (ids, _) = self.encode_with_prosody_and_eos(tokens, &[], eos_token)?;
        Ok(ids)
    }

    /// Encode IPA tokens with prosody alignment.
    pub fn encode_with_prosody(
        &self,
        tokens: &[String],
        prosody: &[Option<ProsodyInfo>],
    ) -> Result<(Vec<i64>, Vec<ProsodyFeature>), G2pError> {
        self.encode_with_prosody_and_eos(tokens, prosody, None)
    }

    /// Encode IPA tokens with prosody alignment and a custom EOS token.
    pub fn encode_with_prosody_and_eos(
        &self,
        tokens: &[String],
        prosody: &[Option<ProsodyInfo>],
        eos_token: Option<&str>,
    ) -> Result<(Vec<i64>, Vec<ProsodyFeature>), G2pError> {
        let resolved_eos = self.resolve_eos_id(eos_token)?;
        let mut ids = Vec::with_capacity(tokens.len() * 3 + 3);
        let mut pros = Vec::with_capacity(tokens.len() * 3 + 3);

        // BOS + PAD
        ids.push(self.bos_id);
        pros.push([0, 0, 0]);
        ids.push(self.pad_id);
        pros.push([0, 0, 0]);

        for (i, token) in tokens.iter().enumerate() {
            // If the token has a PUA mapping, use the single PUA char;
            // otherwise iterate the chars of the original token.
            let mapped: String = match token_to_pua(token) {
                Some(pua_char) => pua_char.to_string(),
                None => token.clone(),
            };
            for ch in mapped.chars() {
                let ch_str = ch.to_string();
                match self.id_map.get(&ch_str) {
                    Some(id_list) => {
                        let p = prosody.get(i).and_then(|o| o.as_ref());
                        let feat = match p {
                            Some(info) => [info.a1, info.a2, info.a3],
                            None => [0, 0, 0],
                        };
                        for &id in id_list {
                            ids.push(id);
                            pros.push(feat);
                        }
                    }
                    None => match self.mode {
                        UnknownTokenMode::Strict => {
                            return Err(G2pError::PhonemeIdNotFound { phoneme: ch_str });
                        }
                        UnknownTokenMode::Skip => {
                            tracing::warn!(phoneme = %ch_str, "unknown symbol dropped");
                        }
                    },
                }
            }
            ids.push(self.pad_id);
            pros.push([0, 0, 0]);
        }

        ids.push(resolved_eos);
        pros.push([0, 0, 0]);
        Ok((ids, pros))
    }
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

    #[test]
    fn test_piper_encoder_basic() {
        let map = make_map(&[
            ("^", &[1]),
            ("_", &[0]),
            ("$", &[2]),
            ("a", &[15]),
            ("k", &[30]),
        ]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a", "k"].into_iter().map(String::from).collect();
        let ids = encoder.encode(&tokens).unwrap();
        assert_eq!(ids[0], 1); // BOS
        assert_eq!(*ids.last().unwrap(), 2); // EOS
        assert!(ids.contains(&15));
        assert!(ids.contains(&30));
    }

    #[test]
    fn test_piper_encoder_strict_error() {
        let map = make_map(&[("^", &[1]), ("_", &[0]), ("$", &[2]), ("a", &[15])]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Strict).unwrap();
        let tokens: Vec<String> = vec!["a", "Z"].into_iter().map(String::from).collect();
        assert!(encoder.encode(&tokens).is_err());
    }

    #[test]
    fn test_piper_encoder_skip_unknown() {
        let map = make_map(&[("^", &[1]), ("_", &[0]), ("$", &[2]), ("a", &[15])]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a", "Z"].into_iter().map(String::from).collect();
        let ids = encoder.encode(&tokens).unwrap();
        assert!(ids.contains(&15));
    }

    #[test]
    fn test_piper_encoder_missing_bos() {
        let map = make_map(&[("_", &[0]), ("$", &[2])]);
        assert!(PiperEncoder::new(map, UnknownTokenMode::Skip).is_err());
    }

    #[test]
    fn test_encode_with_default_eos() {
        let map = make_map(&[
            ("^", &[1]),
            ("_", &[0]),
            ("$", &[2]),
            ("a", &[15]),
            ("k", &[30]),
        ]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a", "k"].into_iter().map(String::from).collect();
        let ids_default = encoder.encode(&tokens).unwrap();
        let ids_none = encoder.encode_with_eos(&tokens, None).unwrap();
        assert_eq!(ids_default, ids_none);
    }

    #[test]
    fn test_encode_with_question_eos() {
        let map = make_map(&[
            ("^", &[1]),
            ("_", &[0]),
            ("$", &[2]),
            ("?", &[99]),
            ("a", &[15]),
        ]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();
        let ids = encoder.encode_with_eos(&tokens, Some("?")).unwrap();
        // Last element should be "?" ID (99), not default EOS (2)
        assert_eq!(*ids.last().unwrap(), 99);
        // BOS should still be first
        assert_eq!(ids[0], 1);
    }

    #[test]
    fn test_encode_with_pua_eos() {
        // "?!" maps to PUA U+E016 via token_to_pua
        let pua_char = crate::token_map::token_to_pua("?!").unwrap();
        let pua_str = pua_char.to_string();
        let map = make_map(&[
            ("^", &[1]),
            ("_", &[0]),
            ("$", &[2]),
            (&pua_str, &[88]),
            ("a", &[15]),
        ]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();
        let ids = encoder.encode_with_eos(&tokens, Some("?!")).unwrap();
        assert_eq!(*ids.last().unwrap(), 88);
    }

    #[test]
    fn test_encode_with_prosody_and_eos() {
        let map = make_map(&[
            ("^", &[1]),
            ("_", &[0]),
            ("$", &[2]),
            ("?", &[99]),
            ("a", &[15]),
        ]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();
        let prosody = vec![Some(ProsodyInfo {
            a1: -2,
            a2: 1,
            a3: 5,
        })];
        let (ids, pros) = encoder
            .encode_with_prosody_and_eos(&tokens, &prosody, Some("?"))
            .unwrap();
        // Last ID should be custom EOS
        assert_eq!(*ids.last().unwrap(), 99);
        // Prosody for EOS should be zero
        assert_eq!(*pros.last().unwrap(), [0, 0, 0]);
        // ids and pros must have same length
        assert_eq!(ids.len(), pros.len());
    }

    #[test]
    fn test_resolve_eos_invalid() {
        let map = make_map(&[("^", &[1]), ("_", &[0]), ("$", &[2]), ("a", &[15])]);
        let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
        let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();
        let result = encoder.encode_with_eos(&tokens, Some("NONEXISTENT"));
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(
            msg.contains("NONEXISTENT"),
            "error should mention the unknown token, got: {msg}"
        );
    }
}

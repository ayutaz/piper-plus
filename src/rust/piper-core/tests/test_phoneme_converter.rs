use piper_plus_g2p::ProsodyInfo;
use piper_plus_g2p::encode as phoneme_converter;
use std::collections::HashMap;

fn make_test_id_map() -> HashMap<String, Vec<i64>> {
    let mut map = HashMap::new();
    map.insert("_".to_string(), vec![0]);
    map.insert("^".to_string(), vec![1]);
    map.insert("$".to_string(), vec![2]);
    map.insert("?".to_string(), vec![3]);
    map.insert("a".to_string(), vec![10]);
    map.insert("i".to_string(), vec![11]);
    map.insert("k".to_string(), vec![12]);
    map.insert("o".to_string(), vec![13]);
    map.insert("N".to_string(), vec![14]);
    map.insert("#".to_string(), vec![15]);
    map.insert("[".to_string(), vec![16]);
    map.insert("]".to_string(), vec![17]);
    // PUA characters
    map.insert("\u{E000}".to_string(), vec![20]); // a: long vowel
    map.insert("\u{E019}".to_string(), vec![21]); // N_m
    map
}

#[test]
fn test_basic_token_conversion() {
    let map = make_test_id_map();
    let tokens: Vec<String> = ["^", "k", "o", "$"].iter().map(|s| s.to_string()).collect();
    let ids = phoneme_converter::tokens_to_ids(&tokens, &map).unwrap();
    assert_eq!(ids, vec![1, 12, 13, 2]);
}

#[test]
fn test_pua_token_conversion() {
    let map = make_test_id_map();
    let tokens: Vec<String> = ["\u{E000}"].iter().map(|s| s.to_string()).collect();
    let ids = phoneme_converter::tokens_to_ids(&tokens, &map).unwrap();
    assert_eq!(ids, vec![20]);
}

#[test]
fn test_unknown_phoneme_error() {
    let map = make_test_id_map();
    let tokens: Vec<String> = ["z"].iter().map(|s| s.to_string()).collect();
    let result = phoneme_converter::tokens_to_ids(&tokens, &map);
    assert!(result.is_err());
    let err = result.unwrap_err();
    let msg = format!("{err}");
    assert!(
        msg.contains("z"),
        "error message should contain the unknown phoneme 'z', got: {msg}"
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
            a2: 2,
            a3: 5,
        }),
    ];
    let features = phoneme_converter::prosody_to_features(&prosody);
    assert_eq!(features[0], [-2, 1, 5]);
    assert_eq!(features[1], [0, 0, 0]);
    assert_eq!(features[2], [0, 2, 5]);
}

#[test]
fn test_empty_input() {
    let map = make_test_id_map();
    let tokens: Vec<String> = vec![];
    let ids = phoneme_converter::tokens_to_ids(&tokens, &map).unwrap();
    assert!(ids.is_empty());
}

#[test]
fn test_prosody_all_none() {
    let prosody: Vec<Option<ProsodyInfo>> = vec![None, None, None];
    let features = phoneme_converter::prosody_to_features(&prosody);
    assert!(features.iter().all(|f| *f == [0, 0, 0]));
}

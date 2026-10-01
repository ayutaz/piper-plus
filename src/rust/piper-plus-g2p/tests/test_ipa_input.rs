//! Model-specific IPA input contracts for Issue #752.
use piper_plus_g2p::{IpaTokenizer, PhonemeIdMap, PiperEncoder, UnknownTokenMode};

fn map(entries: &[(&str, &[i64])]) -> PhonemeIdMap {
    [("^", &[1][..]), ("_", &[0][..]), ("$", &[2][..])]
        .into_iter()
        .chain(entries.iter().copied())
        .map(|(token, ids)| (token.to_owned(), ids.to_vec()))
        .collect()
}

fn encode(entries: &[(&str, &[i64])], ipa: &str) -> Vec<i64> {
    PiperEncoder::new(map(entries), UnknownTokenMode::Strict)
        .unwrap()
        .encode_ipa(ipa)
        .unwrap()
}

#[test]
fn single_symbols_need_no_language_backend() {
    assert_eq!(encode(&[("k", &[3]), ("a", &[4])], "ka"), [1, 0, 3, 0, 4, 0, 2]);
}

#[test]
fn pua_affricate_is_one_token() {
    let model = map(&[("\u{e054}", &[3]), ("a", &[4])]);
    assert_eq!(IpaTokenizer::new(&model).tokenize("tʃa").unwrap(), ["tʃ", "a"]);
    assert_eq!(encode(&[("\u{e054}", &[3]), ("a", &[4])], "tʃa"), [1, 0, 3, 0, 4, 0, 2]);
}

#[test]
fn legacy_model_keeps_character_ids_without_requiring_pua() {
    assert_eq!(encode(&[("t", &[3]), ("ʃ", &[4])], "tʃ"), [1, 0, 3, 0, 4, 0, 2]);
}

#[test]
fn combining_mark_and_aspiration_use_longest_supported_token() {
    let model = map(&[("\u{e056}", &[3]), ("\u{e023}", &[4]), ("\u{e024}", &[5])]);
    assert_eq!(IpaTokenizer::new(&model).tokenize("ɛ̃tɕʰ").unwrap(), ["ɛ̃", "tɕʰ"]);
}

#[test]
fn unsupported_global_pua_alias_does_not_override_model_segmentation() {
    let model = map(&[("a", &[3]), ("n", &[4])]);
    assert_eq!(IpaTokenizer::new(&model).tokenize("an").unwrap(), ["a", "n"]);
}

#[test]
fn ambiguous_supported_compound_is_greedy() {
    let model = map(&[("a", &[3]), ("n", &[4]), ("\u{e02c}", &[5])]);
    assert_eq!(IpaTokenizer::new(&model).tokenize("an").unwrap(), ["an"]);
}

#[test]
fn direct_multi_character_keys_are_supported() {
    assert_eq!(encode(&[("tʃ", &[3]), ("iː", &[4])], "tʃiː"), [1, 0, 3, 0, 4, 0, 2]);
}

#[test]
fn literal_model_key_wins_over_pua_alias() {
    assert_eq!(encode(&[("tʃ", &[3]), ("\u{e054}", &[9])], "tʃ"), [1, 0, 3, 0, 2]);
}

#[test]
fn multiple_ids_get_one_pad_per_model_token() {
    assert_eq!(encode(&[("a", &[3, 4]), ("n", &[5])], "an"), [1, 0, 3, 4, 0, 5, 0, 2]);
}

#[test]
fn word_boundary_and_stress_are_preserved_when_supported() {
    assert_eq!(encode(&[("ˈ", &[3]), ("a", &[4]), (" ", &[5])], "ˈa a"), [1, 0, 3, 0, 4, 0, 5, 0, 4, 0, 2]);
}

#[test]
fn unknown_unicode_reports_byte_offset_even_in_skip_mode() {
    let encoder = PiperEncoder::new(map(&[("ə", &[3])]), UnknownTokenMode::Skip).unwrap();
    let error = encoder.encode_ipa("əʘ").unwrap_err().to_string();
    assert!(error.contains('ʘ'), "{error}");
    assert!(error.contains("byte 2"), "{error}");
}

#[test]
fn unsupported_combining_mark_is_not_silently_dropped() {
    let encoder = PiperEncoder::new(map(&[("ɛ", &[3])]), UnknownTokenMode::Skip).unwrap();
    assert!(encoder.encode_ipa("ɛ̃").is_err());
}

#[test]
fn spaces_are_not_implicitly_token_separators() {
    let tokenizer = IpaTokenizer::new(&map(&[("a", &[3]), ("n", &[4])]));
    assert!(tokenizer.tokenize("a n").is_err());
}

#[test]
fn empty_input_and_internal_markers_are_rejected() {
    let tokenizer = IpaTokenizer::new(&map(&[("a", &[3])]));
    for input in ["", "^a", "a$", "a_", "/a/", "[a]"] {
        assert!(tokenizer.tokenize(input).is_err(), "accepted {input:?}");
    }
}

#[test]
fn empty_id_entries_are_not_supported_tokens() {
    let tokenizer = IpaTokenizer::new(&map(&[("a", &[])]));
    assert!(tokenizer.tokenize("a").is_err());
}

#[test]
fn unicode_spellings_are_not_automatically_normalized() {
    let tokenizer = IpaTokenizer::new(&map(&[("ã", &[3])]));
    assert_eq!(tokenizer.tokenize("ã").unwrap(), ["ã"]);
    assert!(tokenizer.tokenize("ã").is_err());
}

#[test]
fn existing_encoding_contract_is_unchanged() {
    let encoder = PiperEncoder::new(map(&[("a", &[3])]), UnknownTokenMode::Skip).unwrap();
    assert_eq!(encoder.encode(&["a".into(), "Z".into()]).unwrap(), [1, 0, 3, 0, 0, 2]);
}

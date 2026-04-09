//! Integration tests for the Swedish (SV) phonemizer.
//!
//! Validates that `SwedishPhonemizer` is correctly wired into the `piper-core`
//! phonemizer infrastructure: trait implementation, post-processing, language
//! detection, and basic phonemization quality.
//!
//! No external data dependencies (rule-based G2P).

use piper_plus::phonemize::Phonemizer;
use piper_plus::phonemize::swedish::SwedishPhonemizer;

// =========================================================================
// Basic trait compliance
// =========================================================================

#[test]
fn test_language_code() {
    let p = SwedishPhonemizer::new();
    assert_eq!(p.language_code(), "sv");
}

#[test]
fn test_default_impl() {
    let p = SwedishPhonemizer;
    assert_eq!(p.language_code(), "sv");
}

#[test]
fn test_get_phoneme_id_map_returns_none() {
    let p = SwedishPhonemizer::new();
    assert!(
        p.get_phoneme_id_map().is_none(),
        "Swedish phonemizer should return None for phoneme_id_map (uses config.json)"
    );
}

// =========================================================================
// Basic phonemization
// =========================================================================

#[test]
fn test_phonemize_basic_word() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("hej").unwrap();
    assert!(!tokens.is_empty(), "should produce phonemes for 'hej'");
    assert_eq!(
        tokens.len(),
        prosody.len(),
        "tokens and prosody must have same length"
    );
}

#[test]
fn test_phonemize_tack() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("tack").unwrap();
    assert!(!tokens.is_empty(), "should produce phonemes for 'tack'");
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_phonemize_sentence() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("Hur m\u{00e5}r du idag?").unwrap();
    assert!(
        !tokens.is_empty(),
        "should produce phonemes for a Swedish sentence"
    );
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_phonemize_god_morgon() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p
        .phonemize_with_prosody("God morgon, hur m\u{00e5}r du?")
        .unwrap();
    assert!(!tokens.is_empty());
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_phonemize_empty() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("").unwrap();
    assert!(tokens.is_empty());
    assert!(prosody.is_empty());
}

// =========================================================================
// Multi-word and punctuation
// =========================================================================

#[test]
fn test_multi_word_has_space() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("god dag").unwrap();
    assert!(
        tokens.iter().any(|t| t == " "),
        "multi-word input should contain space separator in {:?}",
        tokens
    );
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_punctuation_passthrough() {
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("hej!").unwrap();
    assert!(
        tokens.iter().any(|t| t == "!"),
        "punctuation should pass through in {:?}",
        tokens
    );
}

#[test]
fn test_question_mark() {
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("Var \u{00e4}r du?").unwrap();
    assert!(
        tokens.iter().any(|t| t == "?"),
        "question mark should pass through in {:?}",
        tokens
    );
}

// =========================================================================
// Swedish-specific phonology: sj-ljud, tj-ljud
// =========================================================================

#[test]
fn test_sj_sound_skjorta() {
    // "sj" cluster -> sj-ljud (voiceless fricative)
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("sjuk").unwrap();
    // The sj-ljud phoneme varies by implementation; just verify non-empty output
    assert!(
        !tokens.is_empty(),
        "sj-cluster word 'sjuk' should produce phonemes"
    );
}

#[test]
fn test_sk_before_front_vowel() {
    // "sk" before front vowels (e, i, y, \u{00e4}, \u{00f6}) -> sj-ljud
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("ske").unwrap();
    assert!(
        !tokens.is_empty(),
        "'ske' should produce phonemes (sk before front vowel)"
    );
}

#[test]
fn test_tj_sound() {
    // "tj" -> voiceless palatal fricative
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("tjugo").unwrap();
    assert!(
        !tokens.is_empty(),
        "'tjugo' should produce phonemes (tj-ljud)"
    );
}

#[test]
fn test_kj_sound() {
    // "kj" -> same as tj-ljud
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("kjol").unwrap();
    assert!(
        !tokens.is_empty(),
        "'kjol' should produce phonemes (kj -> tj-ljud)"
    );
}

// =========================================================================
// Swedish vowel system: \u{00e5}, \u{00e4}, \u{00f6}
// =========================================================================

#[test]
fn test_a_ring_vowel() {
    // \u{00e5} is a distinct vowel in Swedish
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("\u{00e5}r").unwrap();
    assert!(!tokens.is_empty(), "'\u{00e5}r' should produce phonemes");
}

#[test]
fn test_a_umlaut_vowel() {
    // \u{00e4} is a distinct vowel in Swedish
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("\u{00e4}pple").unwrap();
    assert!(!tokens.is_empty(), "'\u{00e4}pple' should produce phonemes");
}

#[test]
fn test_o_umlaut_vowel() {
    // \u{00f6} is a distinct vowel in Swedish
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("\u{00f6}ga").unwrap();
    assert!(!tokens.is_empty(), "'\u{00f6}ga' should produce phonemes");
}

// =========================================================================
// Retroflexes (consonant clusters with r)
// =========================================================================

#[test]
fn test_retroflex_rt() {
    // "rt" may produce retroflex in some positions
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("kort").unwrap();
    assert!(
        !tokens.is_empty(),
        "'kort' should produce phonemes (potential retroflex)"
    );
}

#[test]
fn test_retroflex_rn() {
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("barn").unwrap();
    assert!(
        !tokens.is_empty(),
        "'barn' should produce phonemes (potential retroflex)"
    );
}

// =========================================================================
// Post-process IDs (BOS/EOS/padding)
// =========================================================================

#[test]
fn test_post_process_ids_inserts_bos_eos() {
    let p = SwedishPhonemizer::new();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("^".to_string(), vec![1i64]);
    id_map.insert("$".to_string(), vec![2i64]);
    id_map.insert("_".to_string(), vec![0i64]);

    let ids = vec![10i64, 20, 30];
    let prosody = vec![Some([0i32, 0, 0]), Some([0, 0, 0]), Some([0, 0, 0])];

    let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);

    // Should start with BOS and end with EOS
    assert_eq!(*result_ids.first().unwrap(), 1, "should start with BOS");
    assert_eq!(*result_ids.last().unwrap(), 2, "should end with EOS");
    // Should contain original phoneme IDs
    assert!(
        result_ids.contains(&10) && result_ids.contains(&20) && result_ids.contains(&30),
        "should contain all original phoneme IDs in {:?}",
        result_ids,
    );
    // IDs and prosody must have same length
    assert_eq!(
        result_ids.len(),
        result_prosody.len(),
        "IDs and prosody must have same length"
    );
    // Should have padding between phonemes
    assert!(
        result_ids.len() > 5,
        "should have BOS + padded phonemes + EOS, got {:?}",
        result_ids,
    );
}

// =========================================================================
// detect_primary_language
// =========================================================================

#[test]
fn test_detect_primary_language_returns_sv() {
    let p = SwedishPhonemizer::new();
    assert_eq!(
        p.detect_primary_language("Hej, hur m\u{00e5}r du?"),
        "sv",
        "detect_primary_language should return 'sv' for Swedish phonemizer"
    );
}

#[test]
fn test_detect_primary_language_empty_string() {
    let p = SwedishPhonemizer::new();
    assert_eq!(
        p.detect_primary_language(""),
        "sv",
        "detect_primary_language should return 'sv' even for empty input"
    );
}

// =========================================================================
// Engine-level phonemizer selection via PiperVoice::create_phonemizer
// =========================================================================

#[cfg(feature = "onnx")]
mod engine_integration {
    use piper_plus::PiperVoice;
    use piper_plus::config::{PhonemeType, VoiceConfig};
    use std::collections::HashMap;

    #[test]
    fn test_sv_phonemizer_selected_in_multilingual_config() {
        // A multilingual config that includes SV should create a phonemizer
        // that can handle Swedish text.
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 100,
            num_symbols: 173,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 3,
            language_id_map: [("en".into(), 0i64), ("es".into(), 1), ("sv".into(), 2)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        let result = PiperVoice::create_phonemizer(&config, None);
        assert!(
            result.is_ok(),
            "create_phonemizer with SV should succeed: {:?}",
            result.err()
        );
        let phonemizer = result.unwrap();

        // The multilingual phonemizer should be able to phonemize Swedish text
        let (tokens, prosody) = phonemizer
            .phonemize_with_prosody("Hej, jag heter Anna.")
            .unwrap();
        assert!(!tokens.is_empty(), "should phonemize Swedish text");
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_sv_only_multilingual_config() {
        // SV as the sole non-English language
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 10,
            num_symbols: 100,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: [("en".into(), 0i64), ("sv".into(), 1)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        let result = PiperVoice::create_phonemizer(&config, None);
        assert!(
            result.is_ok(),
            "create_phonemizer with en+sv should succeed: {:?}",
            result.err()
        );
        let phonemizer = result.unwrap();
        // Default latin should be "en"
        assert_eq!(phonemizer.language_code(), "en");
    }

    #[test]
    fn test_sv_default_latin_fallback() {
        // When 'en' is not present, SV should be selected as default_latin
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 10,
            num_symbols: 100,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: [("zh".into(), 0i64), ("sv".into(), 1)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        let result = PiperVoice::create_phonemizer(&config, None);
        assert!(
            result.is_ok(),
            "create_phonemizer with zh+sv should succeed: {:?}",
            result.err()
        );
        let phonemizer = result.unwrap();
        // SV should be selected as default_latin (it's in the es/fr/pt/sv fallback list)
        assert_eq!(phonemizer.language_code(), "sv");
    }
}

// =========================================================================
// Snapshot / quality tests (baseline for M2-21 feedback)
// =========================================================================

#[test]
fn test_stockholm_produces_output() {
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("Stockholm").unwrap();
    assert!(
        tokens.len() >= 3,
        "'Stockholm' should produce at least 3 phonemes, got {:?}",
        tokens
    );
}

#[test]
fn test_common_phrase_jag_heter() {
    let p = SwedishPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("Jag heter Erik.").unwrap();
    assert!(
        tokens.len() >= 5,
        "'Jag heter Erik.' should produce multiple phonemes, got {:?}",
        tokens
    );
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_numbers_passthrough_or_skip() {
    let p = SwedishPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("123").unwrap();
    // Numbers should either be skipped or passed through
    assert!(
        tokens.is_empty() || tokens.iter().all(|t| t.len() <= 1),
        "digits should be handled gracefully: {:?}",
        tokens
    );
}

#[test]
fn test_special_characters() {
    let p = SwedishPhonemizer::new();
    // Should not panic on special characters
    let (tokens, prosody) = p.phonemize_with_prosody("@#%&").unwrap();
    assert_eq!(tokens.len(), prosody.len());
}

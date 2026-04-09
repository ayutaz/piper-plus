//! Integration tests for Korean and Swedish G2P pipelines.
//!
//! Verifies the full encoding roundtrip: Phonemizer -> PiperEncoder,
//! custom dictionary application, and multilingual phonemization with ko/sv.

use std::collections::HashMap;

use piper_plus_g2p::encode::{PiperEncoder, UnknownTokenMode};
use piper_plus_g2p::phonemizer::{PhonemeIdMap, Phonemizer};
use piper_plus_g2p::token_map::token_to_pua;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Build a PhonemeIdMap with BOS/EOS/PAD plus additional entries.
fn make_id_map(extra: &[(&str, i64)]) -> PhonemeIdMap {
    let mut map: PhonemeIdMap = HashMap::new();
    map.insert("^".to_string(), vec![1]); // BOS
    map.insert("$".to_string(), vec![2]); // EOS
    map.insert("_".to_string(), vec![0]); // PAD
    map.insert(" ".to_string(), vec![3]); // space
    map.insert(".".to_string(), vec![4]); // period

    for (key, id) in extra {
        map.insert(key.to_string(), vec![*id]);
    }
    map
}

// ===========================================================================
// 1. Korean encoding roundtrip
// ===========================================================================

#[cfg(feature = "korean")]
mod korean_encoding {
    use super::*;
    use piper_plus_g2p::korean::KoreanPhonemizer;

    #[test]
    fn test_korean_encoding_roundtrip_ga() {
        // Phonemize "가" -> expect tokens ["k", "a"]
        let phonemizer = KoreanPhonemizer::new();
        let (tokens, _prosody) = phonemizer.phonemize_with_prosody("가").unwrap();
        assert!(!tokens.is_empty(), "phonemization should produce tokens");

        // Build an id_map covering the expected tokens
        let mut extra: Vec<(&str, i64)> = vec![("k", 10), ("a", 11)];

        // Add PUA entries for tense consonants that might appear in other tests
        if let Some(pua) = token_to_pua("k\u{0348}") {
            // k͈ (tense k)
            extra.push(("placeholder_kk", 50));
            // We need the actual PUA char as key
            let _ = pua; // used below
        }

        let id_map = make_id_map(&extra);
        let encoder = PiperEncoder::new(id_map, UnknownTokenMode::Skip).unwrap();
        let ids = encoder.encode(&tokens).unwrap();

        // Verify BOS at start, EOS at end
        assert_eq!(ids[0], 1, "first ID should be BOS (1)");
        assert_eq!(*ids.last().unwrap(), 2, "last ID should be EOS (2)");

        // Verify token IDs are present
        assert!(ids.contains(&10), "should contain ID for 'k'");
        assert!(ids.contains(&11), "should contain ID for 'a'");
    }

    #[test]
    fn test_korean_tense_consonant_pua_mapping() {
        // Phonemize "까" -> tense ㄲ should produce PUA_KK (U+E04D) + "a"
        let phonemizer = KoreanPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody("까").unwrap();

        // The tense consonant k͈ should be mapped to PUA U+E04D
        let pua_kk = token_to_pua("k\u{0348}").expect("PUA mapping for k͈ should exist");
        let pua_kk_str = pua_kk.to_string();

        assert!(
            tokens.contains(&pua_kk_str),
            "tokens should contain PUA for tense k (k͈): got {:?}",
            tokens
        );

        // Now encode with a map that includes the PUA char
        let mut id_map = make_id_map(&[("a", 11)]);
        id_map.insert(pua_kk_str.clone(), vec![50]);

        let encoder = PiperEncoder::new(id_map, UnknownTokenMode::Skip).unwrap();
        let ids = encoder.encode(&tokens).unwrap();

        assert!(
            ids.contains(&50),
            "encoded IDs should contain the PUA-mapped tense k ID"
        );
        assert!(ids.contains(&11), "encoded IDs should contain 'a' ID");
    }

    #[test]
    fn test_korean_unreleased_final_pua() {
        // "박" -> p + a + k̚ (unreleased final, PUA U+E050)
        let phonemizer = KoreanPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody("박").unwrap();

        let pua_k_unrel = token_to_pua("k\u{031a}").expect("PUA mapping for k̚ should exist");
        let pua_str = pua_k_unrel.to_string();

        assert!(
            tokens.contains(&pua_str),
            "tokens for '박' should contain unreleased k̚ PUA: got {:?}",
            tokens
        );
    }

    #[test]
    fn test_korean_multi_syllable_encoding() {
        // "한글" -> h a n k ɯ l (6 tokens)
        let phonemizer = KoreanPhonemizer::new();
        let (tokens, prosody) = phonemizer.phonemize_with_prosody("한글").unwrap();

        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must have same length"
        );

        // All tokens should be single-char
        for t in &tokens {
            assert_eq!(
                t.chars().count(),
                1,
                "each Korean token should be a single char, got {:?}",
                t
            );
        }

        // Build id_map for all tokens and encode
        let mut id_map = make_id_map(&[]);
        for (i, t) in tokens.iter().enumerate() {
            id_map
                .entry(t.clone())
                .or_insert_with(|| vec![100 + i as i64]);
        }

        let encoder = PiperEncoder::new(id_map, UnknownTokenMode::Strict).unwrap();
        let ids = encoder.encode(&tokens).unwrap();

        // BOS + (token + PAD) * N + EOS
        assert_eq!(ids[0], 1, "should start with BOS");
        assert_eq!(*ids.last().unwrap(), 2, "should end with EOS");
        assert!(
            ids.len() > tokens.len(),
            "encoded IDs should include padding"
        );
    }
}

// ===========================================================================
// 2. Swedish encoding roundtrip
// ===========================================================================

#[cfg(feature = "swedish")]
mod swedish_encoding {
    use super::*;
    use piper_plus_g2p::swedish::SwedishPhonemizer;

    #[test]
    fn test_swedish_encoding_roundtrip_hej() {
        let phonemizer = SwedishPhonemizer::new();
        let (tokens, prosody) = phonemizer.phonemize_with_prosody("hej").unwrap();

        assert!(
            !tokens.is_empty(),
            "phonemization of 'hej' should produce tokens"
        );
        assert_eq!(tokens.len(), prosody.len());

        // Build an id_map from the actual produced tokens
        let mut id_map = make_id_map(&[]);
        for (i, t) in tokens.iter().enumerate() {
            id_map
                .entry(t.clone())
                .or_insert_with(|| vec![100 + i as i64]);
        }

        let encoder = PiperEncoder::new(id_map, UnknownTokenMode::Strict).unwrap();
        let ids = encoder.encode(&tokens).unwrap();

        assert_eq!(ids[0], 1, "should start with BOS");
        assert_eq!(*ids.last().unwrap(), 2, "should end with EOS");
    }

    #[test]
    fn test_swedish_long_vowel_pua_mapping() {
        // Swedish long vowels should map to PUA codepoints.
        // "mat" (food) should produce a long vowel in stressed position:
        // ɑː (PUA U+E05E) for the stressed 'a'.
        let phonemizer = SwedishPhonemizer::new();

        // Verify PUA mappings exist for Swedish long vowels
        let long_vowels = [
            ("i\u{02D0}", '\u{E059}'),        // iː
            ("y\u{02D0}", '\u{E05A}'),        // yː
            ("e\u{02D0}", '\u{E05B}'),        // eː
            ("\u{025B}\u{02D0}", '\u{E05C}'), // ɛː
            ("\u{00F8}\u{02D0}", '\u{E05D}'), // øː
            ("\u{0251}\u{02D0}", '\u{E05E}'), // ɑː
            ("o\u{02D0}", '\u{E05F}'),        // oː
            ("u\u{02D0}", '\u{E060}'),        // uː
            ("\u{0289}\u{02D0}", '\u{E061}'), // ʉː
        ];

        for (token, expected_pua) in &long_vowels {
            let pua = token_to_pua(token);
            assert_eq!(
                pua,
                Some(*expected_pua),
                "PUA mapping for {:?} should be U+{:04X}",
                token,
                *expected_pua as u32
            );
        }

        // Phonemize a word that should contain a long vowel
        let (tokens, _) = phonemizer.phonemize_with_prosody("mat").unwrap();

        // Check that at least one token is a PUA long vowel char
        let pua_chars: Vec<char> = long_vowels.iter().map(|(_, pua)| *pua).collect();
        let has_long_vowel = tokens
            .iter()
            .any(|t| t.chars().count() == 1 && pua_chars.contains(&t.chars().next().unwrap()));
        assert!(
            has_long_vowel,
            "Swedish 'mat' should produce a long vowel PUA token; got tokens: {:?}",
            tokens
        );
    }

    #[test]
    fn test_swedish_stress_marker_in_output() {
        // Swedish phonemizer should insert stress markers (U+02C8)
        let phonemizer = SwedishPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody("hej").unwrap();

        let stress_marker = '\u{02C8}'; // ˈ
        let has_stress = tokens.iter().any(|t| t.chars().any(|c| c == stress_marker));
        assert!(
            has_stress,
            "Swedish output should contain stress marker; got: {:?}",
            tokens
        );
    }

    #[test]
    fn test_swedish_full_encode_with_pua() {
        // Full pipeline: phonemize -> encode with PUA-aware id_map
        let phonemizer = SwedishPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody("god dag").unwrap();

        // Build id_map dynamically from tokens
        let mut id_map = make_id_map(&[]);
        for (i, t) in tokens.iter().enumerate() {
            id_map
                .entry(t.clone())
                .or_insert_with(|| vec![100 + i as i64]);
        }

        let encoder = PiperEncoder::new(id_map, UnknownTokenMode::Strict).unwrap();
        let ids = encoder.encode(&tokens).unwrap();

        assert_eq!(ids[0], 1, "BOS");
        assert_eq!(*ids.last().unwrap(), 2, "EOS");
        // PAD tokens (0) should be interspersed
        assert!(
            ids.iter().filter(|&&id| id == 0).count() > 0,
            "should contain PAD tokens"
        );
    }
}

// ===========================================================================
// 3. Korean custom dictionary
// ===========================================================================

#[cfg(feature = "korean")]
mod korean_custom_dict {
    use super::*;
    use piper_plus_g2p::custom_dict::CustomDictionary;
    use piper_plus_g2p::korean::KoreanPhonemizer;

    #[test]
    fn test_korean_custom_dict_word_override() {
        // Create a custom dictionary that replaces a Korean word
        let mut dict = CustomDictionary::new();
        dict.add_word("서울", "소울", 5);

        // Verify the replacement works
        let replaced = dict.apply_to_text("서울에서");
        assert_eq!(replaced, "소울에서");

        // Phonemize the replaced text
        let phonemizer = KoreanPhonemizer::new();
        let (tokens_replaced, _) = phonemizer.phonemize_with_prosody(&replaced).unwrap();

        // Phonemize the original text for comparison
        let (tokens_original, _) = phonemizer.phonemize_with_prosody("서울에서").unwrap();

        // The tokens should differ because the dictionary changed the input
        assert_ne!(
            tokens_replaced, tokens_original,
            "custom dict replacement should change phonemization output"
        );
    }

    #[test]
    fn test_korean_custom_dict_technical_term() {
        // Override an English loanword that appears in Korean text
        let mut dict = CustomDictionary::new();
        dict.add_word("API", "에이피아이", 5);

        let result = dict.apply_to_text("API 사용법");
        assert!(
            result.contains("에이피아이"),
            "should replace API with Korean pronunciation"
        );

        // Phonemize should succeed on the replaced text
        let phonemizer = KoreanPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody(&result).unwrap();
        assert!(!tokens.is_empty());
    }

    #[test]
    fn test_korean_custom_dict_json_load() {
        use std::io::Write;

        let json = r#"{"version":"1.0","entries":{"컴퓨터":"콤퓨타"}}"#;
        let path = std::env::temp_dir().join(format!(
            "piper_plus_g2p_ko_dict_{}.json",
            std::process::id()
        ));
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(json.as_bytes()).unwrap();
        f.flush().unwrap();

        let mut dict = CustomDictionary::new();
        dict.load_dictionary(&path).unwrap();

        assert_eq!(
            dict.get_pronunciation("컴퓨터"),
            Some("콤퓨타"),
            "should load Korean custom dictionary entry"
        );

        let replaced = dict.apply_to_text("컴퓨터를 사용합니다");
        assert!(replaced.contains("콤퓨타"));

        let _ = std::fs::remove_file(&path);
    }
}

// ===========================================================================
// 4. Swedish custom dictionary
// ===========================================================================

#[cfg(feature = "swedish")]
mod swedish_custom_dict {
    use super::*;
    use piper_plus_g2p::custom_dict::CustomDictionary;
    use piper_plus_g2p::swedish::SwedishPhonemizer;

    #[test]
    fn test_swedish_custom_dict_word_override() {
        let mut dict = CustomDictionary::new();
        dict.add_word("Stockholm", "Stansen", 5);

        let replaced = dict.apply_to_text("Jag bor i Stockholm");
        assert!(
            replaced.contains("Stansen"),
            "should replace Stockholm: got {:?}",
            replaced
        );

        // Phonemize the replaced text should succeed
        let phonemizer = SwedishPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody(&replaced).unwrap();
        assert!(!tokens.is_empty());
    }

    #[test]
    fn test_swedish_custom_dict_technical_term() {
        let mut dict = CustomDictionary::new();
        dict.add_word("API", "appi", 5);

        let result = dict.apply_to_text("Anropa ett API");
        assert!(result.contains("appi"));

        let phonemizer = SwedishPhonemizer::new();
        let (tokens, _) = phonemizer.phonemize_with_prosody(&result).unwrap();
        assert!(!tokens.is_empty());
    }

    #[test]
    fn test_swedish_custom_dict_json_load() {
        use std::io::Write;

        let json = r#"{"version":"2.0","entries":{"IKEA":{"pronunciation":"ikea","priority":8}}}"#;
        let path = std::env::temp_dir().join(format!(
            "piper_plus_g2p_sv_dict_{}.json",
            std::process::id()
        ));
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(json.as_bytes()).unwrap();
        f.flush().unwrap();

        let mut dict = CustomDictionary::new();
        dict.load_dictionary(&path).unwrap();

        assert_eq!(dict.get_pronunciation("ikea"), Some("ikea"));

        let replaced = dict.apply_to_text("Besok IKEA idag");
        assert!(replaced.contains("ikea"));

        let _ = std::fs::remove_file(&path);
    }
}

// ===========================================================================
// 5. Multilingual phonemizer with ko + sv
// ===========================================================================

#[cfg(all(feature = "korean", feature = "swedish"))]
mod multilingual_ko_sv {
    use super::*;
    use piper_plus_g2p::korean::KoreanPhonemizer;
    use piper_plus_g2p::multilingual::MultilingualPhonemizer;
    use piper_plus_g2p::swedish::SwedishPhonemizer;

    fn make_ko_sv_multilingual() -> MultilingualPhonemizer {
        let languages = vec!["ko".to_string(), "sv".to_string()];
        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        phonemizers.insert("ko".to_string(), Box::new(KoreanPhonemizer::new()));
        phonemizers.insert("sv".to_string(), Box::new(SwedishPhonemizer::new()));
        MultilingualPhonemizer::new(languages, "sv".to_string(), phonemizers)
    }

    #[test]
    fn test_multilingual_korean_text() {
        let mp = make_ko_sv_multilingual();
        let (tokens, prosody) = mp.phonemize_with_prosody("안녕하세요").unwrap();

        assert!(!tokens.is_empty(), "Korean text should produce tokens");
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_multilingual_swedish_text() {
        let mp = make_ko_sv_multilingual();
        let (tokens, prosody) = mp.phonemize_with_prosody("hej").unwrap();

        assert!(!tokens.is_empty(), "Swedish text should produce tokens");
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_multilingual_mixed_ko_sv_text() {
        let mp = make_ko_sv_multilingual();

        // Mixed Korean + Latin(Swedish) text
        let (tokens, prosody) = mp.phonemize_with_prosody("안녕 hej").unwrap();

        assert!(!tokens.is_empty(), "mixed ko+sv text should produce tokens");
        assert_eq!(tokens.len(), prosody.len());
        // Should have more tokens than either language alone since it combines both
        assert!(
            tokens.len() >= 3,
            "mixed text should produce at least 3 tokens; got {}",
            tokens.len()
        );
    }

    #[test]
    fn test_multilingual_detect_primary_language_ko() {
        let mp = make_ko_sv_multilingual();
        let lang = mp.detect_primary_language("한국어 텍스트");
        assert_eq!(lang, "ko", "should detect Korean as primary language");
    }

    #[test]
    fn test_multilingual_detect_primary_language_sv() {
        let mp = make_ko_sv_multilingual();
        // Pure Latin text defaults to the default_latin_language ("sv")
        let lang = mp.detect_primary_language("hej");
        assert_eq!(lang, "sv", "Latin text should default to Swedish");
    }

    #[test]
    fn test_multilingual_empty_input() {
        let mp = make_ko_sv_multilingual();
        let (tokens, prosody) = mp.phonemize_with_prosody("").unwrap();
        assert!(tokens.is_empty());
        assert!(prosody.is_empty());
    }

    #[test]
    fn test_multilingual_encode_mixed_text() {
        let mp = make_ko_sv_multilingual();
        let (tokens, _) = mp.phonemize_with_prosody("가 hej").unwrap();

        // Build id_map dynamically from tokens
        let mut id_map = make_id_map(&[]);
        for (i, t) in tokens.iter().enumerate() {
            id_map
                .entry(t.clone())
                .or_insert_with(|| vec![100 + i as i64]);
        }

        let encoder = PiperEncoder::new(id_map, UnknownTokenMode::Strict).unwrap();
        let ids = encoder.encode(&tokens).unwrap();

        assert_eq!(ids[0], 1, "BOS");
        assert_eq!(*ids.last().unwrap(), 2, "EOS");
        assert!(ids.len() > tokens.len(), "should include PAD insertion");
    }
}

// ===========================================================================
// 6. Multilingual with ko + sv + en (three-language)
// ===========================================================================

#[cfg(all(feature = "korean", feature = "swedish", feature = "english"))]
mod multilingual_ko_sv_en {
    use super::*;
    use piper_plus_g2p::english::EnglishPhonemizer;
    use piper_plus_g2p::korean::KoreanPhonemizer;
    use piper_plus_g2p::multilingual::MultilingualPhonemizer;
    use piper_plus_g2p::swedish::SwedishPhonemizer;

    #[test]
    fn test_three_language_multilingual() {
        // English phonemizer needs a dictionary -- use minimal HashMap
        let en = EnglishPhonemizer::new_with_hashmap(HashMap::new());

        let languages = vec!["ko".to_string(), "sv".to_string(), "en".to_string()];
        let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
        phonemizers.insert("ko".to_string(), Box::new(KoreanPhonemizer::new()));
        phonemizers.insert("sv".to_string(), Box::new(SwedishPhonemizer::new()));
        phonemizers.insert("en".to_string(), Box::new(en));

        let mp = MultilingualPhonemizer::new(languages, "en".to_string(), phonemizers);

        // Korean-only text
        let (ko_tokens, _) = mp.phonemize_with_prosody("가나다").unwrap();
        assert!(!ko_tokens.is_empty(), "Korean text should produce tokens");

        // Verify language detection with Hangul
        let lang = mp.detect_primary_language("가나다");
        assert_eq!(lang, "ko");
    }
}

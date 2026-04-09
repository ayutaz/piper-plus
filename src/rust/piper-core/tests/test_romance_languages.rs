//! Integration tests for Spanish, French, and Portuguese phonemizers.
//!
//! These are all rule-based phonemizers with no external data dependencies.

use piper_plus::phonemize::Phonemizer;

// =========================================================================
// Spanish Tests
// =========================================================================
mod spanish {
    use super::*;
    use piper_plus::phonemize::spanish::SpanishPhonemizer;

    #[test]
    fn test_language_code() {
        let p = SpanishPhonemizer::new();
        assert_eq!(p.language_code(), "es");
    }

    #[test]
    fn test_basic_phonemize() {
        let p = SpanishPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("hola").unwrap();
        assert!(!tokens.is_empty(), "phonemize should produce tokens");
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must have same length"
        );
    }

    #[test]
    fn test_seseo_c_before_e() {
        // Latin American seseo: c before e/i -> /s/
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("cero").unwrap();
        assert!(
            tokens.iter().any(|t| t == "s"),
            "c before e should produce 's' (seseo) in {:?}",
            tokens
        );
    }

    #[test]
    fn test_seseo_z() {
        // z -> /s/ (seseo)
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("zapato").unwrap();
        assert!(
            tokens.iter().any(|t| t == "s"),
            "z should produce 's' (seseo) in {:?}",
            tokens
        );
    }

    #[test]
    fn test_silent_h() {
        // h is silent in Spanish
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("hola").unwrap();
        assert!(
            !tokens.iter().any(|t| t == "h"),
            "h should be silent (not in output) in {:?}",
            tokens
        );
    }

    #[test]
    fn test_ch_affricate() {
        // "ch" -> tʃ (PUA E054)
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("chico").unwrap();
        // The affricate tʃ should be PUA-mapped to U+E054
        assert!(
            tokens.iter().any(|t| t == "\u{E054}" || t == "t\u{0283}"),
            "ch should produce tʃ affricate in {:?}",
            tokens
        );
    }

    #[test]
    fn test_ll_yeismo() {
        // "ll" -> ʝ
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("calle").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{029D}"),
            "ll should produce ʝ (yeismo) in {:?}",
            tokens
        );
    }

    #[test]
    fn test_rr_trill() {
        // "rr" -> trill (PUA E01D)
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("perro").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{E01D}" || t == "rr"),
            "rr should produce trill in {:?}",
            tokens
        );
    }

    #[test]
    fn test_word_initial_r_is_trill() {
        // Word-initial r -> trill (same as rr)
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("rio").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{E01D}" || t == "rr"),
            "word-initial r should produce trill in {:?}",
            tokens
        );
    }

    #[test]
    fn test_n_tilde() {
        // ñ -> ɲ
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("ni\u{00F1}o").unwrap(); // niño
        assert!(
            tokens.iter().any(|t| t == "\u{0272}"),
            "\u{00F1} should produce \u{0272} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_stress_marker_present() {
        // Content words should have a stress marker
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("casa").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{02C8}"),
            "content word 'casa' should have stress marker \u{02C8} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_function_word_no_stress() {
        // Function words should not have stress marker
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("de").unwrap();
        assert!(
            !tokens.iter().any(|t| t == "\u{02C8}"),
            "function word 'de' should not have stress marker in {:?}",
            tokens
        );
    }

    #[test]
    fn test_multi_word_sentence() {
        let p = SpanishPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("hola mundo").unwrap();
        assert!(
            tokens.iter().any(|t| t == " "),
            "multi-word should contain space separator in {:?}",
            tokens
        );
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_punctuation_passthrough() {
        let p = SpanishPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("hola!").unwrap();
        assert!(
            tokens.iter().any(|t| t == "!"),
            "punctuation should pass through in {:?}",
            tokens
        );
    }

    #[test]
    fn test_get_phoneme_id_map_returns_none() {
        let p = SpanishPhonemizer::new();
        assert!(
            p.get_phoneme_id_map().is_none(),
            "Spanish phonemizer should return None for phoneme_id_map"
        );
    }

    #[test]
    fn test_post_process_ids_inserts_bos_eos() {
        // Spanish post_process_ids does BOS + intersperse padding + EOS
        let p = SpanishPhonemizer::new();
        let mut id_map = std::collections::HashMap::new();
        id_map.insert("^".to_string(), vec![1i64]);
        id_map.insert("$".to_string(), vec![2i64]);
        id_map.insert("_".to_string(), vec![0i64]);

        let ids = vec![10i64, 20];
        let prosody = vec![Some([0i32, 2, 2]), Some([0, 0, 2])];

        let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);
        // Expected: BOS(1) + 10 + pad(0) + 20 + EOS(2)
        assert_eq!(result_ids, vec![1, 10, 0, 20, 2]);
        assert_eq!(result_ids.len(), result_prosody.len());
    }

    #[test]
    fn test_b_v_allophony() {
        // Word-initial b/v -> [b], intervocalic -> [β]
        let p = SpanishPhonemizer::new();
        // "vaca" -> word-initial v -> [b]
        let (tokens, _) = p.phonemize_with_prosody("vaca").unwrap();
        assert!(
            tokens.iter().any(|t| t == "b"),
            "word-initial v should produce [b] in {:?}",
            tokens
        );
    }
}

// =========================================================================
// French Tests
// =========================================================================
mod french {
    use super::*;
    use piper_plus::phonemize::french::FrenchPhonemizer;

    #[test]
    fn test_language_code() {
        let p = FrenchPhonemizer::new();
        assert_eq!(p.language_code(), "fr");
    }

    #[test]
    fn test_basic_phonemize() {
        let p = FrenchPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("bonjour").unwrap();
        assert!(!tokens.is_empty(), "phonemize should produce tokens");
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must have same length"
        );
    }

    #[test]
    fn test_nasal_vowel_bon() {
        // "bon" should contain nasal vowel ɔ̃ (PUA E058)
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("bon").unwrap();
        assert!(
            tokens
                .iter()
                .any(|t| t == "\u{E058}" || t == "\u{0254}\u{0303}"),
            "bon should contain nasal \u{0254}\u{0303} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_nasal_vowel_an() {
        // "an" / "en" -> ɑ̃ (PUA E057)
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("enfant").unwrap();
        assert!(
            tokens
                .iter()
                .any(|t| t == "\u{E057}" || t == "\u{0251}\u{0303}"),
            "enfant should contain nasal \u{0251}\u{0303} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_nasal_vowel_in() {
        // "in" -> ɛ̃ (PUA E056)
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("fin").unwrap();
        assert!(
            tokens
                .iter()
                .any(|t| t == "\u{E056}" || t == "\u{025B}\u{0303}"),
            "fin should contain nasal \u{025B}\u{0303} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_silent_h() {
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("homme").unwrap();
        assert!(
            !tokens.iter().any(|t| t == "h"),
            "h should be silent in {:?}",
            tokens
        );
    }

    #[test]
    fn test_ch_produces_sh() {
        // "ch" -> ʃ
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("chat").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0283}"),
            "ch should produce \u{0283} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_gn_palatal_nasal() {
        // "gn" -> ɲ
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("montagne").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0272}"),
            "gn should produce \u{0272} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_ou_produces_u() {
        // "ou" -> u
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("jour").unwrap();
        // "jour" = j + ou(->u) + r
        assert!(
            tokens.iter().any(|t| t == "u"),
            "ou should produce u in {:?}",
            tokens
        );
    }

    #[test]
    fn test_oi_produces_wa() {
        // "oi" -> wa
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("moi").unwrap();
        assert!(
            tokens.iter().any(|t| t == "w") && tokens.iter().any(|t| t == "a"),
            "oi should produce w+a in {:?}",
            tokens
        );
    }

    #[test]
    fn test_silent_final_consonants() {
        // Word-final 't', 's', etc. are typically silent
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("chat").unwrap();
        // "chat" -> ʃ + a (final t is silent)
        let last_non_space: Option<&String> = tokens.iter().rev().find(|t| t.as_str() != " ");
        assert_ne!(
            last_non_space.map(|s| s.as_str()),
            Some("t"),
            "final t should be silent in 'chat': {:?}",
            tokens
        );
    }

    #[test]
    fn test_intervocalic_s_voicing() {
        // Single s between vowels -> z
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("maison").unwrap();
        assert!(
            tokens.iter().any(|t| t == "z"),
            "intervocalic s should become z in {:?}",
            tokens
        );
    }

    #[test]
    fn test_multi_word_sentence() {
        let p = FrenchPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("bonjour le monde").unwrap();
        assert!(
            tokens.iter().any(|t| t == " "),
            "multi-word should have space separator in {:?}",
            tokens
        );
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_get_phoneme_id_map_returns_none() {
        let p = FrenchPhonemizer::new();
        assert!(
            p.get_phoneme_id_map().is_none(),
            "French phonemizer should return None for phoneme_id_map"
        );
    }

    #[test]
    fn test_post_process_ids_inserts_bos_eos() {
        // French post_process_ids does BOS + pad-interspersed IDs + EOS
        let p = FrenchPhonemizer::new();
        let mut id_map = std::collections::HashMap::new();
        id_map.insert("^".to_string(), vec![1i64]);
        id_map.insert("$".to_string(), vec![2i64]);
        id_map.insert("_".to_string(), vec![0i64]);

        let ids = vec![10i64, 20];
        let prosody = vec![Some([0i32, 2, 2]), Some([0, 0, 2])];

        let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);
        // Verify BOS and EOS are present
        assert_eq!(*result_ids.first().unwrap(), 1, "should start with BOS");
        assert_eq!(*result_ids.last().unwrap(), 2, "should end with EOS");
        // Verify original phoneme IDs are included
        assert!(result_ids.contains(&10), "should contain phoneme ID 10");
        assert!(result_ids.contains(&20), "should contain phoneme ID 20");
        assert_eq!(
            result_ids.len(),
            result_prosody.len(),
            "IDs and prosody must have same length"
        );
    }

    #[test]
    fn test_er_verb_ending() {
        // Polysyllabic -er -> /e/ (verb infinitive)
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("parler").unwrap();
        // Should end with /e/ not /ɛʁ/
        // Find last vowel-like token
        let last_vowel = tokens
            .iter()
            .rev()
            .find(|t| matches!(t.as_str(), "e" | "\u{025B}" | "a" | "i" | "o" | "u"));
        assert_eq!(
            last_vowel.map(|s| s.as_str()),
            Some("e"),
            "polysyllabic -er should end with /e/ in {:?}",
            tokens
        );
    }

    #[test]
    fn test_r_is_uvular() {
        // French r -> ʁ
        let p = FrenchPhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("rue").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0281}"),
            "r should produce uvular \u{0281} in {:?}",
            tokens
        );
    }
}

// =========================================================================
// Portuguese Tests
// =========================================================================
mod portuguese {
    use super::*;
    use piper_plus::phonemize::portuguese::PortuguesePhonemizer;

    #[test]
    fn test_language_code() {
        let p = PortuguesePhonemizer::new();
        assert_eq!(p.language_code(), "pt");
    }

    #[test]
    fn test_basic_phonemize() {
        let p = PortuguesePhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("ol\u{00E1}").unwrap(); // olá
        assert!(!tokens.is_empty(), "phonemize should produce tokens");
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must have same length"
        );
    }

    #[test]
    fn test_r_polymorphism_initial() {
        // Word-initial r -> ʁ (uvular)
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("rio").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0281}"),
            "word-initial r should be uvular \u{0281} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_r_polymorphism_intervocalic() {
        // Intervocalic r -> ɾ (tap)
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("caro").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{027E}"),
            "intervocalic r should be tap \u{027E} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_rr_uvular() {
        // "rr" -> ʁ
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("carro").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0281}"),
            "rr should produce uvular \u{0281} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_nasal_vowel() {
        // "bom" -> nasal o (õ)
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("bom").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{00F5}"),
            "bom should contain nasal \u{00F5} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_coda_l_vocalization() {
        // Final l -> w (BR Portuguese)
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("Brasil").unwrap();
        assert!(
            tokens.iter().any(|t| t == "w"),
            "coda l should become w in {:?}",
            tokens
        );
        assert!(
            !tokens.iter().any(|t| t == "l"),
            "should not contain l in coda position: {:?}",
            tokens
        );
    }

    #[test]
    fn test_t_palatalization_before_i() {
        // BR Portuguese: t before i -> tʃ (PUA E054)
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("tia").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{E054}"),
            "t before i should produce affricate PUA E054 in {:?}",
            tokens
        );
    }

    #[test]
    fn test_d_palatalization_before_i() {
        // BR Portuguese: d before i -> dʒ (PUA E055)
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("dia").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{E055}"),
            "d before i should produce affricate PUA E055 in {:?}",
            tokens
        );
    }

    #[test]
    fn test_lh_palatal_lateral() {
        // "lh" -> ʎ
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("filho").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{028E}"),
            "lh should produce palatal lateral \u{028E} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_nh_palatal_nasal() {
        // "nh" -> ɲ
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("junho").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0272}"),
            "nh should produce palatal nasal \u{0272} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_ch_produces_sh() {
        // "ch" -> ʃ
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("chave").unwrap();
        assert!(
            tokens.iter().any(|t| t == "\u{0283}"),
            "ch should produce \u{0283} in {:?}",
            tokens
        );
    }

    #[test]
    fn test_unstressed_final_o_reduction() {
        // Unstressed final o -> u
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("gato").unwrap();
        let last = tokens.last().unwrap();
        assert_eq!(
            last.as_str(),
            "u",
            "unstressed final o should reduce to u in {:?}",
            tokens
        );
    }

    #[test]
    fn test_intervocalic_s_voicing() {
        // s between vowels -> z
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("casa").unwrap();
        assert!(
            tokens.iter().any(|t| t == "z"),
            "intervocalic s should become z in {:?}",
            tokens
        );
    }

    #[test]
    fn test_multi_word_sentence() {
        let p = PortuguesePhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("bom dia").unwrap();
        assert!(
            tokens.iter().any(|t| t == " "),
            "multi-word should have space separator in {:?}",
            tokens
        );
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_get_phoneme_id_map_returns_none() {
        let p = PortuguesePhonemizer::new();
        assert!(
            p.get_phoneme_id_map().is_none(),
            "Portuguese phonemizer should return None for phoneme_id_map"
        );
    }

    #[test]
    fn test_post_process_ids_inserts_bos_eos() {
        // Portuguese post_process_ids does BOS/EOS/padding insertion
        let p = PortuguesePhonemizer::new();
        let mut id_map = std::collections::HashMap::new();
        id_map.insert("^".to_string(), vec![1i64]);
        id_map.insert("$".to_string(), vec![2i64]);
        id_map.insert("_".to_string(), vec![0i64]);

        let ids = vec![10i64, 20];
        let prosody = vec![Some([0i32, 2, 2]), Some([0, 0, 2])];

        let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);
        // Expected: BOS(1) + pad(0) + 10 + pad(0) + 20 + pad(0) + EOS(2)
        assert_eq!(result_ids, vec![1, 0, 10, 0, 20, 0, 2]);
        assert_eq!(result_ids.len(), result_prosody.len());
    }

    #[test]
    fn test_cedilla_produces_s() {
        // ç -> s
        let p = PortuguesePhonemizer::new();
        let (tokens, _) = p.phonemize_with_prosody("cora\u{00E7}\u{00E3}o").unwrap(); // coração
        assert!(
            tokens.iter().any(|t| t == "s"),
            "cedilla should produce s in {:?}",
            tokens
        );
    }

    #[test]
    fn test_prosody_has_stress() {
        // At least one phoneme should be marked as stressed (a2=2)
        let p = PortuguesePhonemizer::new();
        let (_, prosody) = p.phonemize_with_prosody("casa").unwrap();
        let has_stress = prosody.iter().any(|p| p.is_some_and(|info| info.a2 == 2));
        assert!(has_stress, "should have at least one stressed phoneme");
    }
}

// =========================================================================
// detect_primary_language tests (all romance languages)
// =========================================================================

mod detect_primary_language {
    use super::*;
    use piper_plus::phonemize::french::FrenchPhonemizer;
    use piper_plus::phonemize::portuguese::PortuguesePhonemizer;
    use piper_plus::phonemize::spanish::SpanishPhonemizer;

    // --- Spanish ---

    #[test]
    fn test_detect_primary_language_returns_es() {
        let p = SpanishPhonemizer::new();
        assert_eq!(
            p.detect_primary_language("hola mundo"),
            "es",
            "detect_primary_language should return 'es' for Spanish phonemizer"
        );
    }

    #[test]
    fn test_detect_primary_language_es_empty_string() {
        let p = SpanishPhonemizer::new();
        assert_eq!(
            p.detect_primary_language(""),
            "es",
            "detect_primary_language should return 'es' even for empty input"
        );
    }

    // --- French ---

    #[test]
    fn test_detect_primary_language_returns_fr() {
        let p = FrenchPhonemizer::new();
        assert_eq!(
            p.detect_primary_language("bonjour le monde"),
            "fr",
            "detect_primary_language should return 'fr' for French phonemizer"
        );
    }

    #[test]
    fn test_detect_primary_language_fr_empty_string() {
        let p = FrenchPhonemizer::new();
        assert_eq!(
            p.detect_primary_language(""),
            "fr",
            "detect_primary_language should return 'fr' even for empty input"
        );
    }

    // --- Portuguese ---

    #[test]
    fn test_detect_primary_language_returns_pt() {
        let p = PortuguesePhonemizer::new();
        assert_eq!(
            p.detect_primary_language("bom dia"),
            "pt",
            "detect_primary_language should return 'pt' for Portuguese phonemizer"
        );
    }

    #[test]
    fn test_detect_primary_language_pt_empty_string() {
        let p = PortuguesePhonemizer::new();
        assert_eq!(
            p.detect_primary_language(""),
            "pt",
            "detect_primary_language should return 'pt' even for empty input"
        );
    }
}

//! Integration tests verifying Rust token_map.rs PUA mappings
//! EXACTLY match the Python token_mapper.py canonical definitions.
//!
//! If any of these tests fail, the Rust and Python token maps are out of sync,
//! which will cause model inference to produce wrong phoneme IDs.

use piper_plus::phonemize::token_map::{FIXED_PUA_MAP, token_to_pua};

// =========================================================================
// Japanese (JA) — U+E000..U+E01C
// =========================================================================

#[test]
fn test_ja_long_vowels_match_python() {
    assert_eq!(token_to_pua("a:"), Some('\u{E000}'));
    assert_eq!(token_to_pua("i:"), Some('\u{E001}'));
    assert_eq!(token_to_pua("u:"), Some('\u{E002}'));
    assert_eq!(token_to_pua("e:"), Some('\u{E003}'));
    assert_eq!(token_to_pua("o:"), Some('\u{E004}'));
}

#[test]
fn test_ja_special_match_python() {
    assert_eq!(token_to_pua("cl"), Some('\u{E005}'));
}

#[test]
fn test_ja_palatalized_match_python() {
    // These MUST match Python exactly (was previously wrong)
    assert_eq!(token_to_pua("ky"), Some('\u{E006}'));
    assert_eq!(token_to_pua("kw"), Some('\u{E007}'));
    assert_eq!(token_to_pua("gy"), Some('\u{E008}'));
    assert_eq!(token_to_pua("gw"), Some('\u{E009}'));
    assert_eq!(token_to_pua("ty"), Some('\u{E00A}')); // Was ny (FIXED)
    assert_eq!(token_to_pua("dy"), Some('\u{E00B}')); // Was by (FIXED)
    assert_eq!(token_to_pua("py"), Some('\u{E00C}'));
    assert_eq!(token_to_pua("by"), Some('\u{E00D}')); // Was my (FIXED)
}

#[test]
fn test_ja_affricates_match_python() {
    assert_eq!(token_to_pua("ch"), Some('\u{E00E}'));
    assert_eq!(token_to_pua("ts"), Some('\u{E00F}'));
    assert_eq!(token_to_pua("sh"), Some('\u{E010}'));
    assert_eq!(token_to_pua("zy"), Some('\u{E011}')); // Was dy (FIXED)
    assert_eq!(token_to_pua("hy"), Some('\u{E012}')); // Was ty (FIXED)
}

#[test]
fn test_ja_nasals_liquids_match_python() {
    assert_eq!(token_to_pua("ny"), Some('\u{E013}')); // Was hy (FIXED)
    assert_eq!(token_to_pua("my"), Some('\u{E014}')); // Was ry (FIXED)
    assert_eq!(token_to_pua("ry"), Some('\u{E015}')); // Was fw (FIXED)
}

#[test]
fn test_ja_question_markers_match_python() {
    assert_eq!(token_to_pua("?!"), Some('\u{E016}'));
    assert_eq!(token_to_pua("?."), Some('\u{E017}'));
    assert_eq!(token_to_pua("?~"), Some('\u{E018}'));
}

#[test]
fn test_ja_n_variants_match_python() {
    assert_eq!(token_to_pua("N_m"), Some('\u{E019}'));
    assert_eq!(token_to_pua("N_n"), Some('\u{E01A}'));
    assert_eq!(token_to_pua("N_ng"), Some('\u{E01B}'));
    assert_eq!(token_to_pua("N_uvular"), Some('\u{E01C}'));
}

// =========================================================================
// Multilingual shared — U+E01D..U+E01E
// =========================================================================

#[test]
fn test_multilingual_shared_match_python() {
    assert_eq!(token_to_pua("rr"), Some('\u{E01D}'));
    assert_eq!(token_to_pua("y_vowel"), Some('\u{E01E}'));
}

// =========================================================================
// Chinese (ZH) — U+E020..U+E04A
// =========================================================================

#[test]
fn test_zh_initials_match_python() {
    assert_eq!(token_to_pua("p\u{02b0}"), Some('\u{E020}')); // ph  aspirated bilabial
    assert_eq!(token_to_pua("t\u{02b0}"), Some('\u{E021}')); // th  aspirated alveolar
    assert_eq!(token_to_pua("k\u{02b0}"), Some('\u{E022}')); // kh  aspirated velar
    assert_eq!(token_to_pua("t\u{0255}"), Some('\u{E023}')); // tc  alveolo-palatal affricate
    assert_eq!(token_to_pua("t\u{0255}\u{02b0}"), Some('\u{E024}')); // tch aspirated alveolo-palatal
    assert_eq!(token_to_pua("t\u{0282}"), Some('\u{E025}')); // ts  retroflex affricate
    assert_eq!(token_to_pua("t\u{0282}\u{02b0}"), Some('\u{E026}')); // tsh aspirated retroflex
    assert_eq!(token_to_pua("ts\u{02b0}"), Some('\u{E027}')); // tsh aspirated alveolar affricate
}

#[test]
fn test_zh_diphthongs_match_python() {
    assert_eq!(token_to_pua("a\u{026a}"), Some('\u{E028}')); // ai
    assert_eq!(token_to_pua("e\u{026a}"), Some('\u{E029}')); // ei
    assert_eq!(token_to_pua("a\u{028a}"), Some('\u{E02A}')); // ao
    assert_eq!(token_to_pua("o\u{028a}"), Some('\u{E02B}')); // ou
}

#[test]
fn test_zh_nasal_finals_match_python() {
    assert_eq!(token_to_pua("an"), Some('\u{E02C}'));
    assert_eq!(token_to_pua("\u{0259}n"), Some('\u{E02D}')); // en
    assert_eq!(token_to_pua("a\u{014b}"), Some('\u{E02E}')); // ang
    assert_eq!(token_to_pua("\u{0259}\u{014b}"), Some('\u{E02F}')); // eng
    assert_eq!(token_to_pua("u\u{014b}"), Some('\u{E030}')); // ong
}

#[test]
fn test_zh_i_compound_finals_match_python() {
    assert_eq!(token_to_pua("ia"), Some('\u{E031}'));
    assert_eq!(token_to_pua("i\u{025b}"), Some('\u{E032}')); // ie
    assert_eq!(token_to_pua("iou"), Some('\u{E033}'));
    assert_eq!(token_to_pua("ia\u{028a}"), Some('\u{E034}')); // iao
    assert_eq!(token_to_pua("i\u{025b}n"), Some('\u{E035}')); // ian
    assert_eq!(token_to_pua("in"), Some('\u{E036}'));
    assert_eq!(token_to_pua("ia\u{014b}"), Some('\u{E037}')); // iang
    assert_eq!(token_to_pua("i\u{014b}"), Some('\u{E038}')); // ing
    assert_eq!(token_to_pua("iu\u{014b}"), Some('\u{E039}')); // iong
}

#[test]
fn test_zh_u_compound_finals_match_python() {
    assert_eq!(token_to_pua("ua"), Some('\u{E03A}'));
    assert_eq!(token_to_pua("uo"), Some('\u{E03B}'));
    assert_eq!(token_to_pua("ua\u{026a}"), Some('\u{E03C}')); // uai
    assert_eq!(token_to_pua("ue\u{026a}"), Some('\u{E03D}')); // uei
    assert_eq!(token_to_pua("uan"), Some('\u{E03E}'));
    assert_eq!(token_to_pua("u\u{0259}n"), Some('\u{E03F}')); // uen
    assert_eq!(token_to_pua("ua\u{014b}"), Some('\u{E040}')); // uang
    assert_eq!(token_to_pua("u\u{0259}\u{014b}"), Some('\u{E041}')); // ueng
}

#[test]
fn test_zh_u_umlaut_compound_finals_match_python() {
    assert_eq!(token_to_pua("y\u{025b}"), Some('\u{E042}')); // yue
    assert_eq!(token_to_pua("y\u{025b}n"), Some('\u{E043}')); // yuan
    assert_eq!(token_to_pua("yn"), Some('\u{E044}'));
}

#[test]
fn test_zh_syllabic_consonant_match_python() {
    // Syllabic retroflex: U+027B (ɻ) + U+0329 (combining vertical line below)
    assert_eq!(token_to_pua("\u{027b}\u{0329}"), Some('\u{E045}'));
}

#[test]
fn test_zh_tone_markers_match_python() {
    assert_eq!(token_to_pua("tone1"), Some('\u{E046}'));
    assert_eq!(token_to_pua("tone2"), Some('\u{E047}'));
    assert_eq!(token_to_pua("tone3"), Some('\u{E048}'));
    assert_eq!(token_to_pua("tone4"), Some('\u{E049}'));
    assert_eq!(token_to_pua("tone5"), Some('\u{E04A}'));
}

// =========================================================================
// Korean (KO) — U+E04B..U+E052
// =========================================================================

#[test]
fn test_ko_tense_consonants_match_python() {
    assert_eq!(token_to_pua("p\u{0348}"), Some('\u{E04B}')); // tense bilabial
    assert_eq!(token_to_pua("t\u{0348}"), Some('\u{E04C}')); // tense alveolar
    assert_eq!(token_to_pua("k\u{0348}"), Some('\u{E04D}')); // tense velar
    assert_eq!(token_to_pua("s\u{0348}"), Some('\u{E04E}')); // tense sibilant
    assert_eq!(token_to_pua("t\u{0348}\u{0255}"), Some('\u{E04F}')); // tense alveolo-palatal
}

#[test]
fn test_ko_unreleased_finals_match_python() {
    assert_eq!(token_to_pua("k\u{031a}"), Some('\u{E050}')); // unreleased velar
    assert_eq!(token_to_pua("t\u{031a}"), Some('\u{E051}')); // unreleased alveolar
    assert_eq!(token_to_pua("p\u{031a}"), Some('\u{E052}')); // unreleased bilabial
}

// =========================================================================
// Spanish/Portuguese (ES/PT) — U+E054..U+E055
// =========================================================================

#[test]
fn test_es_pt_affricates_match_python() {
    assert_eq!(token_to_pua("t\u{0283}"), Some('\u{E054}')); // voiceless postalveolar
    assert_eq!(token_to_pua("d\u{0292}"), Some('\u{E055}')); // voiced postalveolar
}

// =========================================================================
// French (FR) — U+E056..U+E058
// =========================================================================

#[test]
fn test_fr_nasal_vowels_match_python() {
    assert_eq!(token_to_pua("\u{025b}\u{0303}"), Some('\u{E056}')); // nasal open-mid front
    assert_eq!(token_to_pua("\u{0251}\u{0303}"), Some('\u{E057}')); // nasal open back
    assert_eq!(token_to_pua("\u{0254}\u{0303}"), Some('\u{E058}')); // nasal open-mid back
}

// =========================================================================
// Negative tests — tokens that must NOT be in the fixed map
// =========================================================================

#[test]
fn test_no_fw_in_fixed_pua() {
    // "fw" was incorrectly in the Rust token_map but is NOT in Python
    assert_eq!(token_to_pua("fw"), None);
}

#[test]
fn test_nonexistent_tokens_return_none() {
    assert_eq!(token_to_pua("syl"), None);
    assert_eq!(token_to_pua("\u{0265}"), None); // ɥ not a PUA token
    assert_eq!(token_to_pua("xx"), None);
    assert_eq!(token_to_pua(""), None);
    assert_eq!(token_to_pua("tone0"), None);
    assert_eq!(token_to_pua("tone6"), None);
}

// =========================================================================
// Structural invariants
// =========================================================================

#[test]
fn test_total_entry_count_matches_python() {
    // Python FIXED_PUA_MAPPING has exactly 99 entries (PUA v2)
    assert_eq!(FIXED_PUA_MAP.len(), 99);
}

#[test]
fn test_no_collisions() {
    let mut seen: std::collections::HashSet<u32> = std::collections::HashSet::new();
    for (token, code) in FIXED_PUA_MAP.iter() {
        assert!(
            seen.insert(*code),
            "duplicate PUA code: 0x{:04X} for token {:?}",
            code,
            token
        );
    }
}

#[test]
fn test_all_codes_in_pua_range() {
    // Unicode Private Use Area: U+E000..U+F8FF
    for (token, code) in FIXED_PUA_MAP.iter() {
        assert!(
            *code >= 0xE000 && *code <= 0xF8FF,
            "code 0x{:04X} for token {:?} is outside PUA range",
            code,
            token
        );
    }
}

#[test]
fn test_no_duplicate_tokens() {
    let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
    for (token, code) in FIXED_PUA_MAP.iter() {
        assert!(
            seen.insert(token),
            "duplicate token {:?} at code 0x{:04X}",
            token,
            code
        );
    }
}

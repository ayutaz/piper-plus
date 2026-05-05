//! M4-1: クロスプラットフォーム G2P ゴールデンテスト (Rust)
//!
//! `tests/fixtures/g2p/phoneme_test_cases.json` を読み込み、
//! piper_plus_g2p の各言語 Phonemizer に対してアサーションを実行する。
//! Python/JS と同じフィクスチャを共有することで 3 プラットフォームの
//! 出力一致を保証する。
//!
//! Run: cargo test --test test_g2p_golden

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use piper_plus_g2p::Phonemizer;
use serde::Deserialize;

// ---------------------------------------------------------------------------
// Fixture deserialization
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct Fixture {
    test_cases: Vec<TestCase>,
    pua_map_count: usize,
    #[serde(default)]
    pua_map: HashMap<String, String>,
    #[serde(default)]
    encode_test_cases: Vec<EncodeTestCase>,
}

#[derive(Debug, Deserialize)]
struct TestCase {
    language: String,
    input: String,
    description: Option<String>,
    expected_tokens: Option<Vec<String>>,
    expected_token_count_min: Option<usize>,
    expected_contains: Option<Vec<String>>,
    expected_has_question_marker: Option<bool>,
    expected_contains_any_tone: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct EncodeTestCase {
    tokens: Vec<String>,
    description: String,
    expected_has_bos: bool,
    expected_has_eos: bool,
    expected_min_length: usize,
    #[serde(default)]
    expected_first_token: Option<String>,
}

fn load_fixture() -> Fixture {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    let fixture_path = repo_root
        .join("tests")
        .join("fixtures")
        .join("g2p")
        .join("phoneme_test_cases.json");
    let content = std::fs::read_to_string(&fixture_path)
        .unwrap_or_else(|e| panic!("Failed to read fixture {fixture_path:?}: {e}"));
    serde_json::from_str(&content).expect("Failed to parse fixture JSON")
}

fn cases_for<'a>(fixture: &'a Fixture, lang: &str) -> Vec<&'a TestCase> {
    fixture
        .test_cases
        .iter()
        .filter(|c| c.language == lang)
        .collect()
}

// ---------------------------------------------------------------------------
// Helper: run assertions for one case
// ---------------------------------------------------------------------------

fn assert_case(tokens: &[String], case: &TestCase) {
    let desc = case.description.as_deref().unwrap_or(case.input.as_str());

    if let Some(min) = case.expected_token_count_min {
        assert!(
            tokens.len() >= min,
            "{lang} token count {got} < {min} for {desc:?}: {tokens:?}",
            lang = case.language,
            got = tokens.len(),
        );
    }

    if let Some(expected) = &case.expected_tokens {
        assert_eq!(
            tokens,
            expected,
            "{lang} exact token mismatch for {desc:?}",
            lang = case.language,
        );
    }

    if let Some(expected_contains) = &case.expected_contains {
        let token_set: HashSet<&str> = tokens.iter().map(|s| s.as_str()).collect();
        for expected in expected_contains {
            // Rust phonemizer returns PUA-encoded single chars for multi-char tokens.
            // Convert expected token names to their PUA form if a mapping exists.
            let pua_str: Option<String> =
                piper_plus_g2p::token_map::token_to_pua(expected).map(|c| c.to_string());
            let lookup = pua_str.as_deref().unwrap_or(expected.as_str());
            assert!(
                token_set.contains(lookup),
                "{lang} output missing {expected:?} for {desc:?}: {tokens:?}",
                lang = case.language,
            );
        }
    }
}

// ---------------------------------------------------------------------------
// Spanish (rule-based, deterministic)
// ---------------------------------------------------------------------------

#[test]
fn test_es_golden() {
    let fixture = load_fixture();
    let p = piper_plus_g2p::spanish::SpanishPhonemizer::new();
    for case in cases_for(&fixture, "es") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// French (rule-based)
// ---------------------------------------------------------------------------

#[test]
fn test_fr_golden() {
    let fixture = load_fixture();
    let p = piper_plus_g2p::french::FrenchPhonemizer::new();
    for case in cases_for(&fixture, "fr") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// Portuguese (rule-based)
// ---------------------------------------------------------------------------

#[test]
fn test_pt_golden() {
    let fixture = load_fixture();
    let p = piper_plus_g2p::portuguese::PortuguesePhonemizer::new();
    for case in cases_for(&fixture, "pt") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// Swedish (rule-based)
// ---------------------------------------------------------------------------

#[test]
fn test_sv_golden() {
    let fixture = load_fixture();
    let p = piper_plus_g2p::swedish::SwedishPhonemizer::new();
    for case in cases_for(&fixture, "sv") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// Korean (rule-based)
// ---------------------------------------------------------------------------

#[test]
fn test_ko_golden() {
    let fixture = load_fixture();
    let p = piper_plus_g2p::korean::KoreanPhonemizer::new();
    for case in cases_for(&fixture, "ko") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// Chinese (rule-based pinyin)
// ---------------------------------------------------------------------------

#[test]
fn test_zh_golden() {
    let fixture = load_fixture();
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    let single_path = repo_root
        .join("test")
        .join("models")
        .join("pinyin_single.json");
    let phrase_path = repo_root
        .join("test")
        .join("models")
        .join("pinyin_phrases.json");
    let p = match piper_plus_g2p::chinese::ChinesePhonemizer::new(&single_path, &phrase_path) {
        Ok(p) => p,
        Err(_) => {
            eprintln!("SKIP: pinyin dictionary not found — skipping ZH golden test");
            return;
        }
    };
    for case in cases_for(&fixture, "zh") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        // ZH: structural checks (tone markers)
        // Rust phonemizer returns PUA-encoded chars; convert tone names to PUA form.
        if case.expected_contains_any_tone == Some(true) {
            let tone_pua: Vec<String> = ["tone1", "tone2", "tone3", "tone4", "tone5"]
                .iter()
                .filter_map(|t| piper_plus_g2p::token_map::token_to_pua(t))
                .map(|c| c.to_string())
                .collect();
            let has_tone = tokens.iter().any(|t| tone_pua.contains(t));
            assert!(
                has_tone,
                "ZH output missing tone marker for {:?}: {:?}",
                case.input, tokens
            );
        }
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// English (requires CMU dictionary — skipped when not available)
// ---------------------------------------------------------------------------

#[test]
fn test_en_golden() {
    let fixture = load_fixture();
    let p = match piper_plus_g2p::english::EnglishPhonemizer::new() {
        Ok(p) => p,
        Err(_) => {
            eprintln!("SKIP: CMU dictionary not found — skipping EN golden test");
            return;
        }
    };
    for case in cases_for(&fixture, "en") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();
        assert_case(&tokens, case);
    }
}

// ---------------------------------------------------------------------------
// Japanese (requires OpenJTalk — structural checks only)
// ---------------------------------------------------------------------------

#[cfg(feature = "japanese")]
#[test]
fn test_ja_golden() {
    let fixture = load_fixture();
    use piper_plus_g2p::japanese::JapanesePhonemizer;

    let p = match JapanesePhonemizer::new() {
        Ok(p) => p,
        Err(_) => {
            eprintln!("SKIP: OpenJTalk dictionary not found — skipping JA golden test");
            return;
        }
    };

    let question_markers: HashSet<&str> = ["?", "?!", "?.", "?~"].iter().copied().collect();

    for case in cases_for(&fixture, "ja") {
        let (tokens, _) = p.phonemize_with_prosody(&case.input).unwrap();

        if let Some(min) = case.expected_token_count_min {
            assert!(
                tokens.len() >= min,
                "JA token count {} < {} for {:?}: {:?}",
                tokens.len(),
                min,
                case.input,
                tokens
            );
        }
        if let Some(expected_contains) = &case.expected_contains {
            let token_set: HashSet<&str> = tokens.iter().map(|s| s.as_str()).collect();
            for expected in expected_contains {
                assert!(
                    token_set.contains(expected.as_str()),
                    "JA output missing {:?} for {:?}: {:?}",
                    expected,
                    case.input,
                    tokens
                );
            }
        }
        if case.expected_has_question_marker == Some(true) {
            let has_marker = tokens.iter().any(|t| question_markers.contains(t.as_str()));
            assert!(
                has_marker,
                "JA output missing question marker for {:?}: {:?}",
                case.input, tokens
            );
        }
    }
}

// ---------------------------------------------------------------------------
// Encode test cases (PiperEncoder BOS/EOS/PAD insertion)
// ---------------------------------------------------------------------------

/// Load the real phoneme_id_map from the multilingual test model config.
fn load_phoneme_id_map() -> piper_plus_g2p::PhonemeIdMap {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    let config_path = repo_root
        .join("test")
        .join("models")
        .join("multilingual-test-medium.onnx.json");
    let content = std::fs::read_to_string(&config_path)
        .unwrap_or_else(|e| panic!("Failed to read config {config_path:?}: {e}"));
    let parsed: serde_json::Value =
        serde_json::from_str(&content).expect("Failed to parse config JSON");
    let id_map_value = parsed
        .get("phoneme_id_map")
        .expect("config missing phoneme_id_map");
    serde_json::from_value(id_map_value.clone()).expect("Failed to parse phoneme_id_map")
}

#[test]
fn test_encode_golden() {
    let fixture = load_fixture();
    assert!(
        !fixture.encode_test_cases.is_empty(),
        "encode_test_cases should not be empty in fixture"
    );

    let id_map = load_phoneme_id_map();
    let encoder =
        piper_plus_g2p::PiperEncoder::new(id_map.clone(), piper_plus_g2p::UnknownTokenMode::Skip)
            .expect("PiperEncoder::new failed");

    // Resolve BOS/EOS/PAD IDs from the real config for assertion.
    let bos_id = id_map["^"][0];
    let eos_id = id_map["$"][0];
    let pad_id = id_map["_"][0];

    for case in &fixture.encode_test_cases {
        let tokens: Vec<String> = case.tokens.iter().map(|s| s.to_string()).collect();
        let ids = encoder
            .encode(&tokens)
            .unwrap_or_else(|e| panic!("encode failed for {:?}: {e}", case.description));

        // Check minimum length
        assert!(
            ids.len() >= case.expected_min_length,
            "encode length {got} < {min} for {desc:?}: {ids:?}",
            got = ids.len(),
            min = case.expected_min_length,
            desc = case.description,
        );

        // Check BOS
        if case.expected_has_bos {
            assert_eq!(
                ids[0],
                bos_id,
                "first ID should be BOS ({bos_id}) for {desc:?}, got {got}",
                desc = case.description,
                got = ids[0],
            );
        }

        // Check EOS
        if case.expected_has_eos {
            assert_eq!(
                *ids.last().unwrap(),
                eos_id,
                "last ID should be EOS ({eos_id}) for {desc:?}, got {got}",
                desc = case.description,
                got = ids.last().unwrap(),
            );
        }

        // Check PAD insertion: second element should be PAD (BOS, PAD, ...)
        assert_eq!(
            ids[1],
            pad_id,
            "second ID should be PAD ({pad_id}) for {desc:?}, got {got}",
            desc = case.description,
            got = ids[1],
        );

        // Check that PAD appears between phoneme tokens:
        // After BOS+PAD prefix, every other position before EOS should be PAD.
        // The pattern is: BOS PAD (token PAD)* EOS
        // Verify PAD appears before EOS (the second-to-last element).
        let second_last = ids[ids.len() - 2];
        assert_eq!(
            second_last,
            pad_id,
            "second-to-last ID should be PAD ({pad_id}) for {desc:?}, got {got}",
            desc = case.description,
            got = second_last,
        );

        // Verify expected_first_token if specified
        if let Some(ref first_token) = case.expected_first_token {
            let expected_first_id = id_map
                .get(first_token)
                .and_then(|ids| ids.first().copied())
                .unwrap_or_else(|| panic!("expected_first_token {first_token:?} not in id_map"));
            assert_eq!(
                ids[0],
                expected_first_id,
                "first token should map to {first_token:?} ({expected_first_id}) for {desc:?}",
                desc = case.description,
            );
        }
    }
}

// ---------------------------------------------------------------------------
// PUA map individual match test (all 99 entries — PUA v2)
// ---------------------------------------------------------------------------

#[test]
fn test_pua_map_individual() {
    let fixture = load_fixture();

    // Verify fixture has the expected number of entries
    assert_eq!(
        fixture.pua_map.len(),
        fixture.pua_map_count,
        "pua_map entry count ({}) != pua_map_count ({})",
        fixture.pua_map.len(),
        fixture.pua_map_count,
    );
    assert_eq!(
        fixture.pua_map_count, 99,
        "pua_map_count should be 99 (PUA v2), got {}",
        fixture.pua_map_count,
    );

    // Verify FIXED_PUA_MAP count matches fixture
    assert_eq!(
        piper_plus_g2p::token_map::FIXED_PUA_MAP.len(),
        fixture.pua_map_count,
        "FIXED_PUA_MAP length ({}) != fixture pua_map_count ({})",
        piper_plus_g2p::token_map::FIXED_PUA_MAP.len(),
        fixture.pua_map_count,
    );

    // Check every entry in the fixture against token_to_pua
    for (token, hex_str) in &fixture.pua_map {
        let expected_code = u32::from_str_radix(hex_str.trim_start_matches("0x"), 16)
            .unwrap_or_else(|e| panic!("invalid hex {hex_str:?} for token {token:?}: {e}"));
        let expected_char = char::from_u32(expected_code)
            .unwrap_or_else(|| panic!("invalid codepoint 0x{expected_code:04X} for {token:?}"));

        let actual = piper_plus_g2p::token_map::token_to_pua(token);
        assert_eq!(
            actual,
            Some(expected_char),
            "PUA mismatch for token {token:?}: expected U+{expected_code:04X}, got {:?}",
            actual.map(|c| format!("U+{:04X}", c as u32)),
        );
    }

    // Also verify every entry in FIXED_PUA_MAP is present in the fixture
    for (token, code) in piper_plus_g2p::token_map::FIXED_PUA_MAP.iter() {
        let hex_str = format!("0x{:04X}", code);
        let fixture_val = fixture.pua_map.get(*token);
        assert!(
            fixture_val.is_some(),
            "FIXED_PUA_MAP token {token:?} (0x{code:04X}) missing from fixture pua_map"
        );
        assert_eq!(
            fixture_val.unwrap().to_uppercase(),
            hex_str.to_uppercase(),
            "FIXED_PUA_MAP token {token:?}: Rust has 0x{code:04X}, fixture has {:?}",
            fixture_val.unwrap(),
        );
    }
}

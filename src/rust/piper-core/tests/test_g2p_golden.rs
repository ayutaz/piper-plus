//! M4-1: クロスプラットフォーム G2P ゴールデンテスト (Rust)
//!
//! `tests/fixtures/g2p/phoneme_test_cases.json` を読み込み、
//! piper_plus_g2p の各言語 Phonemizer に対してアサーションを実行する。
//! Python/JS と同じフィクスチャを共有することで 3 プラットフォームの
//! 出力一致を保証する。
//!
//! Run: cargo test --test test_g2p_golden

use std::collections::HashSet;
use std::path::PathBuf;

use piper_plus_g2p::Phonemizer;
use serde::Deserialize;

// ---------------------------------------------------------------------------
// Fixture deserialization
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct Fixture {
    test_cases: Vec<TestCase>,
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

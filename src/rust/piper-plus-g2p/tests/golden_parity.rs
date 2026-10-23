//! Golden parity with Python for the multilingual phonemizer.
//!
//! Compares `MultilingualPhonemizer::phonemize_with_language` with
//! `tests/fixtures/g2p/phoneme_test_cases_golden.json`, which Python's
//! `MultilingualPhonemizer` generates with the case language as the Latin
//! default. piper-core phonemizes with the same call when a language is
//! given, so this is the output a Rust caller gets.
//!
//! Cases known to differ are listed in `tests/fixtures/g2p/known_divergences.json`
//! for the `rust` runtime. A difference that is not listed fails, and so does a
//! listed case that now matches, so the list shrinks as the linked issues are
//! fixed. English words that must never phonemize to nothing are listed in
//! `tests/fixtures/g2p/english_no_drop_words.json` and follow the same rule.
//!
//! Multi-codepoint phonemes (rr, tʃ, tone3) are one PUA character here
//! (`pua.json`) and spelled out in the golden; that representation difference
//! is not a divergence. Only the golden side is mapped, so output that forgets
//! the PUA encoding still fails.
//!
//! The dictionaries are the checked-in `data/` files, so nothing here is
//! skipped when a dictionary is missing: a load failure fails the test.
//! Japanese needs OpenJTalk and Korean is absent from the golden (and from the
//! trained models), so both are left out.

#![cfg(all(
    feature = "english",
    feature = "chinese",
    feature = "spanish",
    feature = "french",
    feature = "portuguese",
    feature = "swedish"
))]

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use piper_plus_g2p::Phonemizer;
use piper_plus_g2p::multilingual::MultilingualPhonemizer;
use serde_json::Value;

const RUNTIME: &str = "rust";
const LANGUAGES: [&str; 6] = ["en", "es", "fr", "pt", "sv", "zh"];

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repository root")
        .to_path_buf()
}

fn load_json(relative: &str) -> Value {
    let path = repo_root().join(relative);
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("cannot parse {}: {e}", path.display()))
}

fn phonemizer() -> MultilingualPhonemizer {
    let data = Path::new(env!("CARGO_MANIFEST_DIR")).join("data");
    let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
    phonemizers.insert(
        "en".into(),
        Box::new(
            piper_plus_g2p::english::EnglishPhonemizer::new_with_dict(
                &data.join("cmudict_data.json"),
            )
            .expect("data/cmudict_data.json must load"),
        ),
    );
    phonemizers.insert(
        "zh".into(),
        Box::new(
            piper_plus_g2p::chinese::ChinesePhonemizer::new(
                &data.join("pinyin_single.json"),
                &data.join("pinyin_phrases.json"),
            )
            .expect("data/pinyin_*.json must load"),
        ),
    );
    phonemizers.insert(
        "es".into(),
        Box::new(piper_plus_g2p::spanish::SpanishPhonemizer::new()),
    );
    phonemizers.insert(
        "fr".into(),
        Box::new(piper_plus_g2p::french::FrenchPhonemizer::new()),
    );
    phonemizers.insert(
        "pt".into(),
        Box::new(piper_plus_g2p::portuguese::PortuguesePhonemizer::new()),
    );
    phonemizers.insert(
        "sv".into(),
        Box::new(piper_plus_g2p::swedish::SwedishPhonemizer::new()),
    );
    MultilingualPhonemizer::new(
        LANGUAGES.iter().map(|l| l.to_string()).collect(),
        "en".into(),
        phonemizers,
    )
}

/// Maps the golden spelling of multi-codepoint phonemes to their PUA character.
fn pua_table() -> HashMap<String, String> {
    let doc = load_json("src/python/g2p/piper_plus_g2p/data/pua.json");
    doc["entries"]
        .as_array()
        .expect("pua.json entries")
        .iter()
        .map(|e| {
            let token = e["token"].as_str().unwrap().to_string();
            let hex = e["codepoint"].as_str().unwrap().trim_start_matches("0x");
            let cp = u32::from_str_radix(hex, 16).unwrap();
            (token, char::from_u32(cp).unwrap().to_string())
        })
        .collect()
}

fn lists_runtime(entry: &Value) -> bool {
    entry["runtimes"]
        .as_array()
        .is_some_and(|r| r.iter().any(|v| v == RUNTIME))
}

/// Tokens are joined with one space; a word boundary token " " therefore
/// appears as three spaces (two empty parts when split).
fn split_phonemes(s: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    if s.is_empty() {
        return tokens;
    }
    let mut empty_parts = 0;
    for part in s.split(' ') {
        if !part.is_empty() {
            empty_parts = 0;
            tokens.push(part.to_string());
        } else {
            empty_parts += 1;
            if empty_parts == 2 {
                empty_parts = 0;
                tokens.push(" ".to_string());
            }
        }
    }
    tokens
}

#[test]
fn matches_python_golden_except_listed_divergences() {
    let pua = pua_table();
    let registry = load_json("tests/fixtures/g2p/known_divergences.json");
    let golden = load_json("tests/fixtures/g2p/phoneme_test_cases_golden.json");
    let known: HashSet<(String, String)> = registry["divergences"]
        .as_array()
        .expect("divergences")
        .iter()
        .filter(|e| lists_runtime(e))
        .map(|e| {
            (
                e["language"].as_str().unwrap().to_string(),
                e["input"].as_str().unwrap().to_string(),
            )
        })
        .collect();
    let p = phonemizer();

    let mut verified = 0;
    let mut known_count = 0;
    let mut failures = Vec::new();
    for case in golden["test_cases"].as_array().expect("test_cases") {
        let lang = case["language"].as_str().unwrap();
        let input = case["input"].as_str().unwrap();
        if !LANGUAGES.contains(&lang) {
            continue;
        }
        let golden_phonemes = case["expected_phonemes"].as_str().unwrap();
        let expected: Vec<String> = split_phonemes(golden_phonemes)
            .into_iter()
            .map(|t| pua.get(&t).cloned().unwrap_or(t))
            .collect();
        let actual = p.phonemize_with_language(input, lang).map(|(t, _)| t);
        let matches = actual.as_ref().is_ok_and(|t| *t == expected);
        verified += 1;

        let label = format!("[{lang}] '{input}'");
        let listed = known.contains(&(lang.to_string(), input.to_string()));
        if matches && listed {
            failures.push(format!(
                "{label} now matches; remove it from known_divergences.json"
            ));
        } else if !matches && listed {
            known_count += 1;
        } else if !matches {
            let got = match &actual {
                Ok(t) => t.join(" "),
                Err(e) => format!("(phonemize failed: {e})"),
            };
            failures.push(format!(
                "{label}\n  expected: {golden_phonemes}\n  actual:   {got}"
            ));
        }
    }

    assert!(verified > 0, "no golden case compared");
    assert!(
        failures.is_empty(),
        "{} failure(s), {known_count} known, {verified} cases:\n{}",
        failures.len(),
        failures.join("\n")
    );
}

#[test]
fn english_words_are_not_dropped() {
    let list = load_json("tests/fixtures/g2p/english_no_drop_words.json");
    let known_drops: HashSet<String> = list["known_drops"]
        .as_array()
        .expect("known_drops")
        .iter()
        .filter(|e| lists_runtime(e))
        .map(|e| e["word"].as_str().unwrap().to_string())
        .collect();
    let p = phonemizer();

    let mut checked = 0;
    let mut failures = Vec::new();
    for word in list["words"].as_array().expect("words") {
        let word = word.as_str().unwrap();
        let tokens = p
            .phonemize_with_language(word, "en")
            .map(|(t, _)| t)
            .unwrap_or_default();
        let spoken = tokens.iter().any(|t| {
            !matches!(
                t.as_str(),
                " " | "." | "," | "!" | "?" | ";" | ":" | "'" | "\"" | "-"
            )
        });
        checked += 1;
        let listed = known_drops.contains(word);
        if spoken && listed {
            failures.push(format!(
                "'{word}' is now spoken; remove it from known_drops"
            ));
        } else if !spoken && !listed {
            failures.push(format!(
                "'{word}' produced no phoneme: '{}'",
                tokens.join(" ")
            ));
        }
    }

    assert!(checked > 0, "english_no_drop_words.json has no words");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

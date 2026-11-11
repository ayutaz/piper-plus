//! Every phonemizer strips control characters before phonemizing.
//!
//! Contract: `docs/spec/input-sanitize-contract.toml` (runtime `rust-g2p`).
//! Cases: `tests/fixtures/input_sanitize_cases.json`, a byte-for-byte copy of
//! the canonical `tests/fixtures/g2p/input_sanitize_cases.json` that every
//! runtime reads (`scripts/check_input_sanitize_contract.py` keeps the copy
//! equal).
//!
//! Regression focus: #934 (2026-11) said the Python G2P matched
//! `Phonemizer::validate_input`, but nothing called `validate_input`: a NUL
//! or a C1 character reached every Rust phonemizer. The last test counts every
//! `impl Phonemizer for` under `src/`, so a new phonemizer has to be added to
//! the list this file tests before the suite passes again.

use std::collections::{BTreeSet, HashMap};
use std::path::Path;

use piper_plus_g2p::Phonemizer;
use piper_plus_g2p::multilingual::{MultilingualPhonemizer, PassthroughPhonemizer};
use serde_json::Value;

const FIXTURE: &str = include_str!("fixtures/input_sanitize_cases.json");

/// Types that only forward to another phonemizer (or exist only in tests).
const DELEGATING: &[&str] = &[
    "SharedPhonemizer",
    "PassthroughPhonemizer",
    "LabelPhonemizer",
];

fn cases() -> Value {
    serde_json::from_str(FIXTURE).expect("input_sanitize_cases.json parses")
}

fn data() -> std::path::PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("data")
}

/// A phonemizer under test: fixture language, type name, phonemizer.
type Entry = (&'static str, &'static str, Box<dyn Phonemizer>);

// Each push depends on a feature, so the list cannot be one `vec![]`.
#[allow(clippy::vec_init_then_push)]
fn single_language() -> Vec<Entry> {
    #[allow(unused_mut)]
    let mut out: Vec<Entry> = Vec::new();
    #[cfg(feature = "naist-jdic")]
    out.push((
        "ja",
        "JapanesePhonemizer",
        Box::new(piper_plus_g2p::japanese::JapanesePhonemizer::new_bundled().unwrap()),
    ));
    #[cfg(feature = "english")]
    out.push((
        "en",
        "EnglishPhonemizer",
        Box::new(
            piper_plus_g2p::english::EnglishPhonemizer::new_with_dict(
                &data().join("cmudict_data.json"),
            )
            .unwrap(),
        ),
    ));
    #[cfg(feature = "chinese")]
    out.push(("zh", "ChinesePhonemizer", Box::new(chinese())));
    #[cfg(feature = "korean")]
    out.push((
        "ko",
        "KoreanPhonemizer",
        Box::new(piper_plus_g2p::korean::KoreanPhonemizer::new()),
    ));
    #[cfg(feature = "spanish")]
    out.push((
        "es",
        "SpanishPhonemizer",
        Box::new(piper_plus_g2p::spanish::SpanishPhonemizer::new()),
    ));
    #[cfg(feature = "french")]
    out.push((
        "fr",
        "FrenchPhonemizer",
        Box::new(piper_plus_g2p::french::FrenchPhonemizer::new()),
    ));
    #[cfg(feature = "portuguese")]
    out.push((
        "pt",
        "PortuguesePhonemizer",
        Box::new(piper_plus_g2p::portuguese::PortuguesePhonemizer::new()),
    ));
    #[cfg(feature = "portuguese")]
    out.push((
        "pt-PT",
        "EuropeanPortuguesePhonemizer",
        Box::new(piper_plus_g2p::portuguese::EuropeanPortuguesePhonemizer::new()),
    ));
    #[cfg(feature = "swedish")]
    out.push((
        "sv",
        "SwedishPhonemizer",
        Box::new(piper_plus_g2p::swedish::SwedishPhonemizer::new()),
    ));
    out
}

#[cfg(feature = "chinese")]
fn chinese() -> piper_plus_g2p::chinese::ChinesePhonemizer {
    piper_plus_g2p::chinese::ChinesePhonemizer::new(
        &data().join("pinyin_single.json"),
        &data().join("pinyin_phrases.json"),
    )
    .unwrap()
}

/// Two set-ups, as in the Python test: Latin text to en, and (without en) to es.
fn multilingual() -> Vec<MultilingualPhonemizer> {
    [("en", true), ("es", false)]
        .into_iter()
        .map(|(latin, with_en)| {
            let mut phonemizers: HashMap<String, Box<dyn Phonemizer>> = HashMap::new();
            for (lang, _, p) in single_language() {
                if (lang != "en" || with_en) && lang != "pt-PT" {
                    phonemizers.insert(lang.to_string(), p);
                }
            }
            phonemizers
                .entry("ja".into())
                .or_insert_with(|| Box::new(PassthroughPhonemizer::new("ja")));
            let languages = phonemizers.keys().cloned().collect();
            MultilingualPhonemizer::new(languages, latin.to_string(), phonemizers)
        })
        .collect()
}

fn phonemizers_for(language: &str) -> Vec<Box<dyn Phonemizer>> {
    if language == "multilingual" {
        return multilingual()
            .into_iter()
            .map(|m| Box::new(m) as Box<dyn Phonemizer>)
            .collect();
    }
    single_language()
        .into_iter()
        .filter(|(lang, _, _)| *lang == language)
        .map(|(_, _, p)| p)
        .collect()
}

/// Both entry points, rendered with `{:?}` (`ProsodyInfo` has no `PartialEq`).
fn read(p: &dyn Phonemizer, text: &str, language: &str) -> [String; 2] {
    let lang = if language == "multilingual" {
        "es"
    } else {
        language
    };
    [
        format!("{:?}", p.phonemize_with_prosody(text)),
        format!("{:?}", p.phonemize_with_language(text, lang)),
    ]
}

#[test]
fn strip_cases_match() {
    let p = PassthroughPhonemizer::new("es");
    for case in cases()["strip_cases"].as_array().unwrap() {
        let input = case["input"].as_str().unwrap();
        let want = case["expected"].as_str().unwrap();
        assert_eq!(
            p.validate_input(input).unwrap(),
            want,
            "strip_cases[{}]",
            case["name"]
        );
    }
}

#[test]
fn dirty_word_reads_like_clean() {
    let mut checked = 0;
    for case in cases()["word_cases"].as_array().unwrap() {
        let language = case["language"].as_str().unwrap();
        for p in phonemizers_for(language) {
            let dirty = read(p.as_ref(), case["dirty"].as_str().unwrap(), language);
            let clean = read(p.as_ref(), case["clean"].as_str().unwrap(), language);
            assert_eq!(
                dirty, clean,
                "{language} {} ({}): dirty and clean read differently",
                case["clean"], case["control"]
            );
            checked += 1;
        }
    }
    assert!(checked > 0, "no phonemizer was built: check the features");
}

#[cfg(feature = "chinese")]
#[test]
fn zh_embedded_english_is_stripped() {
    let zh = chinese();
    assert_eq!(
        zh.phonemize_embedded_english("G\u{0}PS"),
        zh.phonemize_embedded_english("GPS")
    );
}

#[test]
fn only_controls_read_as_empty_text() {
    for language in ["es", "multilingual"] {
        for p in phonemizers_for(language) {
            assert_eq!(
                read(p.as_ref(), "\u{0}\u{1}\u{7f}\u{85}", language),
                read(p.as_ref(), "", language),
                "{language}"
            );
        }
    }
}

#[test]
fn long_japanese_is_accepted() {
    // piper-core passes the whole text, so the contract sets no length limit.
    for m in multilingual() {
        assert!(m.phonemize_with_prosody(&"あ".repeat(4000)).is_ok());
    }
}

#[test]
fn validate_input_counts_chars() {
    // 4000 characters are 12000 bytes: within the 10000-character limit.
    let p = PassthroughPhonemizer::new("ja");
    assert!(p.validate_input(&"あ".repeat(4000)).is_ok());
    assert!(p.validate_input(&"a".repeat(10_001)).is_err());
}

/// The phonemizers this file builds, by type name.
const COVERED: &[&str] = &[
    "JapanesePhonemizer",
    "EnglishPhonemizer",
    "ChinesePhonemizer",
    "KoreanPhonemizer",
    "SpanishPhonemizer",
    "FrenchPhonemizer",
    "PortuguesePhonemizer",
    "EuropeanPortuguesePhonemizer",
    "SwedishPhonemizer",
    "MultilingualPhonemizer",
];

#[test]
fn every_phonemizer_impl_is_covered() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let pattern = regex::Regex::new(r"impl\s+Phonemizer\s+for\s+(\w+)").unwrap();
    let mut found = BTreeSet::new();
    let mut stack = vec![src];
    while let Some(dir) = stack.pop() {
        for entry in std::fs::read_dir(&dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                stack.push(path);
            } else if path.extension().is_some_and(|e| e == "rs") {
                let text = std::fs::read_to_string(&path).unwrap();
                for cap in pattern.captures_iter(&text) {
                    found.insert(cap[1].to_string());
                }
            }
        }
    }
    let known: BTreeSet<String> = COVERED
        .iter()
        .chain(DELEGATING)
        .map(|s| s.to_string())
        .collect();
    assert_eq!(
        found, known,
        "a phonemizer was added or removed: build it in single_language() \
         (or list it in DELEGATING if it only forwards) and update COVERED"
    );

    // Every covered type is built when its feature is on.
    let built: BTreeSet<&str> = single_language().iter().map(|(_, name, _)| *name).collect();
    for name in single_language().iter().map(|(_, name, _)| *name) {
        assert!(
            COVERED.contains(&name),
            "{name} is built but not in COVERED"
        );
    }
    #[cfg(all(
        feature = "naist-jdic",
        feature = "english",
        feature = "chinese",
        feature = "korean",
        feature = "spanish",
        feature = "french",
        feature = "portuguese",
        feature = "swedish"
    ))]
    for name in COVERED.iter().filter(|n| **n != "MultilingualPhonemizer") {
        assert!(built.contains(name), "{name} is in COVERED but never built");
    }
    let _ = built;
}

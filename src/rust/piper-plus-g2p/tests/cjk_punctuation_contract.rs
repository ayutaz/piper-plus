//! CJK punctuation contract (Issue #823).
//!
//! Reads `tests/fixtures/g2p/cjk_punctuation_cases.json`, which
//! `scripts/build_cjk_punctuation_fixture.py` builds from
//! `docs/spec/cjk-punctuation-contract.toml`. Every runtime has the same test,
//! so a detector or Latin-segment rewrite that drifts from the contract fails
//! in the runtime that drifted.

#![cfg(all(feature = "english", feature = "chinese", feature = "spanish"))]

use std::collections::HashMap;
use std::path::Path;

use piper_plus_g2p::Phonemizer;
use piper_plus_g2p::multilingual::{
    MultilingualPhonemizer, PassthroughPhonemizer, UnicodeLanguageDetector,
    normalize_cjk_punctuation_for_latin, segment_text,
};
use serde_json::Value;

fn load_fixture() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repository root")
        .join("tests/fixtures/g2p/cjk_punctuation_cases.json");
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("cannot parse {}: {e}", path.display()))
}

fn detector(fixture: &Value) -> UnicodeLanguageDetector {
    let languages: Vec<String> = fixture["detector_languages"]
        .as_array()
        .expect("detector_languages")
        .iter()
        .map(|l| l.as_str().unwrap().to_string())
        .collect();
    UnicodeLanguageDetector::new(&languages, fixture["default_latin"].as_str().unwrap())
}

/// `(code_point, char, latin)` for each entry of `fixture[key]`.
fn entries(fixture: &Value, key: &str) -> Vec<(String, char, Option<String>)> {
    fixture[key]
        .as_array()
        .unwrap_or_else(|| panic!("{key}"))
        .iter()
        .map(|e| {
            let s = e["char"].as_str().unwrap();
            let mut chars = s.chars();
            let ch = chars.next().expect("one character");
            assert!(chars.next().is_none(), "{s:?} is not one character");
            (
                e["code_point"].as_str().unwrap().to_string(),
                ch,
                e["latin"].as_str().map(str::to_string),
            )
        })
        .collect()
}

#[test]
fn fixture_is_not_empty() {
    let fixture = load_fixture();
    assert!(entries(&fixture, "neutral").len() > 100);
    assert_eq!(entries(&fixture, "fullwidth_latin").len(), 52);
}

#[test]
fn neutral_code_points_belong_to_no_language() {
    let fixture = load_fixture();
    let det = detector(&fixture);
    for context_has_kana in [false, true] {
        let wrong: Vec<(String, String)> = entries(&fixture, "neutral")
            .into_iter()
            .filter_map(|(cp, ch, _)| {
                det.detect_char(ch, context_has_kana)
                    .map(|lang| (cp, lang.to_string()))
            })
            .collect();
        assert!(
            wrong.is_empty(),
            "context_has_kana={context_has_kana}: {wrong:?}"
        );
    }
}

#[test]
fn fullwidth_latin_letters_stay_latin() {
    let fixture = load_fixture();
    let det = detector(&fixture);
    let default_latin = fixture["default_latin"].as_str().unwrap();
    let wrong: Vec<String> = entries(&fixture, "fullwidth_latin")
        .into_iter()
        .filter(|(_, ch, _)| det.detect_char(*ch, false) != Some(default_latin))
        .map(|(cp, _, _)| cp)
        .collect();
    assert!(wrong.is_empty(), "{wrong:?}");
}

#[test]
fn latin_segment_rewrite() {
    let fixture = load_fixture();
    let wrong: Vec<(String, String, String)> = entries(&fixture, "neutral")
        .into_iter()
        .filter_map(|(cp, ch, latin)| {
            let latin = latin.expect("latin");
            let actual = normalize_cjk_punctuation_for_latin(&ch.to_string()).into_owned();
            (actual != latin).then_some((cp, actual, latin))
        })
        .collect();
    assert!(
        wrong.is_empty(),
        "(code point, actual, expected): {wrong:?}"
    );
    // Everything else is left alone, the fullwidth Latin letters included.
    for text in ["Hello, world!", "café", "ＡＢＣ", "你好", "こんにちは", ""] {
        assert_eq!(normalize_cjk_punctuation_for_latin(text), text);
    }
}

/// The checked-in dictionaries, plus a passthrough "ja": with Japanese
/// configured, CJK punctuation used to become a Japanese segment.
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
    phonemizers.insert("ja".into(), Box::new(PassthroughPhonemizer::new("ja")));
    MultilingualPhonemizer::new(
        ["en", "es", "ja", "zh"]
            .iter()
            .map(|l| l.to_string())
            .collect(),
        "en".into(),
        phonemizers,
    )
}

fn tokens(p: &MultilingualPhonemizer, text: &str) -> Vec<String> {
    p.phonemize_with_prosody(text).expect("phonemize").0
}

#[test]
fn chinese_sentence_keeps_its_punctuation() {
    let p = phonemizer();
    let t = tokens(&p, "你好，今天天气很好。");
    assert_eq!(t.iter().filter(|t| *t == ",").count(), 1, "{t:?}");
    assert_eq!(t.last().map(String::as_str), Some("."), "{t:?}");
    let t = tokens(&p, "北京欢迎你。");
    assert_eq!(t.last().map(String::as_str), Some("."), "{t:?}");

    let fixture = load_fixture();
    let langs: Vec<String> = segment_text("你好，今天天气很好。", &detector(&fixture))
        .into_iter()
        .map(|(lang, _)| lang)
        .collect();
    assert_eq!(langs, ["zh"]);
}

#[test]
fn english_after_chinese_comma_is_read_as_a_loanword() {
    // The ZH-EN dispatch needs the Chinese segment right before the English
    // one; a Japanese segment for "，" used to sit between them.
    let p = phonemizer();
    let with_comma: Vec<String> = tokens(&p, "你好，GPS")
        .into_iter()
        .filter(|t| t != ",")
        .collect();
    assert_eq!(with_comma, tokens(&p, "你好GPS"));
}

#[test]
fn latin_text_with_cjk_punctuation_reads_like_ascii() {
    // The English G2P deletes characters it does not know, which used to
    // join "Hello，world" into one word.
    let p = phonemizer();
    for (cjk, ascii, lang) in [
        ("Hello，world", "Hello,world", "en"),
        ("Hello、world。", "Hello,world.", "en"),
        ("Hola，amigo！", "Hola,amigo!", "en"),
        ("Hola，amigo！", "Hola,amigo!", "es"),
        ("I have ３ cats．", "I have 3 cats.", "en"),
    ] {
        let actual = p.phonemize_with_language(cjk, lang).expect("phonemize").0;
        let expected = p.phonemize_with_language(ascii, lang).expect("phonemize").0;
        assert_eq!(actual, expected, "[{lang}] {cjk:?} vs {ascii:?}");
    }
}

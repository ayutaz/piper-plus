use piper_core::phonemize::korean::KoreanPhonemizer;
use piper_core::phonemize::Phonemizer;

#[test]
fn test_language_code() {
    let p = KoreanPhonemizer::new();
    assert_eq!(p.language_code(), "ko");
}

#[test]
fn test_basic_hangul() {
    let p = KoreanPhonemizer::new();
    let (tokens, prosody) = p.phonemize_with_prosody("한글").unwrap();
    assert!(!tokens.is_empty());
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_hangul_decomposition_ga() {
    // 가 = ㄱ(k) + ㅏ(a) + no final
    let p = KoreanPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("가").unwrap();
    assert!(tokens.iter().any(|t| t == "k" || t == "a"));
}

#[test]
fn test_hangul_decomposition_han() {
    // 한 = ㅎ(h) + ㅏ(a) + ㄴ(n)
    let p = KoreanPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("한").unwrap();
    assert!(tokens.iter().any(|t| t == "h" || t == "a" || t == "n"));
}

#[test]
fn test_prosody_all_zero() {
    let p = KoreanPhonemizer::new();
    let (_, prosody) = p.phonemize_with_prosody("한글").unwrap();
    for p_info in prosody.iter().flatten() {
        assert_eq!(p_info.a1, 0);
        assert_eq!(p_info.a2, 0);
    }
}

#[test]
fn test_non_hangul_passthrough() {
    let p = KoreanPhonemizer::new();
    let (tokens, _) = p.phonemize_with_prosody("123").unwrap();
    // Digits should either be skipped or passed through
    assert!(tokens.is_empty() || tokens.iter().all(|t| t.len() <= 1));
}

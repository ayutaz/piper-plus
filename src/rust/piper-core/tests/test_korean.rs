use piper_plus::phonemize::Phonemizer;
use piper_plus::phonemize::korean::KoreanPhonemizer;

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

// ---------------------------------------------------------------------------
// detect_primary_language
// ---------------------------------------------------------------------------

#[test]
fn test_detect_primary_language_returns_ko() {
    let p = KoreanPhonemizer::new();
    assert_eq!(
        p.detect_primary_language("안녕하세요"),
        "ko",
        "detect_primary_language should return 'ko' for Korean phonemizer"
    );
}

#[test]
fn test_detect_primary_language_empty_string() {
    let p = KoreanPhonemizer::new();
    assert_eq!(
        p.detect_primary_language(""),
        "ko",
        "detect_primary_language should return 'ko' even for empty input"
    );
}

// ---------------------------------------------------------------------------
// get_phoneme_id_map
// ---------------------------------------------------------------------------

#[test]
fn test_get_phoneme_id_map() {
    let p = KoreanPhonemizer::new();
    assert!(
        p.get_phoneme_id_map().is_none(),
        "Korean phonemizer should return None for phoneme_id_map (uses config.json)"
    );
}

// ---------------------------------------------------------------------------
// post_process_ids
// ---------------------------------------------------------------------------

#[test]
fn test_post_process_ids_passthrough() {
    let p = KoreanPhonemizer::new();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("^".to_string(), vec![1i64]);
    id_map.insert("$".to_string(), vec![2i64]);
    id_map.insert("_".to_string(), vec![0i64]);

    let ids = vec![10i64, 20, 30];
    let prosody = vec![Some([0i32, 0, 0]), Some([0, 0, 0]), Some([0, 0, 0])];

    let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);

    // Korean uses default_post_process_ids: BOS + intersperse padding + EOS
    assert_eq!(*result_ids.first().unwrap(), 1, "should start with BOS");
    assert_eq!(*result_ids.last().unwrap(), 2, "should end with EOS");
    assert!(
        result_ids.contains(&10) && result_ids.contains(&20) && result_ids.contains(&30),
        "should contain all original phoneme IDs"
    );
    assert_eq!(
        result_ids.len(),
        result_prosody.len(),
        "IDs and prosody must have same length"
    );
}

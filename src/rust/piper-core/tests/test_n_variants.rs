//! Integration tests for Japanese N phoneme context-dependent variant rules.
//!
//! Tests `piper_plus::phonemize::japanese::apply_n_phoneme_rules` which
//! replaces bare "N" tokens with context-appropriate variants:
//!
//! - N_m      : before m/b/p/my/by/py (bilabial assimilation)
//! - N_n      : before n/t/d/ny/ty/dy/ts/ch (alveolar assimilation)
//! - N_ng     : before k/g/ky/kw/gy/gw (velar assimilation)
//! - N_uvular : at phrase end, before vowels, or other consonants

#[cfg(feature = "japanese")]
mod tests {
    use piper_plus::phonemize::japanese::apply_n_phoneme_rules;

    // -----------------------------------------------------------------------
    // Bilabial assimilation (N_m)
    // -----------------------------------------------------------------------

    #[test]
    fn test_n_before_m() {
        // "さんま" → s a N m a → N before m → N_m
        let mut tokens: Vec<String> = ["s", "a", "N", "m", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_m");
    }

    #[test]
    fn test_n_before_b() {
        // N before b → N_m (bilabial)
        let mut tokens: Vec<String> = ["a", "N", "b", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_before_p() {
        // "さんぽ" → s a N p o → N before p → N_m
        let mut tokens: Vec<String> = ["s", "a", "N", "p", "o"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_m");
    }

    #[test]
    fn test_n_before_my() {
        // N before my (palatalized bilabial) → N_m
        let mut tokens: Vec<String> = ["a", "N", "my", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_before_by() {
        // N before by (palatalized bilabial) → N_m
        let mut tokens: Vec<String> = ["a", "N", "by", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_before_py() {
        // N before py (palatalized bilabial) → N_m
        let mut tokens: Vec<String> = ["a", "N", "py", "o"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    // -----------------------------------------------------------------------
    // Alveolar assimilation (N_n)
    // -----------------------------------------------------------------------

    #[test]
    fn test_n_before_n() {
        // "あんない" → a N n a i → N before n → N_n
        let mut tokens: Vec<String> = ["a", "N", "n", "a", "i"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_t() {
        // N before t → N_n (alveolar)
        let mut tokens: Vec<String> = ["a", "N", "t", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_d() {
        // N before d → N_n (alveolar)
        let mut tokens: Vec<String> = ["a", "N", "d", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_ts() {
        // N before ts → N_n (alveolar affricate)
        let mut tokens: Vec<String> = ["a", "N", "ts", "u"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_ch() {
        // N before ch → N_n (alveolar affricate)
        let mut tokens: Vec<String> = ["a", "N", "ch", "i"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_ny() {
        // N before ny (palatalized alveolar) → N_n
        let mut tokens: Vec<String> = ["a", "N", "ny", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_ty() {
        // N before ty (palatalized alveolar) → N_n
        let mut tokens: Vec<String> = ["a", "N", "ty", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_before_dy() {
        // N before dy (palatalized alveolar) → N_n
        let mut tokens: Vec<String> = ["a", "N", "dy", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    // -----------------------------------------------------------------------
    // Velar assimilation (N_ng)
    // -----------------------------------------------------------------------

    #[test]
    fn test_n_before_k() {
        // "ぎんこう" → g i N k o u → N before k → N_ng
        let mut tokens: Vec<String> = ["g", "i", "N", "k", "o", "u"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_ng");
    }

    #[test]
    fn test_n_before_g() {
        // N before g → N_ng (velar)
        let mut tokens: Vec<String> = ["a", "N", "g", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_ky() {
        // N before ky (palatalized velar) → N_ng
        let mut tokens: Vec<String> = ["a", "N", "ky", "o"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_kw() {
        // N before kw (labialized velar) → N_ng
        let mut tokens: Vec<String> = ["a", "N", "kw", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_gy() {
        // N before gy (palatalized velar) → N_ng
        let mut tokens: Vec<String> = ["a", "N", "gy", "o"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_before_gw() {
        // N before gw (labialized velar) → N_ng
        let mut tokens: Vec<String> = ["a", "N", "gw", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    // -----------------------------------------------------------------------
    // Uvular / default (N_uvular)
    // -----------------------------------------------------------------------

    #[test]
    fn test_n_at_end() {
        // "ほん" → h o N (end) → N_uvular
        let mut tokens: Vec<String> = ["h", "o", "N"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_uvular");
    }

    #[test]
    fn test_n_before_vowel_a() {
        // N before vowel 'a' → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_vowel_i() {
        // N before vowel 'i' → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "i"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_vowel_u() {
        // N before vowel 'u' → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "u"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_vowel_e() {
        // N before vowel 'e' → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "e"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_vowel_o() {
        // N before vowel 'o' → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "o"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_other_consonant() {
        // N before 'w' (not in any assimilation set) → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "w", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_h() {
        // N before 'h' (not in any assimilation set) → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "h", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_s() {
        // N before 's' → N_uvular (s is not in any assimilation set)
        let mut tokens: Vec<String> = ["a", "N", "s", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    #[test]
    fn test_n_before_r() {
        // N before 'r' → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "r", "a"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    // -----------------------------------------------------------------------
    // Prosody marker skipping
    // -----------------------------------------------------------------------

    #[test]
    fn test_n_skips_prosody_hash_to_k() {
        // N then '#' (accent boundary) then k → skip '#', N_ng
        let mut tokens: Vec<String> = ["a", "N", "#", "k", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
        // '#' itself should pass through unchanged
        assert_eq!(tokens[2], "#");
    }

    #[test]
    fn test_n_skips_prosody_underscore_to_m() {
        // N then '_' (pause) then m → skip '_', N_m
        let mut tokens: Vec<String> = ["a", "N", "_", "m", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_m");
    }

    #[test]
    fn test_n_skips_prosody_bracket_to_t() {
        // N then '[' (pitch rise) then t → skip '[', N_n
        let mut tokens: Vec<String> = ["a", "N", "[", "t", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_n");
    }

    #[test]
    fn test_n_skips_multiple_prosody_markers() {
        // N then '#' ']' then g → skip both markers, N_ng
        let mut tokens: Vec<String> = ["a", "N", "#", "]", "g", "o"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_ng");
    }

    #[test]
    fn test_n_only_prosody_markers_after() {
        // N then only prosody markers, no actual phoneme → N_uvular
        let mut tokens: Vec<String> = ["a", "N", "#", "$"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular");
    }

    // -----------------------------------------------------------------------
    // No-N and passthrough
    // -----------------------------------------------------------------------

    #[test]
    fn test_no_n_tokens_unchanged() {
        // Input without N should be unchanged
        let expected: Vec<String> = ["k", "o", "n", "i", "ch", "i", "w", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let mut tokens: Vec<String> = expected.clone();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens, expected);
    }

    #[test]
    fn test_empty_input() {
        let mut tokens: Vec<String> = vec![];
        apply_n_phoneme_rules(&mut tokens);
        assert!(tokens.is_empty());
    }

    #[test]
    fn test_single_n_only() {
        // Just "N" alone → N_uvular (nothing follows)
        let mut tokens: Vec<String> = ["N"].iter().map(|s| s.to_string()).collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens, vec!["N_uvular"]);
    }

    #[test]
    fn test_non_n_tokens_preserved() {
        // All non-N tokens should pass through as-is
        let mut tokens: Vec<String> = ["^", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[0], "^");
        assert_eq!(tokens[1], "k");
        assert_eq!(tokens[2], "o");
        assert_eq!(tokens[3], "N_n"); // N before n → N_n
        assert_eq!(tokens[4], "n");
        assert_eq!(tokens[10], "$");
    }

    // -----------------------------------------------------------------------
    // Multiple N tokens
    // -----------------------------------------------------------------------

    #[test]
    fn test_multiple_n_tokens() {
        // Multiple N tokens each resolved independently
        let mut tokens: Vec<String> = ["N", "m", "a", "N", "k", "a", "N"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[0], "N_m"); // before m → bilabial
        assert_eq!(tokens[3], "N_ng"); // before k → velar
        assert_eq!(tokens[6], "N_uvular"); // at end → uvular
    }

    #[test]
    fn test_consecutive_n_tokens() {
        // Two consecutive N tokens: first N looks ahead to second N.
        // "N" is not in SKIP_TOKENS, so the first N sees "N" as next phoneme.
        // "N" is not in BILABIAL/ALVEOLAR/VELAR → N_uvular.
        // Second N has nothing after it → N_uvular.
        let mut tokens: Vec<String> = ["a", "N", "N", "k", "a"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[1], "N_uvular"); // first N sees next N (not in any set)
        assert_eq!(tokens[2], "N_ng"); // second N sees k → velar
    }

    // -----------------------------------------------------------------------
    // Lowercase 'n' vs uppercase 'N'
    // -----------------------------------------------------------------------

    #[test]
    fn test_lowercase_n_not_affected() {
        // Lowercase 'n' (regular alveolar nasal) should NOT be converted
        let expected: Vec<String> = ["n", "a", "n", "i"].iter().map(|s| s.to_string()).collect();
        let mut tokens: Vec<String> = expected.clone();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens, expected);
    }

    // -----------------------------------------------------------------------
    // Output length invariant
    // -----------------------------------------------------------------------

    #[test]
    fn test_output_length_equals_input() {
        // The function should never add or remove tokens
        let mut tokens: Vec<String> = ["^", "s", "a", "N", "p", "o", "_", "h", "o", "N", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let original_len = tokens.len();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens.len(), original_len);
    }

    // -----------------------------------------------------------------------
    // Realistic word-level patterns
    // -----------------------------------------------------------------------

    #[test]
    fn test_sanpo() {
        // さんぽ (walk) → s a N p o
        let mut tokens: Vec<String> = ["^", "s", "a", "N", "p", "o", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_m"); // before p → bilabial
    }

    #[test]
    fn test_annai() {
        // あんない (guidance) → a N n a i
        let mut tokens: Vec<String> = ["^", "a", "N", "n", "a", "i", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[2], "N_n"); // before n → alveolar
    }

    #[test]
    fn test_ginkou() {
        // ぎんこう (bank) → g i N k o u
        let mut tokens: Vec<String> = ["^", "g", "i", "N", "k", "o", "u", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_ng"); // before k → velar
    }

    #[test]
    fn test_hon() {
        // ほん (book) → h o N (end)
        let mut tokens: Vec<String> = ["^", "h", "o", "N", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_uvular"); // before $ (skipped) → end → uvular
    }

    #[test]
    fn test_denwa() {
        // でんわ (phone) → d e N w a
        // 'w' is not in BILABIAL/ALVEOLAR/VELAR → N_uvular
        let mut tokens: Vec<String> = ["^", "d", "e", "N", "w", "a", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_uvular");
    }

    #[test]
    fn test_shinbun() {
        // しんぶん (newspaper) → sh i N b u N
        let mut tokens: Vec<String> = ["^", "sh", "i", "N", "b", "u", "N", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_m"); // first N before b → bilabial
        assert_eq!(tokens[6], "N_uvular"); // second N before $ → uvular
    }

    #[test]
    fn test_kangen() {
        // かんげん (return) → k a N g e N
        let mut tokens: Vec<String> = ["^", "k", "a", "N", "g", "e", "N", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_ng"); // first N before g → velar
        assert_eq!(tokens[6], "N_uvular"); // second N before $ → uvular
    }

    #[test]
    fn test_kanten() {
        // かんてん (viewpoint) → k a N t e N
        let mut tokens: Vec<String> = ["^", "k", "a", "N", "t", "e", "N", "$"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        apply_n_phoneme_rules(&mut tokens);
        assert_eq!(tokens[3], "N_n"); // first N before t → alveolar
        assert_eq!(tokens[6], "N_uvular"); // second N before $ → uvular
    }
}

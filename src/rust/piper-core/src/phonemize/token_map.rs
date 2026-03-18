//! PUA (Private Use Area) マッピング.
//!
//! Python (token_mapper.py) および C++ (各 *_phonemize.cpp) と同一のテーブル。
//! 学習済みモデルの重みに依存するため変更不可。

use std::collections::HashMap;
use std::sync::LazyLock;

/// 固定 PUA マッピング (89 エントリ)
/// 多文字音素トークン → Unicode Private Use Area コードポイント
pub static FIXED_PUA_MAP: LazyLock<Vec<(&'static str, u32)>> = LazyLock::new(|| {
    vec![
        // === Japanese (U+E000-E01C) ===
        // Long vowels
        ("a:", 0xE000), ("i:", 0xE001), ("u:", 0xE002), ("e:", 0xE003), ("o:", 0xE004),
        // Special
        ("cl", 0xE005),
        // Palatalized consonants
        ("ky", 0xE006), ("kw", 0xE007), ("gy", 0xE008), ("gw", 0xE009),
        ("ny", 0xE00A), ("by", 0xE00B), ("py", 0xE00C), ("my", 0xE00D),
        // Affricates / Fricatives
        ("ch", 0xE00E), ("ts", 0xE00F), ("sh", 0xE010), ("dy", 0xE011),
        ("ty", 0xE012), ("hy", 0xE013),
        // Other
        ("ry", 0xE014), ("fw", 0xE015),
        // Question markers (Issue #204)
        ("?!", 0xE016), ("?.", 0xE017), ("?~", 0xE018),
        // N variants (Issue #207)
        ("N_m", 0xE019), ("N_n", 0xE01A), ("N_ng", 0xE01B), ("N_uvular", 0xE01C),

        // === Multilingual shared (U+E01D-E01E) ===
        ("rr", 0xE01D),         // Spanish trill
        ("y_vowel", 0xE01E),    // Front rounded vowel (ZH/FR)

        // === Chinese (U+E020-E04A) ===
        // Aspirated consonants
        ("pʰ", 0xE020), ("tʰ", 0xE021), ("kʰ", 0xE022),
        ("tɕ", 0xE023), ("tɕʰ", 0xE024),
        ("tʂ", 0xE025), ("tʂʰ", 0xE026), ("tsʰ", 0xE027),
        // Diphthongs
        ("aɪ", 0xE028), ("eɪ", 0xE029), ("aʊ", 0xE02A), ("oʊ", 0xE02B),
        // Nasal finals
        ("an", 0xE02C), ("ən", 0xE02D), ("aŋ", 0xE02E), ("əŋ", 0xE02F), ("uŋ", 0xE030),
        // Compound finals
        ("ia", 0xE031), ("iɛ", 0xE032), ("iɛn", 0xE033), ("iaŋ", 0xE034), ("iŋ", 0xE035),
        ("ua", 0xE036), ("uo", 0xE037), ("uaɪ", 0xE038), ("ueɪ", 0xE039),
        ("uan", 0xE03A), ("uən", 0xE03B), ("uaŋ", 0xE03C),
        ("yɛ", 0xE03D), ("yan", 0xE03E), ("yn", 0xE03F),
        // Special
        ("iaʊ", 0xE040), ("ioʊ", 0xE041), ("yŋ", 0xE042),
        ("ɥ", 0xE043), ("ɻ", 0xE044),
        ("syl", 0xE045), // Syllabic consonant (zhi/chi/shi/ri)
        // Tone markers
        ("tone1", 0xE046), ("tone2", 0xE047), ("tone3", 0xE048),
        ("tone4", 0xE049), ("tone5", 0xE04A),

        // === Korean (U+E04B-E052) ===
        ("p͈", 0xE04B), ("t͈", 0xE04C), ("k͈", 0xE04D), ("s͈", 0xE04E), ("t͈ɕ", 0xE04F),
        ("k̚", 0xE050), ("t̚", 0xE051), ("p̚", 0xE052),

        // === Spanish/Portuguese (U+E054-E055) ===
        ("tʃ", 0xE054), ("dʒ", 0xE055),

        // === French (U+E056-E058) ===
        ("ɛ̃", 0xE056), ("ɑ̃", 0xE057), ("ɔ̃", 0xE058),
    ]
});

/// トークン→PUA 文字の前方マッピング
pub static TOKEN_TO_PUA: LazyLock<HashMap<&'static str, char>> = LazyLock::new(|| {
    FIXED_PUA_MAP
        .iter()
        .filter_map(|(token, code)| {
            char::from_u32(*code).map(|c| (*token, c))
        })
        .collect()
});

/// PUA 文字→トークンの逆方向マッピング
pub static PUA_TO_TOKEN: LazyLock<HashMap<char, &'static str>> = LazyLock::new(|| {
    FIXED_PUA_MAP
        .iter()
        .filter_map(|(token, code)| {
            char::from_u32(*code).map(|c| (c, *token))
        })
        .collect()
});

/// 多文字トークンを PUA コードポイントに変換
pub fn token_to_pua(token: &str) -> Option<char> {
    TOKEN_TO_PUA.get(token).copied()
}

/// PUA コードポイントをトークン文字列に変換
pub fn pua_to_token(ch: char) -> Option<&'static str> {
    PUA_TO_TOKEN.get(&ch).copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fixed_pua_count() {
        assert_eq!(FIXED_PUA_MAP.len(), 87);
    }

    #[test]
    fn test_japanese_pua() {
        assert_eq!(token_to_pua("a:"), Some('\u{E000}'));
        assert_eq!(token_to_pua("N_m"), Some('\u{E019}'));
        assert_eq!(token_to_pua("?!"), Some('\u{E016}'));
    }

    #[test]
    fn test_chinese_pua() {
        assert_eq!(token_to_pua("tone1"), Some('\u{E046}'));
        assert_eq!(token_to_pua("tɕ"), Some('\u{E023}'));
    }

    #[test]
    fn test_reverse_mapping() {
        assert_eq!(pua_to_token('\u{E000}'), Some("a:"));
        assert_eq!(pua_to_token('\u{E056}'), Some("ɛ̃"));
    }

    #[test]
    fn test_no_collisions() {
        let mut seen_codes: std::collections::HashSet<u32> = std::collections::HashSet::new();
        for (_, code) in FIXED_PUA_MAP.iter() {
            assert!(seen_codes.insert(*code), "duplicate PUA code: 0x{:04X}", code);
        }
    }
}

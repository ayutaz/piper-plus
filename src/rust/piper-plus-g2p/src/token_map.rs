//! PUA (Private Use Area) マッピング.
//!
//! Python (token_mapper.py) および C++ (各 *_phonemize.cpp) と同一のテーブル。
//! 学習済みモデルの重みに依存するため変更不可。

use std::collections::HashMap;
use std::sync::LazyLock;

/// PUA compatibility version. Increment when new PUA mappings are added.
pub const PUA_COMPAT_VERSION: u32 = 2;

/// Check if a model's PUA version is compatible.
pub fn check_pua_compat(model_version: Option<u32>) -> Result<(), String> {
    match model_version {
        None => Ok(()),
        Some(v) if v == PUA_COMPAT_VERSION => Ok(()),
        Some(v) => Err(format!(
            "PUA version mismatch: model has pua_compat_version={v}, \
             but piper-g2p expects version {PUA_COMPAT_VERSION}"
        )),
    }
}

/// 固定 PUA マッピング (99 エントリ)
/// 多文字音素トークン → Unicode Private Use Area コードポイント
pub static FIXED_PUA_MAP: LazyLock<Vec<(&'static str, u32)>> = LazyLock::new(|| {
    vec![
        // === Japanese (U+E000-E01C) ===
        // Long vowels
        ("a:", 0xE000),
        ("i:", 0xE001),
        ("u:", 0xE002),
        ("e:", 0xE003),
        ("o:", 0xE004),
        // Special consonants
        ("cl", 0xE005),
        // Palatalized consonants
        ("ky", 0xE006),
        ("kw", 0xE007),
        ("gy", 0xE008),
        ("gw", 0xE009),
        ("ty", 0xE00A),
        ("dy", 0xE00B),
        ("py", 0xE00C),
        ("by", 0xE00D),
        // Affricates and special sounds
        ("ch", 0xE00E),
        ("ts", 0xE00F),
        ("sh", 0xE010),
        ("zy", 0xE011),
        ("hy", 0xE012),
        // Palatalized nasals/liquids
        ("ny", 0xE013),
        ("my", 0xE014),
        ("ry", 0xE015),
        // Question type markers (Issue #204)
        ("?!", 0xE016),
        ("?.", 0xE017),
        ("?~", 0xE018),
        // N phoneme variants (Issue #207)
        ("N_m", 0xE019),
        ("N_n", 0xE01A),
        ("N_ng", 0xE01B),
        ("N_uvular", 0xE01C),
        // === Multilingual shared (U+E01D-E01E) ===
        ("rr", 0xE01D),      // Spanish trill r
        ("y_vowel", 0xE01E), // Close front rounded vowel [y] (ZH pinyin ü, FR lune)
        // 0xE01F reserved (unused gap)

        // === Chinese (U+E020-E04A) ===
        // --- Initials (aspirated/affricate) ---
        ("p\u{02b0}", 0xE020),         // pʰ  aspirated bilabial (pinyin p)
        ("t\u{02b0}", 0xE021),         // tʰ  aspirated alveolar (pinyin t)
        ("k\u{02b0}", 0xE022),         // kʰ  aspirated velar (pinyin k)
        ("t\u{0255}", 0xE023),         // tɕ  alveolo-palatal affricate (pinyin j)
        ("t\u{0255}\u{02b0}", 0xE024), // tɕʰ  aspirated alveolo-palatal (pinyin q)
        ("t\u{0282}", 0xE025),         // tʂ  retroflex affricate (pinyin zh)
        ("t\u{0282}\u{02b0}", 0xE026), // tʂʰ  aspirated retroflex (pinyin ch)
        ("ts\u{02b0}", 0xE027),        // tsʰ  aspirated alveolar affricate (pinyin c)
        // --- Diphthongs ---
        ("a\u{026a}", 0xE028), // aɪ  (pinyin ai)
        ("e\u{026a}", 0xE029), // eɪ  (pinyin ei)
        ("a\u{028a}", 0xE02A), // aʊ  (pinyin ao)
        ("o\u{028a}", 0xE02B), // oʊ  (pinyin ou)
        // --- Nasal finals ---
        ("an", 0xE02C),               // an  (pinyin an)
        ("\u{0259}n", 0xE02D),        // ən  (pinyin en)
        ("a\u{014b}", 0xE02E),        // aŋ  (pinyin ang)
        ("\u{0259}\u{014b}", 0xE02F), // əŋ  (pinyin eng)
        ("u\u{014b}", 0xE030),        // uŋ  (pinyin ong)
        // --- i-compound finals (齐齿呼) ---
        ("ia", 0xE031),         // ia  (pinyin ia/ya)
        ("i\u{025b}", 0xE032),  // iɛ  (pinyin ie/ye)
        ("iou", 0xE033),        // iou (pinyin iu/you)
        ("ia\u{028a}", 0xE034), // iaʊ (pinyin iao/yao)
        ("i\u{025b}n", 0xE035), // iɛn (pinyin ian/yan)
        ("in", 0xE036),         // in  (pinyin in/yin)
        ("ia\u{014b}", 0xE037), // iaŋ (pinyin iang/yang)
        ("i\u{014b}", 0xE038),  // iŋ  (pinyin ing/ying)
        ("iu\u{014b}", 0xE039), // iuŋ (pinyin iong/yong)
        // --- u-compound finals (合口呼) ---
        ("ua", 0xE03A),                // ua  (pinyin ua/wa)
        ("uo", 0xE03B),                // uo  (pinyin uo/wo)
        ("ua\u{026a}", 0xE03C),        // uaɪ (pinyin uai/wai)
        ("ue\u{026a}", 0xE03D),        // ueɪ (pinyin ui/wei)
        ("uan", 0xE03E),               // uan (pinyin uan/wan)
        ("u\u{0259}n", 0xE03F),        // uən (pinyin un/wen)
        ("ua\u{014b}", 0xE040),        // uaŋ (pinyin uang/wang)
        ("u\u{0259}\u{014b}", 0xE041), // uəŋ (pinyin ueng/weng)
        // --- ü-compound finals (撮口呼) ---
        ("y\u{025b}", 0xE042),  // yɛ  (pinyin üe/yue)
        ("y\u{025b}n", 0xE043), // yɛn (pinyin üan/yuan)
        ("yn", 0xE044),         // yn  (pinyin ün/yun)
        // --- Syllabic consonants ---
        ("\u{027b}\u{0329}", 0xE045), // ɻ̩  syllabic retroflex (zhi/chi/shi/ri)
        // --- Tone markers ---
        ("tone1", 0xE046),
        ("tone2", 0xE047),
        ("tone3", 0xE048),
        ("tone4", 0xE049),
        ("tone5", 0xE04A),
        // === Korean (U+E04B-E052) ===
        // --- Tense consonants (fortis / 경음) ---
        ("p\u{0348}", 0xE04B),         // p͈  tense bilabial (ㅃ)
        ("t\u{0348}", 0xE04C),         // t͈  tense alveolar (ㄸ)
        ("k\u{0348}", 0xE04D),         // k͈  tense velar (ㄲ)
        ("s\u{0348}", 0xE04E),         // s͈  tense sibilant (ㅆ)
        ("t\u{0348}\u{0255}", 0xE04F), // t͈ɕ  tense alveolo-palatal affricate (ㅉ)
        // --- Unreleased finals (내파음) ---
        ("k\u{031a}", 0xE050), // k̚  unreleased velar
        ("t\u{031a}", 0xE051), // t̚  unreleased alveolar
        ("p\u{031a}", 0xE052), // p̚  unreleased bilabial
        // 0xE053 reserved (unused gap)

        // === Spanish/Portuguese (U+E054-E055) ===
        ("t\u{0283}", 0xE054), // tʃ  voiceless postalveolar affricate
        ("d\u{0292}", 0xE055), // dʒ  voiced postalveolar affricate
        // === French (U+E056-E058) ===
        // --- Nasal vowels ---
        ("\u{025b}\u{0303}", 0xE056), // ɛ̃  nasal open-mid front unrounded
        ("\u{0251}\u{0303}", 0xE057), // ɑ̃  nasal open back unrounded
        ("\u{0254}\u{0303}", 0xE058), // ɔ̃  nasal open-mid back rounded
        // === Swedish (U+E059-E061) ===
        // --- Long vowels (Complementary Quantity) ---
        ("i\u{02D0}", 0xE059),        // iː  close front unrounded long
        ("y\u{02D0}", 0xE05A),        // yː  close front rounded long
        ("e\u{02D0}", 0xE05B),        // eː  close-mid front unrounded long
        ("\u{025B}\u{02D0}", 0xE05C), // ɛː  open-mid front unrounded long
        ("\u{00F8}\u{02D0}", 0xE05D), // øː  close-mid front rounded long
        ("\u{0251}\u{02D0}", 0xE05E), // ɑː  open back unrounded long
        ("o\u{02D0}", 0xE05F),        // oː  close-mid back rounded long
        ("u\u{02D0}", 0xE060),        // uː  close back rounded long
        ("\u{0289}\u{02D0}", 0xE061), // ʉː  close central rounded long
        // === Additional multi-codepoint diphthongs / nasal vowels (PUA v2) ===
        ("\u{0254}\u{026A}", 0xE062), // ɔɪ  English diphthong (OY)
        ("\u{0153}\u{0303}", 0xE063), // œ̃   French nasal open-mid front rounded vowel
        ("\u{0250}\u{0303}", 0xE064), // ɐ̃   Portuguese nasal near-open central vowel
    ]
});

/// トークン→PUA 文字の前方マッピング
pub static TOKEN_TO_PUA: LazyLock<HashMap<&'static str, char>> = LazyLock::new(|| {
    FIXED_PUA_MAP
        .iter()
        .filter_map(|(token, code)| char::from_u32(*code).map(|c| (*token, c)))
        .collect()
});

/// PUA 文字→トークンの逆方向マッピング
pub static PUA_TO_TOKEN: LazyLock<HashMap<char, &'static str>> = LazyLock::new(|| {
    FIXED_PUA_MAP
        .iter()
        .filter_map(|(token, code)| char::from_u32(*code).map(|c| (c, *token)))
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
        // Must match Python token_mapper.py FIXED_PUA_MAPPING count exactly
        assert_eq!(FIXED_PUA_MAP.len(), 99);
    }

    #[test]
    fn test_japanese_palatalized_order() {
        // Verify E00A-E015 match Python canonical order exactly
        assert_eq!(token_to_pua("ty"), Some('\u{E00A}'));
        assert_eq!(token_to_pua("dy"), Some('\u{E00B}'));
        assert_eq!(token_to_pua("py"), Some('\u{E00C}'));
        assert_eq!(token_to_pua("by"), Some('\u{E00D}'));
        assert_eq!(token_to_pua("zy"), Some('\u{E011}'));
        assert_eq!(token_to_pua("hy"), Some('\u{E012}'));
        assert_eq!(token_to_pua("ny"), Some('\u{E013}'));
        assert_eq!(token_to_pua("my"), Some('\u{E014}'));
        assert_eq!(token_to_pua("ry"), Some('\u{E015}'));
        // "fw" must NOT exist in the mapping
        assert_eq!(token_to_pua("fw"), None);
    }

    #[test]
    fn test_chinese_compound_finals() {
        // i-compound finals
        assert_eq!(token_to_pua("iou"), Some('\u{E033}'));
        assert_eq!(token_to_pua("in"), Some('\u{E036}'));
        // u-compound finals
        assert_eq!(token_to_pua("uan"), Some('\u{E03E}'));
        // ü-compound finals
        assert_eq!(token_to_pua("yn"), Some('\u{E044}'));
        // Syllabic consonant: ɻ̩ (U+027B + U+0329)
        assert_eq!(token_to_pua("\u{027b}\u{0329}"), Some('\u{E045}'));
        // "syl", "ɥ", "ɻ" (single), "ioʊ", "yŋ", "yan" must NOT exist
        assert_eq!(token_to_pua("syl"), None);
        assert_eq!(token_to_pua("\u{0265}"), None); // ɥ
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
            assert!(
                seen_codes.insert(*code),
                "duplicate PUA code: 0x{:04X}",
                code
            );
        }
    }
}

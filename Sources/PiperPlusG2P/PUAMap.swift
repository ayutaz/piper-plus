// PUAMap.swift — Private Use Area codepoint mapping.
//
// Mirrors `src/rust/piper-plus-g2p/src/token_map.rs::FIXED_PUA_MAP` exactly
// (99 entries). The Rust phonemizer encodes every multi-character token as
// a single PUA codepoint before returning it through the FFI, so callers
// (including Swift tests using the cross-runtime fixture) need this map to
// translate human-readable token names like "rr" or "cl" back to the PUA
// chars they will actually see in `PhonemizeResult.tokens`.
//
// IMPORTANT: do not edit the codepoint assignments without updating every
// other runtime — they are baked into trained model weights.

import Foundation

public enum PUAMap {
    /// Compatibility version (matches Rust `PUA_COMPAT_VERSION`).
    public static let compatVersion: UInt32 = 2

    /// All 99 (token, codepoint) pairs in canonical order.
    public static let fixedMap: [(String, UInt32)] = [
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
        ("rr", 0xE01D),       // Spanish trill r
        ("y_vowel", 0xE01E),  // Close front rounded vowel [y]
        // 0xE01F reserved (unused gap)

        // === Chinese (U+E020-E04A) ===
        // --- Initials (aspirated/affricate) ---
        ("p\u{02B0}", 0xE020),
        ("t\u{02B0}", 0xE021),
        ("k\u{02B0}", 0xE022),
        ("t\u{0255}", 0xE023),
        ("t\u{0255}\u{02B0}", 0xE024),
        ("t\u{0282}", 0xE025),
        ("t\u{0282}\u{02B0}", 0xE026),
        ("ts\u{02B0}", 0xE027),
        // --- Diphthongs ---
        ("a\u{026A}", 0xE028),
        ("e\u{026A}", 0xE029),
        ("a\u{028A}", 0xE02A),
        ("o\u{028A}", 0xE02B),
        // --- Nasal finals ---
        ("an", 0xE02C),
        ("\u{0259}n", 0xE02D),
        ("a\u{014B}", 0xE02E),
        ("\u{0259}\u{014B}", 0xE02F),
        ("u\u{014B}", 0xE030),
        // --- i-compound finals ---
        ("ia", 0xE031),
        ("i\u{025B}", 0xE032),
        ("iou", 0xE033),
        ("ia\u{028A}", 0xE034),
        ("i\u{025B}n", 0xE035),
        ("in", 0xE036),
        ("ia\u{014B}", 0xE037),
        ("i\u{014B}", 0xE038),
        ("iu\u{014B}", 0xE039),
        // --- u-compound finals ---
        ("ua", 0xE03A),
        ("uo", 0xE03B),
        ("ua\u{026A}", 0xE03C),
        ("ue\u{026A}", 0xE03D),
        ("uan", 0xE03E),
        ("u\u{0259}n", 0xE03F),
        ("ua\u{014B}", 0xE040),
        ("u\u{0259}\u{014B}", 0xE041),
        // --- ü-compound finals ---
        ("y\u{025B}", 0xE042),
        ("y\u{025B}n", 0xE043),
        ("yn", 0xE044),
        // --- Syllabic consonants ---
        ("\u{027B}\u{0329}", 0xE045),
        // --- Tone markers ---
        ("tone1", 0xE046),
        ("tone2", 0xE047),
        ("tone3", 0xE048),
        ("tone4", 0xE049),
        ("tone5", 0xE04A),
        // === Korean (U+E04B-E052) ===
        // --- Tense consonants ---
        ("p\u{0348}", 0xE04B),
        ("t\u{0348}", 0xE04C),
        ("k\u{0348}", 0xE04D),
        ("s\u{0348}", 0xE04E),
        ("t\u{0348}\u{0255}", 0xE04F),
        // --- Unreleased finals ---
        ("k\u{031A}", 0xE050),
        ("t\u{031A}", 0xE051),
        ("p\u{031A}", 0xE052),
        // 0xE053 reserved (unused gap)

        // === Spanish/Portuguese (U+E054-E055) ===
        ("t\u{0283}", 0xE054),
        ("d\u{0292}", 0xE055),
        // === French (U+E056-E058) ===
        ("\u{025B}\u{0303}", 0xE056),
        ("\u{0251}\u{0303}", 0xE057),
        ("\u{0254}\u{0303}", 0xE058),
        // === Swedish (U+E059-E061) ===
        ("i\u{02D0}", 0xE059),
        ("y\u{02D0}", 0xE05A),
        ("e\u{02D0}", 0xE05B),
        ("\u{025B}\u{02D0}", 0xE05C),
        ("\u{00F8}\u{02D0}", 0xE05D),
        ("\u{0251}\u{02D0}", 0xE05E),
        ("o\u{02D0}", 0xE05F),
        ("u\u{02D0}", 0xE060),
        ("\u{0289}\u{02D0}", 0xE061),
        // === Additional multi-codepoint diphthongs / nasal vowels (PUA v2) ===
        ("\u{0254}\u{026A}", 0xE062),
        ("\u{0153}\u{0303}", 0xE063),
        ("\u{0250}\u{0303}", 0xE064),
    ]

    private static let tokenToPuaTable: [String: Character] = {
        var d: [String: Character] = [:]
        d.reserveCapacity(fixedMap.count)
        for (token, code) in fixedMap {
            if let scalar = Unicode.Scalar(code) {
                d[token] = Character(scalar)
            }
        }
        return d
    }()

    private static let puaToTokenTable: [Character: String] = {
        var d: [Character: String] = [:]
        d.reserveCapacity(fixedMap.count)
        for (token, code) in fixedMap {
            if let scalar = Unicode.Scalar(code) {
                d[Character(scalar)] = token
            }
        }
        return d
    }()

    /// Map a multi-character token name (e.g. "rr", "cl") to its PUA codepoint.
    /// Returns nil if the token has no PUA encoding.
    public static func tokenToPua(_ token: String) -> Character? {
        tokenToPuaTable[token]
    }

    /// Map a PUA codepoint back to its token name. Returns nil for non-PUA chars.
    public static func puaToToken(_ ch: Character) -> String? {
        puaToTokenTable[ch]
    }
}

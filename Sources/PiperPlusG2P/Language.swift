// Language.swift — supported G2P languages.
//
// The raw values match the language codes used by the underlying Rust
// piper-plus-g2p crate (and its C FFI). Adding a new case here only
// matters if the Rust side gains a new language; otherwise the new code
// would never be registered by piper_plus_g2p_create.

import Foundation

public enum Language: String, CaseIterable, Sendable {
    case japanese = "ja"
    case english = "en"
    case chinese = "zh"
    case korean = "ko"
    case spanish = "es"
    case french = "fr"
    case portuguese = "pt"
    case swedish = "sv"
}

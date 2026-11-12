// TextSanitizer.swift — the input-sanitize rule every piper-plus runtime
// shares (docs/spec/input-sanitize-contract.toml).
//
// The Rust G2P under this wrapper strips too, but it cannot see a NUL:
// `Phonemizer.phonemize` passes the text as a C string, which ends at the
// first NUL. `phonemize` therefore strips before the FFI call.

public enum TextSanitizer {
    /// Return `text` cleaned by the input-sanitize rule: newline, tab and
    /// carriage return stay (sentence splitting and SSML use them); VT, FF
    /// and NEL (U+000B, U+000C, U+0085) become a space; every other control
    /// character (Unicode category Cc: U+0000-001F, U+007F-009F) is removed.
    /// Format characters, separators and NBSP stay. Idempotent.
    public static func stripControlChars(_ text: String) -> String {
        var out = String.UnicodeScalarView()
        for scalar in text.unicodeScalars {
            switch scalar.value {
            case 0x09, 0x0A, 0x0D:
                out.append(scalar)
            case 0x0B, 0x0C, 0x85:
                out.append(" ")
            case 0x00 ... 0x1F, 0x7F ... 0x9F:
                continue
            default:
                out.append(scalar)
            }
        }
        return String(out)
    }
}

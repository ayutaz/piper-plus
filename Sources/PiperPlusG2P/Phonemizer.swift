// Phonemizer.swift — idiomatic Swift wrapper around the C FFI in piper_plus_g2p.h.
//
// The C API exposes a handle (`PiperG2pHandle`) that owns a registry of
// language phonemizers. `init(languages:)` creates the handle and registers
// each requested language; `phonemize(_:language:)` runs G2P and returns
// the parsed JSON envelope. The handle is freed automatically in `deinit`.

@_exported import PiperPlusG2PBinary
import Foundation

public final class Phonemizer: @unchecked Sendable {
    private let handle: OpaquePointer
    private let decoder: JSONDecoder

    /// Create a phonemizer with the given languages registered.
    ///
    /// - Parameter languages: languages to register. Defaults to all
    ///   supported languages. Note: registering more languages costs
    ///   initialization time and memory (NAIST-JDIC for Japanese is
    ///   ~25 MB; CMU dictionary for English is ~3.7 MB).
    /// - Throws: ``G2PError/initializationFailed`` if the underlying
    ///   `piper_plus_g2p_create` returns NULL.
    public init(languages: [Language] = Language.allCases) throws {
        let csv = languages.map(\.rawValue).joined(separator: ",")
        // `piper_plus_g2p_create` returns `struct PiperG2pHandle *`. cbindgen
        // emits it as an opaque forward-declared struct, which the Swift
        // clang importer bridges directly to `OpaquePointer?` — no extra
        // wrapping is needed (and wrapping it would not type-check, since
        // OpaquePointer's initializers expect raw pointers).
        let raw: OpaquePointer? = csv.withCString { ptr in
            piper_plus_g2p_create(ptr)
        }
        guard let raw else {
            throw G2PError.initializationFailed(requestedLanguages: languages)
        }
        self.handle = raw
        self.decoder = JSONDecoder()
    }

    deinit {
        piper_plus_g2p_free(handle)
    }

    /// Phonemize `text` using the phonemizer registered for `language`.
    ///
    /// - Returns: tokens (IPA + occasional PUA codepoints for language-
    ///   specific phonemes) plus the language code echo.
    /// - Throws: ``G2PError`` on null result, invalid UTF-8, or JSON
    ///   decode failure.
    public func phonemize(_ text: String, language: Language) throws -> PhonemizeResult {
        let raw: UnsafeMutablePointer<CChar>? = text.withCString { textPtr in
            language.rawValue.withCString { langPtr in
                piper_plus_g2p_phonemize(handle, textPtr, langPtr)
            }
        }
        guard let raw else {
            throw G2PError.phonemizeReturnedNull(language: language)
        }
        defer { piper_plus_g2p_free_string(raw) }

        guard let data = String(cString: raw).data(using: .utf8) else {
            throw G2PError.invalidUTF8
        }
        do {
            return try decoder.decode(PhonemizeResult.self, from: data)
        } catch {
            throw G2PError.decodeFailed(String(describing: error))
        }
    }

    /// Languages successfully registered by `init`. May be a strict subset
    /// of the requested set if a language failed to register internally.
    public var availableLanguages: [Language] {
        guard let raw = piper_plus_g2p_available_languages(handle) else {
            return []
        }
        defer { piper_plus_g2p_free_string(raw) }
        return String(cString: raw)
            .split(separator: ",")
            .compactMap { Language(rawValue: String($0).trimmingCharacters(in: .whitespaces)) }
    }
}

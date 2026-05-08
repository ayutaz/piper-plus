// G2PError.swift — errors thrown by the Swift wrapper.
//
// Each case carries the diagnostic information needed to triage failures
// without re-running with extra logging. `initializationFailed` includes
// the requested language set so a caller can immediately see which
// languages SwiftPM was asked to register; `phonemizeReturnedNull`
// includes the language under which the call was issued so multi-language
// callers can distinguish "Japanese not registered" from "English input
// rejected" without correlating against the original call site.

import Foundation

public enum G2PError: Error, Sendable, Equatable {
    /// `piper_plus_g2p_create` returned NULL.
    /// `requestedLanguages` is the language list passed to `Phonemizer.init`,
    /// preserved so the caller can log / surface the failed configuration.
    case initializationFailed(requestedLanguages: [Language])

    /// `piper_plus_g2p_phonemize` returned NULL.
    /// `language` is the language under which the call was issued — typically
    /// indicates the language was not registered at init, or the input could
    /// not be parsed by that phonemizer.
    case phonemizeReturnedNull(language: Language)

    /// FFI returned a byte sequence that is not valid UTF-8. Should not
    /// happen in practice; indicates a corrupted FFI boundary.
    case invalidUTF8

    /// JSON envelope returned by the FFI failed to decode into
    /// `PhonemizeResult`. The associated value is a description of the
    /// underlying decoding error.
    case decodeFailed(String)
}

extension G2PError: CustomStringConvertible {
    public var description: String {
        switch self {
        case .initializationFailed(let languages):
            let codes = languages.map(\.rawValue).joined(separator: ",")
            return "piper_plus_g2p_create returned NULL — could not register requested languages: [\(codes)]."
        case .phonemizeReturnedNull(let language):
            return "piper_plus_g2p_phonemize returned NULL for language=\(language.rawValue) — language was not registered, or input could not be phonemized."
        case .invalidUTF8:
            return "Result was not valid UTF-8."
        case .decodeFailed(let detail):
            return "Failed to decode result JSON: \(detail)"
        }
    }
}

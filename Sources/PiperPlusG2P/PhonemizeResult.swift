// PhonemizeResult.swift — JSON envelope returned by piper_plus_g2p_phonemize.

import Foundation

public struct PhonemizeResult: Codable, Sendable, Equatable {
    public let tokens: [String]
    public let language: String

    public init(tokens: [String], language: String) {
        self.tokens = tokens
        self.language = language
    }
}

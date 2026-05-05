// G2PError.swift — errors thrown by the Swift wrapper.

import Foundation

public enum G2PError: Error, Sendable, Equatable {
    case initializationFailed
    case phonemizeReturnedNull
    case invalidUTF8
    case decodeFailed(String)
}

extension G2PError: CustomStringConvertible {
    public var description: String {
        switch self {
        case .initializationFailed:
            return "piper_plus_g2p_create returned NULL — the requested languages could not be registered."
        case .phonemizeReturnedNull:
            return "piper_plus_g2p_phonemize returned NULL — the language was not registered or input is invalid."
        case .invalidUTF8:
            return "Result was not valid UTF-8."
        case .decodeFailed(let detail):
            return "Failed to decode result JSON: \(detail)"
        }
    }
}

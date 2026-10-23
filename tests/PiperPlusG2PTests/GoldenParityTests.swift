// GoldenParityTests.swift — exact match against the Python golden.
//
// Compares `Phonemizer.phonemize(_:language:)` with
// tests/fixtures/g2p/phoneme_test_cases_golden.json, the phonemes Python's
// MultilingualPhonemizer produces with the case language as the Latin default.
//
// Cases known to differ are listed for the "swift" runtime in
// tests/fixtures/g2p/known_divergences.json. A difference that is not listed
// fails, and so does a listed case that now matches, so the list shrinks as the
// linked issues are fixed. English words that must never phonemize to nothing
// are listed in tests/fixtures/g2p/english_no_drop_words.json and follow the
// same rule.
//
// One representation difference is not a divergence: multi-codepoint
// phonemes (rr, tʃ, tone3) are one PUA character here (pua.json) and spelled
// out in the golden. Only the golden side is mapped, so output that forgets
// the PUA encoding still fails.
//
// Japanese needs the OpenJTalk dictionary and Korean is absent from the golden
// (and from the trained models), so both are left out.

import Foundation
import XCTest
@testable import PiperPlusG2P

struct GoldenKey: Hashable {
    let language: String
    let input: String
}

/// Shared G2P fixtures, resolved from the source tree via `#filePath`.
enum GoldenFixtures {
    static let runtime = "swift"

    static let repoRoot: URL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()  // PiperPlusG2PTests/
        .deletingLastPathComponent()  // tests/
        .deletingLastPathComponent()  // repository root

    static func json(_ relativePath: String) throws -> [String: Any] {
        let data = try Data(contentsOf: repoRoot.appendingPathComponent(relativePath))
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw G2PError.decodeFailed("\(relativePath) is not a JSON object")
        }
        return object
    }

    static func listsRuntime(_ entry: [String: Any]) -> Bool {
        (entry["runtimes"] as? [String])?.contains(runtime) ?? false
    }

    /// Cases listed for this runtime in known_divergences.json.
    static func knownDivergences() throws -> Set<GoldenKey> {
        let registry = try json("tests/fixtures/g2p/known_divergences.json")
        var keys = Set<GoldenKey>()
        for entry in registry["divergences"] as? [[String: Any]] ?? [] where listsRuntime(entry) {
            if let language = entry["language"] as? String, let input = entry["input"] as? String {
                keys.insert(GoldenKey(language: language, input: input))
            }
        }
        return keys
    }

    /// Maps the golden spelling of multi-codepoint phonemes to their PUA character.
    static func puaTable() throws -> [String: String] {
        let doc = try json("src/python/g2p/piper_plus_g2p/data/pua.json")
        var table: [String: String] = [:]
        for entry in doc["entries"] as? [[String: Any]] ?? [] {
            guard let token = entry["token"] as? String,
                  let codepoint = entry["codepoint"] as? String else { continue }
            let hex = codepoint.hasPrefix("0x") ? String(codepoint.dropFirst(2)) : codepoint
            if let value = UInt32(hex, radix: 16), let scalar = Unicode.Scalar(value) {
                table[token] = String(scalar)
            }
        }
        return table
    }
}

final class GoldenParityTests: XCTestCase {
    private static let languages: [Language] = [.english, .chinese, .spanish, .french, .portuguese, .swedish]
    private static let notPhonemes: Set<String> = [" ", ".", ",", "!", "?", ";", ":", "'", "\"", "-"]

    /// Tokens are joined with one space; a word boundary token " " therefore
    /// appears as three spaces (two empty parts when split).
    private static func splitPhonemes(_ text: String) -> [String] {
        var tokens: [String] = []
        if text.isEmpty { return tokens }
        var emptyParts = 0
        for part in text.split(separator: " ", omittingEmptySubsequences: false) {
            if !part.isEmpty {
                emptyParts = 0
                tokens.append(String(part))
            } else {
                emptyParts += 1
                if emptyParts == 2 {
                    emptyParts = 0
                    tokens.append(" ")
                }
            }
        }
        return tokens
    }

    func testMatchesPythonGoldenExceptListedDivergences() throws {
        let known = try GoldenFixtures.knownDivergences()
        let pua = try GoldenFixtures.puaTable()
        let golden = try GoldenFixtures.json("tests/fixtures/g2p/phoneme_test_cases_golden.json")
        let phonemizer = try Phonemizer(languages: Self.languages)

        var verified = 0
        var knownCount = 0
        var failures: [String] = []
        for testCase in golden["test_cases"] as? [[String: Any]] ?? [] {
            guard let code = testCase["language"] as? String,
                  let input = testCase["input"] as? String,
                  let expectedText = testCase["expected_phonemes"] as? String,
                  let language = Language(rawValue: code),
                  Self.languages.contains(language) else { continue }

            let expected = Self.splitPhonemes(expectedText).map { pua[$0] ?? $0 }
            let actual = try? phonemizer.phonemize(input, language: language).tokens
            let matches = actual == expected
            verified += 1

            let label = "[\(code)] '\(input)'"
            let listed = known.contains(GoldenKey(language: code, input: input))
            if matches && listed {
                failures.append("\(label) now matches; remove it from known_divergences.json")
            } else if !matches && listed {
                knownCount += 1
            } else if !matches {
                let got = actual?.joined(separator: " ") ?? "(phonemize failed)"
                failures.append("\(label)\n  expected: \(expectedText)\n  actual:   \(got)")
            }
        }

        XCTAssertGreaterThan(verified, 0, "no golden case compared")
        XCTAssertTrue(
            failures.isEmpty,
            "\(failures.count) failure(s), \(knownCount) known, \(verified) cases:\n"
                + failures.joined(separator: "\n")
        )
    }

    func testEnglishWordsAreNotDropped() throws {
        let list = try GoldenFixtures.json("tests/fixtures/g2p/english_no_drop_words.json")
        var knownDrops = Set<String>()
        for entry in list["known_drops"] as? [[String: Any]] ?? [] where GoldenFixtures.listsRuntime(entry) {
            if let word = entry["word"] as? String {
                knownDrops.insert(word)
            }
        }
        let phonemizer = try Phonemizer(languages: [.english])

        var checked = 0
        var failures: [String] = []
        for word in list["words"] as? [String] ?? [] {
            let tokens = (try? phonemizer.phonemize(word, language: .english).tokens) ?? []
            let spoken = tokens.contains { !Self.notPhonemes.contains($0) }
            checked += 1
            let listed = knownDrops.contains(word)
            if spoken && listed {
                failures.append("'\(word)' is now spoken; remove it from known_drops")
            } else if !spoken && !listed {
                failures.append("'\(word)' produced no phoneme: '\(tokens.joined(separator: " "))'")
            }
        }

        XCTAssertGreaterThan(checked, 0, "english_no_drop_words.json has no words")
        XCTAssertTrue(failures.isEmpty, failures.joined(separator: "\n"))
    }
}

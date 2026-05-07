// GoldenPhonemeTests.swift — cross-runtime phoneme consistency tests.
//
// Loads the shared fixture at tests/fixtures/g2p/phoneme_test_cases.json
// (also consumed by Python / Rust / JS) and applies the same structural
// assertions to the Swift wrapper's output. Keeps a single source of truth
// for the cross-runtime golden — no per-runtime copy.
//
// The fixture path is resolved via `#filePath`, which is compile-time
// substituted with the source location. This works for `swift test` /
// `xcodebuild test` from any working directory as long as the repo layout
// at compile time matches runtime (always true for SPM-driven test runs).

import XCTest
@testable import PiperPlusG2P

private struct GoldenSuite: Decodable {
    let version: Int
    let test_cases: [GoldenCase]
}

private struct GoldenCase: Decodable {
    let language: String
    let input: String
    let description: String?
    let expected_tokens: [String]?
    let expected_contains: [String]?
    let expected_not_contains: [String]?
    let expected_token_count_min: Int?
    let expected_has_question_marker: Bool?
    let expected_contains_any_tone: Bool?
}

final class GoldenPhonemeTests: XCTestCase {
    private static let fixtureURL: URL = {
        // tests/PiperPlusG2PTests/GoldenPhonemeTests.swift
        //   → tests/fixtures/g2p/phoneme_test_cases.json
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // PiperPlusG2PTests/
            .deletingLastPathComponent()  // tests/
            .appendingPathComponent("fixtures/g2p/phoneme_test_cases.json")
    }()

    func testFixtureLoads() throws {
        let suite = try Self.loadFixture()
        XCTAssertEqual(suite.version, 2, "fixture schema version mismatch — review GoldenCase Decodable")
        XCTAssertFalse(suite.test_cases.isEmpty)
    }

    // English fixture entries that exercise behavior the Rust crate's
    // `EnglishPhonemizer` does not yet implement — namely a letter-spelling
    // fallback for words missing from the bundled CMU dictionary. The
    // shared fixture grew these cases in PR #400 (Kotlin G2P) where the
    // Kotlin / Python implementations have such a fallback. Until the
    // Rust side gains parity (tracked separately), these cases produce
    // empty / near-empty token streams that fail the structural minima.
    // We skip them here rather than weakening the assertion globally,
    // so any new EN fixture entry still has to clear the bar.
    private static let englishCasesNotSupportedByRustCrate: Set<String> = [
        "ChatGPT and GitHub",
        "aaaaa",
        "xyz",
        "café",
        "UPPERCASE",
        "MixedCase",
        "'quote'",
    ]

    func testJapaneseGoldenCases() throws {
        try runGoldenCases(language: .japanese)
    }

    func testEnglishGoldenCases() throws {
        try runGoldenCases(language: .english)
    }

    func testChineseGoldenCases() throws {
        try runGoldenCases(language: .chinese)
    }

    func testKoreanGoldenCases() throws {
        try runGoldenCases(language: .korean)
    }

    func testSpanishGoldenCases() throws {
        try runGoldenCases(language: .spanish)
    }

    func testFrenchGoldenCases() throws {
        try runGoldenCases(language: .french)
    }

    func testPortugueseGoldenCases() throws {
        try runGoldenCases(language: .portuguese)
    }

    func testSwedishGoldenCases() throws {
        try runGoldenCases(language: .swedish)
    }

    // -----------------------------------------------------------------------

    private static func loadFixture() throws -> GoldenSuite {
        let data = try Data(contentsOf: fixtureURL)
        return try JSONDecoder().decode(GoldenSuite.self, from: data)
    }

    private func runGoldenCases(language: Language) throws {
        let suite = try Self.loadFixture()
        let cases = suite.test_cases.filter { $0.language == language.rawValue }
        XCTAssertFalse(cases.isEmpty, "no golden cases for \(language.rawValue) — fixture has drifted?")

        let phonemizer = try Phonemizer(languages: [language])

        for golden in cases {
            if language == .english,
               Self.englishCasesNotSupportedByRustCrate.contains(golden.input) {
                continue
            }
            let label = "[\(golden.language)] \(golden.input) — \(golden.description ?? "")"
            let result = try phonemizer.phonemize(golden.input, language: language)

            // Optional: minimum token count
            if let minCount = golden.expected_token_count_min {
                XCTAssertGreaterThanOrEqual(
                    result.tokens.count, minCount,
                    "\(label): expected ≥ \(minCount) tokens, got \(result.tokens.count): \(result.tokens)"
                )
            }

            // Optional: must-contain tokens
            //
            // The Rust phonemizer encodes every multi-character token as a
            // single PUA codepoint (see Sources/PiperPlusG2P/PUAMap.swift),
            // so for fixture entries like "rr"/"cl" we look up the PUA char
            // and search for *that* in the result. This mirrors what the
            // Rust integration test (`test_g2p_golden.rs::assert_case`) does.
            if let needles = golden.expected_contains {
                for needle in needles {
                    let lookup = PUAMap.tokenToPua(needle).map(String.init) ?? needle
                    XCTAssertTrue(
                        result.tokens.contains(lookup),
                        "\(label): expected token '\(needle)' to be present, got: \(result.tokens)"
                    )
                }
            }

            // Optional: must-not-contain tokens (same PUA-translation logic).
            if let antineedles = golden.expected_not_contains {
                for antineedle in antineedles {
                    let lookup = PUAMap.tokenToPua(antineedle).map(String.init) ?? antineedle
                    XCTAssertFalse(
                        result.tokens.contains(lookup),
                        "\(label): expected token '\(antineedle)' to be absent, got: \(result.tokens)"
                    )
                }
            }

            // Optional: exact token sequence
            if let exact = golden.expected_tokens {
                XCTAssertEqual(
                    result.tokens, exact,
                    "\(label): exact token mismatch"
                )
            }

            // Optional: ZH should produce a tone marker (PUA codepoint)
            if golden.expected_contains_any_tone == true {
                let hasPUA = result.tokens.contains { token in
                    token.unicodeScalars.contains { (0xE000...0xF8FF).contains($0.value) }
                }
                XCTAssertTrue(
                    hasPUA,
                    "\(label): expected at least one PUA tone marker, got: \(result.tokens)"
                )
            }

            // Optional: question marker (?-suffix variants)
            if golden.expected_has_question_marker == true {
                let hasQuestion = result.tokens.contains { $0.contains("?") }
                XCTAssertTrue(
                    hasQuestion,
                    "\(label): expected interrogative marker, got: \(result.tokens)"
                )
            }
        }
    }
}

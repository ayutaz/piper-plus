// InputSanitizeContractTests.swift — control characters are stripped before
// a text is read.
//
// Contract: docs/spec/input-sanitize-contract.toml (runtime "swift-g2p").
// Cases: tests/fixtures/g2p/input_sanitize_cases.json (input_sanitize_cases),
// read from the source tree like the golden fixtures.
//
// Regression focus: the Rust G2P under this wrapper strips control
// characters, but `phonemize` hands it the text through `withCString`, and a
// C string ends at the first NUL: "ho" + NUL + "la" reached Rust as "ho".
// `Phonemizer.phonemize` therefore strips before the FFI call.

import XCTest
@testable import PiperPlusG2P

final class InputSanitizeContractTests: XCTestCase {
    private static let nul = String(Unicode.Scalar(UInt8(0)))

    private func fixture() throws -> [String: Any] {
        try GoldenFixtures.json("tests/fixtures/g2p/input_sanitize_cases.json")
    }

    func testStripMatchesEveryStripCase() throws {
        let cases = try XCTUnwrap(fixture()["strip_cases"] as? [[String: Any]])
        XCTAssertGreaterThan(cases.count, 10)
        for c in cases {
            let input = try XCTUnwrap(c["input"] as? String)
            let expected = try XCTUnwrap(c["expected"] as? String)
            XCTAssertEqual(TextSanitizer.stripControlChars(input), expected, "\(c["name"] ?? "?")")
        }
    }

    func testStripIsIdempotent() throws {
        let cases = try XCTUnwrap(fixture()["strip_cases"] as? [[String: Any]])
        for c in cases {
            let once = TextSanitizer.stripControlChars(try XCTUnwrap(c["input"] as? String))
            XCTAssertEqual(TextSanitizer.stripControlChars(once), once)
        }
    }

    func testStripMatchesTheRuleForEveryBmpScalar() {
        for value in UInt32(0) ... 0xFFFF {
            guard let scalar = Unicode.Scalar(value) else { continue }  // surrogates
            let text = "a" + String(scalar) + "b"
            let expected: String
            switch value {
            case 0x09, 0x0A, 0x0D: expected = text
            case 0x0B, 0x0C, 0x85: expected = "a b"
            case 0x00 ... 0x1F, 0x7F ... 0x9F: expected = "ab"
            default: expected = text
            }
            XCTAssertEqual(TextSanitizer.stripControlChars(text), expected, "U+\(String(value, radix: 16))")
        }
    }

    func testPhonemizeReadsEveryWordCaseLikeTheCleanText() throws {
        let cases = try XCTUnwrap(fixture()["word_cases"] as? [[String: Any]])
        let phonemizer = try Phonemizer()
        var checked = 0
        for c in cases {
            // pt-PT is not a Language case; "multilingual" needs a language.
            guard let code = c["language"] as? String, let language = Language(rawValue: code) else {
                continue
            }
            let clean = try XCTUnwrap(c["clean"] as? String)
            let dirty = try XCTUnwrap(c["dirty"] as? String)
            let label = "\(code) \(c["control"] ?? "?") '\(clean)'"
            let want = try phonemizer.phonemize(clean, language: language)
            XCTAssertFalse(want.tokens.isEmpty, label)
            XCTAssertEqual(try phonemizer.phonemize(dirty, language: language).tokens, want.tokens, label)
            checked += 1
        }
        XCTAssertGreaterThan(checked, 30)
    }

    func testNulInsideAWordDoesNotCutTheText() throws {
        let phonemizer = try Phonemizer(languages: [.spanish])
        let clean = try phonemizer.phonemize("hola mundo", language: .spanish)
        let dirty = try phonemizer.phonemize("ho" + Self.nul + "la mundo", language: .spanish)
        XCTAssertEqual(dirty.tokens, clean.tokens)
    }

    func testTextOfOnlyControlCharactersReadsLikeAnEmptyText() throws {
        let phonemizer = try Phonemizer(languages: [.spanish])
        let controls = [0x00, 0x01, 0x7F, 0x9F].map { String(Unicode.Scalar(UInt8($0))) }.joined()
        XCTAssertEqual(
            try phonemizer.phonemize(controls, language: .spanish).tokens,
            try phonemizer.phonemize("", language: .spanish).tokens
        )
    }
}

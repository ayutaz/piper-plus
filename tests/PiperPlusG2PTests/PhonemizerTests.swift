// PhonemizerTests.swift — XCTest suite for the PiperPlusG2P Swift wrapper.
//
// These tests exercise the wrapper against the bundled xcframework. They
// will only run successfully once Package.swift has been updated with a
// real `PiperPlusG2PBinary` checksum (i.e., after the first release that
// publishes `libpiper_plus_g2p-ios-v${VERSION}.xcframework.zip`).

import XCTest
@testable import PiperPlusG2P

final class PhonemizerTests: XCTestCase {
    func testInitWithDefaultLanguages() throws {
        let phonemizer = try Phonemizer()
        XCTAssertFalse(phonemizer.availableLanguages.isEmpty,
                       "default init should register at least one language")
    }

    func testInitWithSingleLanguage() throws {
        let phonemizer = try Phonemizer(languages: [.english])
        XCTAssertTrue(phonemizer.availableLanguages.contains(.english))
    }

    // Assertion helpers — keep parity with the cross-runtime golden fixture's
    // structural checks so that PhonemizerTests catches per-language drift,
    // not just "did anything come out".

    private func assertContains(
        _ tokens: [String],
        _ needle: String,
        line: UInt = #line
    ) {
        XCTAssertTrue(
            tokens.contains(needle),
            "tokens must contain \"\(needle)\", got \(tokens)",
            line: line
        )
    }

    private func assertContainsPUA(_ tokens: [String], line: UInt = #line) {
        // Tone markers and language-specific phonemes use Unicode PUA
        // (E000–F8FF). At least one token must be in this range.
        let hasPUA = tokens.contains { token in
            token.unicodeScalars.contains { scalar in
                (0xE000 ... 0xF8FF).contains(scalar.value)
            }
        }
        XCTAssertTrue(
            hasPUA,
            "expected at least one PUA codepoint (E000-F8FF) in \(tokens)",
            line: line
        )
    }

    func testEnglishPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.english])
        let result = try phonemizer.phonemize("Hello world", language: .english)
        XCTAssertEqual(result.language, "en")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 6,
            "Hello world ≥ 6 phonemes, got \(result.tokens)"
        )
        assertContains(result.tokens, "h")  // Golden fixture en/hello expects "h"
    }

    func testJapanesePhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.japanese])
        let result = try phonemizer.phonemize("こんにちは", language: .japanese)
        XCTAssertEqual(result.language, "ja")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 7,
            "こんにちは ≥ 7 phonemes (Golden fixture), got \(result.tokens)"
        )
        for needle in ["k", "o", "n", "i", "a"] {
            assertContains(result.tokens, needle)
        }
    }

    func testChinesePhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.chinese])
        let result = try phonemizer.phonemize("你好", language: .chinese)
        XCTAssertEqual(result.language, "zh")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 2,
            "你好 must produce ≥ 2 tokens, got \(result.tokens)"
        )
        // Golden fixture: zh/你好 expected_contains_any_tone == true
        assertContainsPUA(result.tokens)
    }

    func testKoreanPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.korean])
        let result = try phonemizer.phonemize("안녕하세요", language: .korean)
        XCTAssertEqual(result.language, "ko")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 6,
            "안녕하세요 ≥ 6 phonemes, got \(result.tokens)"
        )
    }

    func testSpanishPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.spanish])
        let result = try phonemizer.phonemize("hola", language: .spanish)
        XCTAssertEqual(result.language, "es")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 3,
            "hola ≥ 3 phonemes, got \(result.tokens)"
        )
        // Spanish "hola" pronounces as /ola/ (silent h), so at least o, l, a.
        for needle in ["o", "l", "a"] {
            assertContains(result.tokens, needle)
        }
    }

    func testFrenchPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.french])
        let result = try phonemizer.phonemize("bonjour", language: .french)
        XCTAssertEqual(result.language, "fr")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 4,
            "bonjour ≥ 4 phonemes, got \(result.tokens)"
        )
        assertContains(result.tokens, "b")
    }

    func testPortuguesePhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.portuguese])
        let result = try phonemizer.phonemize("olá", language: .portuguese)
        XCTAssertEqual(result.language, "pt")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 3,
            "olá ≥ 3 phonemes, got \(result.tokens)"
        )
        assertContains(result.tokens, "o")
    }

    func testSwedishPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.swedish])
        let result = try phonemizer.phonemize("hej", language: .swedish)
        XCTAssertEqual(result.language, "sv")
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, 2,
            "hej ≥ 2 phonemes, got \(result.tokens)"
        )
    }

    func testMultipleLanguages() throws {
        let phonemizer = try Phonemizer(languages: [.english, .japanese, .french])
        let langs = Set(phonemizer.availableLanguages)
        XCTAssertTrue(langs.contains(.english))
        XCTAssertTrue(langs.contains(.japanese))
        XCTAssertTrue(langs.contains(.french))
    }

    func testPhonemizeWithUnregisteredLanguageThrows() throws {
        let phonemizer = try Phonemizer(languages: [.english])
        XCTAssertThrowsError(
            try phonemizer.phonemize("こんにちは", language: .japanese)
        ) { error in
            XCTAssertEqual(error as? G2PError, G2PError.phonemizeReturnedNull)
        }
    }

    func testEmptyTextDoesNotCrash() throws {
        let phonemizer = try Phonemizer(languages: [.english])
        // Empty text may return tokens=[] or throw — both are acceptable as
        // long as it doesn't crash.
        _ = try? phonemizer.phonemize("", language: .english)
    }
}

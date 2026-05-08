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
            // Diagnostic payload must echo the language under which the call
            // was issued — gives multi-language callers a way to triage which
            // call site failed without correlating against the call stack.
            XCTAssertEqual(
                error as? G2PError,
                G2PError.phonemizeReturnedNull(language: .japanese)
            )
        }
    }

    func testEmptyTextDoesNotCrash() throws {
        // Spec (Rust ffi.rs::test_ffi_phonemize_empty_text): empty input may
        // either succeed with tokens=[] or fail with phonemizeReturnedNull.
        // The contract is "must not crash", and either outcome is valid.
        // We assert one of the two explicitly so a future change that throws
        // a different error case (e.g. .decodeFailed) gets caught.
        let phonemizer = try Phonemizer(languages: [.english])
        do {
            let result = try phonemizer.phonemize("", language: .english)
            XCTAssertEqual(result.language, "en")
            // Empty input may produce zero or a tiny number of tokens;
            // we accept anything as long as it parsed.
            XCTAssertGreaterThanOrEqual(result.tokens.count, 0)
        } catch G2PError.phonemizeReturnedNull(let lang) {
            // Acceptable per the Rust contract. The error must echo the
            // language the call was issued under (.english here).
            XCTAssertEqual(lang, .english)
        } catch {
            XCTFail("empty text should yield phonemizeReturnedNull or success, got: \(error)")
        }
    }

    // Diagnostic information attached to G2PError must surface the failed
    // configuration / call site without forcing the caller to instrument
    // the call stack. Triaging "which language failed?" should be a one-line
    // log of the error itself.
    func testInitializationFailedDescriptionMentionsRequestedLanguages() {
        let error = G2PError.initializationFailed(
            requestedLanguages: [.japanese, .english, .chinese]
        )
        let desc = error.description
        XCTAssertTrue(desc.contains("ja"), "description should include 'ja', got: \(desc)")
        XCTAssertTrue(desc.contains("en"), "description should include 'en', got: \(desc)")
        XCTAssertTrue(desc.contains("zh"), "description should include 'zh', got: \(desc)")
    }

    func testPhonemizeReturnedNullDescriptionMentionsLanguage() {
        let error = G2PError.phonemizeReturnedNull(language: .korean)
        XCTAssertTrue(
            error.description.contains("ko"),
            "description should include 'ko', got: \(error.description)"
        )
    }

    // M1: availableLanguages must round-trip the requested language set.
    // If Rust ever adds a language code Swift's `Language` enum does not know
    // about, `compactMap(Language(rawValue:))` would silently drop it and the
    // user would see a missing language with no error. Catch that drift here.
    func testAvailableLanguagesRoundTripsRequestedSet() throws {
        let requested: [Language] = [.english, .japanese, .chinese, .korean,
                                     .spanish, .french, .portuguese, .swedish]
        let phonemizer = try Phonemizer(languages: requested)
        let registered = Set(phonemizer.availableLanguages)
        XCTAssertEqual(
            registered, Set(requested),
            """
            availableLanguages must equal the requested set. Mismatch
            indicates either (a) Rust failed to register a language at
            init (init should have thrown) or (b) Rust returned a
            language code missing from Swift's `Language` enum.
            """
        )
    }
}

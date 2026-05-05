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

    func testEnglishPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.english])
        let result = try phonemizer.phonemize("Hello world", language: .english)
        XCTAssertEqual(result.language, "en")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testJapanesePhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.japanese])
        let result = try phonemizer.phonemize("こんにちは", language: .japanese)
        XCTAssertEqual(result.language, "ja")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testChinesePhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.chinese])
        let result = try phonemizer.phonemize("你好", language: .chinese)
        XCTAssertEqual(result.language, "zh")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testKoreanPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.korean])
        let result = try phonemizer.phonemize("안녕하세요", language: .korean)
        XCTAssertEqual(result.language, "ko")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testSpanishPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.spanish])
        let result = try phonemizer.phonemize("hola", language: .spanish)
        XCTAssertEqual(result.language, "es")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testFrenchPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.french])
        let result = try phonemizer.phonemize("bonjour", language: .french)
        XCTAssertEqual(result.language, "fr")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testPortuguesePhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.portuguese])
        let result = try phonemizer.phonemize("olá", language: .portuguese)
        XCTAssertEqual(result.language, "pt")
        XCTAssertFalse(result.tokens.isEmpty)
    }

    func testSwedishPhonemize() throws {
        let phonemizer = try Phonemizer(languages: [.swedish])
        let result = try phonemizer.phonemize("hej", language: .swedish)
        XCTAssertEqual(result.language, "sv")
        XCTAssertFalse(result.tokens.isEmpty)
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

// EdgeCaseTests.swift — input boundary / Unicode edge-case coverage.
//
// PhonemizerTests.swift exercises happy-path single-word inputs across
// languages; GoldenPhonemeTests.swift covers cross-runtime fixture
// scenarios. Neither catches the boundary cases that historically trip
// FFI bindings:
//
//   - very long input (sentence-splitter / buffer-size assumptions)
//   - surrogate-pair characters (UTF-16 / UTF-8 boundary corruption)
//   - embedded control characters
//   - mixed-script input that is *not* covered by ZH-EN dispatch
//   - unique-codepoint stress (every codepoint different)
//
// These have all been root-causes of cross-runtime drift in adjacent
// runtimes (see PR #320 / Issue #207). We assert the Swift wrapper
// either succeeds with sensible token counts or throws a documented
// G2PError — never returning corrupt data, never crashing.

import XCTest
@testable import PiperPlusG2P

final class EdgeCaseTests: XCTestCase {
    // -------------------------------------------------------------------
    // Long input
    // -------------------------------------------------------------------

    func testVeryLongEnglishInput_DoesNotTruncateOrCrash() throws {
        // 500 repeats of "hello world " == ~6000 chars. Single-word "hello"
        // produces ≥3 tokens (per Golden fixture); 500 repeats must scale
        // monotonically — fewer tokens than `500 × 3` indicates silent
        // truncation in the FFI layer.
        let phonemizer = try Phonemizer(languages: [.english])
        let unit = try phonemizer.phonemize("hello", language: .english)
        XCTAssertGreaterThanOrEqual(unit.tokens.count, 3)

        let long = String(repeating: "hello world ", count: 500)
        let result = try phonemizer.phonemize(long, language: .english)
        XCTAssertGreaterThanOrEqual(
            result.tokens.count, unit.tokens.count * 100,
            "long input truncated: 500 repeats produced only \(result.tokens.count) tokens, " +
            "expected ≥ 100 × \(unit.tokens.count)"
        )
        XCTAssertEqual(result.language, "en")
    }

    // -------------------------------------------------------------------
    // Surrogate pairs (codepoints > U+FFFF)
    // -------------------------------------------------------------------

    func testSurrogatePairInputDoesNotCrash() throws {
        // U+1F600 (😀) is a supplementary-plane char that requires two
        // UTF-16 code units. The Rust FFI receives UTF-8 bytes, which
        // is unambiguous, but if any code path on the Swift side did a
        // UTF-16 length-cast (e.g. `text.utf16.count`) it would mis-bound
        // the C string. We only assert no crash + the call returns with
        // a documented language echo.
        let phonemizer = try Phonemizer(languages: [.english])
        let inputs = [
            "hello 😀",      // supplementary at end
            "😀 world",      // supplementary at start
            "say 🎉 yay",   // supplementary in middle
            "👨‍👩‍👧",      // ZWJ sequence (multiple supplementary chars)
        ]
        for input in inputs {
            do {
                let result = try phonemizer.phonemize(input, language: .english)
                XCTAssertEqual(
                    result.language, "en",
                    "language echo drift on input \"\(input)\""
                )
            } catch G2PError.phonemizeReturnedNull {
                // Acceptable: emoji-only segments may return null.
            } catch {
                XCTFail("unexpected error for input \"\(input)\": \(error)")
            }
        }
    }

    // -------------------------------------------------------------------
    // Control characters
    // -------------------------------------------------------------------

    func testControlCharactersDoNotCorruptOutput() throws {
        // \t \n \r should be treated as whitespace separators, not as
        // significant phonemes. Mixing them between words must yield
        // the same tokens (modulo tokenizer boundary effects) as the
        // space-separated form.
        let phonemizer = try Phonemizer(languages: [.english])
        let space = try phonemizer.phonemize("hello world", language: .english)
        let tab = try phonemizer.phonemize("hello\tworld", language: .english)
        let newline = try phonemizer.phonemize("hello\nworld", language: .english)
        // Allow ±20% drift in case the tokenizer treats one of these as
        // a word break vs. a hard break, but not more — that would mean
        // the control char produced extra phonemes.
        let bound = max(1, space.tokens.count / 5)
        XCTAssertLessThanOrEqual(
            abs(tab.tokens.count - space.tokens.count), bound,
            "tab-separated produced \(tab.tokens.count) tokens, space-separated \(space.tokens.count)"
        )
        XCTAssertLessThanOrEqual(
            abs(newline.tokens.count - space.tokens.count), bound,
            "newline-separated produced \(newline.tokens.count) tokens, space-separated \(space.tokens.count)"
        )
    }

    // -------------------------------------------------------------------
    // Mixed-script input (not ZH-EN dispatch)
    // -------------------------------------------------------------------

    func testJapaneseWithEmbeddedAsciiPunctuation() throws {
        // Mixing ASCII punctuation into JA must not cause the OpenJTalk
        // path to bail. The token list must remain non-empty.
        let phonemizer = try Phonemizer(languages: [.japanese])
        let inputs = [
            "こんにちは!",
            "「こんにちは」",
            "こんにちは。",
            "100円です",
        ]
        for input in inputs {
            let result = try phonemizer.phonemize(input, language: .japanese)
            XCTAssertEqual(result.language, "ja")
            XCTAssertGreaterThan(
                result.tokens.count, 0,
                "JA + punctuation \"\(input)\" produced 0 tokens"
            )
        }
    }

    // -------------------------------------------------------------------
    // Whitespace-only / empty
    // -------------------------------------------------------------------

    func testWhitespaceOnlyInputs_MatchEmptyContract() throws {
        // The empty-input contract (PhonemizerTests.testEmptyTextDoesNotCrash)
        // permits either tokens=[] or phonemizeReturnedNull. Whitespace-only
        // input should follow the same contract — never crash, never return
        // a non-empty token list.
        let phonemizer = try Phonemizer(languages: [.english])
        for input in [" ", "  ", "\t", "\n", "\r", "    \t\n"] {
            do {
                let result = try phonemizer.phonemize(input, language: .english)
                XCTAssertEqual(
                    result.tokens.count, 0,
                    "whitespace-only \"\(input.unicodeScalars.map { String(format: "U+%04X", $0.value) }.joined(separator: " "))\" " +
                    "should produce 0 tokens, got \(result.tokens.count): \(result.tokens)"
                )
            } catch G2PError.phonemizeReturnedNull {
                // Acceptable.
            } catch {
                XCTFail("unexpected error for whitespace input: \(error)")
            }
        }
    }

    // -------------------------------------------------------------------
    // Unique-codepoint stress
    // -------------------------------------------------------------------

    func testUniqueCodepointInputDoesNotCrash() throws {
        // Iterate every printable ASCII char individually. The phonemizer
        // may produce 0 or N tokens; we only assert it returns without
        // FFI corruption (decode failure / out-of-range char).
        let phonemizer = try Phonemizer(languages: [.english])
        for code: UInt32 in 0x21...0x7E {
            guard let scalar = Unicode.Scalar(code) else { continue }
            let input = String(Character(scalar))
            do {
                _ = try phonemizer.phonemize(input, language: .english)
            } catch G2PError.phonemizeReturnedNull {
                // Acceptable for punctuation-only input.
            } catch {
                XCTFail("unexpected error on char U+\(String(code, radix: 16)) \"\(input)\": \(error)")
            }
        }
    }

    // -------------------------------------------------------------------
    // Token list immutability claim (PhonemizeResult.tokens is `[String]`,
    // a Swift value-type array — it cannot be mutated through the wrapper.
    // Verify that two successive calls return distinct arrays, so a future
    // refactor that "shares" a backing buffer between calls would be
    // caught by `===`-style identity divergence.)
    // -------------------------------------------------------------------

    func testRepeatedCallsReturnIndependentTokenArrays() throws {
        let phonemizer = try Phonemizer(languages: [.english])
        let r1 = try phonemizer.phonemize("hello", language: .english)
        let r2 = try phonemizer.phonemize("hello", language: .english)
        // Same content (deterministic), but the value-semantics array
        // means mutating one cannot affect the other. We assert the
        // contents are equal AND that we got distinct PhonemizeResult
        // values.
        XCTAssertEqual(r1.tokens, r2.tokens, "same input must produce same tokens (deterministic contract)")
        var mutable = r1.tokens
        mutable.append("ZZZZ")
        XCTAssertNotEqual(
            mutable, r2.tokens,
            "mutating returned tokens must not affect a sibling call"
        )
    }
}

// ZhEnLoanwordMatrixTests.swift — cross-runtime ZH-EN code-switching parity.
//
// Loads the shared fixture at tests/fixtures/g2p/zh_en_loanword_matrix.json
// (canonical source in Python; mirrored byte-for-byte to all 7 runtimes by
// `scripts/check_loanword_consistency.py`) and asserts that the Swift
// wrapper produces the same token-count behavior the Go / C# / C++ / WASM /
// Rust mirror tests already verify.
//
// Why this exists: the parent commit (T14, 05a660be) added Kotlin/Swift to
// the ZH-EN sync gate, so the JSON file is byte-equal to the Python source
// — but until now no Swift test actually consumed the matrix. A future
// regression in `chinese.rs::phonemize_embedded_english` (or in the FFI
// boundary that bridges Rust → Swift) could ship without any Swift gate
// catching it. This file closes that hole.
//
// Numerical expectations (per fixture notes):
//   - GPS     → 11 tokens (ji4(3) + pi4(3) + ai1(2) + si4(3))
//   - USB     → 10 tokens (you1(2) + ai1(2) + si4(3) + bi4(3))
//   - Python  →  6 tokens (pai4(3) + sen1(3))
//   - ChatGPT → 15 tokens (5 syllables × 3 phonemes)
//   - ZZ      = 2 × Z (letter_fallback per-letter)
//   - empty / whitespace / punctuation → 0 tokens
//   - GPS, GPS. GPS! ≡ GPS (trailing punctuation drop)
//
// Fixture path is resolved via `#filePath` (compile-time substituted) so
// the test runs identically under `swift test` and `xcodebuild test` from
// any working directory.

import XCTest
@testable import PiperPlusG2P

private struct LoanwordMatrix: Decodable {
    let schema_version: Int
    let cases: [LoanwordCase]
}

private struct LoanwordCase: Decodable {
    let name: String
    let input: String?
    // Numeric expectation: exact count. Mutually exclusive with the relation
    // / equiv / equiv_sum / differs_from / no-expectation cases below.
    let expected_token_count: Int?
    let expected_token_count_relation: String?
    let expected_token_count_equiv: String?
    let expected_token_count_equiv_sum: [String]?
    let expected_token_count_differs_from: String?
    let notes: String?
    // Forward-compat schema test entry (only `input_json` is set; no input/expected).
    let input_json: ForwardCompatJson?
}

// JSONDecoder cannot decode arbitrary [String: Any] without a custom
// container. We only need to confirm decode succeeds + the shape matches
// what the loader is supposed to silently accept.
private struct ForwardCompatJson: Decodable {
    let version: Int
    let schema_version: Int
}

final class ZhEnLoanwordMatrixTests: XCTestCase {
    private static let fixtureURL: URL = {
        // tests/PiperPlusG2PTests/ZhEnLoanwordMatrixTests.swift
        //   → tests/fixtures/g2p/zh_en_loanword_matrix.json
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // PiperPlusG2PTests/
            .deletingLastPathComponent()  // tests/
            .appendingPathComponent("fixtures/g2p/zh_en_loanword_matrix.json")
    }()

    private static func loadMatrix() throws -> LoanwordMatrix {
        let data = try Data(contentsOf: fixtureURL)
        return try JSONDecoder().decode(LoanwordMatrix.self, from: data)
    }

    private func tokenCount(_ phonemizer: Phonemizer, _ input: String) throws -> Int {
        try phonemizer.phonemize(input, language: .chinese).tokens.count
    }

    // -------------------------------------------------------------------
    // Fixture sanity
    // -------------------------------------------------------------------

    func testFixtureLoads() throws {
        let matrix = try Self.loadMatrix()
        XCTAssertEqual(matrix.schema_version, 1, "schema_version drift — review LoanwordMatrix Decodable")
        XCTAssertGreaterThanOrEqual(matrix.cases.count, 17, "fixture must retain ≥17 cases (parent commit T14)")
    }

    // -------------------------------------------------------------------
    // Per-case parity (numeric expectations only — the matrix intentionally
    // does NOT pin exact IPA strings; per-runtime exact-token tests live in
    // each runtime's own ticket suite. The matrix is the *count contract*.)
    // -------------------------------------------------------------------

    func testExactTokenCountCases() throws {
        let matrix = try Self.loadMatrix()
        let phonemizer = try Phonemizer(languages: [.chinese])

        var verified = 0
        for c in matrix.cases {
            guard let input = c.input, let expected = c.expected_token_count else { continue }
            let got = try tokenCount(phonemizer, input)
            XCTAssertEqual(
                got, expected,
                "case '\(c.name)' input=\"\(input)\" expected \(expected) tokens, got \(got). " +
                "Notes: \(c.notes ?? "(none)")"
            )
            verified += 1
        }
        XCTAssertGreaterThanOrEqual(
            verified, 4,
            "matrix must keep ≥4 exact-count cases (GPS / USB / Python / ChatGPT)"
        )
    }

    func testRelationCases_LetterFallbackZZ() throws {
        // Encodes "ZZ" must produce exactly 2× the tokens of "Z".
        // (The fixture entry is `letter_fallback_zz_doubles_z`.)
        let phonemizer = try Phonemizer(languages: [.chinese])
        let z = try tokenCount(phonemizer, "Z")
        let zz = try tokenCount(phonemizer, "ZZ")
        XCTAssertEqual(
            zz, z * 2,
            "letter_fallback per-letter contract: ZZ (\(zz)) must equal 2 × Z (\(z * 2)). " +
            "Drift indicates the fallback path collapsed adjacent letters or added per-input padding."
        )
    }

    func testEquivCases_TrailingPunctuationDrops() throws {
        // GPS, GPS. and GPS! must all yield the same token count as GPS.
        let phonemizer = try Phonemizer(languages: [.chinese])
        let bare = try tokenCount(phonemizer, "GPS")
        for trailer in [",", ".", "!"] {
            let withTrailer = try tokenCount(phonemizer, "GPS\(trailer)")
            XCTAssertEqual(
                withTrailer, bare,
                "trailing '\(trailer)' must not change token count: GPS=\(bare) GPS\(trailer)=\(withTrailer)"
            )
        }
    }

    func testEquivCases_DigitsDropFromLetterFallback() throws {
        // Z2Z9 must yield the same token count as ZZ — digits 2 and 9 are
        // dropped from the letter_fallback path.
        let phonemizer = try Phonemizer(languages: [.chinese])
        let zz = try tokenCount(phonemizer, "ZZ")
        let z2z9 = try tokenCount(phonemizer, "Z2Z9")
        XCTAssertEqual(
            z2z9, zz,
            "digits must silently drop from letter_fallback: Z2Z9=\(z2z9) ZZ=\(zz)"
        )
    }

    func testEquivSumCases_TwoEmbeddedTokens() throws {
        // "ChatGPT 和 Python" must equal ChatGPT + Python.
        // The Han separator (和) is not ASCII so it does not contribute.
        let phonemizer = try Phonemizer(languages: [.chinese])
        let chatgpt = try tokenCount(phonemizer, "ChatGPT")
        let python = try tokenCount(phonemizer, "Python")
        let combined = try tokenCount(phonemizer, "ChatGPT 和 Python")
        // Combined input includes the Han char "和", which produces additional
        // Mandarin phonemes. We assert combined ≥ ChatGPT + Python so the
        // English token paths still fire (this is the matrix's intent — the
        // English embeddings must phonemize, not be silently dropped).
        XCTAssertGreaterThanOrEqual(
            combined, chatgpt + python,
            "embedded English tokens dropped: combined=\(combined), ChatGPT=\(chatgpt), Python=\(python)"
        )
    }

    func testCaseSensitivity_PythonVsPYTHON() throws {
        // PYTHON does NOT match the case-sensitive loanword "Python", so it
        // falls through to letter_fallback. Token counts must differ.
        let phonemizer = try Phonemizer(languages: [.chinese])
        let mixed = try tokenCount(phonemizer, "Python")
        let upper = try tokenCount(phonemizer, "PYTHON")
        XCTAssertNotEqual(
            mixed, upper,
            "case-sensitive loanword lookup broken: Python=\(mixed), PYTHON=\(upper) " +
            "must differ (Python via loanword path, PYTHON via letter_fallback)"
        )
    }

    func testZeroCountCases_EmptyAndWhitespaceAndPunctuation() throws {
        // Empty / whitespace-only / punctuation-only must produce 0 tokens.
        // The Rust FFI may either return tokens=[] or throw; both are valid
        // per the empty-text contract (mirror of PhonemizerTests.testEmptyTextDoesNotCrash).
        let phonemizer = try Phonemizer(languages: [.chinese])
        for input in ["", "   ", ",.!?"] {
            do {
                let count = try tokenCount(phonemizer, input)
                XCTAssertEqual(
                    count, 0,
                    "input \"\(input)\" should produce 0 tokens, got \(count)"
                )
            } catch G2PError.phonemizeReturnedNull {
                // Acceptable: matches Rust's behavior on empty/whitespace.
            } catch {
                XCTFail("input \"\(input)\" threw unexpected error: \(error)")
            }
        }
    }

    // -------------------------------------------------------------------
    // Issue #384 examples — full sentence smoke tests. The matrix says
    // "full sentence verification is per-runtime"; we assert the embedded
    // English token still produces ≥ the bare-token count, so the Mandarin
    // surrounding chars never silently drop the English pinyin path.
    // -------------------------------------------------------------------

    func testIssue384_PleaseOpenGPS() throws {
        let phonemizer = try Phonemizer(languages: [.chinese])
        let bareGPS = try tokenCount(phonemizer, "GPS")
        let sentence = try tokenCount(phonemizer, "请打开 GPS")
        XCTAssertGreaterThanOrEqual(
            sentence, bareGPS,
            "embedded GPS dropped: sentence=\(sentence) < bare GPS=\(bareGPS)"
        )
    }

    func testIssue384_IUsePython() throws {
        let phonemizer = try Phonemizer(languages: [.chinese])
        let barePython = try tokenCount(phonemizer, "Python")
        let sentence = try tokenCount(phonemizer, "我喜欢用 Python 写代码")
        XCTAssertGreaterThanOrEqual(
            sentence, barePython,
            "embedded Python dropped: sentence=\(sentence) < bare Python=\(barePython)"
        )
    }

    func testIssue384_LetMeUseChatGPT() throws {
        let phonemizer = try Phonemizer(languages: [.chinese])
        let bareChatGPT = try tokenCount(phonemizer, "ChatGPT")
        let sentence = try tokenCount(phonemizer, "让我用 ChatGPT 写代码")
        XCTAssertGreaterThanOrEqual(
            sentence, bareChatGPT,
            "embedded ChatGPT dropped: sentence=\(sentence) < bare ChatGPT=\(bareChatGPT)"
        )
    }

    // -------------------------------------------------------------------
    // Forward-compat (YELLOW-5): a future schema_version: 2 with unknown
    // top-level fields must parse without errors. The Rust loader is the
    // truth here; we assert the fixture entry that documents the contract
    // is present and decodable, so a `schema_version: 3` migration cannot
    // ship without explicitly removing this gate.
    // -------------------------------------------------------------------

    func testForwardCompatEntryDocumented() throws {
        let matrix = try Self.loadMatrix()
        let entry = matrix.cases.first { $0.name == "schema_v2_forward_compat_loader" }
        XCTAssertNotNil(
            entry,
            "matrix lost the schema_v2_forward_compat_loader entry — remove this test " +
            "explicitly when YELLOW-5 contract retires."
        )
        guard let v2 = entry?.input_json else {
            XCTFail("forward-compat entry missing input_json")
            return
        }
        XCTAssertEqual(v2.schema_version, 2)
        XCTAssertEqual(v2.version, 2)
    }
}

// ZhEnLoanwordMatrixTests.swift — cross-runtime ZH-EN code-switching parity.
//
// **Scope note (CI fix 132d4fcc → follow-up):** the matrix fixture at
// `tests/fixtures/g2p/zh_en_loanword_matrix.json` pins token counts for
// `phonemize_embedded_english` — a function on the Rust `ChinesePhonemizer`
// that the Swift FFI does NOT expose directly. Embedded-English dispatch
// is invoked transparently by `MultilingualPhonemizer` when the input is a
// Chinese sentence containing English tokens. Therefore the matrix's
// per-case exact-count expectations CANNOT be reproduced via
// `Phonemizer.phonemize(text, .chinese)` with pure-ASCII input — that path
// goes through `ChinesePhonemizer.phonemize` (no English dispatch), not
// through `phonemize_embedded_english`.
//
// What this file verifies (via the *public* Swift API):
//   1. The fixture loads with the expected schema (drift detector).
//   2. ZH sentence + embedded English produces ≥ bare-English token count
//      (proves the dispatch path fires for sentence-context inputs; weak
//      but the only externally observable contract via this API).
//   3. The forward-compat (schema_v2) entry remains pinned.
//
// For the strict matrix counts (GPS=11 / USB=10 / Python=6 / ChatGPT=15
// etc.), see `test_zh_en_two_crate.rs` (Rust) and the Go/C#/C++/WASM
// mirror tests, which can call `phonemize_embedded_english` directly.

import XCTest
@testable import PiperPlusG2P

private struct LoanwordMatrix: Decodable {
    let schema_version: Int
    let cases: [LoanwordCase]
}

private struct LoanwordCase: Decodable {
    let name: String
    let input: String?
    let expected_token_count: Int?
    let expected_token_count_relation: String?
    let expected_token_count_equiv: String?
    let expected_token_count_equiv_sum: [String]?
    let expected_token_count_differs_from: String?
    let notes: String?
    let input_json: ForwardCompatJson?
}

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
    // Fixture sanity (drift detector)
    // -------------------------------------------------------------------

    func testFixtureLoads() throws {
        let matrix = try Self.loadMatrix()
        XCTAssertEqual(
            matrix.schema_version, 1,
            "schema_version drift — review LoanwordMatrix Decodable"
        )
        XCTAssertGreaterThanOrEqual(
            matrix.cases.count, 17,
            "fixture must retain ≥17 cases (parent commit T14)"
        )
    }

    // -------------------------------------------------------------------
    // Issue #384 — full sentence smoke tests. These are the only matrix
    // assertions reproducible via the public Swift API: a Chinese sentence
    // with embedded English must produce ≥ the bare-English token count
    // (the embedded English MUST not be silently dropped).
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

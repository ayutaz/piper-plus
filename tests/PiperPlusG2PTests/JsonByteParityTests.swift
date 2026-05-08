// JsonByteParityTests.swift — sync-gate parity for Swift-bundled JSON.
//
// The ZH-EN code-switching loanword dictionary
// (`Sources/PiperPlusG2P/Resources/zh_en_loanword.json`) is one of 10 mirror
// copies enforced byte-for-byte by `scripts/check_loanword_consistency.py`
// against `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` (the
// canonical Python source). The CI gate prevents commits that diverge,
// but the gate runs only at PR time and only on the file as it appears in
// the repo — it does NOT verify what actually ships inside the SPM
// product's `Bundle.module`.
//
// A misconfigured `Package.swift` (e.g. `.copy(...)` instead of `.process(...)`,
// or the file path drifting after a refactor) could silently strip the
// resource from the bundle while leaving the source file intact. The CI
// gate would still pass; downstream consumers that read the JSON via
// `Bundle.module.url(forResource:withExtension:)` would get nil.
//
// This test catches that by re-asserting the byte-equality contract from
// inside the running test bundle.
//
// NOTE: The current test target does not declare the resource (Package.swift
// only ships it from the *library* target). We therefore load via the
// repo-root path resolved through `#filePath`. If a future refactor moves
// the resource to the test target, switch to `Bundle.module` here.

import XCTest
@testable import PiperPlusG2P

final class JsonByteParityTests: XCTestCase {
    private static let pythonCanonicalURL: URL = {
        // tests/PiperPlusG2PTests/JsonByteParityTests.swift
        //   → src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<2 { url.deleteLastPathComponent() }
        // url == tests/
        url.deleteLastPathComponent()
        // url == repo root
        return url
            .appendingPathComponent("src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json")
    }()

    private static let swiftMirrorURL: URL = {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<2 { url.deleteLastPathComponent() }
        url.deleteLastPathComponent()
        return url.appendingPathComponent("Sources/PiperPlusG2P/Resources/zh_en_loanword.json")
    }()

    private static let matrixCanonicalURL: URL = {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<2 { url.deleteLastPathComponent() }
        url.deleteLastPathComponent()
        return url.appendingPathComponent("tests/fixtures/g2p/zh_en_loanword_matrix.json")
    }()

    private static let matrixSwiftMirrorURL: URL = {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/zh_en_loanword_matrix.json")
    }()

    func testZhEnLoanwordSwiftMirrorIsByteEqualToPythonCanonical() throws {
        let pythonBytes = try Data(contentsOf: Self.pythonCanonicalURL)
        let swiftBytes  = try Data(contentsOf: Self.swiftMirrorURL)
        XCTAssertEqual(
            pythonBytes, swiftBytes,
            """
            Sources/PiperPlusG2P/Resources/zh_en_loanword.json drifted from
            src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json. Run
            `python scripts/check_loanword_consistency.py --fix` from the
            repo root, then `git add Sources/PiperPlusG2P/Resources/`.
            """
        )
    }

    func testZhEnLoanwordMatrixSwiftMirrorIsByteEqualToCanonical() throws {
        let canonicalBytes = try Data(contentsOf: Self.matrixCanonicalURL)
        let mirrorBytes    = try Data(contentsOf: Self.matrixSwiftMirrorURL)
        XCTAssertEqual(
            canonicalBytes, mirrorBytes,
            """
            tests/PiperPlusG2PTests/Fixtures/zh_en_loanword_matrix.json drifted
            from tests/fixtures/g2p/zh_en_loanword_matrix.json. Run
            `python scripts/check_loanword_consistency.py --fix` from the
            repo root.
            """
        )
    }

    func testCanonicalJsonStructureIsParseable() throws {
        // Beyond byte-equality, the file must remain valid JSON. A
        // malformed mirror would still byte-equal the source, but the test
        // gate that says "this is the dictionary the runtime sees" deserves
        // an explicit parse round-trip.
        let bytes = try Data(contentsOf: Self.swiftMirrorURL)
        let any = try JSONSerialization.jsonObject(with: bytes, options: [])
        guard let dict = any as? [String: Any] else {
            XCTFail("top-level JSON must be an object")
            return
        }
        XCTAssertNotNil(dict["acronyms"], "missing 'acronyms' section")
        XCTAssertNotNil(dict["loanwords"], "missing 'loanwords' section")
        XCTAssertNotNil(dict["letter_fallback"], "missing 'letter_fallback' section")
    }

    func testLoanwordSchemaCounts_MatchCanonicalSourceSpec() throws {
        // CLAUDE.md pins: acronyms 66 / loanwords 40 / letter_fallback 26.
        // A change to any of those counts is a deliberate Python source
        // edit; this test fires on accidental drift in either source or
        // mirror (since they are byte-equal, the Swift mirror's count is
        // a proxy for the Python source's count).
        let bytes = try Data(contentsOf: Self.swiftMirrorURL)
        guard let dict = try JSONSerialization.jsonObject(with: bytes, options: []) as? [String: Any]
        else {
            XCTFail("not an object"); return
        }
        let acronyms = dict["acronyms"] as? [String: Any] ?? [:]
        let loanwords = dict["loanwords"] as? [String: Any] ?? [:]
        let fallback = dict["letter_fallback"] as? [String: Any] ?? [:]
        XCTAssertEqual(
            acronyms.count, 66,
            "acronyms count drifted from CLAUDE.md spec (66). Update CLAUDE.md if intentional."
        )
        XCTAssertEqual(
            loanwords.count, 40,
            "loanwords count drifted from CLAUDE.md spec (40). Update CLAUDE.md if intentional."
        )
        XCTAssertEqual(
            fallback.count, 26,
            "letter_fallback count must equal 26 (A-Z); got \(fallback.count)"
        )
    }
}

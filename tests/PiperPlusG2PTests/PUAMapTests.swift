// PUAMapTests.swift — invariants for the Swift mirror of FIXED_PUA_MAP.
//
// `Sources/PiperPlusG2P/PUAMap.swift` is a hand-written copy of
// `src/rust/piper-plus-g2p/src/token_map.rs::FIXED_PUA_MAP`. The
// cross-runtime consistency gate (`scripts/check_pua_consistency.py`)
// is the primary defense against drift, but it only catches token /
// codepoint mismatches — it does *not* catch silent table shrinkage
// from typos that produce out-of-range scalars (e.g. surrogate
// codepoints) which would be dropped by the `Unicode.Scalar(code)`
// fallible initializer when constructing `tokenToPuaTable`.
//
// These XCTest assertions provide a fast in-process check that:
//   - the 99-entry count matches Rust and Python G2P
//   - `compatVersion` matches the canonical `PUA_COMPAT_VERSION`
//   - every codepoint is inside the PUA range (E000–F8FF)
//   - no two tokens share a codepoint (would corrupt round-trip)
//   - all entries survived the dict construction (no silent drops)
//
// If pua.json is bumped to v3, both the count assertion and the
// version assertion will fail here, preventing a release that ships
// with a stale Swift mirror.

import XCTest
@testable import PiperPlusG2P

final class PUAMapTests: XCTestCase {
    func testFixedMapEntryCount() {
        XCTAssertEqual(
            PUAMap.fixedMap.count, 99,
            """
            PUAMap.fixedMap must have exactly 99 entries to match
            src/rust/piper-plus-g2p/src/token_map.rs::FIXED_PUA_MAP and
            src/python/g2p/piper_plus_g2p/data/pua.json. If pua.json
            was bumped to v3, update PUAMap.swift and PUAMap.compatVersion.
            """
        )
    }

    func testCompatVersionMatchesCanonical() {
        XCTAssertEqual(
            PUAMap.compatVersion, 2,
            """
            PUAMap.compatVersion must match PUA_COMPAT_VERSION in
            src/rust/piper-plus-g2p/src/token_map.rs and the `version`
            field in pua.json. Bumping one without the other indicates
            an incomplete cross-runtime change.
            """
        )
    }

    func testAllCodepointsInPUARange() {
        for (token, code) in PUAMap.fixedMap {
            XCTAssertTrue(
                (0xE000 ... 0xF8FF).contains(code),
                "token \(token) codepoint U+\(String(code, radix: 16, uppercase: true)) is outside the PUA range"
            )
        }
    }

    func testNoCodepointCollisions() {
        var seen: [UInt32: String] = [:]
        for (token, code) in PUAMap.fixedMap {
            if let prior = seen[code] {
                XCTFail(
                    "codepoint U+\(String(code, radix: 16, uppercase: true)) collision: '\(prior)' vs '\(token)'"
                )
            }
            seen[code] = token
        }
    }

    func testNoTokenCollisions() {
        var seen: Set<String> = []
        for (token, _) in PUAMap.fixedMap {
            if !seen.insert(token).inserted {
                XCTFail("token '\(token)' appears more than once in fixedMap")
            }
        }
    }

    func testRoundTripEveryEntry() {
        // Every entry must be reachable through both forward and reverse
        // lookups. If any codepoint failed `Unicode.Scalar(code)` (e.g.
        // surrogate range typo), the dict construction silently drops it
        // and this test catches the discrepancy.
        for (token, code) in PUAMap.fixedMap {
            guard let pua = PUAMap.tokenToPua(token) else {
                XCTFail("forward lookup missing for token '\(token)' (U+\(String(code, radix: 16, uppercase: true)))")
                continue
            }
            XCTAssertEqual(
                pua.unicodeScalars.first?.value, code,
                "forward lookup for '\(token)' returned wrong codepoint"
            )
            XCTAssertEqual(
                PUAMap.puaToToken(pua), token,
                "reverse lookup did not round-trip for '\(token)'"
            )
        }
    }

    func testUnknownTokenReturnsNil() {
        XCTAssertNil(PUAMap.tokenToPua("definitely-not-a-real-token-zz9"))
    }

    func testNonPUACharacterReturnsNil() {
        // Latin 'a' is U+0061, well outside PUA.
        XCTAssertNil(PUAMap.puaToToken(Character("a")))
    }
}

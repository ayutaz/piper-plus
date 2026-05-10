// PiperPlusSmokeTests.swift — XCTest suite for the PiperPlus SPM product
// (synthesis engine, Issue #377).
//
// These smoke tests assert that the C API exposed via the bundled
// xcframework is correctly re-exported through `import PiperPlus`
// (Sources/PiperPlus/PiperPlus.swift uses `@_exported import
// PiperPlusBinary`). They DO NOT load an ONNX model or synthesize audio
// — that requires a real model file and is out of scope for a pre-tag
// SPM smoke check.
//
// Pre-release runnability:
//   The release Package.swift uses URL-based binaryTargets at GitHub
//   Release assets that don't resolve before tag publication, so
//   `swift test --filter PiperPlusTests` cannot run from the release
//   manifest until v1.13.0+ ships. PiperPlusG2PTests handle this with
//   Package.ci.swift (workflows/swift-g2p-ci.yml swaps it in). A
//   parallel CI flow for the synthesis engine would need:
//     1. A macOS slice for libpiper_plus (release-shared-lib.yml only
//        builds iOS slices today — see docs/spec/ios-shared-lib.md §6).
//     2. A Package.synthesis.ci.swift pointing PiperPlusBinary at a
//        locally-built macOS xcframework.
//   Until that lands, this file exists as compile-time check only. It
//   will run automatically once a release with a matching xcframework
//   is published OR once the macOS slice + CI swap is added.

import XCTest
@testable import PiperPlus

final class PiperPlusSmokeTests: XCTestCase {

    // MARK: - Version & API

    func testVersionReturnsNonEmptyString() {
        guard let cstr = piper_plus_version() else {
            XCTFail("piper_plus_version() returned NULL — header guarantees static storage")
            return
        }
        let s = String(cString: cstr)
        XCTAssertFalse(
            s.isEmpty,
            "piper_plus_version() must return a non-empty version string"
        )
    }

    func testApiVersionIsOne() {
        // Header declares PIPER_PLUS_API_VERSION == 1. piper_plus_api_version()
        // exists so consumers can detect ABI breakage at runtime; we pin
        // the only currently-published version here so any bump becomes
        // visible in this test (and forces a deliberate version bump
        // alongside CHANGELOG / migration docs).
        let api = piper_plus_api_version()
        XCTAssertEqual(
            api, 1,
            "API version 1 is the only currently-published version"
        )
    }

    // MARK: - Status enum bridging

    func testStatusEnumValuesMatchHeader() {
        // Verify Swift's C enum bridging returns the documented numeric
        // values. If a future header adds new variants, those should
        // also be pinned here so consumers can rely on the raw integer
        // codes (as documented in piper_plus.h §"Status codes").
        XCTAssertEqual(PIPER_PLUS_OK.rawValue, 0)
        XCTAssertEqual(PIPER_PLUS_DONE.rawValue, 1)
        XCTAssertEqual(PIPER_PLUS_ERR.rawValue, -1)
        XCTAssertEqual(PIPER_PLUS_ERR_MODEL.rawValue, -2)
        XCTAssertEqual(PIPER_PLUS_ERR_CONFIG.rawValue, -3)
        XCTAssertEqual(PIPER_PLUS_ERR_TEXT.rawValue, -4)
        XCTAssertEqual(PIPER_PLUS_ERR_BUSY.rawValue, -5)
        XCTAssertEqual(PIPER_PLUS_ERR_ORT.rawValue, -6)
    }

    // MARK: - Lifecycle

    func testCreateWithNullConfigReturnsError() {
        // piper_plus_create requires a non-NULL config. Spec: passing NULL
        // must NOT crash; it must return a non-OK status with out_engine
        // left NULL.
        var engine: OpaquePointer?
        let status = piper_plus_create(nil, &engine)
        XCTAssertNotEqual(
            status, PIPER_PLUS_OK,
            "create(NULL, &out) must return a non-OK status"
        )
        XCTAssertNil(engine, "out_engine must remain NULL on error")
    }

    func testCreateWithInvalidModelPathReturnsError() {
        // A path that does not exist on disk must produce a non-OK status
        // (most likely ERR_MODEL or ERR) without crashing. This exercises
        // the path validation branch of create() through the Swift bridge.
        var config = PiperPlusConfig()
        let path = strdup("/nonexistent/__piper_plus_smoke__.onnx")
        defer { free(path) }
        config.model_path = UnsafePointer(path)

        var engine: OpaquePointer?
        let status = piper_plus_create(&config, &engine)
        XCTAssertNotEqual(
            status, PIPER_PLUS_OK,
            "create() with invalid model_path must not return OK"
        )
        XCTAssertNil(engine, "out_engine must remain NULL on error")
    }

    func testFreeOnNullEngineDoesNotCrash() {
        // Defensive contract: piper_plus_free(NULL) must be a no-op.
        // Mirrors the C-stdlib free(NULL) convention. If this test
        // crashes, the xcframework is mis-built or the C ABI changed.
        piper_plus_free(nil)
        // Reaching here without a SIGSEGV is the success condition.
    }

    // MARK: - Default options

    func testDefaultSynthOptionsAreDocumented() {
        // Header docstring: defaults are noise_scale=0.667, length_scale=1.0,
        // noise_w=0.8, sentence_silence_sec=0.2, speaker_id=0,
        // language_id=-1 (auto), speaker_embedding_dim=0.
        let opts = piper_plus_default_options()
        XCTAssertEqual(opts.noise_scale, 0.667, accuracy: 1e-3,
                       "noise_scale default = 0.667")
        XCTAssertEqual(opts.length_scale, 1.0, accuracy: 1e-3,
                       "length_scale default = 1.0")
        XCTAssertEqual(opts.noise_w, 0.8, accuracy: 1e-3,
                       "noise_w default = 0.8")
        XCTAssertEqual(opts.sentence_silence_sec, 0.2, accuracy: 1e-3,
                       "sentence_silence_sec default = 0.2")
        XCTAssertEqual(opts.speaker_id, 0, "speaker_id default = 0")
        XCTAssertEqual(opts.language_id, -1, "language_id default = -1 (auto-detect)")
        XCTAssertEqual(opts.speaker_embedding_dim, 0,
                       "speaker_embedding_dim default = 0 (use speaker_id path)")
    }

    // MARK: - Error info plumbing

    func testGetLastErrorIsReachable() {
        // After a deliberate failure, the symbol must be callable. We
        // don't assert the *content* of the error message because the
        // exact wording is not part of the public contract — only that
        // the symbol is correctly re-exported through `import PiperPlus`
        // and is safe to call from Swift.
        var engine: OpaquePointer?
        _ = piper_plus_create(nil, &engine)
        // Per header: "NUL-terminated error string, or NULL if no error".
        // Either return is acceptable; we only verify the call is safe.
        _ = piper_plus_get_last_error()
    }
}

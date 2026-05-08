// ConcurrencyTests.swift — exercises `Phonemizer.@unchecked Sendable`.
//
// The Swift wrapper marks `Phonemizer` as `@unchecked Sendable` because
// the underlying Rust FFI is read-only after `init`. These tests verify
// that multiple Tasks can call `phonemize(_:language:)` concurrently on
// the same instance without crashing or returning corrupt results, and
// that creating Phonemizer instances in parallel is safe.

import XCTest
@testable import PiperPlusG2P

final class ConcurrencyTests: XCTestCase {
    func testParallelPhonemizeOnSingleInstance() async throws {
        let phonemizer = try Phonemizer(
            languages: [.english, .japanese, .chinese]
        )

        let inputs: [(text: String, lang: Language, expectedLang: String)] = [
            ("hello world", .english, "en"),
            ("こんにちは", .japanese, "ja"),
            ("你好", .chinese, "zh"),
        ]

        await withTaskGroup(of: (String, [String])?.self) { group in
            for i in 0..<60 {
                let item = inputs[i % inputs.count]
                group.addTask {
                    guard let result = try? phonemizer.phonemize(
                        item.text, language: item.lang
                    ) else { return nil }
                    return (result.language, result.tokens)
                }
            }

            var ok = 0
            for await result in group {
                guard let (lang, tokens) = result else { continue }
                XCTAssertFalse(tokens.isEmpty, "tokens must not be empty for lang=\(lang)")
                XCTAssertTrue(["en", "ja", "zh"].contains(lang),
                              "unexpected language echo: \(lang)")
                ok += 1
            }
            XCTAssertEqual(ok, 60, "all 60 concurrent calls should succeed")
        }
    }

    func testParallelInstanceCreation() async throws {
        let count = await withTaskGroup(of: Phonemizer?.self, returning: Int.self) { group in
            for _ in 0..<20 {
                group.addTask { try? Phonemizer(languages: [.english]) }
            }
            var ok = 0
            for await instance in group {
                if instance != nil { ok += 1 }
            }
            return ok
        }
        XCTAssertEqual(count, 20, "all 20 parallel inits should succeed")
    }

    func testRepeatedInitDeinit() throws {
        // Stress deinit path: create + drop 100 instances. Detects FFI
        // double-free or use-after-free under address-sanitizer (when CI
        // is run with `swift test --sanitize=address`); under ordinary
        // builds, asserts that every iteration produces a usable handle
        // — i.e. the registry is rebuilt cleanly each time and previous
        // deinit did not leave a global in a poisoned state.
        for i in 0..<100 {
            let p = try Phonemizer(languages: [.english])
            let langs = p.availableLanguages
            XCTAssertTrue(
                langs.contains(.english),
                "iteration \(i): repeated init/deinit must continue to register requested languages"
            )

            // Run a representative phonemize on every 10th iteration to make
            // sure the pipeline stays functional, not just constructable.
            // (Doing it every iteration would slow the test 100×.)
            if i % 10 == 0 {
                let result = try p.phonemize("hello", language: .english)
                XCTAssertEqual(result.language, "en", "iteration \(i): language echo mismatch")
                XCTAssertFalse(result.tokens.isEmpty, "iteration \(i): tokens unexpectedly empty")
            }
        }
    }
}

// HelloG2P/main.swift — minimal CLI demo for PiperPlusG2P (Issue #387).
//
// Usage:
//   swift run HelloG2P                              # default samples
//   swift run HelloG2P "ja:こんにちは" "en:hi"      # custom inputs
//
// Each input is passed as `<lang>:<text>` where lang is one of the 8
// language codes recognized by PiperPlusG2P (ja, en, zh, ko, es, fr, pt, sv).
// Output is one phonemized line per input on stdout, errors on stderr.

import Foundation
import PiperPlusG2P

struct InvalidArgument: Error, CustomStringConvertible {
    let arg: String
    var description: String {
        "invalid argument \"\(arg)\" — expected <lang>:<text> with lang ∈ ja/en/zh/ko/es/fr/pt/sv"
    }
}

func parse(_ arg: String) throws -> (Language, String) {
    let parts = arg.split(separator: ":", maxSplits: 1)
    guard parts.count == 2, let lang = Language(rawValue: String(parts[0])) else {
        throw InvalidArgument(arg: arg)
    }
    return (lang, String(parts[1]))
}

let defaultSamples: [(Language, String)] = [
    (.japanese, "こんにちは、世界。"),
    (.english, "Hello, world!"),
    (.chinese, "你好，世界。"),
]

let arguments = Array(CommandLine.arguments.dropFirst())
let samples: [(Language, String)]
do {
    samples = arguments.isEmpty ? defaultSamples : try arguments.map(parse)
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(2)
}

// Register exactly the languages we plan to use — registering all 8
// would still work, but each unused language adds startup cost (NAIST-JDIC
// alone is ~25 MB) and binary size for no benefit.
let requested = Array(Set(samples.map(\.0)))

let phonemizer: Phonemizer
do {
    phonemizer = try Phonemizer(languages: requested)
} catch {
    FileHandle.standardError.write(Data("init failed: \(error)\n".utf8))
    exit(1)
}

print("Registered: \(phonemizer.availableLanguages.map(\.rawValue).sorted().joined(separator: ", "))")
print("")

for (lang, text) in samples {
    do {
        let result = try phonemizer.phonemize(text, language: lang)
        print("[\(lang.rawValue)] \(text)")
        print("  tokens (\(result.tokens.count)): \(result.tokens.joined(separator: " "))")
        print("")
    } catch {
        FileHandle.standardError.write(
            Data("phonemize failed for \(lang.rawValue) \"\(text)\": \(error)\n".utf8)
        )
    }
}

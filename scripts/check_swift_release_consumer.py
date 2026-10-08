"""Prepare a clean SwiftPM consumer for a published, exact release version."""

import argparse
import re
from pathlib import Path
from textwrap import dedent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("Invalid release version: expected MAJOR.MINOR.PATCH")
    destination = args.destination
    destination.mkdir(parents=True, exist_ok=True)
    # Only the immutable 2.0.0 manifest needs this documented workaround.
    # Later releases must prove that their own transitive SDK pin works.
    ort_override = (
        '.package(url: "https://github.com/microsoft/onnxruntime-swift-package-manager", exact: "1.20.0"),'
        if args.version == "2.0.0"
        else ""
    )
    (destination / "Package.swift").write_text(
        dedent(
            """\
            // swift-tools-version: 5.9
            import PackageDescription
            let package = Package(
                name: "ReleaseConsumer",
                platforms: [.macOS(.v13)],
                dependencies: [
                    .package(url: "https://github.com/ayutaz/piper-plus", exact: "__VERSION__"),
                    __ORT_OVERRIDE__
                ],
                targets: [
                    .executableTarget(
                        name: "ReleaseConsumer",
                        dependencies: [
                            .product(name: "PiperPlusG2P", package: "piper-plus"),
                        ]
                    ),
                ]
            )
            """
        )
        .replace("__VERSION__", args.version)
        .replace("__ORT_OVERRIDE__", ort_override),
        encoding="utf-8",
    )
    source = destination / "Sources/ReleaseConsumer/main.swift"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        dedent(
            """\
            import PiperPlusG2P
            let phonemizer = try Phonemizer(languages: [.japanese, .english, .chinese])
            let samples: [(Language, String)] = [
                (.japanese, "こんにちは、世界。"),
                (.english, "Hello, world!"),
                (.chinese, "你好，世界。"),
            ]
            for (language, text) in samples {
                let result = try phonemizer.phonemize(text, language: language)
                guard !result.tokens.isEmpty,
                      result.tokens.contains(where: { !$0.isEmpty }) else {
                    fatalError("Empty phonemes for \\(language.rawValue)")
                }
                print("\\(language.rawValue): \\(result.tokens.joined(separator: " "))")
            }
            """
        ),
        encoding="utf-8",
    )
    print(f"Prepared public SwiftPM consumer for {args.version}: {destination}")


if __name__ == "__main__":
    main()

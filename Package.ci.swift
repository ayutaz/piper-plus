// swift-tools-version: 5.9
//
// CI-only Package manifest — used by .github/workflows/swift-g2p-ci.yml.
//
// The release `Package.swift` declares the synthesis engine (`PiperPlus`)
// alongside `PiperPlusG2P` with URL-based binaryTargets that point at
// GitHub Release assets. Those URLs do not resolve before tag publication,
// so `swift test` cannot run on the release manifest pre-release.
//
// This file is the smallest manifest that lets CI exercise
// `PiperPlusG2PTests` against the locally-built xcframework:
//
//   1. swift-g2p-ci.yml builds piper-plus-g2p as a universal macOS
//      staticlib, generates the C header via cbindgen, and assembles
//      `build-mac/piper_plus_g2p.xcframework`.
//   2. CI runs `cp Package.ci.swift Package.swift` so SwiftPM consumes
//      this manifest instead of the release one.
//   3. `swift test --filter PiperPlusG2PTests` runs against the local
//      xcframework via `path:` instead of `url:` + `checksum:`.
//
// **Tracked, not generated.** Keeping this file in git (rather than
// emitting it from a heredoc inside the workflow) means any divergence
// between release and CI manifests is visible in `git diff`, reviewable
// in PRs, and survives editor / CI engine churn. Drop the synthesis
// engine target here only — Sources/PiperPlusG2P/* files referenced
// below MUST stay byte-for-byte identical to what the release manifest
// imports.
//
// Adding a new dependency or platform constraint to release `Package.swift`?
// Mirror it here so CI catches the issue before tag time, *not* after.

import PackageDescription

let package = Package(
    name: "PiperPlusG2PCI",
    // Match the release manifest's iOS target so any iOS-only API used
    // in Sources/PiperPlusG2P/*.swift fails to compile here too. macOS
    // is added because SwiftPM CI runs `swift test` on a macOS runner.
    platforms: [
        .iOS(.v15),
        .macOS(.v13),
    ],
    products: [
        .library(name: "PiperPlusG2P", targets: ["PiperPlusG2P"]),
    ],
    targets: [
        .target(
            name: "PiperPlusG2P",
            dependencies: [.target(name: "PiperPlusG2PBinary")],
            path: "Sources/PiperPlusG2P"
        ),
        .binaryTarget(
            name: "PiperPlusG2PBinary",
            // Path is relative to repo root (== package root). The
            // workflow assembles this xcframework before invoking
            // `swift test` (see Assemble step in swift-g2p-ci.yml).
            path: "build-mac/piper_plus_g2p.xcframework"
        ),
        .testTarget(
            name: "PiperPlusG2PTests",
            dependencies: ["PiperPlusG2P"],
            path: "tests/PiperPlusG2PTests"
        ),
    ]
)

// swift-tools-version: 5.9
//
// HelloG2P — minimal CLI demo for PiperPlusG2P (Issue #387).
//
// This is a standalone Swift Package that depends on the published
// piper-plus release (`from: "1.14.0"`). To run it locally:
//
//   cd examples/swift-g2p/HelloG2P
//   swift run HelloG2P
//
// Pre-release / in-tree development: comment out the URL-based dependency
// below and uncomment the `path:` form. SwiftPM will then resolve against
// the in-tree Package.swift at the piper-plus repo root, which works even
// when v1.14.0 has not been tagged yet (you must build the xcframework
// locally first — see examples/swift-g2p/README.md § Local Development).

import PackageDescription

let package = Package(
    name: "HelloG2P",
    // macOS-only: the executable target needs a host runtime, and iOS
    // executables can't be `swift run`. PiperPlusG2P itself supports both
    // iOS and macOS (xcframework ships all three slices since v1.14.0) —
    // see docs/guides/swift-g2p-integration.md for iOS app integration.
    platforms: [.macOS(.v13)],
    dependencies: [
        // Tag-based dependency. Replace with the local `path:` form below
        // for pre-release testing.
        .package(url: "https://github.com/ayutaz/piper-plus", from: "1.14.0"),
        // .package(name: "piper-plus", path: "../../.."),
    ],
    targets: [
        .executableTarget(
            name: "HelloG2P",
            dependencies: [
                .product(name: "PiperPlusG2P", package: "piper-plus"),
            ]
        ),
    ]
)

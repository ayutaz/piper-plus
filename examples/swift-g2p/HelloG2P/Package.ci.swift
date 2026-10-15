// swift-tools-version: 5.9
//
// CI-only Package manifest for HelloG2P — used by .github/workflows/swift-g2p-ci.yml.
//
// The release HelloG2P/Package.swift declares a tag-based dependency
// (`from: "2.0.1"`) on `https://github.com/ayutaz/piper-plus`, using the
// published release and its xcframework. CI uses the local binary built
// from the current source instead of downloading that published binary.
//
// CI swaps in this file (`cp Package.ci.swift Package.swift`) so the
// HelloG2P consumer resolves against the in-tree workspace at
// `../../..` — which has *already been swapped* to its own
// `Package.ci.swift` earlier in the same workflow (the root CI manifest
// uses `path:`-based binaryTarget pointing at the locally-built
// `build-mac/piper_plus_g2p.xcframework`).
//
// Layered swap pattern:
//   repo-root/Package.swift     <- copied from repo-root/Package.ci.swift
//   HelloG2P/Package.swift      <- copied from HelloG2P/Package.ci.swift (this file)
//
// Tracked in git (not heredoc'd from the workflow) so the example's
// CI version is reviewable in `git diff` like the production manifest.
// Drift between this and `examples/swift-g2p/HelloG2P/Package.swift`
// (release form) is also visible at PR time.

import PackageDescription

let package = Package(
    name: "HelloG2P",
    // Match the release manifest: macOS-only host runtime so `swift run`
    // works directly on the macOS CI runner.
    platforms: [.macOS(.v13)],
    dependencies: [
        // path: form resolves the in-tree workspace, bypassing the
        // published v2.0.1 binary URL. The repo root's
        // Package.swift in CI is itself the swapped Package.ci.swift,
        // which points PiperPlusG2PBinary at build-mac/piper_plus_g2p.xcframework.
        .package(name: "piper-plus", path: "../../.."),
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

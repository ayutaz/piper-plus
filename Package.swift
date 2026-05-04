// swift-tools-version: 5.9
//
// piper-plus Swift Package Manager manifest
//
// Distributes the iOS xcframework via `binaryTarget(url:, checksum:)` pointing
// at the corresponding GitHub Release asset. Version and checksum below are
// updated automatically by `.github/workflows/release-shared-lib.yml` on each
// tag push (see "Update Package.swift checksum" step).
//
// For consumer-facing usage, see:
//   - examples/swift/README.md  (SPM quick start + manual drag-and-drop)
//   - docs/guides/ios-integration.md  (cross-runtime guide)
//   - docs/spec/ios-shared-lib.md  (specification)
//
// ONNX Runtime is declared as a dependency via Microsoft's official SPM
// package, pinned to the same version M2 links against (see
// docs/spec/ort-versions.md). Consumers DO NOT need to add ORT separately
// — it transparently flows through this package.

import PackageDescription

// Updated by CI on tag push. The placeholder values below are intentionally
// invalid until the first v1.13.0 release lands; `swift package resolve` will
// succeed only against tags that have a corresponding release asset.
let version = "1.13.0"
let checksum = "0000000000000000000000000000000000000000000000000000000000000000"

let package = Package(
    name: "PiperPlus",
    platforms: [
        .iOS(.v15),
        .macOS(.v12),
    ],
    products: [
        .library(
            name: "PiperPlus",
            targets: ["PiperPlus"]
        ),
    ],
    dependencies: [
        // ORT version is pinned to match M2's CMake build (1.17.0).
        // Bumping this requires bumping `release-shared-lib.yml`'s
        // ONNXRUNTIME_VERSION and `docs/spec/ort-versions.md` in lockstep.
        .package(
            url: "https://github.com/microsoft/onnxruntime-swift-package-manager",
            exact: "1.17.0"
        ),
    ],
    targets: [
        .binaryTarget(
            name: "PiperPlus",
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(version)/libpiper_plus-ios-\(version).xcframework.zip",
            checksum: checksum
        ),
    ]
)

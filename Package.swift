// swift-tools-version: 5.9
//
// piper-plus Swift Package Manager manifest
//
// Distributes the iOS xcframework via `binaryTarget(url:, checksum:)` pointing
// at the corresponding GitHub Release asset.
//
// IMPORTANT — release flow (sherpa-onnx-style manual update, see Issue #377):
//
// SwiftPM resolves `binaryTarget(url:, checksum:)` against the manifest as it
// exists at the resolved git ref (typically a tag). The version + checksum
// below MUST therefore be present at the tag commit itself; updating them in
// a follow-up commit on `dev` does NOT retroactively fix `swift package
// resolve` for the already-published tag.
//
// Maintainer release procedure:
//   1. On `dev`, run `release-shared-lib.yml` via `workflow_dispatch` (no tag).
//      The `Assemble piper_plus.xcframework` job uploads
//      `libpiper_plus-ios.xcframework.zip` as a workflow artifact.
//   2. Download the artifact zip locally and compute its checksum:
//        swift package compute-checksum libpiper_plus-ios.xcframework.zip
//   3. Update the `version` and `checksum` constants below to match the
//      upcoming release tag (e.g. `v1.13.0`) and the computed checksum.
//   4. Commit on `dev`:    `chore(spm): bump Package.swift to v1.13.0`
//   5. Tag on `dev`:       `git tag v1.13.0 && git push origin v1.13.0`
//      The release workflow re-builds the same artifact (deterministic), so
//      the checksum continues to match. SwiftPM resolution against the new
//      tag now succeeds.
//
// For consumer-facing usage, see:
//   - examples/swift/README.md  (SPM quick start + manual drag-and-drop)
//   - docs/guides/ios-integration.md  (cross-runtime guide)
//   - docs/spec/ios-shared-lib.md  (specification)
//
// ONNX Runtime is NOT declared as an SPM dependency here:
//   - SwiftPM `binaryTarget` cannot declare `dependencies`, so even if we
//     listed `onnxruntime-swift-package-manager`, it would not be linked
//     transitively to consumer targets.
//   - Consumer apps must add the ORT package themselves (see
//     `examples/swift/README.md` for the consumer-side `Package.swift`
//     template). This matches the sherpa-onnx-spm convention.

import PackageDescription

// Updated manually before each tag push (see header comment, step 3).
// The placeholder values below are intentionally invalid until the first
// v1.13.0 release lands; `swift package resolve` succeeds only against tags
// where this manifest was updated to match a published release asset.
let version = "1.13.0"
let checksum = "0000000000000000000000000000000000000000000000000000000000000000"

let package = Package(
    name: "PiperPlus",
    // iOS-only: the released xcframework currently contains
    // ios-arm64 + ios-arm64_x86_64-simulator slices. macOS / visionOS /
    // Mac Catalyst slices are M5 candidates (see docs/spec/ios-shared-lib.md).
    platforms: [
        .iOS(.v15),
    ],
    products: [
        .library(
            name: "PiperPlus",
            targets: ["PiperPlus"]
        ),
    ],
    targets: [
        .binaryTarget(
            name: "PiperPlus",
            // The release-shared-lib workflow renames the asset to
            // `libpiper_plus-ios-v${VERSION}.xcframework.zip` (with the
            // leading `v`), so the URL below interpolates `v\(version)` to
            // match.
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(version)/libpiper_plus-ios-v\(version).xcframework.zip",
            checksum: checksum
        ),
    ]
)

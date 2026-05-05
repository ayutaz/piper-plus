// swift-tools-version: 5.9
//
// piper-plus Swift Package Manager manifest
//
// Distributes the iOS xcframework via `binaryTarget(url:, checksum:)` pointing
// at the corresponding GitHub Release asset, wrapped in a `target` that pulls
// onnxruntime as a transitive dependency.
//
// Consumer usage (just one package):
//
//   .package(url: "https://github.com/ayutaz/piper-plus", from: "1.13.0")
//
// `import PiperPlus` then re-exports the C API from the bundled xcframework,
// and onnxruntime is linked automatically through the wrapper target.
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
// Tag-time CI guards:
//   - The `release` job verifies that this `Package.swift` has a non-placeholder
//     checksum (rejects all-zero), AND that it matches the released
//     xcframework zip's SHA-256. A mismatch fails the release before publishing.
//
// For consumer-facing usage, see:
//   - examples/swift/README.md  (SPM quick start + manual drag-and-drop)
//   - docs/guides/ios-integration.md  (cross-runtime guide)
//   - docs/spec/ios-shared-lib.md  (specification)

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
    // Mac Catalyst slices are not yet supported (see docs/spec/ios-shared-lib.md §6).
    platforms: [
        .iOS(.v15),
    ],
    products: [
        .library(
            name: "PiperPlus",
            targets: ["PiperPlus"]
        ),
    ],
    dependencies: [
        // ONNX Runtime is required at runtime (the xcframework's static
        // archive references _OrtCreateEnv etc.). We pull it via Microsoft's
        // official SwiftPM package and re-export through the wrapper target
        // so consumers don't have to declare it themselves.
        .package(
            url: "https://github.com/microsoft/onnxruntime-swift-package-manager",
            from: "1.17.0"
        ),
    ],
    targets: [
        // Wrapper Swift target — exists so we can attach `dependencies:`
        // (binaryTarget cannot). It re-exports `PiperPlusBinary` so
        // `import PiperPlus` from consumer code surfaces the full C API.
        .target(
            name: "PiperPlus",
            dependencies: [
                .target(name: "PiperPlusBinary"),
                .product(
                    name: "onnxruntime",
                    package: "onnxruntime-swift-package-manager"
                ),
            ],
            path: "Sources/PiperPlus"
        ),
        // Binary xcframework — produced by .github/workflows/release-shared-lib.yml.
        // The release-shared-lib workflow renames the asset to
        // `libpiper_plus-ios-v${VERSION}.xcframework.zip` (with the leading
        // `v`), so the URL below interpolates `v\(version)` to match.
        .binaryTarget(
            name: "PiperPlusBinary",
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(version)/libpiper_plus-ios-v\(version).xcframework.zip",
            checksum: checksum
        ),
    ]
)

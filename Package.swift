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

// G2P-only artifact — produced by the same release workflow but as a
// separate xcframework that does NOT depend on ONNX Runtime. Consumers
// who need only G2P (text → IPA tokens) can pull just `PiperPlusG2P`.
// Bumped independently of the synthesis `version` above: the G2P product
// debuts in v1.14.0 (Issue #387), one tag after the synthesis xcframework
// (which shipped at v1.13.0 per Issue #377). Both follow the same manual
// release procedure documented in the file header.
//
// The G2P xcframework ships iOS device + iOS simulator + macOS slices as
// of v1.14.0 — the artifact name is `-apple-` (not `-ios-`) to reflect
// the broader Apple platform coverage. The synthesis xcframework remains
// iOS-only because its ORT dependency has its own macOS distribution.
//
// IMPORTANT: until the v1.14.0 tag publishes the xcframework asset and
// this checksum is updated, `swift package resolve` against this manifest
// will fail with "artifact has changed checksum" / "asset not found".
// Consumers should depend on a *tagged* version (`from: "1.14.0"`), not
// the dev branch.
let g2pVersion = "1.14.0"
let g2pChecksum = "0000000000000000000000000000000000000000000000000000000000000000"

let package = Package(
    name: "PiperPlus",
    // Package-level minimum platforms. PiperPlus (synthesis engine) is
    // effectively iOS-only — its xcframework only contains ios-arm64 +
    // ios-arm64_x86_64-simulator slices, and consumer linking against it
    // from a macOS target will fail at SPM resolve time. macOS is declared
    // here only so PiperPlusG2P (which has a macOS slice in v1.14.0+) can
    // be consumed from `swift run` / macOS CLI targets without forcing the
    // consumer to drop iOS-only references entirely. visionOS / Mac
    // Catalyst slices are not yet supported (see
    // docs/spec/ios-shared-lib.md §6 and docs/spec/swift-g2p.md §7.1).
    platforms: [
        .iOS(.v15),
        .macOS(.v13),
    ],
    products: [
        .library(
            name: "PiperPlus",
            targets: ["PiperPlus"]
        ),
        // G2P-only product — no ONNX Runtime dependency. See
        // docs/guides/swift-g2p-integration.md for usage.
        .library(
            name: "PiperPlusG2P",
            targets: ["PiperPlusG2P"]
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
        // PiperPlusG2P (Issue #387) — Swift wrapper around the Rust
        // piper-plus-g2p crate's C FFI. Independent from the synthesis
        // engine: no ORT dependency, ~3-5 MB xcframework after compression.
        .target(
            name: "PiperPlusG2P",
            dependencies: [
                .target(name: "PiperPlusG2PBinary"),
            ],
            path: "Sources/PiperPlusG2P"
        ),
        // The artifact filename uses `-apple-` (not `-ios-`) since v1.14.0
        // because the xcframework now bundles iOS device + iOS simulator +
        // macOS slices. Older `-ios-` URLs are *not* maintained.
        .binaryTarget(
            name: "PiperPlusG2PBinary",
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(g2pVersion)/libpiper_plus_g2p-apple-v\(g2pVersion).xcframework.zip",
            checksum: g2pChecksum
        ),
        // Test target — runs against the resolved binaryTarget. Excluded
        // from `swift build` until a published xcframework is available.
        .testTarget(
            name: "PiperPlusG2PTests",
            dependencies: ["PiperPlusG2P"],
            path: "tests/PiperPlusG2PTests"
        ),
    ]
)

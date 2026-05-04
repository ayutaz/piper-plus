// PiperPlus — Swift Package Manager wrapper module.
//
// This file exists so SwiftPM has a Swift `target` to attach package
// dependencies to. `binaryTarget` cannot declare its own dependencies, so we
// wrap it: `PiperPlusBinary` is the xcframework, `PiperPlus` (this target)
// pulls onnxruntime transitively and re-exports the C API.
//
// Consumer code:
//
//   import PiperPlus
//   let synth = piper_plus_create(...)        // C API from piper_plus.h
//
// The actual API surface lives in `piper_plus.h` inside the xcframework,
// exposed via `module.modulemap`. The `@_exported import` below makes those
// C symbols visible through `PiperPlus` without consumers having to import
// `PiperPlusBinary` directly.

@_exported import PiperPlusBinary

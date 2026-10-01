# piper-plus-g2p

Multilingual G2P (Grapheme-to-Phoneme) for TTS. eSpeak-ng free. MIT licensed. 8 languages.

## Why piper-plus-g2p?

- **MIT licensed** -- no eSpeak-ng (GPL) dependency in your TTS pipeline
- **8 languages** -- JA, EN, ZH, KO, ES, FR, PT, SV with consistent IPA output
- **IPA-first design** -- returns pure IPA token sequences; encoding to model-specific phoneme IDs is a separate step

## Quick Start

Add to your `Cargo.toml`:

```toml
[dependencies]
piper-plus-g2p = { version = "0.4", features = ["naist-jdic"] }
```

```rust
use piper_plus_g2p::{Phonemizer, PhonemizerRegistry, PiperEncoder, UnknownTokenMode};
use piper_plus_g2p::english::EnglishPhonemizer;

let mut registry = PhonemizerRegistry::new();
registry.register("en", Box::new(EnglishPhonemizer::new().unwrap()));

let phonemizer = registry.get("en").unwrap();
let (tokens, prosody) = phonemizer
    .phonemize_with_prosody("Hello, world!")
    .unwrap();

// Encode tokens to phoneme IDs for a Piper ONNX model:
// let encoder = PiperEncoder::new(phoneme_id_map, UnknownTokenMode::Strict)?;
// let ids = encoder.encode(&tokens)?;
```

## Feature Flags

| Flag | Default | Description |
|---|---|---|
| `english` | **on** | Enable English phonemizer |
| `chinese` | **on** | Enable Chinese phonemizer |
| `korean` | **on** | Enable Korean phonemizer |
| `spanish` | **on** | Enable Spanish phonemizer |
| `french` | **on** | Enable French phonemizer |
| `portuguese` | **on** | Enable Portuguese phonemizer |
| `japanese` | off | Enable Japanese phonemizer (pulls in `jpreprocess`) |
| `naist-jdic` | off | Bundle the NAIST-JDIC dictionary for Japanese (implies `japanese`) |
| `all-languages` | off | Enable all language backends including `japanese` |
| `ffi` | off | Expose C-compatible FFI symbols (`piper_plus_g2p_*`) for mobile bindings |
| `bundled-dicts` | off | Embed `cmudict_data.json` / `pinyin_*.json` via `include_str!`/`include_bytes!`. Required for iOS App Sandbox. Adds ~6.3 MB to the binary. |

To use only specific languages, disable defaults:

```toml
[dependencies]
piper-plus-g2p = { version = "0.4", default-features = false, features = ["english", "japanese"] }
```

## Supported Languages

| Language | Code | Feature flag | Backend |
|---|---|---|---|
| Japanese | `ja` | `japanese` | jpreprocess (NAIST-JDIC) |
| English | `en` | `english` | Rule-based (CMUdict-derived) |
| Chinese | `zh` | `chinese` | Pinyin-to-IPA |
| Korean | `ko` | `korean` | Rule-based |
| Spanish | `es` | `spanish` | Rule-based |
| French | `fr` | `french` | Rule-based |
| Portuguese (BR) | `pt` / `pt-BR` | `portuguese` | Rule-based |
| Portuguese (EU) | `pt-PT` / `pt-pt` | `portuguese` | Rule-based + EU post-processing (palatalisation, final-e, final-s, coda-l, r-realization) |
| Swedish    | `sv` | `swedish`    | Rule-based |

### Brazilian vs European Portuguese

`PortuguesePhonemizer::new(Dialect::BR)` and `PortuguesePhonemizer::new(Dialect::EU)`
share the same class but differ in five post-processing transformations
(see `docs/spec/pt-dialect-contract.toml`). EU also introduces the central
vowel `ɨ` and the velarised lateral `ɫ` (registered in the PUA contract).

## SSML Basic Profile

`piper-plus-g2p` is the **Rust canonical** SSML parser for the entire
project. The `ssml` module exposes `is_ssml(text)` / `parse(text)` /
`Segment` types covering `<speak>`, `<break time="..." strength="...">`,
and `<prosody rate="...">` (W3C SSML subset). `piper-core` re-exports
`piper_plus_g2p::ssml`, and `piper-plus-wasm` exposes the same API as
`isSsml` / `parseSsml` to JavaScript.

## Piper Model Compatibility

Use `PiperEncoder` to convert IPA tokens to phoneme IDs for Piper ONNX models:

```rust
use piper_plus_g2p::encode::{PiperEncoder, UnknownTokenMode};

// Load phoneme_id_map from model's config.json
let encoder = PiperEncoder::new(phoneme_id_map, UnknownTokenMode::Strict)?;
let phoneme_ids = encoder.encode(&tokens)?;
```

### Direct IPA input (Rust, next release)

If your application already produces IPA, for example for a constructed language
in a game, skip the language phonemizer entirely:

```rust
use piper_plus_g2p::{PhonemeIdMap, PiperEncoder, UnknownTokenMode};

let config: serde_json::Value =
    serde_json::from_str(&std::fs::read_to_string("voice.onnx.json")?)?;
let map: PhonemeIdMap = serde_json::from_value(config["phoneme_id_map"].clone())?;
let encoder = PiperEncoder::new(map, UnknownTokenMode::Strict)?;
let phoneme_ids = encoder.encode_ipa("ka")?;
```

Use the config shipped with the **same ONNX model** used for synthesis. IPA has no
universal numeric ID table. No G2P registration, dictionary, or language backend
is required; `default-features = false` is sufficient for this API.

`encode_ipa` uses the following rules:

- Match the longest token supported by the target model. Canonical PUA spellings
  are considered only when that PUA key is present in the model's map.
- Resolve literal model keys before PUA aliases. For example, `tʃ` can map to
  one PUA token in a piper-plus model, or to `t` and `ʃ` in a character-based
  model. Direct multi-character keys are supported as well.
- Add `BOS, PAD, token IDs, PAD, ..., EOS`. A token may expand to multiple IDs;
  the PAD is inserted after the whole ID list.
- Reject unknown symbols with their UTF-8 byte offset, even when the encoder
  was constructed with `UnknownTokenMode::Skip`.
- Preserve spaces as word-boundary tokens **only if the model supports them**.
  Spaces are not separators between manually specified phonemes. Do not include
  transcription wrappers such as `/ka/` or `[ka]`.
- Reject empty input and caller-supplied `^`, `$`, `_` boundary/padding markers.

You can inspect segmentation separately with
`IpaTokenizer::new(&map).tokenize("ka")?` before creating the encoder.

**Ambiguity:** if both `an` and `a`/`n` are supported, the string `an` selects the
compound token. To control boundaries, use `encoder.encode(&["a".into(),
"n".into()])` under the existing G2P/PUA encoding convention. This token-array
API retains its previous behavior, including how it handles unknown symbols.

**Notation and acoustic limits:** matching is literal. Unicode normalization,
tie-bar removal (`t͡ʃ` to `tʃ`), and substitutions such as `y` to `y_vowel`,
`r` to `rr`, or Japanese `iː` to `i:` are not inferred. Use the model's token
spellings explicitly. The tokenizer also accepts existing internal token
spellings; it is not a validator for the complete IPA standard. ID conversion
does not add untrained sounds or derive accent, tone, or prosody features.
Constructed-language pronunciation quality still depends on the trained model.

`encode::tokens_to_ids` is a lower-level exact map lookup for already-encoded
symbols. It performs neither PUA conversion nor BOS/EOS/PAD insertion; it is not
the general entry point for clean IPA input.

## C FFI (Mobile Bindings)

Enable the `ffi` feature for C-compatible functions suitable for
iOS (Swift) and Android (Kotlin) bindings:

```toml
piper-plus-g2p = { version = "0.4", features = ["ffi", "all-languages", "naist-jdic", "bundled-dicts"] }
```

The crate exposes 5 C functions with the `piper_plus_g2p_` prefix:

| Function | Purpose |
|---|---|
| `piper_plus_g2p_create(const char *langs)` | Create a handle, registering the comma-separated language codes (or NULL for the feature-derived default set). |
| `piper_plus_g2p_phonemize(handle, text, lang)` | Run G2P; returns an owned UTF-8 JSON string `{"tokens": [...], "language": "..."}` on success, or NULL on failure / panic. |
| `piper_plus_g2p_available_languages(handle)` | Return an owned UTF-8 comma-separated list of currently registered language codes. |
| `piper_plus_g2p_free_string(char *)` | Free a string returned by `phonemize` / `available_languages`. No-op on NULL. |
| `piper_plus_g2p_free(handle)` | Drop the handle. No-op on NULL. |

All entry points are wrapped in `catch_unwind`, so Rust panics never
cross the FFI boundary. See `src/ffi.rs` and `cbindgen.toml` for the
canonical signatures.

### iOS / App Sandbox

For iOS — where loading external dictionary files is impractical due
to App Sandbox — enable `bundled-dicts` to embed JSON dictionaries
into the binary. Use `EnglishPhonemizer::new_bundled()` and
`ChinesePhonemizer::new_bundled()` for in-memory initialization.

The Swift wrapper is distributed separately as the `PiperPlusG2P`
SPM product (xcframework). See
[docs/guides/platform/swift-g2p-integration.md](../../../docs/guides/platform/swift-g2p-integration.md).

## Cross-Platform Consistency

Also available as:

- **Python**: `piper-plus-g2p` on PyPI
- **npm**: `@piper-plus/g2p` for browser/WASM
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize`
- **Kotlin (Android)**: `io.github.ayutaz:piper-plus-g2p-android` on Maven Central
- **Swift (iOS / macOS)**: `PiperPlusG2P` product in [Package.swift](../../../Package.swift) (SPM)

All implementations share the same PUA mapping, the same `zh_en_loanword.json`
canonical dictionary (10-mirror sync, CI gated), and are validated against a
common test fixture.

## Minimum Supported Rust Version

1.88

## License

MIT

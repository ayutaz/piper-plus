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
piper-plus-g2p = { version = "0.1", features = ["naist-jdic"] }
```

```rust
use piper_plus_g2p::{Phonemizer, PhonemizerRegistry};
use piper_plus_g2p::english::EnglishPhonemizer;

let mut registry = PhonemizerRegistry::new();
registry.register("en", Box::new(EnglishPhonemizer::new().unwrap()));

let phonemizer = registry.get("en").unwrap();
let (tokens, prosody) = phonemizer
    .phonemize_with_prosody("Hello, world!")
    .unwrap();

// Encode tokens to phoneme IDs for a Piper ONNX model:
// let ids = piper_plus_g2p::encode::tokens_to_ids(&tokens, &phoneme_id_map)?;
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

To use only specific languages, disable defaults:

```toml
[dependencies]
piper-plus-g2p = { version = "0.1", default-features = false, features = ["english", "japanese"] }
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
| Portuguese | `pt` | `portuguese` | Rule-based |
| Swedish    | `sv` | `swedish`    | Rule-based |

## Piper Model Compatibility

Use `PiperEncoder` to convert IPA tokens to phoneme IDs for Piper ONNX models:

```rust
use piper_plus_g2p::encode::{PiperEncoder, UnknownTokenMode};

// Load phoneme_id_map from model's config.json
let encoder = PiperEncoder::new(phoneme_id_map, UnknownTokenMode::Strict)?;
let phoneme_ids = encoder.encode(&tokens)?;
```

## C FFI (Mobile Bindings)

Enable the `ffi` feature for C-compatible functions suitable for
iOS (Swift) and Android (Kotlin) bindings via UniFFI:

```toml
piper-plus-g2p = { version = "0.1", features = ["ffi", "english"] }
```

## Cross-Platform Consistency

Also available as:
- **Python**: `piper-plus-g2p` on PyPI
- **npm**: `@piper-plus/g2p` for browser/WASM
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize`

All implementations share the same PUA mapping and are validated
against a common test fixture.

## Minimum Supported Rust Version

1.88

## License

MIT

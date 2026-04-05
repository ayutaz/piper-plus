# @piper-plus/g2p

Multilingual G2P (Grapheme-to-Phoneme) for TTS. Converts text to IPA phoneme sequences without eSpeak-ng. Runs in the browser via WebAssembly.

## Install

```bash
npm install @piper-plus/g2p
```

## Quick Start

```js
import { G2P } from '@piper-plus/g2p';

// Initialize with desired languages
const g2p = await G2P.create({ languages: ['ja', 'en'] });

// Convert text to IPA tokens
const tokens = g2p.phonemize('Hello, world!');
// => ["h", "ʌ", "l", "oʊ", ",", " ", "w", "ɜː", "l", "d", "!"]

const jaTokens = g2p.phonemize('こんにちは');
// => ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]

// Encode for Piper TTS inference
import { Encoder } from '@piper-plus/g2p/encode';
const encoder = new Encoder(config);
const ids = encoder.encode(tokens);
```

## Per-Language Imports

Each language can be imported independently to minimize bundle size:

```js
import { JapaneseG2P } from '@piper-plus/g2p/ja';
import { EnglishG2P } from '@piper-plus/g2p/en';
import { KoreanG2P } from '@piper-plus/g2p/ko';
import { SwedishG2P } from '@piper-plus/g2p/sv';
```

## Supported Languages

| Language   | Code | Method              | External Dependencies |
|------------|------|---------------------|-----------------------|
| Japanese   | ja   | OpenJTalk WASM      | NAIST-jdic (auto-download) |
| English    | en   | Rule-based          | None |
| Chinese    | zh   | Pinyin-based        | None |
| Spanish    | es   | Rule-based          | None |
| French     | fr   | Rule-based          | None |
| Portuguese | pt   | Rule-based          | None |
| Korean     | ko   | Hangul decomposition | None |
| Swedish    | sv   | Rule-based          | None |

## Features

- **IPA-first** -- `phonemize()` returns IPA token arrays; no PUA encoding by default
- **Prosody info** -- Japanese G2P provides A1/A2/A3 accent features via `phonemizeWithProsody()`
- **Language detection** -- `UnicodeLanguageDetector` auto-detects language from text
- **Custom dictionaries** -- Override pronunciations with JSON v1.0/v2.0 or TSV format
- **Tree-shakeable** -- Per-language subpath exports for minimal bundle size
- **No eSpeak-ng** -- Zero GPL dependencies; fully MIT licensed

## Comparison

| Feature             | @piper-plus/g2p | phonemizer | gruut  | Misaki  |
|---------------------|:--------------:|:----------:|:------:|:-------:|
| License             | MIT            | GPL-3.0    | MIT    | Apache-2.0 |
| Languages           | 8              | 100+       | ~20    | 2       |
| Japanese            | Yes            | No         | No     | Yes     |
| Browser/WASM        | Yes            | No         | No     | No      |
| eSpeak-ng free      | Yes            | No         | Yes    | Yes     |
| Maintained (2026)   | Yes            | Yes        | No     | Yes     |

## API

### `G2P.create(options)`

Creates and initializes a G2P instance.

- `options.languages` -- Array of language codes to load (default: all)
- Returns: `Promise<G2P>`

### `g2p.phonemize(text, lang?)`

Converts text to IPA token array. Language is auto-detected if omitted.

### `g2p.phonemizeWithProsody(text, lang?)`

Returns `{ tokens, prosody }` with per-token prosody features (Japanese only).

### `Encoder.encode(tokens)`

Encodes IPA tokens to Piper-compatible phoneme IDs with BOS/EOS/padding.

## Cross-Platform Consistency

Also available as:
- **Python**: `piper-plus-g2p` on PyPI
- **Rust crate**: `piper-plus-g2p` on crates.io
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize`

All implementations share the same PUA mapping (`pua_compat_version: 1`)
and are validated against a common test fixture.

## Zero Dependencies

@piper-plus/g2p has **zero npm runtime dependencies** for rule-based
languages (EN, ZH, KO, ES, FR, PT, SV). Only Japanese requires the bundled
OpenJTalk WASM binary. This eliminates the most common vector for
supply chain attacks in the JavaScript ecosystem.

## License

MIT

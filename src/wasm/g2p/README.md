# @piper-plus/g2p

Multilingual G2P (Grapheme-to-Phoneme) for TTS. Converts text to IPA phoneme sequences without eSpeak-ng. Runs in the browser via WebAssembly.

## Install

```bash
npm install @piper-plus/g2p
```

## Quick Start

```js
import { G2P } from '@piper-plus/g2p';

// Rule-based languages initialise without an external WASM module.
const g2p = await G2P.create({ languages: ['en'] });

// Convert text to IPA tokens
const { tokens } = g2p.phonemize('Hello, world!', { language: 'en' });
// => ["h", "ʌ", "l", "oʊ", ",", " ", "w", "ɜː", "l", "d", "!"]

// Encode for Piper TTS inference
import { Encoder } from '@piper-plus/g2p/encode';
const config = await fetch('/path/to/model.onnx.json').then((r) => r.json());
const encoder = new Encoder(config.phoneme_id_map);
const { phonemeIds, droppedSymbols } = encoder.encode(tokens);
```

`encode()` returns an object, not an array. `droppedSymbols` lists tokens that
have no entry in `phoneme_id_map` and were skipped; it is added after 0.4.2
(0.4.2 returns `{ phonemeIds }` only).

Japanese additionally requires an OpenJTalk WASM module supplied by the
application and the dictionary data loaded by `DictLoader`:

```js
import { DictLoader } from '@piper-plus/g2p';

const loader = new DictLoader();
const jaDict = await loader.loadJaDict();
const openjtalkModule = await loadOpenJTalkWasmModuleFromYourApp();
const jaG2P = await G2P.create({
  languages: ['ja'],
  openjtalkModule,
  jaDict,
});
const { tokens: jaTokens } = jaG2P.phonemize('こんにちは', { language: 'ja' });
// => ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]
```

`loadOpenJTalkWasmModuleFromYourApp()` represents the generated OpenJTalk
WASM loader chosen by the application; `@piper-plus/g2p` provides the G2P
adapter and dictionary loader, not a universal Emscripten module loader.

## Per-Language Imports

Each language can be imported independently to minimize bundle size:

```js
import { JapaneseG2P } from '@piper-plus/g2p/ja';
import { EnglishG2P } from '@piper-plus/g2p/en';
import { KoreanG2P } from '@piper-plus/g2p/ko';
import { SwedishG2P } from '@piper-plus/g2p/sv';
```

### English dictionary

English reads words from the CMU Pronouncing Dictionary bundled as
`data/cmudict_data.json` (~3.7 MB), after the same text normalization as
Python's g2p_en (numbers, accents, `e.g.` / `i.e.`). It is loaded on demand:
importing the package does not read it, and `G2P.create()` loads it only when
English is enabled, so `G2P.create({ languages: ['ja'] })` never fetches it.

```js
import { EnglishG2P } from '@piper-plus/g2p/en';

const en = await EnglishG2P.create(); // or: new EnglishG2P(); await en.initialize();
en.phonemize('It costs $5.'); // numbers are read as words
```

In Node, `new EnglishG2P().phonemize()` also works without `initialize()`: the
file is read synchronously on first use. In a browser an uninitialised
`EnglishG2P` throws, because the file cannot be fetched synchronously. A
dictionary served from elsewhere can be passed as
`new EnglishG2P({ cmuDict })` or `G2P.create({ cmuDict })` (word -> ARPAbet
string, e.g. `{ hello: 'HH AH0 L OW1' }`).

## Supported Languages

| Language   | Code | Method              | External Dependencies |
|------------|------|---------------------|-----------------------|
| Japanese   | ja   | OpenJTalk WASM      | DictLoader dictionary asset |
| English    | en   | CMU dictionary + g2p_en normalization | Bundled `data/cmudict_data.json` (~3.7 MB, loaded on demand) |
| Chinese    | zh   | Pinyin dictionary (bundled, loaded on demand) | None |
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

- `options.languages` -- Array of language codes to load (default: all 8)
- `options.openjtalkModule` -- OpenJTalk WASM module supplied by the
  application (required for Japanese)
- `options.jaDict` -- Japanese dictionary data from `DictLoader.loadJaDict()`
- `options.customDicts` -- `CustomDictionary` instances applied before
  phonemization
- `options.cmuDict` -- English dictionary (lowercase word -> ARPAbet string)
  used instead of the bundled CMU dictionary (optional; see
  [English dictionary](#english-dictionary))
- `options.pinyinDict` -- Pinyin dictionaries for Chinese, `{ single, phrases }`
  (optional; see [Chinese](#chinese))
- Returns: `Promise<G2P>`

### Chinese

Chinese is read with the pinyin dictionaries bundled in the package
(`data/pinyin_single.json`, `data/pinyin_phrases.json`, about 2.7 MB of JSON),
the same dictionaries and steps as the Rust and Python G2P: longest phrase
match, tone sandhi (T3+T3, 一, 不), pinyin to IPA. English next to Chinese
(`'我用 GPS 导航'`) is read as Mandarin pinyin with the ZH-EN loanword
dictionary.

The dictionaries are loaded only when Chinese is enabled: `G2P.create()` loads
them when `zh` is in `languages` (the default includes it), so pass
`languages` without `zh` if you never phonemize Chinese. To load them from a
place of your own, pass `pinyinDict: { single, phrases }` (parsed JSON objects
or JSON text).

`ChineseG2P` on its own needs `await zh.initialize()` (or the `pinyinDict`
option) first. Before that it is in `fallback` mode and passes every
character through as a token, as earlier versions did.

```js
import { ChineseG2P } from '@piper-plus/g2p/zh';

const zh = await new ChineseG2P().initialize();
zh.phonemize('你好').tokens; // ['n', 'i', 'tone2', 'x', 'aʊ', 'tone3']
```

### `g2p.phonemize(text, options?)`

Converts text to an object containing IPA tokens, prosody placeholders, and the
resolved language. Pass `{ language: 'en' }` (for example) to select a language;
omit the options object for Unicode-based language detection.

### `g2p.phonemizeWithProsody(text, options?)`

Returns `{ tokens, prosody, language }` with per-token prosody features
(Japanese only). Both methods use the same options object.

### `Encoder.encode(tokens)`

Encodes IPA tokens to Piper-compatible phoneme IDs with BOS/EOS/padding and
returns `{ phonemeIds, droppedSymbols }` (`droppedSymbols` is added after
0.4.2). `encodeWithProsody(tokens, prosody)` also returns `prosodyFlat`.

## Cross-Platform Consistency

Also available as:

- **Python**: `piper-plus-g2p` on PyPI
- **Rust crate**: `piper-plus-g2p` on crates.io
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize`

The current runtime export uses PUA compatibility version 2 and is validated
against a common test fixture. The `pua_compat_version` field in `package.json` is
still `1` (also in the published 0.4.2); it must be synchronized before a
release that relies on that field.

## Zero Dependencies

@piper-plus/g2p has **zero npm runtime dependencies**. EN, ZH, KO, ES, FR,
PT, and SV need nothing outside the package. Japanese needs an OpenJTalk WASM
module supplied by the application and the dictionary loaded by `DictLoader`;
the package does not bundle an OpenJTalk WASM binary (the Emscripten build was
retired, and 0.4.2 removed the stale `dist/openjtalk.*` entries). This
eliminates the most common vector for supply chain attacks in the JavaScript
ecosystem.

## License

MIT

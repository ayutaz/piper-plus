# piper-plus-g2p/phonemize

Multilingual G2P (Grapheme-to-Phoneme) for TTS — eSpeak-ng free, MIT licensed. 8 languages.

This is a standalone Go module that can be used independently of the piper-plus TTS engine.

## Install

```sh
go get github.com/ayutaz/piper-plus/src/go/phonemize
```

## Quick Start

```go
import "github.com/ayutaz/piper-plus/src/go/phonemize"

// Single language
p := phonemize.NewEnglishPhonemizer(cmuDict)
result, err := p.PhonemizeWithProsody("Hello, world!")

// Multilingual (auto-detects language from Unicode)
phonemizers := map[string]phonemize.Phonemizer{
    "en": phonemize.NewEnglishPhonemizer(cmuDict),
    "zh": phonemize.NewChinesePhonemizer(),
    "es": phonemize.NewSpanishPhonemizer(),
    "fr": phonemize.NewFrenchPhonemizer(),
    "pt": phonemize.NewPortuguesePhonemizer(),
    "ko": phonemize.NewKoreanPhonemizer(),
    "sv": phonemize.NewSwedishPhonemizer(),
}
mp := phonemize.NewMultilingualPhonemizer(
    []string{"en", "zh", "es", "fr", "pt", "ko", "sv"}, "en", phonemizers,
)
result, err := mp.PhonemizeWithProsody("Hello mundo")
```

## Supported Languages

| Language   | Code | Backend                          | Build tag    |
|------------|------|----------------------------------|--------------|
| Japanese   | `ja` | OpenJTalk (CGo)                  | `openjtalk`  |
| English    | `en` | Rule-based (CMUdict-derived)     | (default)    |
| Chinese    | `zh` | Pinyin-to-IPA                    | (default)    |
| Korean     | `ko` | Rule-based                       | (default)    |
| Spanish    | `es` | Rule-based                       | (default)    |
| French     | `fr` | Rule-based                       | (default)    |
| Portuguese | `pt` | Rule-based                       | (default)    |
| Swedish    | `sv` | Rule-based                       | (default)    |

### Japanese (OpenJTalk)

Japanese requires CGo and the `openjtalk` build tag:

```sh
go build -tags openjtalk
go test -tags openjtalk ./...
```

All other 7 languages work without CGo and have no external dependencies beyond `golang.org/x/text`.

## Custom Dictionary

Override phonemization for specific words:

```go
dict, err := phonemize.LoadDictFile("custom.json")
p := phonemize.WrapPhonemizer(phonemize.NewEnglishPhonemizer(cmuDict), dict)
```

## PUA Encoding

Multi-character phoneme tokens (e.g., `"tʃ"`, `"N_m"`, `"tone1"`) are mapped to
single Unicode codepoints in the Private Use Area (U+E000–U+E058) for compatibility
with Piper ONNX model input format.

## Cross-Platform Consistency

Also available as:
- **Python**: `piper-plus-g2p` on PyPI (`pip install piper-plus-g2p`)
- **Rust**: `piper-plus-g2p` on crates.io
- **npm**: `@piper-plus/g2p` for browser/WASM

All implementations share the same PUA mapping and are validated against a common test fixture.

## License

MIT

// Package phonemize provides text-to-phoneme conversion for 8 languages.
//
// Supported languages: Japanese (ja), English (en), Chinese (zh), Korean (ko),
// Spanish (es), French (fr), Portuguese (pt), Swedish (sv).
//
// Japanese requires OpenJTalk and must be built with the openjtalk build tag:
//
//	go build -tags openjtalk
//
// # Architecture
//
// The package provides a [Phonemizer] interface implemented by
// language-specific phonemizers. [MultilingualPhonemizer] automatically
// detects language from Unicode character ranges and delegates to
// the appropriate language phonemizer.
//
// # PUA (Private Use Area) Encoding
//
// Multi-character phoneme tokens (e.g., "tʃ", "N_m", "tone1") are
// mapped to single Unicode codepoints in the Private Use Area via
// [RegisterToken]. Known tokens use the fixed table (U+E000-U+E064, see
// docs/spec/pua-contract.toml); an unknown multi-character token is given the
// next free codepoint from U+E065 upward. This ensures compatibility with ONNX
// model input format.
//
// # Custom Dictionary
//
// [CustomDictionary] allows overriding phonemization for specific words.
// Use [LoadDictFile] to load dictionary files and
// [CustomDictionary.WrapPhonemizer] to create a dictionary-aware phonemizer.
//
// # Usage
//
//	// Create multilingual phonemizer
//	phonemizers := map[string]phonemize.Phonemizer{
//	    "en": phonemize.NewEnglishPhonemizer(cmuDict),
//	    "es": phonemize.NewSpanishPhonemizer(),
//	}
//	mp := phonemize.NewMultilingualPhonemizer(
//	    []string{"en", "es"}, "en", phonemizers,
//	)
//	result, err := mp.PhonemizeWithProsody("Hello mundo")
package phonemize

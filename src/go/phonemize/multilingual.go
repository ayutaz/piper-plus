package phonemize

import (
	"log/slog"
	"strings"

	"golang.org/x/text/unicode/norm"
)

// bosEosTokens is the set of BOS/EOS tokens to strip from segment output.
var bosEosTokens = map[string]bool{
	"^":                  true,
	"$":                  true,
	"?":                  true,
	string(rune(0xE016)): true, // ?!
	string(rune(0xE017)): true, // ?.
	string(rune(0xE018)): true, // ?~
}

// eosOnlyTokens is the subset of bosEosTokens that are EOS-like (excludes "^").
var eosOnlyTokens = map[string]bool{
	"$":                  true,
	"?":                  true,
	string(rune(0xE016)): true, // ?!
	string(rune(0xE017)): true, // ?.
	string(rune(0xE018)): true, // ?~
}

// MultilingualPhonemizer routes text segments to language-specific phonemizers.
//
// Thread safety: MultilingualPhonemizer is safe for concurrent use.
// All mutable state (EOSToken tracking) is passed through return values,
// not shared fields. The underlying per-language phonemizers must also be
// safe for concurrent use.
type MultilingualPhonemizer struct {
	languages            []string
	defaultLatinLanguage string
	detector             *UnicodeLanguageDetector
	phonemizers          map[string]Phonemizer
}

// NewMultilingualPhonemizer creates a MultilingualPhonemizer for the given
// languages. phonemizers maps language codes to their Phonemizer implementations.
func NewMultilingualPhonemizer(
	languages []string,
	defaultLatinLang string,
	phonemizers map[string]Phonemizer,
) *MultilingualPhonemizer {
	detector := NewUnicodeLanguageDetector(languages, defaultLatinLang)
	return &MultilingualPhonemizer{
		languages:            languages,
		defaultLatinLanguage: defaultLatinLang,
		detector:             detector,
		phonemizers:          phonemizers,
	}
}

// LanguageCode returns the joined language codes (e.g., "ja-en-zh-es-fr-pt").
func (m *MultilingualPhonemizer) LanguageCode() string {
	return strings.Join(m.languages, "-")
}

// PhonemizeWithProsody segments text by language, delegates to per-language
// phonemizers, strips BOS/EOS from each segment, and concatenates the results.
// The dynamically determined EOS token is stored in result.EOSToken.
func (m *MultilingualPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	// Normalize to NFC so that decomposed sequences (e.g. e + combining acute
	// from macOS HFS+ or Web APIs) are folded into their composed equivalents
	// before language detection and phonemization.
	text = norm.NFC.String(text)

	segments := SegmentText(text, m.detector)
	if len(segments) == 0 {
		return &PhonemizeResult{
			EOSToken: "$",
		}, nil
	}

	var allTokens []string
	var allProsody []*ProsodyInfo
	// Default EOS is "$" if no segment produces an explicit EOS token
	// (e.g., "?", "?!", "?.", "?~"). This matches Python's behavior.
	lastEOS := "$"

	for _, seg := range segments {
		phonemizer, ok := m.phonemizers[seg.Language]
		if !ok {
			slog.Warn("no phonemizer registered for language, skipping segment",
				"language", seg.Language,
				"text", seg.Text,
			)
			continue
		}

		result, err := phonemizer.PhonemizeWithProsody(seg.Text)
		if err != nil {
			return nil, err
		}

		// Invariant: len(result.Tokens) == len(result.Prosody) after each
		// phonemizer call. BOS/EOS tokens always have nil prosody at matching
		// indices, so filtering them out keeps tokens and prosody aligned.
		if len(result.Tokens) != len(result.Prosody) {
			slog.Warn("tokens/prosody length mismatch from phonemizer",
				"language", seg.Language,
				"tokens_len", len(result.Tokens),
				"prosody_len", len(result.Prosody),
			)
		}

		// Strip BOS/EOS tokens from this segment's output and track the last EOS.
		for i, tok := range result.Tokens {
			if bosEosTokens[tok] {
				if eosOnlyTokens[tok] {
					lastEOS = tok
				}
				continue
			}
			allTokens = append(allTokens, tok)
			var p *ProsodyInfo
			if i < len(result.Prosody) {
				p = result.Prosody[i]
			}
			allProsody = append(allProsody, p)
		}
	}

	return &PhonemizeResult{
		Tokens:   allTokens,
		Prosody:  allProsody,
		EOSToken: lastEOS,
	}, nil
}

// PostProcessMultilingualIDs wraps PostProcessIDs using the EOSToken from
// a PhonemizeResult. It converts tokens to IDs, then adds BOS/EOS markers
// and inter-phoneme padding.
func PostProcessMultilingualIDs(
	result *PhonemizeResult,
	phonemeIDMap map[string][]int64,
) ([]int64, []*ProsodyInfo) {
	ids := TokensToIDs(result.Tokens, phonemeIDMap)
	return PostProcessIDs(ids, result.Prosody, phonemeIDMap, result.EOSToken)
}

// DefaultLatinLanguage determines the best Latin-script language from the
// available languages. Priority: en -> es -> fr -> pt -> first language.
func DefaultLatinLanguage(languages []string) string {
	if len(languages) == 0 {
		return "en"
	}
	langSet := make(map[string]bool, len(languages))
	for _, l := range languages {
		langSet[l] = true
	}
	for _, preferred := range []string{"en", "es", "fr", "pt", "sv"} {
		if langSet[preferred] {
			return preferred
		}
	}
	return languages[0]
}

// Verify that *MultilingualPhonemizer satisfies the Phonemizer interface.
var _ Phonemizer = (*MultilingualPhonemizer)(nil)

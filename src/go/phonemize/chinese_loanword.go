// ZH-EN code-switching: loanword data + embedded-English phonemization
// (Issue #384, design §2.2 / §4.1 G1-G5 / §8.10)

package phonemize

import (
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"unicode"
)

// loanwordFS embeds the bundled ZH-EN loanword JSON. The file is byte-for-byte
// identical to src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
// (CI gate: scripts/check_loanword_consistency.py).
//
//go:embed data/zh_en_loanword.json
var loanwordFS embed.FS

// LoanwordData is the deserialized form of zh_en_loanword.json.
//
// Forward-compatible loader (YELLOW-5): unknown top-level fields in a future
// schema_version: 2 are silently ignored by encoding/json (default behaviour),
// so adding new fields like tone_overrides won't break this loader.
type LoanwordData struct {
	Version        int                 `json:"version"`
	Acronyms       map[string][]string `json:"acronyms"`
	Loanwords      map[string][]string `json:"loanwords"`
	LetterFallback map[string][]string `json:"letter_fallback"`
}

// Sentinel errors for use with errors.Is.
var (
	ErrLoanwordIO     = errors.New("loanword: io error")
	ErrLoanwordSchema = errors.New("loanword: schema violation")
	ErrLoanwordParse  = errors.New("loanword: parse error")
)

var (
	loanwordOnce sync.Once
	loanwordData *LoanwordData
	loanwordErr  error
)

// LoadLoanwordData returns the bundled default ZH-EN loanword data
// (parsed and validated once per process via sync.Once).
//
// Subsequent calls return the same pointer and any persistent error
// (override paths use LoadLoanwordDataFromBytes to bypass the cache).
func LoadLoanwordData() (*LoanwordData, error) {
	loanwordOnce.Do(func() {
		raw, err := loanwordFS.ReadFile("data/zh_en_loanword.json")
		if err != nil {
			loanwordErr = fmt.Errorf("%w: %v", ErrLoanwordIO, err)
			return
		}
		data, err := parseLoanwordJSON("zh_en_loanword.json (bundled)", raw)
		if err != nil {
			loanwordErr = err
			return
		}
		loanwordData = data
	})
	return loanwordData, loanwordErr
}

// LoadLoanwordDataFromBytes parses an arbitrary JSON byte slice into LoanwordData
// without touching the global cache. Used for tests and override paths.
func LoadLoanwordDataFromBytes(label string, raw []byte) (*LoanwordData, error) {
	return parseLoanwordJSON(label, raw)
}

// parseLoanwordJSON validates schema while decoding so that error messages
// match the Python format ("'%s.%s' must be list[str], got %v").
func parseLoanwordJSON(label string, raw []byte) (*LoanwordData, error) {
	// First decode into a generic map so we can produce Python-equivalent
	// error strings for type mismatches.
	var top map[string]any
	if err := json.Unmarshal(raw, &top); err != nil {
		return nil, fmt.Errorf("%w: %s: %v", ErrLoanwordParse, label, err)
	}

	versionAny, ok := top["version"]
	if !ok {
		return nil, fmt.Errorf("%w: %s: missing 'version'", ErrLoanwordSchema, label)
	}
	versionFloat, ok := versionAny.(float64)
	if !ok {
		return nil, fmt.Errorf("%w: %s: 'version' must be int", ErrLoanwordSchema, label)
	}

	out := &LoanwordData{
		Version:        int(versionFloat),
		Acronyms:       map[string][]string{},
		Loanwords:      map[string][]string{},
		LetterFallback: map[string][]string{},
	}

	for _, section := range []string{"acronyms", "loanwords", "letter_fallback"} {
		raw, ok := top[section]
		if !ok {
			continue // missing section ok (forward-compat)
		}
		m, ok := raw.(map[string]any)
		if !ok {
			return nil, fmt.Errorf(
				"%w: %s: section '%s' must be a mapping, got %T",
				ErrLoanwordSchema, label, section, raw,
			)
		}
		var target map[string][]string
		switch section {
		case "acronyms":
			target = out.Acronyms
		case "loanwords":
			target = out.Loanwords
		case "letter_fallback":
			target = out.LetterFallback
		}
		for k, v := range m {
			arr, ok := v.([]any)
			if !ok {
				return nil, fmt.Errorf(
					"%w: %s: '%s.%s' must be list[str], got %v",
					ErrLoanwordSchema, label, section, k, v,
				)
			}
			strs := make([]string, 0, len(arr))
			for _, e := range arr {
				s, ok := e.(string)
				if !ok {
					return nil, fmt.Errorf(
						"%w: %s: '%s.%s' must be list[str], got %v",
						ErrLoanwordSchema, label, section, k, v,
					)
				}
				strs = append(strs, s)
			}
			target[k] = strs
		}
	}

	return out, nil
}

// PhonemizeEmbeddedEnglish phonemizes English text embedded in Chinese context
// as Mandarin pinyin. Matches the Python reference and Rust mirror byte-for-byte.
//
// Lookup priority:
//  1. case-sensitive Loanwords (e.g. "Python", "ChatGPT")
//  2. uppercase Acronyms        (e.g. "GPS", "USB")
//  3. per-letter LetterFallback on uppercased text (digits silently dropped)
//
// Returns nil/empty slice if no token matched.
func (cp *ChinesePhonemizer) PhonemizeEmbeddedEnglish(text string, data *LoanwordData) []string {
	if data == nil {
		// Defensive: caller should have provided valid data; fall back to
		// bundled default rather than panic. Matches Python's
		// `loanword_data is None -> _get_default_loanword_data()` path.
		d, err := LoadLoanwordData()
		if err != nil || d == nil {
			return nil
		}
		data = d
	}

	pinyinSyllables := tokenizeAndLookup(text, data)
	if len(pinyinSyllables) == 0 {
		return nil
	}
	return phonemizeFromPinyinSyllables(pinyinSyllables)
}

// tokenizeAlnum splits text into [A-Za-z0-9]+ runs (drops punctuation/whitespace).
// Mirrors Python's _RE_TOKEN_SPLIT.
func tokenizeAlnum(text string) []string {
	var out []string
	var cur strings.Builder
	for _, r := range text {
		isAlnum := (r >= 'A' && r <= 'Z') || (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9')
		if isAlnum {
			cur.WriteRune(r)
		} else if cur.Len() > 0 {
			out = append(out, cur.String())
			cur.Reset()
		}
	}
	if cur.Len() > 0 {
		out = append(out, cur.String())
	}
	return out
}

// tokenizeAndLookup applies the lookup priority (loanwords -> acronyms ->
// letter_fallback) over each tokenized word.
func tokenizeAndLookup(text string, data *LoanwordData) []string {
	var pinyinSyllables []string
	for _, token := range tokenizeAlnum(text) {
		if token == "" {
			continue
		}

		// 1. Case-sensitive loanword
		if syl, ok := data.Loanwords[token]; ok {
			pinyinSyllables = append(pinyinSyllables, syl...)
			continue
		}

		// 2. Uppercase acronym
		upper := strings.ToUpper(token)
		if syl, ok := data.Acronyms[upper]; ok {
			pinyinSyllables = append(pinyinSyllables, syl...)
			continue
		}

		// 3. Letter-by-letter fallback (digits silently dropped unless registered)
		for _, ch := range upper {
			if unicode.IsDigit(ch) {
				continue
			}
			if syl, ok := data.LetterFallback[string(ch)]; ok {
				pinyinSyllables = append(pinyinSyllables, syl...)
			}
		}
	}
	return pinyinSyllables
}

// phonemizeFromPinyinSyllables converts a list of pinyin syllables (e.g.
// ["ji4", "pi4", "ai1", "si4"]) into IPA tokens with tone markers, then
// applies PUA mapping for multi-char tokens. Mirrors the Rust /
// Python pipeline byte-for-byte.
func phonemizeFromPinyinSyllables(syllables []string) []string {
	if len(syllables) == 0 {
		return nil
	}

	// Step 1: extract tone, normalize
	st := make([]syllableTone, 0, len(syllables))
	for _, s := range syllables {
		base, tone := zhExtractTone(s)
		st = append(st, syllableTone{
			syllable: zhNormalizePinyin(base),
			tone:     tone,
		})
	}

	// Step 2: tone sandhi
	zhApplyToneSandhi(st)

	// Step 3: pinyin -> IPA
	var tokens []string
	for _, syl := range st {
		ipa := zhPinyinToIPA(syl.syllable, syl.tone)
		tokens = append(tokens, ipa...)
	}

	// Step 4: multi-char IPA -> PUA codepoint mapping
	return MapSequence(tokens)
}

package phonemize

import (
	"fmt"
	"sync"
	"unicode/utf8"
)

// fixedPUA maps multi-character phoneme tokens to single PUA codepoints.
// 87 entries total, covering JA, ZH, KO, ES/PT, FR, and shared tokens.
var fixedPUA = map[string]rune{
	// Japanese (0xE000-0xE01C) — 29 entries
	"a:":       0xE000,
	"i:":       0xE001,
	"u:":       0xE002,
	"e:":       0xE003,
	"o:":       0xE004,
	"cl":       0xE005,
	"ky":       0xE006,
	"kw":       0xE007,
	"gy":       0xE008,
	"gw":       0xE009,
	"ty":       0xE00A,
	"dy":       0xE00B,
	"py":       0xE00C,
	"by":       0xE00D,
	"ch":       0xE00E,
	"ts":       0xE00F,
	"sh":       0xE010,
	"zy":       0xE011,
	"hy":       0xE012,
	"ny":       0xE013,
	"my":       0xE014,
	"ry":       0xE015,
	"?!":       0xE016,
	"?.":       0xE017,
	"?~":       0xE018,
	"N_m":      0xE019,
	"N_n":      0xE01A,
	"N_ng":     0xE01B,
	"N_uvular": 0xE01C,

	// Multilingual shared (0xE01D-0xE01E) — 2 entries
	"rr":      0xE01D,
	"y_vowel": 0xE01E,

	// Chinese (0xE020-0xE04A) — 43 entries
	"pʰ":    0xE020,
	"tʰ":    0xE021,
	"kʰ":    0xE022,
	"tɕ":    0xE023,
	"tɕʰ":   0xE024,
	"tʂ":    0xE025,
	"tʂʰ":   0xE026,
	"tsʰ":   0xE027,
	"aɪ":    0xE028,
	"eɪ":    0xE029,
	"aʊ":    0xE02A,
	"oʊ":    0xE02B,
	"an":    0xE02C,
	"ən":    0xE02D,
	"aŋ":    0xE02E,
	"əŋ":    0xE02F,
	"uŋ":    0xE030,
	"ia":    0xE031,
	"iɛ":    0xE032,
	"iou":   0xE033,
	"iaʊ":   0xE034,
	"iɛn":   0xE035,
	"in":    0xE036,
	"iaŋ":   0xE037,
	"iŋ":    0xE038,
	"iuŋ":   0xE039,
	"ua":    0xE03A,
	"uo":    0xE03B,
	"uaɪ":   0xE03C,
	"ueɪ":   0xE03D,
	"uan":   0xE03E,
	"uən":   0xE03F,
	"uaŋ":   0xE040,
	"uəŋ":   0xE041,
	"yɛ":    0xE042,
	"yɛn":   0xE043,
	"yn":    0xE044,
	"ɻ̩":     0xE045,
	"tone1": 0xE046,
	"tone2": 0xE047,
	"tone3": 0xE048,
	"tone4": 0xE049,
	"tone5": 0xE04A,

	// Korean (0xE04B-0xE052) — 8 entries
	"p͈":  0xE04B,
	"t͈":  0xE04C,
	"k͈":  0xE04D,
	"s͈":  0xE04E,
	"t͈ɕ": 0xE04F,
	"k̚":  0xE050,
	"t̚":  0xE051,
	"p̚":  0xE052,

	// Spanish/Portuguese (0xE054-0xE055) — 2 entries
	"tʃ": 0xE054,
	"dʒ": 0xE055,

	// French (0xE056-0xE058) — 3 entries
	"ɛ̃": 0xE056,
	"ɑ̃": 0xE057,
	"ɔ̃": 0xE058,
}

// reversePUA maps PUA codepoints back to multi-character tokens.
var reversePUA map[rune]string

// dynamicPUA maps unknown multi-char tokens to dynamically allocated PUA codepoints.
// This mirrors Python's token_mapper.py behavior of allocating PUA codepoints on the fly.
var (
	dynamicPUA  = make(map[string]string)
	dynamicMu   sync.Mutex
	nextDynamic = rune(0xE059) // Start after last fixed PUA (0xE058 = ɔ̃)
)

// maxPUA is the upper bound of the Unicode Private Use Area (BMP).
const maxPUA = rune(0xF8FF)

func init() {
	reversePUA = make(map[rune]string, len(fixedPUA))
	for token, r := range fixedPUA {
		reversePUA[r] = token
	}
}

// RegisterToken maps a multi-character phoneme token to a single PUA codepoint.
// Single-character tokens are returned as-is.
// Unknown multi-char tokens are dynamically allocated a PUA codepoint (thread-safe),
// mirroring Python's token_mapper.py behavior.
func RegisterToken(token string) string {
	if r, ok := fixedPUA[token]; ok {
		return string(r)
	}
	// Already a single character — return as-is.
	if utf8.RuneCountInString(token) == 1 {
		return token
	}

	// Multi-char token not in fixed PUA map — dynamically allocate a PUA codepoint.
	dynamicMu.Lock()
	defer dynamicMu.Unlock()

	if mapped, ok := dynamicPUA[token]; ok {
		return mapped
	}

	if nextDynamic > maxPUA {
		// PUA space exhausted; return token unchanged as a fallback.
		return token
	}

	r := nextDynamic
	nextDynamic++
	mapped := string(r)
	dynamicPUA[token] = mapped
	reversePUA[r] = token
	return mapped
}

// PUAToToken reverses a PUA codepoint back to the multi-character token.
func PUAToToken(ch rune) (string, bool) {
	token, ok := reversePUA[ch]
	return token, ok
}

// DynamicPUACount returns the number of dynamically allocated PUA codepoints.
func DynamicPUACount() int {
	dynamicMu.Lock()
	defer dynamicMu.Unlock()
	return len(dynamicPUA)
}

// ResetDynamicPUA clears all dynamically allocated PUA mappings.
// Intended for testing only.
func ResetDynamicPUA() {
	dynamicMu.Lock()
	defer dynamicMu.Unlock()
	for token := range dynamicPUA {
		r, _ := utf8.DecodeRuneInString(dynamicPUA[token])
		delete(reversePUA, r)
	}
	dynamicPUA = make(map[string]string)
	nextDynamic = 0xE059
}

// ErrPUAExhausted is returned when the PUA codepoint space is exhausted.
var ErrPUAExhausted = fmt.Errorf("PUA codepoint space exhausted (max U+%04X)", maxPUA)

// MapSequence applies RegisterToken to each token in a slice.
func MapSequence(tokens []string) []string {
	result := make([]string, len(tokens))
	for i, tok := range tokens {
		result[i] = RegisterToken(tok)
	}
	return result
}

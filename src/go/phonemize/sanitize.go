package phonemize

import (
	"strings"
	"unicode"
	"unicode/utf8"
)

// StripControlChars returns text cleaned by the input-sanitize rule shared by
// every runtime (docs/spec/input-sanitize-contract.toml):
//
//   - "\n", "\t" and "\r" stay (sentence splitting and SSML use them);
//   - VT, FF and NEL (U+000B, U+000C, U+0085) separate words, so they become
//     a space;
//   - every other control character (Unicode category Cc: U+0000-001F,
//     U+007F, U+0080-009F) is removed.
//
// Format characters (U+200D, U+FEFF), separators (U+2028), NBSP and bytes
// that are not valid UTF-8 pass through unchanged. It is idempotent and
// returns text itself when there is nothing to change.
func StripControlChars(text string) string {
	if !hasStrippedControl(text) {
		return text
	}
	var b strings.Builder
	b.Grow(len(text))
	for i := 0; i < len(text); {
		r, size := utf8.DecodeRuneInString(text[i:])
		switch {
		case r == utf8.RuneError && size <= 1:
			b.WriteByte(text[i])
		case r == '\v' || r == '\f' || r == '\u0085':
			b.WriteByte(' ')
		case r == '\n' || r == '\t' || r == '\r' || !unicode.IsControl(r):
			b.WriteString(text[i : i+size])
		}
		i += size
	}
	return b.String()
}

func hasStrippedControl(text string) bool {
	for _, r := range text {
		if unicode.IsControl(r) && r != '\n' && r != '\t' && r != '\r' {
			return true
		}
	}
	return false
}

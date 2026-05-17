package piperplus

import (
	"strings"
	"unicode"
	"unicode/utf8"
)

// SplitSentences splits text into individual sentences for streaming synthesis.
// It handles multiple languages: Japanese (。！？．), Chinese (。！？), and
// Western (.!?). Punctuation is kept attached to the preceding sentence.
// Trailing closing punctuation (e.g. 」 ） ”) is consumed greedily as part
// of the same sentence so that 「こんにちは。」 stays in one chunk.
//
// Mirrors Python/Rust/C++ canonical implementations — see
// docs/spec/text-splitter-contract.toml for the shared character set spec.
//
// SSML envelopes (`<speak>...</speak>`) are preserved as single units. If the
// text begins with `<speak` (after leading whitespace) and contains a matching
// `</speak>` close tag, the entire envelope is yielded as one unit and only
// any trailing text after `</speak>` is split using the normal sentence-
// splitting logic. If the `<speak>` tag is unclosed, the function falls back
// to normal splitting.
func SplitSentences(text string) []string {
	if len(text) == 0 {
		return nil
	}

	if envelope, tail, ok := extractSpeakEnvelope(text); ok {
		var result []string
		if envelope != "" {
			result = append(result, envelope)
		}
		if tail != "" {
			result = append(result, splitSentencesPlain(tail)...)
		}
		return result
	}

	return splitSentencesPlain(text)
}

// splitSentencesPlain is the SSML-unaware sentence splitter. Invoked by
// SplitSentences after stripping any SSML envelope (or directly when no
// envelope is present). Implements the post-consume strategy defined by
// docs/spec/text-splitter-contract.toml — see the canonical Python
// implementation in src/python_run/piper/text_splitter.py::split_sentences.
//
// Note: Go currently recognizes all 7 sentence terminators including
// U+FF0E (．), whereas Rust/C# omit U+FF0E (tracked as a separate parity
// follow-up in the contract spec).
func splitSentencesPlain(text string) []string {
	if len(text) == 0 {
		return nil
	}

	var sentences []string
	var current strings.Builder

	runes := []rune(text)
	n := len(runes)
	i := 0
	for i < n {
		r := runes[i]
		current.WriteRune(r)
		i++

		if !isSentenceTerminator(r) {
			continue
		}

		// Greedily consume trailing closing punctuation (e.g. 」 ） ”) so
		// that 「こんにちは。」 stays in one chunk. Issue #346.
		for i < n && isClosingPunctuation(runes[i]) {
			current.WriteRune(runes[i])
			i++
		}

		if s := strings.TrimSpace(current.String()); s != "" {
			sentences = append(sentences, s)
		}
		current.Reset()

		for i < n && unicode.IsSpace(runes[i]) {
			i++
		}
	}

	if s := strings.TrimSpace(current.String()); s != "" {
		sentences = append(sentences, s)
	}

	return sentences
}

// SplitTextChunks splits text into chunks of approximately maxChars,
// preferring to break at sentence boundaries. Single sentences that exceed
// maxChars are kept intact (not broken mid-sentence).
func SplitTextChunks(text string, maxChars int) []string {
	sentences := SplitSentences(text)
	if len(sentences) == 0 {
		return nil
	}

	var chunks []string
	var current strings.Builder

	for _, s := range sentences {
		sLen := utf8.RuneCountInString(s)
		curLen := utf8.RuneCountInString(current.String())

		if curLen == 0 {
			current.WriteString(s)
			continue
		}

		// +1 for the joining space.
		if curLen+1+sLen > maxChars {
			chunks = append(chunks, current.String())
			current.Reset()
			current.WriteString(s)
		} else {
			current.WriteRune(' ')
			current.WriteString(s)
		}
	}

	if current.Len() > 0 {
		chunks = append(chunks, current.String())
	}

	return chunks
}

// extractSpeakEnvelope detects an SSML `<speak>...</speak>` envelope at the
// start of text (after leading whitespace) and returns:
//
//   - envelope: the trimmed envelope string (`<speak ...>...</speak>`)
//   - tail:     trimmed text after `</speak>` (empty if none)
//   - ok:       true if a complete envelope was found
//
// To qualify as an envelope start, the prefix must be exactly `<speak` followed
// by `>`, whitespace, or end-of-string (so e.g. `<speaker>` does not match).
// The closing tag match is case-insensitive on the tag name (matching Python's
// `re.IGNORECASE` and Rust's `find_speak_close`). If the prefix matches but no
// `</speak>` is found, ok is false (caller falls back to normal splitting).
func extractSpeakEnvelope(text string) (envelope, tail string, ok bool) {
	trimmed := strings.TrimLeft(text, " \t\n\r")
	const prefix = "<speak"
	if !strings.HasPrefix(trimmed, prefix) {
		return "", "", false
	}
	if len(trimmed) > len(prefix) {
		switch trimmed[len(prefix)] {
		case '>', ' ', '\t', '\n', '\r':
		default:
			return "", "", false
		}
	}
	closeOff := findSpeakClose(trimmed)
	if closeOff < 0 {
		return "", "", false
	}
	end := closeOff + len("</speak>")
	envelope = strings.TrimSpace(trimmed[:end])
	tail = strings.TrimSpace(trimmed[end:])
	return envelope, tail, true
}

// findSpeakClose returns the byte offset of the closing `</speak>` tag in
// text. The match is case-insensitive on the tag name (matching Python's
// `re.IGNORECASE` and Rust's `find_speak_close`). Returns -1 if no closing
// tag is found.
func findSpeakClose(text string) int {
	const needleLen = len("</speak>")
	if len(text) < needleLen {
		return -1
	}
	lower := []byte("</speak>")
	upper := []byte("</SPEAK>")
	for i := 0; i+needleLen <= len(text); i++ {
		match := true
		for j := 0; j < needleLen; j++ {
			b := text[i+j]
			if b != lower[j] && b != upper[j] {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}

// isSentenceEnd is retained for backward compatibility (was used by depth-
// tracking implementation). Equivalent to isSentenceTerminator.
//
// Deprecated: use isSentenceTerminator.
func isSentenceEnd(r rune) bool { return isSentenceTerminator(r) }

// isSentenceTerminator reports whether r is a sentence-ending terminator.
// Mirrors docs/spec/text-splitter-contract.toml (7 codepoints).
func isSentenceTerminator(r rune) bool {
	switch r {
	case '.', '!', '?': // Western
		return true
	case '。': // 。 CJK fullstop
		return true
	case '！': // ！ fullwidth exclamation
		return true
	case '？': // ？ fullwidth question
		return true
	case '．': // ．fullwidth full stop
		return true
	}
	return false
}

// isClosingPunctuation reports whether r is a closing punctuation mark that
// should be consumed greedily after a sentence terminator.
// Mirrors docs/spec/text-splitter-contract.toml (14 codepoints) and matches
// Python's _CLOSING_PUNCTUATION / Rust's is_closing_punctuation.
func isClosingPunctuation(r rune) bool {
	switch r {
	case ')', ']', '}', '"', '\'':
		return true
	case '」', // 」 Right Corner Bracket
		'』', // 』 Right White Corner Bracket
		'）', // ） Fullwidth Right Parenthesis
		'］', // ］ Fullwidth Right Square Bracket
		'】', // 】 Right Black Lenticular Bracket
		'｣', // ｣ Halfwidth Right Corner Bracket
		'”', // ” Right Double Quotation Mark
		'’', // ’ Right Single Quotation Mark
		'»': // » Right-Pointing Double Angle Quotation Mark
		return true
	}
	return false
}

// isCloseBracket is retained for backward compatibility with external callers
// (e.g. existing parity helpers). Equivalent to isClosingPunctuation.
//
// Deprecated: use isClosingPunctuation, which carries the contract-aligned
// name. The two are kept in sync.
func isCloseBracket(r rune) bool {
	return isClosingPunctuation(r)
}

// isPunctuation reports whether a rune is a sentence-ending or clause-ending punctuation.
func isPunctuation(r rune) bool {
	switch r {
	case '.', '!', '?', ',', ';', ':',
		'。', '！', '？', '．', '、', '，':
		return true
	}
	return false
}

// CalculateDynamicChunkSize returns an appropriate chunk size based on punctuation density.
// This mirrors the C++ calculateDynamicChunkSize() logic.
func CalculateDynamicChunkSize(text string, baseChunkSize int) int {
	if baseChunkSize <= 0 {
		baseChunkSize = 50
	}
	runes := []rune(text)
	n := len(runes)
	if n < baseChunkSize*2 {
		return n // short text, no chunking
	}
	punctCount := 0
	for _, r := range runes {
		if isPunctuation(r) {
			punctCount++
		}
	}
	density := float64(punctCount) / float64(n)
	switch {
	case density > 0.05:
		return baseChunkSize
	case density >= 0.02:
		return baseChunkSize * 2
	default:
		return baseChunkSize * 3
	}
}

// SplitTextForStreaming splits text into chunks optimized for streaming synthesis.
// It uses dynamic chunk sizing based on punctuation density and groups small sentences.
func SplitTextForStreaming(text string, baseChunkSize int) []string {
	sentences := SplitSentences(text)
	if len(sentences) <= 1 {
		return sentences
	}
	chunkSize := CalculateDynamicChunkSize(text, baseChunkSize)
	var chunks []string
	var current strings.Builder
	currentLen := 0
	for _, s := range sentences {
		sLen := len([]rune(s))
		if currentLen > 0 && currentLen+sLen > chunkSize {
			chunks = append(chunks, current.String())
			current.Reset()
			currentLen = 0
		}
		current.WriteString(s)
		currentLen += sLen
	}
	if current.Len() > 0 {
		chunks = append(chunks, current.String())
	}
	return chunks
}

package piperplus

import (
	"strings"
	"unicode"
	"unicode/utf8"
)

// SplitSentences splits text into individual sentences for streaming synthesis.
// It handles multiple languages: Japanese (。！？), Chinese (。！？), and
// Western (.!?). Punctuation is kept attached to the preceding sentence.
// Splits inside quotes or parentheses are suppressed.
//
// Limitations:
//   - Unmatched brackets: If the input contains unclosed brackets or
//     parentheses, the nesting depth never returns to zero and the
//     remaining text is emitted as a single unsplit sentence.
//   - ASCII double-quote ('"'): Handled via a simple toggle, so nested or
//     unbalanced ASCII double-quotes will desynchronise the in-quote state.
//     Use Unicode quotes (\u201c/\u201d) for reliable nesting via the
//     bracket depth mechanism.
//
// SSML envelopes (`<speak>...</speak>`) are preserved as single units per the
// canonical `text-splitter-contract.toml` spec. If the text begins with
// `<speak` (after leading whitespace) and contains a matching `</speak>` close
// tag, the entire envelope is yielded as one unit and only any trailing text
// after `</speak>` is split using the normal sentence-splitting logic. If the
// `<speak>` tag is unclosed, the function falls back to normal splitting.
func SplitSentences(text string) []string {
	if len(text) == 0 {
		return nil
	}

	// SSML envelope detection: if the text starts with `<speak` (after
	// leading whitespace) and we find a matching `</speak>` close tag,
	// preserve the entire envelope as a single unit. Any trailing text
	// after `</speak>` is split using the normal logic. If the tag is
	// unclosed, fall back to normal splitting.
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

// splitSentencesPlain is the SSML-unaware sentence splitter. It is invoked by
// SplitSentences after stripping any SSML envelope (or directly when no
// envelope is present).
func splitSentencesPlain(text string) []string {
	if len(text) == 0 {
		return nil
	}

	var sentences []string
	var current strings.Builder
	depth := 0       // nesting depth for brackets/parentheses
	inQuote := false // toggle for ambiguous ASCII double-quote

	runes := []rune(text)
	for i := 0; i < len(runes); i++ {
		r := runes[i]

		// Track nesting depth.
		justClosed := false
		switch {
		case r == '"':
			// ASCII double-quote is ambiguous; use toggle.
			if inQuote {
				justClosed = true
			}
			inQuote = !inQuote
		case isOpenBracket(r):
			depth++
		case isCloseBracket(r) && depth > 0:
			depth--
			justClosed = true
		}

		current.WriteRune(r)

		// Only split at top-level (not inside quotes/parens).
		if depth > 0 || inQuote {
			continue
		}

		// Check if closing bracket/quote follows a sentence-ending punct.
		// e.g., `Hello."` or `元気です。」` — treat closing mark as sentence end.
		splitHere := isSentenceEnd(r)
		if !splitHere && justClosed && i > 0 {
			prev := runes[i-1]
			splitHere = isSentenceEnd(prev)
		}

		if !splitHere {
			continue
		}

		// For CJK sentence-enders, split immediately (no trailing space needed).
		// Only the actual CJK punctuation triggers an immediate split, not a
		// closing bracket that happens to follow one (e.g., 「…。」と…).
		if isCJKSentenceEnd(r) {
			if s := strings.TrimSpace(current.String()); s != "" {
				sentences = append(sentences, s)
			}
			current.Reset()
			continue
		}

		// For Western punctuation (.!?), require whitespace or end-of-string.
		if i == len(runes)-1 {
			// End of string.
			if s := strings.TrimSpace(current.String()); s != "" {
				sentences = append(sentences, s)
			}
			current.Reset()
			continue
		}

		next := runes[i+1]
		if unicode.IsSpace(next) {
			if s := strings.TrimSpace(current.String()); s != "" {
				sentences = append(sentences, s)
			}
			current.Reset()
		}
	}

	// Flush remaining text.
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
			// Start a new chunk.
			current.WriteString(s)
			continue
		}

		// +1 for the joining space.
		if curLen+1+sLen > maxChars {
			// Flush current chunk.
			chunks = append(chunks, current.String())
			current.Reset()
			current.WriteString(s)
		} else {
			current.WriteRune(' ')
			current.WriteString(s)
		}
	}

	// Flush remaining.
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
	// Ensure the prefix is followed by `>`, whitespace, or end-of-string so
	// that e.g. `<speaker>` does not falsely match.
	if len(trimmed) > len(prefix) {
		switch trimmed[len(prefix)] {
		case '>', ' ', '\t', '\n', '\r':
			// ok — valid `<speak>` or `<speak ...>`.
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
	// Lower-case + upper-case mask for ASCII case-insensitive byte compare.
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

// isSentenceEnd returns true if r is a sentence-ending punctuation mark.
func isSentenceEnd(r rune) bool {
	switch r {
	case '.', '!', '?': // Western
		return true
	case '\u3002': // 。 CJK fullstop
		return true
	case '\uff01': // ！ fullwidth exclamation
		return true
	case '\uff1f': // ？ fullwidth question
		return true
	case '\uff0e': // ．fullwidth full stop
		return true
	}
	return false
}

// isCJKSentenceEnd returns true if r is a CJK sentence-ending punctuation
// mark that doesn't require trailing whitespace to trigger a split.
func isCJKSentenceEnd(r rune) bool {
	switch r {
	case '\u3002', '\uff01', '\uff1f', '\uff0e':
		return true
	}
	return false
}

// isOpenBracket returns true if r is an opening bracket, quote, or paren.
func isOpenBracket(r rune) bool {
	switch r {
	case '(', '[', '{', '\u300c', '\u300e', '\u3010',
		'\u201c', '\uff08':
		// ( [ { 「 『 【 \u201c （
		return true
	}
	return false
}

// isCloseBracket returns true if r is a closing bracket, quote, or paren.
func isCloseBracket(r rune) bool {
	switch r {
	case ')', ']', '}', '\u300d', '\u300f', '\u3011',
		'\u201d', '\uff09':
		// ) ] } 」 』 】 \u201d ）
		return true
	}
	return false
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

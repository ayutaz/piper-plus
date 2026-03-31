package phonemize

import "regexp"

// TextSegment represents a segment of text that is either plain text or explicit phonemes.
type TextSegment struct {
	Text      string
	Phonemes  string
	IsPhoneme bool
}

var inlinePhonemeRe = regexp.MustCompile(`\[\[\s*([^\]]*?)\s*\]\]`)

// ParseInlinePhonemes splits text into segments of plain text and inline phoneme blocks.
// Phoneme blocks use the [[ phonemes ]] notation.
func ParseInlinePhonemes(text string) []TextSegment {
	matches := inlinePhonemeRe.FindAllStringSubmatchIndex(text, -1)
	if len(matches) == 0 {
		if text == "" {
			return nil
		}
		return []TextSegment{{Text: text}}
	}

	var segments []TextSegment
	pos := 0
	for _, m := range matches {
		if m[0] > pos {
			segments = append(segments, TextSegment{Text: text[pos:m[0]]})
		}
		phonemes := text[m[2]:m[3]]
		segments = append(segments, TextSegment{Phonemes: phonemes, IsPhoneme: true})
		pos = m[1]
	}
	if pos < len(text) {
		segments = append(segments, TextSegment{Text: text[pos:]})
	}
	return segments
}

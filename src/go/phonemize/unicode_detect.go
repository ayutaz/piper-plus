package phonemize

import (
	"strings"
	"unicode/utf8"
)

// LangSegment holds a language tag and its associated text fragment.
type LangSegment struct {
	Language string
	Text     string
}

// svUniqueChars contains characters uniquely Swedish (not shared with German).
// å (U+00E5/U+00C5) is distinctive to Swedish among Latin-script languages.
var svUniqueChars = map[rune]bool{
	'\u00e5': true, // å
	'\u00c5': true, // Å
}

// svDetectFunctionWords contains highly distinctive Swedish function words
// that do not appear in EN/ES/PT/FR. Used for word-level language detection
// disambiguation (distinct from svFunctionWords in swedish.go which is used
// for G2P vowel length / stress rules).
var svDetectFunctionWords = map[string]bool{
	"och":    true, // and
	"att":    true, // to/that
	"jag":    true, // I (first person pronoun)
	"det":    true, // it/that
	"inte":   true, // not
	"han":    true, // he
	"hon":    true, // she
	"som":    true, // who/which/as
	"ska":    true, // shall/will
	"med":    true, // with
	"aldrig": true, // never
	"alltid": true, // always
}

// UnicodeLanguageDetector detects language from Unicode character ranges.
type UnicodeLanguageDetector struct {
	languages            map[string]bool
	defaultLatinLanguage string
	hasJA, hasZH, hasKO  bool
	hasSV                bool // whether SV is in the language set
	detectSwedish        bool // hasSV && len(latinLanguages) >= 2
}

// NewUnicodeLanguageDetector creates a detector for the given language set.
// defaultLatinLang is returned for Latin-script characters (e.g. "en", "es").
func NewUnicodeLanguageDetector(languages []string, defaultLatinLang string) *UnicodeLanguageDetector {
	langSet := make(map[string]bool, len(languages))
	var hasJA, hasZH, hasKO bool
	for _, l := range languages {
		langSet[l] = true
		switch l {
		case "ja":
			hasJA = true
		case "zh":
			hasZH = true
		case "ko":
			hasKO = true
		}
	}

	hasSV := langSet["sv"]
	// Count Latin-script languages for Swedish detection
	latinLangs := 0
	for _, l := range []string{"en", "es", "fr", "pt", "sv"} {
		if langSet[l] {
			latinLangs++
		}
	}
	detectSwedish := hasSV && latinLangs >= 2

	return &UnicodeLanguageDetector{
		languages:            langSet,
		defaultLatinLanguage: defaultLatinLang,
		hasJA:                hasJA,
		hasZH:                hasZH,
		hasKO:                hasKO,
		hasSV:                hasSV,
		detectSwedish:        detectSwedish,
	}
}

// DetectChar returns the detected language for a character, or "" for neutral.
// contextHasKana indicates whether the surrounding text contains hiragana/katakana,
// which disambiguates CJK ideographs between Japanese and Chinese.
func (d *UnicodeLanguageDetector) DetectChar(ch rune, contextHasKana bool) string {
	// 1. Hiragana / Katakana / Katakana Extensions -> "ja" (only if JA registered)
	if (ch >= 0x3040 && ch <= 0x309F) ||
		(ch >= 0x30A0 && ch <= 0x30FF) ||
		(ch >= 0x31F0 && ch <= 0x31FF) {
		if d.hasJA {
			return "ja"
		}
		return ""
	}

	// 2. Hangul Syllables / Jamo / Compat Jamo -> "ko" (only if KO registered)
	if (ch >= 0xAC00 && ch <= 0xD7AF) ||
		(ch >= 0x1100 && ch <= 0x11FF) ||
		(ch >= 0x3130 && ch <= 0x318F) {
		if d.hasKO {
			return "ko"
		}
		return ""
	}

	// 3. CJK Unified Ideographs / Extension A / Compat Ideographs
	if (ch >= 0x4E00 && ch <= 0x9FFF) ||
		(ch >= 0x3400 && ch <= 0x4DBF) ||
		(ch >= 0xF900 && ch <= 0xFAFF) {
		if d.hasJA && d.hasZH {
			if contextHasKana {
				return "ja"
			}
			return "zh"
		}
		if d.hasJA {
			return "ja"
		}
		if d.hasZH {
			return "zh"
		}
		// Neither JA nor ZH registered; fall through to neutral.
		return ""
	}

	// 4. Fullwidth Latin (A-Z, a-z) -> defaultLatinLanguage
	if (ch >= 0xFF21 && ch <= 0xFF3A) || (ch >= 0xFF41 && ch <= 0xFF5A) {
		return d.defaultLatinLanguage
	}

	// 5. CJK Punctuation (U+3000-303F) + Fullwidth Forms (excluding fullwidth latin)
	if (ch >= 0x3000 && ch <= 0x303F) ||
		(ch >= 0xFF00 && ch <= 0xFF20) ||
		(ch >= 0xFF3B && ch <= 0xFF40) ||
		(ch >= 0xFF5B && ch <= 0xFFEF) {
		if d.hasJA {
			return "ja"
		}
		if d.hasZH {
			return "zh"
		}
		return ""
	}

	// 6. Latin (basic + supplement)
	if (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
		(ch >= 0x00C0 && ch <= 0x00D6) || // A-grave .. O-diaeresis
		(ch >= 0x00D8 && ch <= 0x00F6) || // O-stroke .. o-diaeresis
		(ch >= 0x00F8 && ch <= 0x00FF) { // o-stroke .. y-diaeresis
		return d.defaultLatinLanguage
	}

	// 7. Neutral (space, digit, ASCII punctuation, everything else)
	return ""
}

// HasKana returns true if text contains any hiragana or katakana character.
func (d *UnicodeLanguageDetector) HasKana(text string) bool {
	for i := 0; i < len(text); {
		ch, size := utf8.DecodeRuneInString(text[i:])
		if ch == utf8.RuneError && size <= 1 {
			i++
			continue
		}
		if (ch >= 0x3040 && ch <= 0x309F) || (ch >= 0x30A0 && ch <= 0x30FF) {
			return true
		}
		i += size
	}
	return false
}

// SegmentText splits text into (language, segment) pairs.
// Neutral characters are absorbed into the preceding language segment.
// If no language is detected and text has content, the entire text is
// returned as a single segment with defaultLatinLanguage.
func SegmentText(text string, detector *UnicodeLanguageDetector) []LangSegment {
	if len(text) == 0 || strings.TrimSpace(text) == "" {
		return nil
	}

	// Pre-scan for kana context.
	contextHasKana := detector.HasKana(text)

	var segments []LangSegment
	currentLang := ""
	var currentBuf []byte

	for i := 0; i < len(text); {
		ch, size := utf8.DecodeRuneInString(text[i:])
		if ch == utf8.RuneError && size <= 1 {
			// Invalid byte: absorb into current segment.
			currentBuf = append(currentBuf, text[i])
			i++
			continue
		}

		lang := detector.DetectChar(ch, contextHasKana)

		switch {
		case lang == "":
			// Neutral: absorb into current segment.
			currentBuf = append(currentBuf, text[i:i+size]...)
		case currentLang == "" || lang == currentLang:
			// Same language or first language encountered.
			currentLang = lang
			currentBuf = append(currentBuf, text[i:i+size]...)
		default:
			// Language changed: flush previous segment.
			if len(currentBuf) > 0 {
				segments = append(segments, LangSegment{
					Language: currentLang,
					Text:     string(currentBuf),
				})
			}
			currentLang = lang
			currentBuf = currentBuf[:0]
			currentBuf = append(currentBuf, text[i:i+size]...)
		}
		i += size
	}

	// Flush remaining buffer.
	if len(currentBuf) > 0 {
		if currentLang == "" {
			// All characters were neutral; use default.
			currentLang = detector.defaultLatinLanguage
		}
		segments = append(segments, LangSegment{
			Language: currentLang,
			Text:     string(currentBuf),
		})
	}

	// Post-pass: word-level Swedish detection within Latin segments.
	if detector.detectSwedish {
		segments = refineLatinSegmentsForSwedish(segments, detector)
	}

	return segments
}

// refineLatinSegmentsForSwedish re-examines Latin-script segments for
// Swedish indicators (specific characters and function words). Segments
// are reclassified as "sv" when a strong indicator is found.
//
// Strong indicators (sufficient to trigger SV classification):
//   - å/Å (uniquely Swedish among Latin-script languages)
//   - Swedish function words (och, att, jag, det, inte, ...)
//
// Weak indicators (NOT sufficient alone):
//   - ä/Ä, ö/Ö (shared with German)
//
// This prevents false positives on German text that contains ä/ö but
// no Swedish-specific indicators.
func refineLatinSegmentsForSwedish(segments []LangSegment, d *UnicodeLanguageDetector) []LangSegment {
	if d.defaultLatinLanguage == "sv" {
		return segments // SV is already the default; no reclassification needed.
	}
	result := make([]LangSegment, 0, len(segments))
	for _, seg := range segments {
		if seg.Language != d.defaultLatinLanguage {
			result = append(result, seg)
			continue
		}
		// Score Swedish indicators in this Latin segment.
		// A "strong" indicator (å or function word) is required for SV
		// classification. ä/ö alone (shared with German) are not sufficient.
		hasStrongIndicator := false
		for _, word := range strings.Fields(seg.Text) {
			wordLower := strings.ToLower(strings.Trim(word, ".,;:!?"))
			if wordLower == "" {
				continue
			}
			// Function words are a strong Swedish signal.
			if svDetectFunctionWords[wordLower] {
				hasStrongIndicator = true
				continue
			}
			// å/Å is uniquely Swedish among Latin-script languages.
			// ä/ö are shared with German, so they alone cannot trigger SV.
			for _, r := range wordLower {
				if svUniqueChars[r] {
					hasStrongIndicator = true
					break
				}
			}
		}
		if hasStrongIndicator {
			result = append(result, LangSegment{Language: "sv", Text: seg.Text})
		} else {
			result = append(result, seg)
		}
	}
	return result
}

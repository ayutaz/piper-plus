// Package ssml provides a basic SSML (Speech Synthesis Markup Language) parser.
//
// It supports a subset of the W3C SSML specification:
//   - <speak> root element
//   - <break time="500ms"/> or <break time="1s"/> for silence
//   - <break strength="medium"/> for predefined silence durations
//   - <prosody rate="slow">text</prosody> for speech rate control
//
// Unknown tags are gracefully degraded by extracting their text content.
// XML syntax errors cause a fallback to plain-text processing.
package ssml

import (
	"encoding/xml"
	"io"
	"math"
	"regexp"
	"strconv"
	"strings"
)

// Segment represents a parsed SSML segment.
//
// Text is the content to phonemize. An empty string indicates a silence-only
// segment. BreakMs is the silence duration in milliseconds to insert after
// this segment. Rate is the speech rate multiplier (length_scale): values
// > 1.0 mean slower speech, values < 1.0 mean faster speech.
type Segment struct {
	Text    string
	BreakMs int
	Rate    float32
}

// breakStrengthMs maps SSML break strength names to millisecond durations.
var breakStrengthMs = map[string]int{
	"none":     0,
	"x-weak":   100,
	"weak":     200,
	"medium":   400,
	"strong":   700,
	"x-strong": 1000,
}

// rateNames maps SSML prosody rate names to length_scale multipliers.
var rateNames = map[string]float32{
	"x-slow": 1.5,
	"slow":   1.25,
	"medium": 1.0,
	"fast":   0.8,
	"x-fast": 0.6,
}

// reSSML detects SSML: starts with optional whitespace then <speak.
var reSSML = regexp.MustCompile(`(?s)^\s*<speak[\s>]`)

// reStripTags removes all XML tags from a string.
var reStripTags = regexp.MustCompile(`<[^>]*>`)

// IsSSML returns true if text looks like an SSML document.
//
// Detection is based on the presence of a <speak opening tag near the
// start of the string.
func IsSSML(text string) bool {
	return reSSML.MatchString(text)
}

// Parse parses an SSML string into a list of Segment values.
//
// If ssmlText is not valid XML the entire string is returned as a single
// plain-text segment (graceful fallback). Non-SSML input is returned as
// a single segment with default rate and zero break.
func Parse(ssmlText string) []Segment {
	if !IsSSML(ssmlText) {
		return []Segment{{Text: ssmlText, Rate: 1.0}}
	}

	decoder := xml.NewDecoder(strings.NewReader(ssmlText))
	segments, err := walk(decoder)
	if err != nil {
		// XML parse error: strip tags and return as plain text.
		stripped := strings.TrimSpace(reStripTags.ReplaceAllString(ssmlText, ""))
		if stripped == "" {
			stripped = ssmlText
		}
		return []Segment{{Text: stripped, Rate: 1.0}}
	}

	merged := merge(segments)
	if len(merged) == 0 {
		return []Segment{{Text: "", Rate: 1.0}}
	}
	return merged
}

// walk processes the XML token stream using a stack-based approach that
// mirrors the Python recursive _walk. The stack tracks the current
// prosody rate inherited from enclosing elements.
func walk(decoder *xml.Decoder) ([]Segment, error) {
	var segments []Segment

	type frame struct {
		tag  string
		rate float32
	}
	stack := []frame{{tag: "", rate: 1.0}} // sentinel root frame

	currentRate := func() float32 {
		return stack[len(stack)-1].rate
	}

	for {
		tok, err := decoder.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}

		switch t := tok.(type) {
		case xml.StartElement:
			tag := localTag(t.Name)
			parentRate := currentRate()

			if tag == "break" {
				breakMs := resolveBreak(t.Attr)
				segments = append(segments, Segment{Text: "", BreakMs: breakMs, Rate: parentRate})
				// Self-closing <break/> is handled by the decoder as a
				// StartElement followed by an EndElement, so we push a frame
				// and let the EndElement pop it.
				stack = append(stack, frame{tag: tag, rate: parentRate})
				continue
			}

			rate := parentRate
			if tag == "prosody" {
				if rateAttr := getAttr(t.Attr, "rate"); rateAttr != "" {
					rate = parseRate(rateAttr)
				}
			}

			stack = append(stack, frame{tag: tag, rate: rate})

		case xml.EndElement:
			if len(stack) > 1 {
				stack = stack[:len(stack)-1]
			}

		case xml.CharData:
			text := strings.TrimSpace(string(t))
			if text != "" {
				segments = append(segments, Segment{Text: text, BreakMs: 0, Rate: currentRate()})
			}
		}
	}

	return segments, nil
}

// resolveBreak computes break duration in ms from a <break> element's attributes.
func resolveBreak(attrs []xml.Attr) int {
	timeAttr := getAttr(attrs, "time")
	if timeAttr != "" {
		return parseBreakTime(timeAttr)
	}

	strengthAttr := getAttr(attrs, "strength")
	if strengthAttr != "" {
		if ms, ok := breakStrengthMs[strings.ToLower(strengthAttr)]; ok {
			return ms
		}
		// Unknown strength defaults to medium.
		return 400
	}

	// No attributes: default to medium.
	return breakStrengthMs["medium"]
}

// parseBreakTime converts "500ms" or "1s" to milliseconds.
// Returns 0 for unparseable values.
func parseBreakTime(s string) int {
	s = strings.TrimSpace(strings.ToLower(s))

	if strings.HasSuffix(s, "ms") {
		v, err := strconv.ParseFloat(s[:len(s)-2], 64)
		if err != nil {
			return 0
		}
		return int(v)
	}

	if strings.HasSuffix(s, "s") {
		v, err := strconv.ParseFloat(s[:len(s)-1], 64)
		if err != nil {
			return 0
		}
		return int(v * 1000)
	}

	// Bare number: assume milliseconds.
	v, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0
	}
	return int(v)
}

// parseRate converts a rate specification to a float32 length_scale multiplier.
//
// Accepted formats:
//   - Named: "slow", "fast", etc.
//   - Percentage: "120%" (120% speaking rate -> length_scale = 100/120)
//   - Bare float: treated as direct length_scale multiplier
func parseRate(s string) float32 {
	s = strings.TrimSpace(strings.ToLower(s))

	// Named rate.
	if v, ok := rateNames[s]; ok {
		return v
	}

	// Percentage.
	if strings.HasSuffix(s, "%") {
		pct, err := strconv.ParseFloat(s[:len(s)-1], 64)
		if err != nil || pct <= 0 {
			return 1.0
		}
		return float32(100.0 / pct)
	}

	// Bare float.
	v, err := strconv.ParseFloat(s, 64)
	if err != nil || v <= 0 {
		return 1.0
	}
	return float32(v)
}

// localTag strips the XML namespace prefix if present.
func localTag(name xml.Name) string {
	return name.Local
}

// getAttr returns the value of the named attribute, or "" if not found.
func getAttr(attrs []xml.Attr, name string) string {
	for _, a := range attrs {
		if a.Name.Local == name {
			return a.Value
		}
	}
	return ""
}

// merge removes empty-text segments with zero break (no-ops).
func merge(segments []Segment) []Segment {
	result := make([]Segment, 0, len(segments))
	for _, s := range segments {
		if strings.TrimSpace(s.Text) != "" || s.BreakMs > 0 {
			result = append(result, s)
		}
	}
	return result
}

// approxEqual compares two float32 values with a small tolerance.
// Exported for use in tests; not part of the public API contract.
func approxEqual(a, b float32) bool {
	return math.Abs(float64(a-b)) < 0.001
}

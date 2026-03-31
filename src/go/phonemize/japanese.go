package phonemize

import (
	"regexp"
	"strconv"
	"strings"
)

// ---------------------------------------------------------------------------
// JapaneseG2PEngine — interface for fullcontext label extraction
// ---------------------------------------------------------------------------

// JapaneseG2PEngine provides fullcontext labels from text.
// Phase 1 uses a subprocess backend (e.g. open_jtalk CLI).
type JapaneseG2PEngine interface {
	ExtractFullcontext(text string) ([]string, error)
}

// ---------------------------------------------------------------------------
// JapanesePhonemizer
// ---------------------------------------------------------------------------

// JapanesePhonemizer converts Japanese text to phonemes using the Kurihara
// method. It delegates fullcontext label extraction to a JapaneseG2PEngine.
type JapanesePhonemizer struct {
	engine JapaneseG2PEngine
}

// NewJapanesePhonemizer creates a JapanesePhonemizer backed by the given engine.
func NewJapanesePhonemizer(engine JapaneseG2PEngine) *JapanesePhonemizer {
	return &JapanesePhonemizer{engine: engine}
}

// PhonemizeWithProsody converts Japanese text to phoneme tokens with prosody.
// It implements the Phonemizer interface.
func (p *JapanesePhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	labels, err := p.engine.ExtractFullcontext(text)
	if err != nil {
		return nil, err
	}
	return labelsToTokensWithProsody(labels, text)
}

// LanguageCode returns "ja".
func (p *JapanesePhonemizer) LanguageCode() string {
	return "ja"
}

// ---------------------------------------------------------------------------
// Label parsing regexes
// ---------------------------------------------------------------------------

var (
	rePhoneme = regexp.MustCompile(`-([^+]+)\+`)
	reA1      = regexp.MustCompile(`/A:([0-9\-]+)\+`)
	reA2      = regexp.MustCompile(`\+(\d+)\+`)
	reA3      = regexp.MustCompile(`\+(\d+)/`)
)

// ---------------------------------------------------------------------------
// Core: fullcontext labels -> phoneme tokens with prosody (Kurihara method)
// ---------------------------------------------------------------------------

// labelsToTokensWithProsody converts OpenJTalk fullcontext labels to phoneme
// tokens with prosody information using the Kurihara method.
//
// The Kurihara method inserts the following prosody marks:
//   - ^   : beginning of sentence (BOS)
//   - $/? : end of sentence (EOS / question type)
//   - _   : short pause (pau)
//   - #   : accent phrase boundary
//   - [   : rising pitch mark (accent phrase head)
//   - ]   : falling pitch mark (accent nucleus)
func labelsToTokensWithProsody(labels []string, text string) (*PhonemizeResult, error) {
	var tokens []string
	var prosody []*ProsodyInfo

	numLabels := len(labels)

	for idx, label := range labels {
		m := rePhoneme.FindStringSubmatch(label)
		if m == nil {
			continue
		}
		phoneme := m[1]

		// Beginning / end silence
		if phoneme == "sil" {
			switch idx {
			case 0:
				tokens = append(tokens, "^")
				prosody = append(prosody, nil)
			case numLabels - 1:
				qt := getQuestionType(text)
				tokens = append(tokens, qt)
				prosody = append(prosody, nil)
			}
			continue
		}

		// Short pause
		if phoneme == "pau" {
			tokens = append(tokens, "_")
			prosody = append(prosody, nil)
			continue
		}

		// Regular phoneme
		tokens = append(tokens, phoneme)

		// Extract A1/A2/A3
		mA1 := reA1.FindStringSubmatch(label)
		mA2 := reA2.FindStringSubmatch(label)
		mA3 := reA3.FindStringSubmatch(label)

		if mA1 == nil || mA2 == nil || mA3 == nil {
			prosody = append(prosody, nil)
			continue
		}

		a1, _ := strconv.Atoi(mA1[1])
		a2, _ := strconv.Atoi(mA2[1])
		a3, _ := strconv.Atoi(mA3[1])

		prosody = append(prosody, &ProsodyInfo{A1: a1, A2: a2, A3: a3})

		// Look-ahead: fetch a2 of the next label
		a2Next := -1
		if idx < numLabels-1 {
			mA2Next := reA2.FindStringSubmatch(labels[idx+1])
			if mA2Next != nil {
				a2Next, _ = strconv.Atoi(mA2Next[1])
			}
		}

		// Insert accent nucleus mark "]" (pitch H->L)
		if a1 == 0 && a2Next == a2+1 {
			tokens = append(tokens, "]")
			prosody = append(prosody, nil)
		}

		// Insert accent phrase boundary "#"
		if a2 == a3 && a2Next == 1 {
			tokens = append(tokens, "#")
			prosody = append(prosody, nil)
		}

		// Insert rising pitch mark "["
		if a2 == 1 && a2Next == 2 {
			tokens = append(tokens, "[")
			prosody = append(prosody, nil)
		}
	}

	// Apply context-dependent N phoneme rules
	tokens = applyNPhonemeRules(tokens)

	// Map multi-char tokens to PUA codepoints
	tokens = MapSequence(tokens)

	// Determine EOS token
	eosToken := getQuestionType(text)

	return &PhonemizeResult{
		Tokens:   tokens,
		Prosody:  prosody,
		EOSToken: eosToken,
	}, nil
}

// ---------------------------------------------------------------------------
// Question type detection
// ---------------------------------------------------------------------------

// getQuestionType returns the appropriate end-of-sentence marker based on
// the text ending. Returns one of: "?!", "?.", "?~", "?", or "$".
func getQuestionType(text string) string {
	stripped := strings.TrimSpace(text)

	// Multi-char patterns first (longer before shorter)
	if strings.HasSuffix(stripped, "?!") ||
		strings.HasSuffix(stripped, "\uff01\uff1f") || // ！？
		strings.HasSuffix(stripped, "\uff1f\uff01") { // ？！
		return "?!"
	}
	if strings.HasSuffix(stripped, "?.") ||
		strings.HasSuffix(stripped, "\u3002\uff1f") || // 。？
		strings.HasSuffix(stripped, "\uff1f\u3002") { // ？。
		return "?."
	}
	if strings.HasSuffix(stripped, "?~") ||
		strings.HasSuffix(stripped, "\uff5e\uff1f") || // ～？
		strings.HasSuffix(stripped, "\uff1f\uff5e") { // ？～
		return "?~"
	}

	// Single ? fallback
	if strings.HasSuffix(stripped, "?") || strings.HasSuffix(stripped, "\uff1f") {
		return "?"
	}

	return "$"
}

// ---------------------------------------------------------------------------
// Context-dependent N phoneme rules
// ---------------------------------------------------------------------------

// skipTokens is the set of tokens that should be skipped when looking ahead
// for the next phoneme after "N".
var skipTokens = map[string]bool{
	"_":  true,
	"#":  true,
	"[":  true,
	"]":  true,
	"^":  true,
	"$":  true,
	"?":  true,
	"?!": true,
	"?.": true,
	"?~": true,
}

// bilabial phonemes: m, my, b, by, p, py
var bilabials = map[string]bool{
	"m": true, "my": true,
	"b": true, "by": true,
	"p": true, "py": true,
}

// alveolar phonemes: n, ny, t, ty, d, dy, ts, ch
var alveolars = map[string]bool{
	"n": true, "ny": true,
	"t": true, "ty": true,
	"d": true, "dy": true,
	"ts": true, "ch": true,
}

// velar phonemes: k, ky, kw, g, gy, gw
var velars = map[string]bool{
	"k": true, "ky": true, "kw": true,
	"g": true, "gy": true, "gw": true,
}

// applyNPhonemeRules replaces each "N" token with a context-dependent variant:
//   - N_m      : before bilabial (m, my, b, by, p, py)
//   - N_n      : before alveolar (n, ny, t, ty, d, dy, ts, ch)
//   - N_ng     : before velar (k, ky, kw, g, gy, gw)
//   - N_uvular : at phrase end or before vowels/other consonants
//
// This is a 1-to-1 replacement (each "N" maps to exactly one variant token),
// so the token count is unchanged and the prosody array stays aligned.
func applyNPhonemeRules(tokens []string) []string {
	result := make([]string, 0, len(tokens))

	for i, token := range tokens {
		if token != "N" {
			result = append(result, token)
			continue
		}

		// Look ahead past skip tokens to find next phoneme
		var nextPhoneme string
		for j := i + 1; j < len(tokens); j++ {
			if !skipTokens[tokens[j]] {
				nextPhoneme = tokens[j]
				break
			}
		}

		switch {
		case nextPhoneme == "":
			result = append(result, "N_uvular") // end of phrase
		case bilabials[nextPhoneme]:
			result = append(result, "N_m")
		case alveolars[nextPhoneme]:
			result = append(result, "N_n")
		case velars[nextPhoneme]:
			result = append(result, "N_ng")
		default:
			result = append(result, "N_uvular") // vowels, other consonants
		}
	}

	return result
}

// ---------------------------------------------------------------------------
// Compile-time interface check
// ---------------------------------------------------------------------------

// Verify that *JapanesePhonemizer satisfies the Phonemizer interface.
var _ Phonemizer = (*JapanesePhonemizer)(nil)

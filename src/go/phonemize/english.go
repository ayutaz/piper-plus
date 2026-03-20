package phonemize

import (
	"strings"
	"unicode"
)

// EnglishPhonemizer converts English text to IPA phonemes.
type EnglishPhonemizer struct {
	cmuDict map[string][]string // word -> ARPAbet phonemes
}

// NewEnglishPhonemizer creates a phonemizer with the given CMU dictionary.
// cmuDict maps lowercase words to ARPAbet phoneme lists (e.g., "hello" -> ["HH","AH0","L","OW1"]).
func NewEnglishPhonemizer(cmuDict map[string][]string) *EnglishPhonemizer {
	return &EnglishPhonemizer{cmuDict: cmuDict}
}

// LanguageCode returns "en".
func (p *EnglishPhonemizer) LanguageCode() string { return "en" }

// ---------------------------------------------------------------------------
// ARPAbet -> IPA mapping
// ---------------------------------------------------------------------------

var arpabetToIPA = map[string]string{
	"AA": "ɑ",
	"AE": "æ",
	"AH": "ʌ",
	"AO": "ɔː",
	"AW": "aʊ",
	"AY": "aɪ",
	"EH": "ɛ",
	"ER": "ɚ", // unstressed default; stressed handled separately
	"EY": "eɪ",
	"IH": "ɪ",
	"IY": "iː",
	"OW": "oʊ",
	"OY": "ɔɪ",
	"UH": "ʊ",
	"UW": "uː",
	"B":  "b",
	"CH": "tʃ",
	"D":  "d",
	"DH": "ð",
	"F":  "f",
	"G":  "ɡ",
	"HH": "h",
	"JH": "dʒ",
	"K":  "k",
	"L":  "l",
	"M":  "m",
	"N":  "n",
	"NG": "ŋ",
	"P":  "p",
	"R":  "ɹ",
	"S":  "s",
	"SH": "ʃ",
	"T":  "t",
	"TH": "θ",
	"V":  "v",
	"W":  "w",
	"Y":  "j",
	"Z":  "z",
	"ZH": "ʒ",
}

// ---------------------------------------------------------------------------
// Function words (destressed)
// ---------------------------------------------------------------------------

var functionWords = map[string]bool{
	// articles / determiners
	"a": true, "an": true, "the": true,
	// pronouns
	"i": true, "me": true, "my": true, "you": true, "your": true,
	"he": true, "him": true, "his": true, "she": true, "her": true,
	"it": true, "its": true, "we": true, "us": true, "our": true,
	"they": true, "them": true, "their": true,
	// be-verbs
	"am": true, "is": true, "are": true, "was": true, "were": true,
	"be": true, "been": true, "being": true,
	// auxiliaries
	"have": true, "has": true, "had": true,
	"do": true, "does": true, "did": true,
	"will": true, "would": true, "can": true, "could": true,
	"shall": true, "should": true, "may": true, "might": true, "must": true,
	// prepositions
	"at": true, "by": true, "for": true, "from": true, "in": true,
	"of": true, "on": true, "to": true, "with": true,
	"about": true, "after": true, "before": true, "between": true,
	"into": true, "through": true,
	// conjunctions
	"and": true, "but": true, "or": true, "if": true, "that": true,
	"than": true, "as": true, "when": true, "while": true,
	"because": true, "since": true, "so": true, "yet": true, "nor": true,
	// others
	"not": true, "no": true,
	"what": true, "who": true, "which": true, "where": true, "how": true,
	"all": true, "some": true, "any": true, "each": true, "every": true,
}

// ---------------------------------------------------------------------------
// Punctuation set
// ---------------------------------------------------------------------------

var punctuationSet = map[rune]bool{
	'.': true, ',': true, '!': true, '?': true, ';': true, ':': true,
}

// ---------------------------------------------------------------------------
// ARPAbet parsing helpers
// ---------------------------------------------------------------------------

// parseArpabet splits an ARPAbet token into (base, stress).
// stress is -1 for consonants (no digit suffix), 0/1/2 for vowels.
func parseArpabet(token string) (base string, stress int) {
	if len(token) == 0 {
		return token, -1
	}
	last := token[len(token)-1]
	if last >= '0' && last <= '2' {
		return token[:len(token)-1], int(last - '0')
	}
	return token, -1
}

// ---------------------------------------------------------------------------
// Single-token ARPAbet -> IPA conversion
// ---------------------------------------------------------------------------

func arpabetTokenToIPA(token string) (ipa string, stress int) {
	base, s := parseArpabet(token)
	// Unstressed AH -> schwa
	if base == "AH" && s == 0 {
		return "ə", s
	}
	if mapped, ok := arpabetToIPA[base]; ok {
		return mapped, s
	}
	// Unknown: return token as-is
	return token, s
}

// ---------------------------------------------------------------------------
// Word-level ARPAbet -> IPA with context rules
// ---------------------------------------------------------------------------

// ipaPhoneme holds an IPA string and its stress level.
type ipaPhoneme struct {
	ipa    string
	stress int
}

// convertWordToIPA converts a word's ARPAbet tokens to IPA with context rules.
// Handles:
//   - AA + R -> "ɑːɹ" (merge)
//   - Stressed ER (stress=1) -> "ɜː"
func convertWordToIPA(tokens []string) []ipaPhoneme {
	result := make([]ipaPhoneme, 0, len(tokens))
	for i := 0; i < len(tokens); i++ {
		base, stress := parseArpabet(tokens[i])

		// AA + R -> ɑːɹ
		if base == "AA" && i+1 < len(tokens) && tokens[i+1] == "R" {
			result = append(result, ipaPhoneme{ipa: "ɑːɹ", stress: stress})
			i++ // skip the R
			continue
		}

		// Stressed ER -> ɜː
		if base == "ER" && stress == 1 {
			result = append(result, ipaPhoneme{ipa: "ɜː", stress: stress})
			continue
		}

		ipa, s := arpabetTokenToIPA(tokens[i])
		result = append(result, ipaPhoneme{ipa: ipa, stress: s})
	}
	return result
}

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

// tokenKind classifies tokenizer output.
type tokenKind int

const (
	tokenWord tokenKind = iota
	tokenPunct
)

type textToken struct {
	text string
	kind tokenKind
}

// tokenizeText splits text into word and punctuation tokens.
// Words are sequences of letters/apostrophes; punctuation characters are
// returned individually. Whitespace is consumed as a separator.
func tokenizeText(text string) []textToken {
	var tokens []textToken
	runes := []rune(text)
	i := 0
	for i < len(runes) {
		ch := runes[i]

		// Skip whitespace
		if unicode.IsSpace(ch) {
			i++
			continue
		}

		// Punctuation
		if punctuationSet[ch] {
			tokens = append(tokens, textToken{text: string(ch), kind: tokenPunct})
			i++
			continue
		}

		// Word: letters and apostrophes
		if unicode.IsLetter(ch) || ch == '\'' {
			start := i
			for i < len(runes) && (unicode.IsLetter(runes[i]) || runes[i] == '\'') {
				i++
			}
			tokens = append(tokens, textToken{text: string(runes[start:i]), kind: tokenWord})
			continue
		}

		// Other character: skip
		i++
	}
	return tokens
}

// ---------------------------------------------------------------------------
// PhonemizeWithProsody — Phonemizer interface implementation
// ---------------------------------------------------------------------------

// PhonemizeWithProsody converts English text to IPA phoneme tokens with prosody.
func (p *EnglishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	tokens := tokenizeText(text)

	var phonemes []string
	var prosody []*ProsodyInfo
	needSpace := false

	for _, tok := range tokens {
		if tok.kind == tokenPunct {
			// Punctuation attaches to preceding word (no space before)
			phonemes = append(phonemes, tok.text)
			prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
			continue
		}

		// Word token
		if needSpace {
			phonemes = append(phonemes, " ")
			prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
		}

		lower := strings.ToLower(tok.text)
		isFunctionWord := functionWords[lower]

		arpTokens, found := p.cmuDict[lower]
		if found {
			ipas := convertWordToIPA(arpTokens)

			// Destress function words
			if isFunctionWord {
				for j := range ipas {
					if ipas[j].stress >= 1 {
						ipas[j].stress = 0
					}
				}
			}

			// A3 = total IPA character count for the word
			wordPhonemeCount := 0
			for _, ph := range ipas {
				wordPhonemeCount += runeCount(ph.ipa)
			}

			for _, ph := range ipas {
				// stress -> A2: primary(1)->2, secondary(2)->1, else 0
				a2 := 0
				if ph.stress == 1 {
					a2 = 2
				} else if ph.stress == 2 {
					a2 = 1
				}

				// Insert stress marker before stressed vowels
				if ph.stress == 1 {
					phonemes = append(phonemes, "ˈ")
					prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhonemeCount})
				} else if ph.stress == 2 {
					phonemes = append(phonemes, "ˌ")
					prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhonemeCount})
				}

				// Each IPA character becomes a separate phoneme token
				for _, ch := range ph.ipa {
					phonemes = append(phonemes, string(ch))
					prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhonemeCount})
				}
			}
		} else {
			// Not in CMU dict: letter-by-letter fallback
			letterCount := runeCount(lower)
			for _, ch := range lower {
				phonemes = append(phonemes, string(ch))
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: letterCount})
			}
		}

		needSpace = true
	}

	// Apply PUA mapping
	phonemes = MapSequence(phonemes)

	return &PhonemizeResult{
		Tokens:   phonemes,
		Prosody:  prosody,
		EOSToken: "$",
	}, nil
}

// runeCount returns the number of runes in a string.
func runeCount(s string) int {
	n := 0
	for range s {
		n++
	}
	return n
}

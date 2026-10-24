package phonemize

import (
	"log/slog"
	"slices"
	"strings"
)

// EnglishPhonemizer converts English text to IPA phonemes.
type EnglishPhonemizer struct {
	cmuDict map[string][]string // word -> ARPAbet phonemes
}

// NewEnglishPhonemizer creates a phonemizer with the given CMU dictionary.
// cmuDict maps lowercase words to ARPAbet phoneme lists (e.g., "hello" -> ["HH","AH0","L","OW1"]).
// If cmuDict is nil, the phonemizer will still function but every word will
// be spelled letter by letter with letter names, producing significantly
// lower quality output.
func NewEnglishPhonemizer(cmuDict map[string][]string) *EnglishPhonemizer {
	if cmuDict == nil {
		slog.Warn("English phonemizer created without CMU dictionary; all words will use letter-by-letter fallback")
	}
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
	"i": true, "me": true, "my": true, "mine": true, "myself": true,
	"you": true, "your": true, "yours": true, "yourself": true,
	"he": true, "him": true, "his": true, "himself": true,
	"she": true, "her": true, "hers": true, "herself": true,
	"it": true, "its": true, "itself": true,
	"we": true, "us": true, "our": true, "ours": true, "ourselves": true,
	"they": true, "them": true, "their": true, "theirs": true, "themselves": true,
	// be-verbs
	"am": true, "is": true, "are": true, "was": true, "were": true,
	"be": true, "been": true, "being": true,
	// auxiliaries
	"have": true, "has": true, "had": true, "having": true,
	"do": true, "does": true, "did": true,
	"will": true, "would": true, "can": true, "could": true,
	"shall": true, "should": true, "may": true, "might": true, "must": true,
	// prepositions
	"at": true, "by": true, "for": true, "from": true, "in": true,
	"of": true, "on": true, "to": true, "with": true,
	"about": true, "after": true, "before": true, "between": true,
	"into": true, "through": true, "under": true,
	// conjunctions
	"and": true, "but": true, "or": true, "nor": true,
	"so": true, "yet": true,
	"if": true, "that": true, "than": true,
	"when": true, "while": true, "as": true,
	"because": true, "since": true,
	// others
	"not": true, "no": true,
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
// Tokens (used by the Portuguese tokenizer)
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

// ---------------------------------------------------------------------------
// Words
//
// The words come from english_normalize.go, which ports g2p_en's number
// expansion, accent stripping, character filter and tokenizer. The helpers
// below handle what g2p_en and english.py do after tokenization.
// ---------------------------------------------------------------------------

// sourceWords returns the words of the original text used to find function
// words.
//
// Mirrors Python re.findall(r"[a-zA-Z']+", text.lower()). Python takes them
// from the text before number expansion and aligns them with the spoken
// words in order, so "the 3 of us" gives "three" the function-word flag of
// "of". The training data was phonemized that way, so it is kept.
func sourceWords(text string) []string {
	words := strings.FieldsFunc(text, func(r rune) bool {
		return r >= 0x80 || !(isASCIILetter(byte(r)) || r == '\'')
	})
	for i, w := range words {
		words[i] = strings.ToLower(w)
	}
	return words
}

// isPunctuationWord reports whether word is one punctuation character
// (, . ; : ! ?), attached to the preceding word without a word boundary.
func isPunctuationWord(word string) bool {
	return len(word) == 1 && punctuationSet[rune(word[0])]
}

// hasASCIILetter reports whether s contains an ASCII letter.
func hasASCIILetter(s string) bool {
	for i := 0; i < len(s); i++ {
		if isASCIILetter(s[i]) {
			return true
		}
	}
	return false
}

// letterNames are the ARPAbet names of a-z, used to spell words that cannot
// be read otherwise.
var letterNames = [26]string{
	"EY1", "B IY1", "S IY1", "D IY1", "IY1", "EH1 F", "JH IY1", "EY1 CH",
	"AY1", "JH EY1", "K EY1", "EH1 L", "EH1 M", "EH1 N", "OW1", "P IY1",
	"K Y UW1", "AA1 R", "EH1 S", "T IY1", "Y UW1", "V IY1",
	"D AH1 B AH0 L Y UW0", "EH1 K S", "W AY1", "Z IY1",
}

// letterNameArpabet returns the name of an ASCII letter in ARPAbet, or nil
// for any other byte.
func letterNameArpabet(c byte) []string {
	if c >= 'A' && c <= 'Z' {
		c += 'a' - 'A'
	}
	if c < 'a' || c > 'z' {
		return nil
	}
	return strings.Fields(letterNames[c-'a'])
}

// splitCamelCase splits a word at CamelCase boundaries, like Python
// re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", word):
// ChatGPT -> Chat + GPT, HTMLParser -> HTML + Parser.
func splitCamelCase(word string) []string {
	isUpper := func(c byte) bool { return c >= 'A' && c <= 'Z' }
	isLower := func(c byte) bool { return c >= 'a' && c <= 'z' }
	runEnd := func(from int, pred func(byte) bool) int {
		j := from
		for j < len(word) && pred(word[j]) {
			j++
		}
		return j
	}
	var parts []string
	for i := 0; i < len(word); {
		switch {
		case isUpper(word[i]):
			upperEnd := runEnd(i, isUpper)
			lowerFollows := upperEnd < len(word) && isLower(word[upperEnd])
			switch {
			case lowerFollows && upperEnd-i >= 2:
				// The last capital starts the next part.
				parts = append(parts, word[i:upperEnd-1])
				i = upperEnd - 1
			case lowerFollows:
				end := runEnd(upperEnd, isLower)
				parts = append(parts, word[i:end])
				i = end
			default:
				parts = append(parts, word[i:upperEnd])
				i = upperEnd
			}
		case isLower(word[i]):
			end := runEnd(i, isLower)
			parts = append(parts, word[i:end])
			i = end
		default:
			i++
		}
	}
	return parts
}

// ---------------------------------------------------------------------------
// Morphological fallback for OOV words
// ---------------------------------------------------------------------------

// morphologicalFallback strips common English suffixes from a lowercase word
// missing from the dictionary and looks up the base form. If found, it
// returns the base ARPAbet with the suffix phonemes appended; otherwise nil.
// Same rules as the Rust and C++ fallback.
//
// Supported suffixes: -ing, -ed, -s/-es/-ies, -er, -ly/-ily, -est
func morphologicalFallback(word string, cmuDict map[string][]string) []string {
	n := len(word)
	tryBase := func(base, suffix string) []string {
		if arpa, ok := cmuDict[base]; ok {
			return slices.Concat(arpa, strings.Fields(suffix))
		}
		return nil
	}
	// doubled reports whether base ends with a doubled letter (sitt, runn).
	doubled := func(base string) bool {
		return len(base) >= 2 && base[len(base)-1] == base[len(base)-2]
	}

	// -ing (running->run, making->make, sitting->sit)
	if n > 4 && strings.HasSuffix(word, "ing") {
		base := word[:n-3]
		if r := tryBase(base, "IH0 NG"); r != nil {
			return r
		}
		if doubled(base) {
			if r := tryBase(base[:len(base)-1], "IH0 NG"); r != nil {
				return r
			}
		}
		if r := tryBase(base+"e", "IH0 NG"); r != nil {
			return r
		}
	}

	// -ed (walked->walk, stopped->stop, loved->love)
	if n > 3 && strings.HasSuffix(word, "ed") {
		base := word[:n-2]
		if r := tryBase(base, "D"); r != nil {
			return r
		}
		if doubled(base) {
			if r := tryBase(base[:len(base)-1], "D"); r != nil {
				return r
			}
		}
		if r := tryBase(word[:n-1], "D"); r != nil {
			return r
		}
	}

	// -s / -es / -ies (cats->cat, boxes->box, countries->country)
	if n > 2 && strings.HasSuffix(word, "s") {
		if n > 4 && strings.HasSuffix(word, "ies") {
			if r := tryBase(word[:n-3]+"y", "Z"); r != nil {
				return r
			}
		}
		if n > 3 && strings.HasSuffix(word, "es") {
			if r := tryBase(word[:n-2], "IH0 Z"); r != nil {
				return r
			}
		}
		if r := tryBase(word[:n-1], "Z"); r != nil {
			return r
		}
	}

	// -er (faster->fast, runner->run)
	if n > 3 && strings.HasSuffix(word, "er") {
		base := word[:n-2]
		if r := tryBase(base, "ER0"); r != nil {
			return r
		}
		if doubled(base) {
			if r := tryBase(base[:len(base)-1], "ER0"); r != nil {
				return r
			}
		}
	}

	// -ly / -ily (quickly->quick, happily->happy)
	if n > 3 && strings.HasSuffix(word, "ly") {
		if r := tryBase(word[:n-2], "L IY0"); r != nil {
			return r
		}
		if n > 4 && word[n-3] == 'i' {
			if r := tryBase(word[:n-3]+"y", "L IY0"); r != nil {
				return r
			}
		}
	}

	// -est (fastest->fast)
	if n > 4 && strings.HasSuffix(word, "est") {
		if r := tryBase(word[:n-3], "AH0 S T"); r != nil {
			return r
		}
	}

	return nil
}

// lookup returns the dictionary entry of word, or of its stem
// (morphological fallback).
func (p *EnglishPhonemizer) lookup(word string) ([]string, bool) {
	lower := strings.ToLower(word)
	// When cmuDict is nil (no dictionary loaded), the map lookup returns the
	// zero value (nil, false), so every word is spelled letter by letter.
	if arpa, ok := p.cmuDict[lower]; ok {
		return arpa, true
	}
	arpa := morphologicalFallback(lower, p.cmuDict)
	return arpa, arpa != nil
}

// wordArpabet returns the ARPAbet of a word; never nil when the word has a
// letter.
//
// Python reads words missing from the dictionary with g2p_en's neural
// guesser, which is not ported. Instead such a word is split at '-' and '.',
// retried without apostrophes, split at CamelCase boundaries, and finally
// spelled letter by letter. The parts are joined into one word.
func (p *EnglishPhonemizer) wordArpabet(word string) []string {
	if arpa, ok := p.lookup(word); ok {
		return arpa
	}
	join := func(parts []string) []string {
		var arpa []string
		for _, part := range parts {
			arpa = append(arpa, p.wordArpabet(part)...)
		}
		return arpa
	}
	if strings.ContainsAny(word, "-.") {
		return join(strings.FieldsFunc(word, func(r rune) bool { return r == '-' || r == '.' }))
	}
	if strings.Contains(word, "'") {
		return p.wordArpabet(strings.ReplaceAll(word, "'", ""))
	}
	if parts := splitCamelCase(word); len(parts) > 1 {
		return join(parts)
	}
	var spelled []string
	for i := 0; i < len(word); i++ {
		spelled = append(spelled, letterNameArpabet(word[i])...)
	}
	return spelled
}

// ---------------------------------------------------------------------------
// PhonemizeWithProsody — Phonemizer interface implementation
// ---------------------------------------------------------------------------

// PhonemizeWithProsody converts English text to IPA phoneme tokens with prosody.
//
// The text is normalized and tokenized like g2p_en (english_normalize.go).
// Each word is read from the CMU dictionary or the fallbacks of wordArpabet,
// converted to IPA, destressed when it is a function word, and given stress
// markers and prosody as Python's english.py does.
func (p *EnglishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	if strings.TrimSpace(text) == "" {
		return &PhonemizeResult{EOSToken: "$"}, nil
	}

	srcWords := sourceWords(text)
	words := normalizeAndTokenize(text)

	var phonemes []string
	var prosody []*ProsodyInfo
	needSpace := false
	srcIdx := 0

	for _, word := range words {
		isPunct := isPunctuationWord(word)

		// A word without a letter ("-", "'", "...") is kept as is, one
		// phoneme per character, as Python does.
		var ipas []ipaPhoneme
		if hasASCIILetter(word) {
			arpa := p.wordArpabet(word)
			if arpa == nil {
				continue
			}
			ipas = convertWordToIPA(arpa)
		} else {
			ipas = []ipaPhoneme{{ipa: word, stress: -1}}
		}

		if !isPunct {
			// Function words are matched against the source words in order.
			if srcIdx < len(srcWords) {
				if functionWords[srcWords[srcIdx]] {
					for j := range ipas {
						if ipas[j].stress >= 1 {
							ipas[j].stress = 0
						}
					}
				}
				srcIdx++
			}
			// Punctuation attaches to the preceding word; other words get a
			// word boundary before them (except the first).
			if needSpace {
				phonemes = append(phonemes, " ")
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
			}
		}

		// A3 = total IPA character count for the word
		wordPhonemeCount := 0
		for _, ph := range ipas {
			wordPhonemeCount += runeCount(ph.ipa)
		}

		for _, ph := range ipas {
			// stress -> A2: primary(1)->2, secondary(2)->1, else 0
			var a2 int
			switch ph.stress {
			case 1:
				a2 = 2
			case 2:
				a2 = 1
			}

			// Insert stress marker before stressed vowels
			switch ph.stress {
			case 1:
				phonemes = append(phonemes, "ˈ")
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhonemeCount})
			case 2:
				phonemes = append(phonemes, "ˌ")
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhonemeCount})
			}

			// Each IPA character becomes a separate phoneme token
			for _, ch := range ph.ipa {
				phonemes = append(phonemes, string(ch))
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhonemeCount})
			}
		}

		needSpace = true
	}

	// Determine EOS token from the last punctuation character.
	eosToken := "$"
eosSearch:
	for i := len(words) - 1; i >= 0; i-- {
		for j := len(words[i]) - 1; j >= 0; j-- {
			switch c := rune(words[i][j]); {
			case !punctuationSet[c]:
				continue
			case c == '?':
				eosToken = "?"
			case c == '!':
				eosToken = "!"
			}
			break eosSearch
		}
	}

	// Apply PUA mapping
	phonemes = MapSequence(phonemes)

	return &PhonemizeResult{
		Tokens:   phonemes,
		Prosody:  prosody,
		EOSToken: eosToken,
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

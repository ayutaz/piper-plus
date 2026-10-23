package phonemize

import (
	"strings"
	"unicode/utf8"
)

// SpanishPhonemizer implements rule-based G2P for Latin American Spanish (seseo).
type SpanishPhonemizer struct{}

// NewSpanishPhonemizer returns a new SpanishPhonemizer.
func NewSpanishPhonemizer() *SpanishPhonemizer {
	return &SpanishPhonemizer{}
}

// LanguageCode returns "es".
func (p *SpanishPhonemizer) LanguageCode() string { return "es" }

// PhonemizeWithProsody converts Spanish text to phoneme tokens with prosody.
func (p *SpanishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	tokens, prosody, eos := esProcess(text)
	mapped := MapSequence(tokens)
	return &PhonemizeResult{Tokens: mapped, Prosody: prosody, EOSToken: eos}, nil
}

// --- constants ---

var esVowels = map[rune]bool{'a': true, 'e': true, 'i': true, 'o': true, 'u': true}

var esAccentMap = map[rune]rune{
	'\u00e1': 'a', // á
	'\u00e9': 'e', // é
	'\u00ed': 'i', // í
	'\u00f3': 'o', // ó
	'\u00fa': 'u', // ú
	'\u00fc': 'u', // ü
}

var esPunctuation = map[rune]bool{
	'.': true, ',': true, '!': true, '?': true,
	';': true, ':': true, '\u00bf': true, '\u00a1': true,
}

var esFunctionWords = map[string]bool{
	"el": true, "la": true, "los": true, "las": true,
	"un": true, "una": true, "de": true, "del": true,
	"al": true, "a": true, "en": true, "con": true,
	"por": true, "y": true, "o": true, "que": true,
	"se": true, "me": true, "te": true, "le": true,
	"lo": true, "nos": true, "su": true, "mi": true,
	"tu": true, "es": true, "no": true, "si": true,
}

// --- helpers ---

func esBaseChar(ch rune) rune {
	if b, ok := esAccentMap[ch]; ok {
		return b
	}
	return ch
}

func esIsVowel(ch rune) bool { return esVowels[esBaseChar(ch)] }

func esHasAccent(ch rune) bool {
	switch ch {
	case '\u00e1', '\u00e9', '\u00ed', '\u00f3', '\u00fa':
		return true
	}
	return false
}

// esNormalize lowercases and returns rune slice.
func esNormalize(text string) []rune {
	return []rune(strings.ToLower(text))
}

// esTokenize splits runes into word tokens and punctuation tokens.
type esToken struct {
	text  string
	isPun bool
}

func esTokenize(runes []rune) []esToken {
	var tokens []esToken
	i := 0
	n := len(runes)
	for i < n {
		ch := runes[i]
		if esPunctuation[ch] {
			tokens = append(tokens, esToken{text: string(ch), isPun: true})
			i++
			continue
		}
		if esIsWordChar(ch) {
			j := i
			for j < n && esIsWordChar(runes[j]) {
				j++
			}
			tokens = append(tokens, esToken{text: string(runes[i:j]), isPun: false})
			i = j
			continue
		}
		i++ // skip whitespace and other chars
	}
	return tokens
}

func esIsWordChar(ch rune) bool {
	if ch >= 'a' && ch <= 'z' {
		return true
	}
	if _, ok := esAccentMap[ch]; ok {
		return true
	}
	if ch == '\u00f1' { // ñ
		return true
	}
	return false
}

// --- stress detection ---

// esUnit is one grapheme unit of a word: a digraph (ch, ll, rr, qu, gu/gü
// before e/i, sc/xc before e/i) or a single letter. start is its rune index.
type esUnit struct {
	start   int
	length  int
	isVowel bool
	silent  bool // silent h
}

// esSegmentGraphemes splits word into grapheme units, as Python's
// _segment_graphemes does, so that syllabification never splits a digraph
// and the silent u of qu/gu is not a vowel.
func esSegmentGraphemes(word []rune) []esUnit {
	n := len(word)
	base := make([]rune, n)
	for i, ch := range word {
		base[i] = esBaseChar(ch)
	}
	frontVowelAt := func(i int) bool { return i < n && (base[i] == 'e' || base[i] == 'i') }

	var units []esUnit
	for i := 0; i < n; {
		bch := base[i]
		next := rune(0)
		if i+1 < n {
			next = base[i+1]
		}
		digraph := false
		switch {
		case bch == 'q' && next == 'u':
			digraph = true
		case bch == 'g' && i+1 < n && word[i+1] == 'ü' && frontVowelAt(i+2):
			digraph = true
		case bch == 'g' && next == 'u' && frontVowelAt(i+2):
			digraph = true
		case bch == 'c' && next == 'h', bch == 'l' && next == 'l', bch == 'r' && next == 'r':
			digraph = true
		case (bch == 's' || bch == 'x') && next == 'c' && frontVowelAt(i+2):
			digraph = true
		}
		switch {
		case digraph:
			units = append(units, esUnit{start: i, length: 2})
			i += 2
		case bch == 'h':
			units = append(units, esUnit{start: i, length: 1, silent: true})
			i++
		default:
			units = append(units, esUnit{start: i, length: 1, isVowel: esVowels[bch]})
			i++
		}
	}
	return units
}

// esInseparableOnsets are consonant pairs that start a syllable together.
var esInseparableOnsets = map[string]bool{
	"bl": true, "br": true, "cl": true, "cr": true, "dr": true, "fl": true, "fr": true,
	"gl": true, "gr": true, "pl": true, "pr": true, "tr": true, "tl": true,
}

// esSyllableStarts returns the unit indices where each syllable starts, as
// Python's _find_syllable_boundaries does. Like Python, a consonant before
// the first vowel also opens a syllable when another consonant precedes it
// ("tres" is "t" + "res").
func esSyllableStarts(word []rune, units []esUnit) []int {
	var ns []int // indices of non-silent units
	for idx, u := range units {
		if !u.silent {
			ns = append(ns, idx)
		}
	}
	if len(ns) == 0 {
		return []int{0}
	}
	isVowel := func(k int) bool { return units[ns[k]].isVowel }
	lastRune := func(k int) rune {
		u := units[ns[k]]
		return word[u.start+u.length-1]
	}
	isStrong := func(r rune) bool { b := esBaseChar(r); return b == 'a' || b == 'e' || b == 'o' }
	isWeak := func(r rune) bool { b := esBaseChar(r); return b == 'i' || b == 'u' }

	starts := []int{0}
	for i := 1; i < len(ns); {
		if isVowel(i) {
			if isVowel(i - 1) {
				prev, curr := lastRune(i-1), lastRune(i)
				switch {
				case isStrong(prev) && isStrong(curr):
					starts = append(starts, i) // hiatus
				case (isWeak(curr) && esHasAccent(curr)) || (isWeak(prev) && esHasAccent(prev)):
					starts = append(starts, i) // accented weak vowel breaks the diphthong
				}
			}
			i++
			continue
		}
		consStart := i
		for i < len(ns) && !isVowel(i) {
			i++
		}
		if i >= len(ns) {
			break // no vowel follows
		}
		pair := func(k int) string { return string([]rune{esBaseChar(lastRune(k)), esBaseChar(lastRune(k + 1))}) }
		switch count := i - consStart; {
		case count == 1:
			starts = append(starts, consStart)
		case count == 2 && esInseparableOnsets[pair(consStart)]:
			starts = append(starts, consStart)
		case count == 2:
			starts = append(starts, consStart+1)
		case esInseparableOnsets[pair(i-2)]:
			starts = append(starts, i-2)
		default:
			starts = append(starts, i-1)
		}
	}
	for k, s := range starts {
		starts[k] = ns[s]
	}
	return starts
}

// esStressIndex returns the rune index of the first vowel of the stressed
// syllable, where Python's _insert_stress_marker puts the stress marker, or
// -1 if that syllable has no vowel.
//
// Stress rules: an accent mark stresses its syllable; otherwise words ending
// in a vowel, n or s stress the penultimate syllable and others the last.
func esStressIndex(word []rune) int {
	if len(word) == 0 {
		return -1
	}
	units := esSegmentGraphemes(word)
	starts := esSyllableStarts(word, units)

	stressed := -1
	for i, ch := range word {
		if !esHasAccent(ch) {
			continue
		}
		stressed = 0
		for s := len(starts) - 1; s >= 0; s-- {
			u := units[starts[s]]
			if u.start <= i {
				stressed = s
				break
			}
		}
		break
	}
	if stressed < 0 {
		switch last := esBaseChar(word[len(word)-1]); {
		case len(starts) == 1:
			stressed = 0
		case esVowels[last] || last == 'n' || last == 's':
			stressed = len(starts) - 2
		default:
			stressed = len(starts) - 1
		}
	}

	end := len(units)
	if stressed+1 < len(starts) {
		end = starts[stressed+1]
	}
	for _, u := range units[starts[stressed]:end] {
		if u.isVowel {
			return u.start
		}
	}
	return -1
}

// --- G2P ---

// esG2P converts a single word to phonemes. Returns phonemes and the
// stressed vowel's phoneme index (-1 if none).
func esG2P(word []rune) (phonemes []string, stressPhIdx int) {
	n := len(word)
	stressRuneIdx := esStressIndex(word)
	stressPhIdx = -1

	// Build base word for context checks.
	base := make([]rune, n)
	for i, ch := range word {
		base[i] = esBaseChar(ch)
	}

	isWordInitOrNasalL := func(i int) bool {
		if i == 0 {
			return true
		}
		prev := base[i-1]
		return prev == 'm' || prev == 'n' || prev == 'l'
	}

	i := 0
	for i < n {
		bch := base[i]
		markStress := (i == stressRuneIdx)

		// --- Digraphs (longest match first) ---

		if bch == 'c' && i+1 < n && base[i+1] == 'h' {
			phonemes = append(phonemes, "tʃ")
			i += 2
			continue
		}
		if bch == 'l' && i+1 < n && base[i+1] == 'l' {
			phonemes = append(phonemes, "ʝ")
			i += 2
			continue
		}
		if bch == 'r' && i+1 < n && base[i+1] == 'r' {
			phonemes = append(phonemes, "rr")
			i += 2
			continue
		}
		if bch == 'q' && i+1 < n && base[i+1] == 'u' {
			phonemes = append(phonemes, "k")
			i += 2
			continue
		}
		// gü before e/i -> ɡw
		if bch == 'g' && i+1 < n && word[i+1] == '\u00fc' && i+2 < n && (base[i+2] == 'e' || base[i+2] == 'i') {
			phonemes = append(phonemes, "ɡ")
			phonemes = append(phonemes, "w")
			i += 2
			continue
		}
		// gu before e/i -> ɡ (u silent)
		if bch == 'g' && i+1 < n && base[i+1] == 'u' && i+2 < n && (base[i+2] == 'e' || base[i+2] == 'i') {
			if isWordInitOrNasalL(i) {
				phonemes = append(phonemes, "ɡ")
			} else {
				phonemes = append(phonemes, "ɣ")
			}
			i += 2
			continue
		}

		// --- Vowels ---
		if esVowels[bch] {
			if markStress {
				stressPhIdx = len(phonemes)
			}
			phonemes = append(phonemes, string(bch))
			i++
			continue
		}

		// --- Single consonants ---
		switch bch {
		case 'b', 'v':
			if isWordInitOrNasalL(i) {
				phonemes = append(phonemes, "b")
			} else {
				phonemes = append(phonemes, "β")
			}
		case 'c':
			if i+1 < n && (base[i+1] == 'e' || base[i+1] == 'i') {
				phonemes = append(phonemes, "s") // seseo
			} else {
				phonemes = append(phonemes, "k")
			}
		case 'd':
			if isWordInitOrNasalL(i) {
				phonemes = append(phonemes, "d")
			} else {
				phonemes = append(phonemes, "ð")
			}
		case 'f':
			phonemes = append(phonemes, "f")
		case 'g':
			switch {
			case i+1 < n && (base[i+1] == 'e' || base[i+1] == 'i'):
				phonemes = append(phonemes, "x")
			case isWordInitOrNasalL(i):
				phonemes = append(phonemes, "ɡ")
			default:
				phonemes = append(phonemes, "ɣ")
			}
		case 'h':
			// silent
		case 'j':
			phonemes = append(phonemes, "x")
		case 'k':
			phonemes = append(phonemes, "k")
		case 'l':
			phonemes = append(phonemes, "l")
		case 'm':
			phonemes = append(phonemes, "m")
		case 'n':
			phonemes = append(phonemes, "n")
		case '\u00f1': // ñ
			phonemes = append(phonemes, "ɲ")
		case 'p':
			phonemes = append(phonemes, "p")
		case 'r':
			if i == 0 || (i > 0 && (base[i-1] == 'l' || base[i-1] == 'n' || base[i-1] == 's')) {
				phonemes = append(phonemes, "rr")
			} else {
				phonemes = append(phonemes, "ɾ")
			}
		case 's':
			// sc + e/i -> single /s/ (Latin American seseo: avoid geminate ss)
			if i+1 < n && base[i+1] == 'c' && i+2 < n && (base[i+2] == 'e' || base[i+2] == 'i') {
				phonemes = append(phonemes, "s")
				i += 2 // skip 's' and 'c'; vowel handled next iteration
				continue
			}
			phonemes = append(phonemes, "s")
		case 't':
			phonemes = append(phonemes, "t")
		case 'w':
			phonemes = append(phonemes, "w")
		case 'x':
			// xc + e/i -> /k,s/ with c absorbed (x already provides /ks/)
			if i+1 < n && base[i+1] == 'c' && i+2 < n && (base[i+2] == 'e' || base[i+2] == 'i') {
				phonemes = append(phonemes, "k")
				phonemes = append(phonemes, "s")
				i += 2 // skip 'x' and 'c'; vowel handled next iteration
				continue
			}
			phonemes = append(phonemes, "k")
			phonemes = append(phonemes, "s")
		case 'y':
			if i == n-1 {
				phonemes = append(phonemes, "i")
			} else {
				phonemes = append(phonemes, "ʝ")
			}
		case 'z':
			phonemes = append(phonemes, "s") // seseo
		default:
			// unknown character: skip
		}
		i++
	}
	return phonemes, stressPhIdx
}

// --- main processing ---

func esProcess(text string) (tokens []string, prosody []*ProsodyInfo, eos string) {
	runes := esNormalize(text)
	wordTokens := esTokenize(runes)
	eos = "$"
	needSpace := false

	for _, tok := range wordTokens {
		if tok.isPun {
			r, _ := utf8.DecodeRuneInString(tok.text)
			ch := tok.text
			tokens = append(tokens, ch)
			prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
			// Track EOS token for sentence-final punctuation.
			if r == '?' || r == '!' || r == '.' {
				eos = ch
			}
			// needSpace stays as it is: the next word is still a new word,
			// as in Python's spanish.py.
			continue
		}

		if needSpace {
			tokens = append(tokens, " ")
			prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
		}

		wordRunes := []rune(tok.text)
		phonemes, stressPhIdx := esG2P(wordRunes)
		isFuncWord := esFunctionWords[tok.text]
		wordPhCount := len(phonemes)

		for pi, ph := range phonemes {
			// Insert stress marker before stressed vowel (not for function words).
			if !isFuncWord && pi == stressPhIdx {
				tokens = append(tokens, "ˈ")
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 2, A3: wordPhCount})
			}
			a2 := 0
			if !isFuncWord && pi == stressPhIdx {
				a2 = 2
			}
			tokens = append(tokens, ph)
			prosody = append(prosody, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhCount})
		}
		needSpace = true
	}

	return tokens, prosody, eos
}

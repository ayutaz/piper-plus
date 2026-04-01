package phonemize

import "strings"

// KoreanPhonemizer implements Hangul decomposition + IPA mapping for Korean.
//
// Converts Korean text to IPA phonemes by decomposing Hangul syllable blocks
// into jamo (initial, medial, final) and mapping each to IPA tokens.
// Basic liaison (연음화) is applied as the only phonological rule.
//
// Prosody values: A1=0, A2=0, A3=number of Hangul syllables in the current word.
type KoreanPhonemizer struct{}

// NewKoreanPhonemizer returns a new KoreanPhonemizer.
func NewKoreanPhonemizer() *KoreanPhonemizer {
	return &KoreanPhonemizer{}
}

// LanguageCode returns "ko".
func (p *KoreanPhonemizer) LanguageCode() string { return "ko" }

// PhonemizeWithProsody converts Korean text to phoneme tokens with prosody.
func (p *KoreanPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	tokens, a3Values, eos := koProcessWithA3(text)
	mapped := MapSequence(tokens)

	prosody := make([]*ProsodyInfo, len(mapped))
	for i := range mapped {
		a3 := 0
		if i < len(a3Values) {
			a3 = a3Values[i]
		}
		prosody[i] = &ProsodyInfo{A1: 0, A2: 0, A3: a3}
	}

	return &PhonemizeResult{Tokens: mapped, Prosody: prosody, EOSToken: eos}, nil
}

// Ensure KoreanPhonemizer implements Phonemizer at compile time.
var _ Phonemizer = (*KoreanPhonemizer)(nil)

// ---------------------------------------------------------------------------
// Hangul syllable block range (U+AC00 .. U+D7A3)
// ---------------------------------------------------------------------------

const (
	koHangulStart = 0xAC00
	koHangulEnd   = 0xD7A3
	koNInitials   = 19
	koNMedials    = 21
	koNFinals     = 28
)

// ---------------------------------------------------------------------------
// IPA codepoints used in Korean phonemization
// ---------------------------------------------------------------------------

const (
	koFlap         = "\u027E" // ɾ alveolar flap (ㄹ initial)
	koEng          = "\u014B" // ŋ velar nasal (ㅇ coda)
	koOpenE        = "\u025B" // ɛ open-mid front unrounded (ㅐ)
	koOpenMidBack  = "\u028C" // ʌ open-mid back unrounded (ㅓ)
	koCloseBackUnr = "\u026F" // ɯ close back unrounded (ㅡ)
	koVelarApprox  = "\u0270" // ɰ velar approximant (ㅢ)
)

// ---------------------------------------------------------------------------
// Initial consonants (초성) — 19 entries, index → IPA token
// Empty string = silent (ㅇ in initial position)
// ---------------------------------------------------------------------------

var koInitialTable = [koNInitials]string{
	"k",    //  0: ㄱ
	"k͈",   //  1: ㄲ (tense)
	"n",    //  2: ㄴ
	"t",    //  3: ㄷ
	"t͈",   //  4: ㄸ (tense)
	koFlap, //  5: ㄹ
	"m",    //  6: ㅁ
	"p",    //  7: ㅂ
	"p͈",   //  8: ㅃ (tense)
	"s",    //  9: ㅅ
	"s͈",   // 10: ㅆ (tense)
	"",     // 11: ㅇ (silent in initial)
	"tɕ",   // 12: ㅈ
	"t͈ɕ",  // 13: ㅉ (tense)
	"tɕʰ",  // 14: ㅊ (aspirated)
	"kʰ",   // 15: ㅋ (aspirated)
	"tʰ",   // 16: ㅌ (aspirated)
	"pʰ",   // 17: ㅍ (aspirated)
	"h",    // 18: ㅎ
}

// ---------------------------------------------------------------------------
// Medial vowels (중성) — 21 entries, index → 1–2 IPA tokens
// Diphthongs produce glide + vowel (2 tokens).
// ---------------------------------------------------------------------------

type koMedialEntry struct {
	ph1 string
	ph2 string // empty if monophthong
}

var koMedialTable = [koNMedials]koMedialEntry{
	{"a", ""},            //  0: ㅏ
	{koOpenE, ""},        //  1: ㅐ
	{"j", "a"},           //  2: ㅑ
	{"j", koOpenE},       //  3: ㅒ
	{koOpenMidBack, ""},  //  4: ㅓ
	{"e", ""},            //  5: ㅔ
	{"j", koOpenMidBack}, //  6: ㅕ
	{"j", "e"},           //  7: ㅖ
	{"o", ""},            //  8: ㅗ
	{"w", "a"},           //  9: ㅘ
	{"w", koOpenE},       // 10: ㅙ
	{"w", "e"},           // 11: ㅚ (modern Seoul: [we])
	{"j", "o"},           // 12: ㅛ
	{"u", ""},            // 13: ㅜ
	{"w", koOpenMidBack}, // 14: ㅝ
	{"w", "e"},           // 15: ㅞ
	{"w", "i"},           // 16: ㅟ
	{"j", "u"},           // 17: ㅠ
	{koCloseBackUnr, ""}, // 18: ㅡ
	{koVelarApprox, "i"}, // 19: ㅢ
	{"i", ""},            // 20: ㅣ
}

// ---------------------------------------------------------------------------
// Final consonants (종성) — 28 entries
//
// Finals are neutralized to 7 surface forms: k̚, t̚, p̚, n, m, l, ŋ.
// Complex finals (겹받침) are simplified to their representative sound.
// Index 0 = no final consonant.
//
// For liaison: liaisonInitial is the initial index the final "becomes"
// when followed by ㅇ (silent initial). -1 means no liaison.
// residualFinal holds the index remaining in the current syllable after
// liaison (for complex finals); 0 means the final moves entirely.
// ---------------------------------------------------------------------------

type koFinalEntry struct {
	ph             string // IPA token; empty if no final
	liaisonInitial int    // initial index for liaison (-1 = no liaison)
	residualFinal  int    // final index remaining after liaison (0 = fully moved)
}

var koFinalTable = [koNFinals]koFinalEntry{
	{"", -1, 0},    //  0: (none)
	{"k̚", 0, 0},   //  1: ㄱ
	{"k̚", 1, 0},   //  2: ㄲ
	{"k̚", 9, 1},   //  3: ㄳ -> ㅅ, residual ㄱ
	{"n", -1, 0},   //  4: ㄴ
	{"n", 12, 4},   //  5: ㄵ -> ㅈ, residual ㄴ
	{"n", -1, 0},   //  6: ㄶ (ㄴ+ㅎ -> n)
	{"t̚", 3, 0},   //  7: ㄷ
	{"l", 5, 0},    //  8: ㄹ
	{"k̚", 0, 8},   //  9: ㄺ -> ㄱ, residual ㄹ
	{"m", 6, 8},    // 10: ㄻ -> ㅁ, residual ㄹ
	{"l", 7, 8},    // 11: ㄼ -> ㅂ, residual ㄹ
	{"l", 9, 8},    // 12: ㄽ -> ㅅ, residual ㄹ
	{"l", 16, 8},   // 13: ㄾ -> ㅌ, residual ㄹ
	{"l", 17, 8},   // 14: ㄿ -> ㅍ, residual ㄹ
	{"l", -1, 0},   // 15: ㅀ (ㄹ+ㅎ -> l)
	{"m", -1, 0},   // 16: ㅁ
	{"p̚", 7, 0},   // 17: ㅂ
	{"p̚", 9, 17},  // 18: ㅄ -> ㅅ, residual ㅂ
	{"t̚", 9, 0},   // 19: ㅅ
	{"t̚", 10, 0},  // 20: ㅆ
	{koEng, -1, 0}, // 21: ㅇ (velar nasal)
	{"t̚", 12, 0},  // 22: ㅈ
	{"t̚", 14, 0},  // 23: ㅊ
	{"k̚", 15, 0},  // 24: ㅋ
	{"t̚", 16, 0},  // 25: ㅌ
	{"p̚", 17, 0},  // 26: ㅍ
	{"t̚", -1, 0},  // 27: ㅎ (h dropped)
}

// ---------------------------------------------------------------------------
// Punctuation
// ---------------------------------------------------------------------------

var koPunctuation = map[rune]bool{
	',': true, '.': true, ';': true, ':': true, '!': true, '?': true,
	'\u3002': true, // 。
	'\uFF0C': true, // ，
	'\uFF01': true, // ！
	'\uFF1F': true, // ？
	'\u3001': true, // 、
}

// ---------------------------------------------------------------------------
// Hangul detection and decomposition
// ---------------------------------------------------------------------------

func koIsHangulSyllable(ch rune) bool {
	return ch >= koHangulStart && ch <= koHangulEnd
}

// koDecompose decomposes a Hangul syllable into (initial, medial, final) indices.
func koDecompose(ch rune) (int, int, int) {
	code := int(ch - koHangulStart)
	initial := code / (koNMedials * koNFinals)
	medial := (code % (koNMedials * koNFinals)) / koNFinals
	final_ := code % koNFinals
	return initial, medial, final_
}

// ---------------------------------------------------------------------------
// NFD Hangul jamo -> NFC recomposition
//
// macOS decomposes Hangul into NFD jamo sequences (U+1100-U+11FF).
// This function recomposes them into precomposed syllables (U+AC00-U+D7A3).
// ---------------------------------------------------------------------------

func koIsLeadingJamo(ch rune) bool  { return ch >= 0x1100 && ch <= 0x1112 }
func koIsVowelJamo(ch rune) bool    { return ch >= 0x1161 && ch <= 0x1175 }
func koIsTrailingJamo(ch rune) bool { return ch >= 0x11A8 && ch <= 0x11C2 }

func koComposeHangulJamo(cps []rune) []rune {
	out := make([]rune, 0, len(cps))
	n := len(cps)
	i := 0

	for i < n {
		if koIsLeadingJamo(cps[i]) && i+1 < n && koIsVowelJamo(cps[i+1]) {
			leading := cps[i] - 0x1100
			vowel := cps[i+1] - 0x1161
			var trailing rune
			if i+2 < n && koIsTrailingJamo(cps[i+2]) {
				trailing = cps[i+2] - 0x11A8 + 1
				i += 3
			} else {
				trailing = 0
				i += 2
			}
			composed := (leading*21+vowel)*28 + trailing + 0xAC00
			out = append(out, composed)
		} else {
			out = append(out, cps[i])
			i++
		}
	}

	return out
}

// ---------------------------------------------------------------------------
// Syllable structure for liaison processing
// ---------------------------------------------------------------------------

type koSyllable struct {
	initial int
	medial  int
	final_  int
}

// koEmitSyllable emits phonemes for a single syllable (after liaison adjustment).
func koEmitSyllable(syl *koSyllable, out *[]string) {
	// Initial consonant
	if syl.initial >= 0 && syl.initial < koNInitials {
		ph := koInitialTable[syl.initial]
		if ph != "" {
			*out = append(*out, ph)
		}
	}

	// Medial vowel (1-2 phonemes)
	if syl.medial >= 0 && syl.medial < koNMedials {
		entry := koMedialTable[syl.medial]
		*out = append(*out, entry.ph1)
		if entry.ph2 != "" {
			*out = append(*out, entry.ph2)
		}
	}

	// Final consonant
	if syl.final_ > 0 && syl.final_ < koNFinals {
		ph := koFinalTable[syl.final_].ph
		if ph != "" {
			*out = append(*out, ph)
		}
	}
}

// ---------------------------------------------------------------------------
// Process a run of Hangul syllables: decompose, apply liaison, emit phonemes
// ---------------------------------------------------------------------------

func koProcessHangulRun(cps []rune, out *[]string) {
	if len(cps) == 0 {
		return
	}

	// Decompose all syllables
	syls := make([]koSyllable, len(cps))
	for i, ch := range cps {
		ini, med, fin := koDecompose(ch)
		syls[i] = koSyllable{initial: ini, medial: med, final_: fin}
	}

	// Apply basic liaison (연음화):
	// If syllable[i] has a final consonant and syllable[i+1] starts with
	// ㅇ (initial==11, silent), move the final to become the next initial.
	for i := 0; i < len(syls)-1; i++ {
		fi := syls[i].final_
		if fi == 0 || fi >= koNFinals {
			continue
		}
		if syls[i+1].initial != 11 {
			continue
		}

		liaisonInit := koFinalTable[fi].liaisonInitial
		if liaisonInit < 0 {
			continue
		}

		// Move final -> next initial (released form)
		syls[i+1].initial = liaisonInit
		// For complex finals, keep residual; for simple finals, clears entirely.
		syls[i].final_ = koFinalTable[fi].residualFinal
	}

	// Emit phonemes for all syllables
	for i := range syls {
		koEmitSyllable(&syls[i], out)
	}
}

// ---------------------------------------------------------------------------
// Core processing
// ---------------------------------------------------------------------------

// koCountHangulSyllables counts the number of Hangul syllable characters in a slice of runes.
func koCountHangulSyllables(cps []rune) int {
	count := 0
	for _, ch := range cps {
		if koIsHangulSyllable(ch) {
			count++
		}
	}
	return count
}

// koProcessWithA3 is like koProcess but also returns per-token A3 values.
// A3 is the number of Hangul syllables in the word that produced each token.
// Space tokens get A3=0; Latin tokens get A3=1 (max(0,1) like Python).
func koProcessWithA3(text string) (tokens []string, a3Values []int, eos string) {
	cps := []rune(strings.ToLower(text))
	if len(cps) == 0 {
		return nil, nil, "$"
	}

	// Recompose NFD Hangul jamo sequences into NFC precomposed syllables
	cps = koComposeHangulJamo(cps)

	eos = "$"
	needSpace := false
	n := len(cps)
	i := 0

	for i < n {
		ch := cps[i]

		// Whitespace -> mark word boundary
		if ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r' {
			needSpace = true
			i++
			continue
		}

		// Punctuation -> emit directly
		if koPunctuation[ch] {
			s := string(ch)
			tokens = append(tokens, s)
			a3Values = append(a3Values, 0)
			switch ch {
			case '?', '\uFF1F':
				eos = "?"
			case '!', '\uFF01':
				eos = "!"
			}
			needSpace = false
			i++
			continue
		}

		// Hangul syllable run
		if koIsHangulSyllable(ch) {
			if needSpace && len(tokens) > 0 {
				tokens = append(tokens, " ")
				a3Values = append(a3Values, 0)
			}

			// Find the extent of the Hangul run
			runStart := i
			for i < n && koIsHangulSyllable(cps[i]) {
				i++
			}
			syllableCount := koCountHangulSyllables(cps[runStart:i])
			if syllableCount < 1 {
				syllableCount = 1
			}
			tokensBefore := len(tokens)
			koProcessHangulRun(cps[runStart:i], &tokens)
			tokensAdded := len(tokens) - tokensBefore
			for j := 0; j < tokensAdded; j++ {
				a3Values = append(a3Values, syllableCount)
			}
			needSpace = true
			continue
		}

		// Latin alphabetic -> pass through lowercase
		if ch >= 'a' && ch <= 'z' {
			if needSpace && len(tokens) > 0 {
				tokens = append(tokens, " ")
				a3Values = append(a3Values, 0)
			}
			tokens = append(tokens, string(ch))
			a3Values = append(a3Values, 1)
			needSpace = true
			i++
			continue
		}

		// Unknown character -> skip
		i++
	}

	return tokens, a3Values, eos
}

func koProcess(text string) (tokens []string, eos string) {
	cps := []rune(strings.ToLower(text))
	if len(cps) == 0 {
		return nil, "$"
	}

	// Recompose NFD Hangul jamo sequences into NFC precomposed syllables
	cps = koComposeHangulJamo(cps)

	eos = "$"
	needSpace := false
	n := len(cps)
	i := 0

	for i < n {
		ch := cps[i]

		// Whitespace -> mark word boundary
		if ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r' {
			needSpace = true
			i++
			continue
		}

		// Punctuation -> emit directly
		if koPunctuation[ch] {
			s := string(ch)
			tokens = append(tokens, s)
			switch ch {
			case '?', '\uFF1F':
				eos = "?"
			case '!', '\uFF01':
				eos = "!"
			}
			needSpace = false
			i++
			continue
		}

		// Hangul syllable run
		if koIsHangulSyllable(ch) {
			if needSpace && len(tokens) > 0 {
				tokens = append(tokens, " ")
			}

			// Find the extent of the Hangul run
			runStart := i
			for i < n && koIsHangulSyllable(cps[i]) {
				i++
			}
			koProcessHangulRun(cps[runStart:i], &tokens)
			needSpace = true
			continue
		}

		// Latin alphabetic -> pass through lowercase
		if ch >= 'a' && ch <= 'z' {
			if needSpace && len(tokens) > 0 {
				tokens = append(tokens, " ")
			}
			tokens = append(tokens, string(ch))
			needSpace = true
			i++
			continue
		}

		// Unknown character -> skip
		i++
	}

	return tokens, eos
}

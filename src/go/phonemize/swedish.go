package phonemize

import (
	"strings"
	"unicode"

	"golang.org/x/text/unicode/norm"
)

// ---------------------------------------------------------------------------
// Swedish G2P constants and exception word lists
// ---------------------------------------------------------------------------
// Reference: src/python/piper_train/phonemize/swedish.py
// This file defines all constants needed by the Swedish G2P engine,
// plus the M2 core G2P logic (struct, normalize, tokenize, loanword,
// consonant conversion, vowel length, word G2P integration) and
// M3 post-processing (retroflex assimilation, stress detection +
// marker insertion, PhonemizeWithProsody integration).

// SwedishPhonemizer converts Swedish text to IPA phonemes using rule-based G2P.
type SwedishPhonemizer struct{}

// NewSwedishPhonemizer returns a new SwedishPhonemizer.
func NewSwedishPhonemizer() *SwedishPhonemizer { return &SwedishPhonemizer{} }

// LanguageCode returns "sv".
func (p *SwedishPhonemizer) LanguageCode() string { return "sv" }

// PhonemizeWithProsody converts Swedish text to phoneme tokens with prosody.
func (p *SwedishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	text = svNormalize(text)
	toks := svTokenize(text)

	var phs []string
	var pro []*ProsodyInfo
	needSpace := false
	eos := "$"

	for _, tk := range toks {
		if tk.isPun {
			// Each punctuation character as a separate token
			for _, c := range tk.text {
				ch := string(c)
				phs = append(phs, ch)
				pro = append(pro, &ProsodyInfo{})
				if c == '?' || c == '!' {
					eos = ch
				}
			}
		} else {
			// Word token — insert inter-word space
			if needSpace {
				phs = append(phs, " ")
				pro = append(pro, &ProsodyInfo{})
			}

			wp := svPhonemizeWord(tk.text)

			// A3: count non-stress-marker phonemes
			wordPhCount := 0
			for _, ph := range wp {
				if ph != "\u02c8" && ph != "\u02cc" {
					wordPhCount++
				}
			}

			// Prosody construction + token append
			for _, ph := range wp {
				a2 := 0
				if ph == "\u02c8" {
					a2 = 2 // primary stress
				}
				phs = append(phs, ph)
				pro = append(pro, &ProsodyInfo{A1: 0, A2: a2, A3: wordPhCount})
			}

			needSpace = true
		}
	}

	// PUA conversion (MapSequence)
	phs = MapSequence(phs)
	return &PhonemizeResult{Tokens: phs, Prosody: pro, EOSToken: eos}, nil
}

var _ Phonemizer = (*SwedishPhonemizer)(nil)

// ---------------------------------------------------------------------------
// Vowel / consonant sets
// ---------------------------------------------------------------------------

var svFrontVowels = map[rune]bool{
	'e': true, 'i': true, 'y': true, '\u00e4': true, '\u00f6': true,
}

var svAllVowels = map[rune]bool{
	'a': true, 'e': true, 'i': true, 'o': true, 'u': true,
	'y': true, '\u00e5': true, '\u00e4': true, '\u00f6': true,
}

var svConsonants = map[rune]bool{
	'b': true, 'c': true, 'd': true, 'f': true, 'g': true,
	'h': true, 'j': true, 'k': true, 'l': true, 'm': true,
	'n': true, 'p': true, 'q': true, 'r': true, 's': true,
	't': true, 'v': true, 'w': true, 'x': true, 'z': true,
}

// ---------------------------------------------------------------------------
// Vowel mappings (Complementary Quantity)
// ---------------------------------------------------------------------------

// svLongVowelMap maps Swedish vowel letters to their long IPA realizations.
// Values are multi-character IPA strings that will be PUA-mapped by MapSequence().
var svLongVowelMap = map[rune]string{
	'a':      "\u0251\u02d0", // ɑː
	'e':      "e\u02d0",      // eː
	'i':      "i\u02d0",      // iː
	'o':      "u\u02d0",      // uː (default; /oː/ for O_LONG_AS_OO words)
	'u':      "\u0289\u02d0", // ʉː
	'y':      "y\u02d0",      // yː
	'\u00e5': "o\u02d0",      // å → oː
	'\u00e4': "\u025b\u02d0", // ä → ɛː
	'\u00f6': "\u00f8\u02d0", // ö → øː
}

// svShortVowelMap maps Swedish vowel letters to their short IPA realizations.
// Values are single-character IPA (no PUA needed).
var svShortVowelMap = map[rune]string{
	'a':      "a",
	'e':      "\u025b", // ɛ
	'i':      "\u026a", // ɪ
	'o':      "\u0254", // ɔ
	'u':      "\u0275", // ɵ
	'y':      "\u028f", // ʏ
	'\u00e5': "\u0254", // å → ɔ
	'\u00e4': "\u025b", // ä → ɛ
	'\u00f6': "\u0153", // ö → œ
}

// svOLongAsOOPhoneme is the long vowel for "o" in O_LONG_AS_OO words.
const svOLongAsOOPhoneme = "o\u02d0" // oː

// ---------------------------------------------------------------------------
// Default consonant → IPA (single-letter fallback)
// ---------------------------------------------------------------------------

// svConsonantDefault maps single consonant letters to their default IPA output.
// Context-dependent rules (k/g + front vowel, etc.) override this.
var svConsonantDefault = map[rune]string{
	'b': "b",
	'c': "k",
	'd': "d",
	'f': "f",
	'g': "\u0261", // ɡ (IPA, U+0261)
	'h': "h",
	'j': "j",
	'k': "k",
	'l': "l",
	'm': "m",
	'n': "n",
	'p': "p",
	'q': "k",
	'r': "r",
	's': "s",
	't': "t",
	'v': "v",
	'w': "v",
	'x': "ks",
	'z': "s",
}

// ---------------------------------------------------------------------------
// Punctuation
// ---------------------------------------------------------------------------

var svPunctuation = map[rune]bool{
	'.': true, ',': true, ';': true, ':': true, '!': true, '?': true,
}

// ---------------------------------------------------------------------------
// Exception word lists (10 categories)
// All lists match Python reference implementation exactly.
// ---------------------------------------------------------------------------

// svHardKWords: k + front vowel → /k/ (hard). 75 words.
var svHardKWords = map[string]bool{
	"backe":    true,
	"bricka":   true,
	"docka":    true,
	"dricka":   true,
	"dyker":    true,
	"dyket":    true,
	"enkel":    true,
	"ficka":    true,
	"flicka":   true,
	"fröken":   true,
	"kebab":    true,
	"kennel":   true,
	"kent":     true,
	"keps":     true,
	"kerna":    true,
	"keso":     true,
	"ketchup":  true,
	"kex":      true,
	"kibbutz":  true,
	"kick":     true,
	"kikare":   true,
	"kille":    true,
	"kilo":     true,
	"kilt":     true,
	"kimono":   true,
	"kines":    true,
	"kinesisk": true,
	"kiosk":    true,
	"kirke":    true,
	"kissa":    true,
	"kitsch":   true,
	"kiwi":     true,
	"leken":    true,
	"leker":    true,
	"lekerska": true,
	"läker":    true,
	"läket":    true,
	"märke":    true,
	"märker":   true,
	"märket":   true,
	"mörker":   true,
	"naken":    true,
	"ocker":    true,
	"onkel":    true,
	"paket":    true,
	"pojke":    true,
	"raket":    true,
	"rike":     true,
	"ryker":    true,
	"räcker":   true,
	"röker":    true,
	"röket":    true,
	"silke":    true,
	"sjunker":  true,
	"skelett":  true,
	"skicka":   true,
	"smeker":   true,
	"sockel":   true,
	"socker":   true,
	"staket":   true,
	"steker":   true,
	"steket":   true,
	"sticker":  true,
	"stryker":  true,
	"säker":    true,
	"söker":    true,
	"söket":    true,
	"tecken":   true,
	"trycke":   true,
	"tänker":   true,
	"tänket":   true,
	"vacker":   true,
	"viker":    true,
	"vinkel":   true,
	"väcker":   true,
}

// svHardKStems: k + front vowel → /k/ stem forms. 33 stems.
var svHardKStems = map[string]bool{
	"back":  true,
	"block": true,
	"brick": true,
	"dock":  true,
	"drick": true,
	"dyk":   true,
	"fick":  true,
	"flick": true,
	"lek":   true,
	"lock":  true,
	"läk":   true,
	"märk":  true,
	"pack":  true,
	"rock":  true,
	"ryk":   true,
	"räck":  true,
	"rök":   true,
	"sack":  true,
	"sick":  true,
	"sjunk": true,
	"skick": true,
	"smek":  true,
	"sock":  true,
	"stek":  true,
	"stick": true,
	"stryk": true,
	"sök":   true,
	"tack":  true,
	"trick": true,
	"tryck": true,
	"tänk":  true,
	"vik":   true,
	"väck":  true,
}

// svHardGWords: g + front vowel → /ɡ/ (hard). 55 words.
var svHardGWords = map[string]bool{
	"agera":     true,
	"arrangera": true,
	"bagel":     true,
	"bageri":    true,
	"berg":      true,
	"borg":      true,
	"bygel":     true,
	"bygge":     true,
	"båge":      true,
	"dager":     true,
	"delegera":  true,
	"duger":     true,
	"engagera":  true,
	"finger":    true,
	"flygel":    true,
	"flyger":    true,
	"fogel":     true,
	"fågel":     true,
	"ge":        true,
	"gecko":     true,
	"gel":       true,
	"ger":       true,
	"hage":      true,
	"hagel":     true,
	"hunger":    true,
	"ignorera":  true,
	"intrigera": true,
	"lager":     true,
	"ligger":    true,
	"ljuger":    true,
	"läge":      true,
	"läger":     true,
	"lägger":    true,
	"mage":      true,
	"nagel":     true,
	"navigera":  true,
	"negera":    true,
	"reagera":   true,
	"regel":     true,
	"segel":     true,
	"seger":     true,
	"segregera": true,
	"spegel":    true,
	"stege":     true,
	"stiger":    true,
	"suger":     true,
	"tagel":     true,
	"tangera":   true,
	"tegel":     true,
	"tiger":     true,
	"tigger":    true,
	"tygel":     true,
	"väger":     true,
	"äger":      true,
	"ängel":     true,
}

// svHardGStems: g + front vowel → /ɡ/ stem forms. 23 stems.
var svHardGStems = map[string]bool{
	"bag":  true,
	"berg": true,
	"borg": true,
	"byg":  true,
	"dag":  true,
	"drag": true,
	"dug":  true,
	"flyg": true,
	"lag":  true,
	"lig":  true,
	"ljug": true,
	"lägg": true,
	"mag":  true,
	"nag":  true,
	"reg":  true,
	"seg":  true,
	"stig": true,
	"sug":  true,
	"tag":  true,
	"tig":  true,
	"vag":  true,
	"väg":  true,
	"äg":   true,
}

// svOLongAsOO: "o" → /oː/ instead of default /uː/. 30 words.
var svOLongAsOO = map[string]bool{
	"blod":     true,
	"bo":       true,
	"bror":     true,
	"dom":      true,
	"flod":     true,
	"fon":      true,
	"fot":      true,
	"god":      true,
	"ion":      true,
	"jord":     true,
	"ko":       true,
	"kol":      true,
	"kontroll": true,
	"lo":       true,
	"lov":      true,
	"mod":      true,
	"mol":      true,
	"mor":      true,
	"nod":      true,
	"ord":      true,
	"pol":      true,
	"ro":       true,
	"rod":      true,
	"roll":     true,
	"rot":      true,
	"son":      true,
	"tog":      true,
	"ton":      true,
	"tro":      true,
	"zon":      true,
}

// svFinalMShortWords: words ending in -m with short vowel. 18 words.
var svFinalMShortWords = map[string]bool{
	"dam":   true,
	"dom":   true,
	"dröm":  true,
	"dum":   true,
	"fem":   true,
	"glöm":  true,
	"gum":   true,
	"ham":   true,
	"hem":   true,
	"kam":   true,
	"lam":   true,
	"lem":   true,
	"ram":   true,
	"rum":   true,
	"som":   true,
	"stam":  true,
	"ström": true,
	"tom":   true,
}

// svFunctionWords: unstressed function words. 37 words.
var svFunctionWords = map[string]bool{
	"att":  true,
	"av":   true,
	"de":   true,
	"dem":  true,
	"den":  true,
	"det":  true,
	"din":  true,
	"du":   true,
	"en":   true,
	"ett":  true,
	"från": true,
	"för":  true,
	"han":  true,
	"har":  true,
	"hon":  true,
	"hos":  true,
	"i":    true,
	"inte": true,
	"jag":  true,
	"kan":  true,
	"med":  true,
	"men":  true,
	"min":  true,
	"när":  true,
	"och":  true,
	"om":   true,
	"på":   true,
	"sig":  true,
	"sin":  true,
	"ska":  true,
	"som":  true,
	"till": true,
	"ur":   true,
	"var":  true,
	"vi":   true,
	"vill": true,
	"är":   true,
}

// svSKBackVowelExceptions: sk + back vowel → /ɧ/ exceptions. 2 words.
var svSKBackVowelExceptions = map[string]bool{
	"människa": true,
	"marskalk": true,
}

// svCHExceptionsK: ch → /k/ exceptions. 5 words.
var svCHExceptionsK = map[string]bool{
	"krist":   true,
	"kristus": true,
	"kron":    true,
	"kronik":  true,
	"och":     true,
}

// svAgeNativeWords: -age suffix that is native Swedish (not French loan). 11 words.
var svAgeNativeWords = map[string]bool{
	"bage":  true,
	"dage":  true,
	"drage": true,
	"frage": true,
	"hage":  true,
	"klage": true,
	"lage":  true,
	"mage":  true,
	"plage": true,
	"sage":  true,
	"tage":  true,
}

// ---------------------------------------------------------------------------
// Loanword suffix rules (T-M2-02)
// ---------------------------------------------------------------------------

type svLoanwordRule struct {
	suffix   string
	phonemes []string
}

// svLoanwordSuffixRules ordered longest-suffix first for correct matching.
var svLoanwordSuffixRules = []svLoanwordRule{
	{"ssion", []string{"\u0267", "u\u02d0", "n"}}, // -ssion → ɧ uː n
	{"tion", []string{"\u0267", "u\u02d0", "n"}},  // -tion  → ɧ uː n
	{"sion", []string{"\u0267", "u\u02d0", "n"}},  // -sion  → ɧ uː n
	{"age", []string{"\u0251\u02d0", "\u0267"}},   // -age   → ɑː ɧ
	{"eur", []string{"\u00f8\u02d0", "r"}},        // -eur   → øː r
	{"eum", []string{"e\u02d0", "\u0275", "m"}},   // -eum   → eː ɵ m
	{"ium", []string{"\u026a", "\u0275", "m"}},    // -ium   → ɪ ɵ m
}

// ---------------------------------------------------------------------------
// Normalization (T-M2-01)
// ---------------------------------------------------------------------------

// svNormalize applies NFC normalization, lowercasing, and whitespace trimming.
func svNormalize(text string) string {
	text = strings.TrimSpace(text)
	text = norm.NFC.String(text)
	text = strings.ToLower(text)
	text = strings.Join(strings.Fields(text), " ")
	return text
}

// ---------------------------------------------------------------------------
// Tokenization (T-M2-01)
// ---------------------------------------------------------------------------

type svToken struct {
	text  string
	isPun bool
}

// svTokenize splits normalized text into word tokens and punctuation tokens.
func svTokenize(text string) []svToken {
	runes := []rune(text)
	var tokens []svToken
	i := 0
	n := len(runes)
	for i < n {
		ch := runes[i]
		if unicode.IsSpace(ch) {
			i++
			continue
		}
		if svPunctuation[ch] {
			tokens = append(tokens, svToken{text: string(ch), isPun: true})
			i++
			continue
		}
		if svIsWordChar(ch) {
			start := i
			for i < n && svIsWordChar(runes[i]) {
				i++
			}
			tokens = append(tokens, svToken{text: string(runes[start:i]), isPun: false})
			continue
		}
		i++ // skip other characters
	}
	return tokens
}

// svIsWordChar returns true if ch is a valid Swedish word character.
// Covers a-z plus Swedish special characters (å, ä, ö) and accented letters
// from loanwords (é, à, ü, á, è, ë, ï).
func svIsWordChar(ch rune) bool {
	if ch >= 'a' && ch <= 'z' {
		return true
	}
	switch ch {
	case '\u00e5', '\u00e4', '\u00f6', // å, ä, ö
		'\u00e9', '\u00e0', '\u00fc', // é, à, ü
		'\u00e1', '\u00e8', '\u00eb', '\u00ef': // á, è, ë, ï
		return true
	}
	return false
}

// ---------------------------------------------------------------------------
// Loanword suffix detection (T-M2-02)
// ---------------------------------------------------------------------------

// svDetectLoanwordSuffix checks for loanword suffix patterns.
// Returns (stem, suffixPhonemes, true) if found, or ("", nil, false).
func svDetectLoanwordSuffix(word string) (string, []string, bool) {
	for _, rule := range svLoanwordSuffixRules {
		if strings.HasSuffix(word, rule.suffix) && len(word) > len(rule.suffix) {
			// -age native exception check
			if rule.suffix == "age" && svAgeNativeWords[word] {
				continue
			}
			stem := word[:len(word)-len(rule.suffix)]
			return stem, rule.phonemes, true
		}
	}
	return "", nil, false
}

// ---------------------------------------------------------------------------
// Consonant conversion (T-M2-03)
// ---------------------------------------------------------------------------

// svConvertConsonant converts consonant(s) starting at pos in runes.
// Returns (ipaPhonemes, charsConsumed).
// fullWord is the complete word (for exception list lookup).
func svConvertConsonant(runes []rune, pos int, fullWord string) ([]string, int) {
	n := len(runes)
	remaining := n - pos
	ch := runes[pos]
	var nextCh rune
	if pos+1 < n {
		nextCh = runes[pos+1]
	}

	// === 3-char patterns (highest priority) ===
	if remaining >= 3 {
		tri := string(runes[pos : pos+3])
		switch tri {
		case "skj":
			return []string{"\u0267"}, 3 // ɧ
		case "stj":
			return []string{"\u0267"}, 3 // ɧ
		case "sch":
			return []string{"\u0267"}, 3 // ɧ
		case "sng":
			return []string{"s", "n"}, 3 // simplified
		case "ckj":
			return []string{"\u0255"}, 3 // ɕ
		}
	}

	// === 2-char patterns ===
	if remaining >= 2 {
		di := string(runes[pos : pos+2])

		// sk + context
		if di == "sk" {
			// sk + front vowel → /ɧ/ (sj-sound)
			// Exception: SK_BACK_VOWEL_EXCEPTIONS
			if remaining >= 3 && svFrontVowels[runes[pos+2]] && !svSKBackVowelExceptions[fullWord] {
				return []string{"\u0267"}, 2 // ɧ
			}
			// sk + back vowel / consonant / word-final → /sk/
			return []string{"s", "k"}, 2
		}

		if di == "sj" {
			return []string{"\u0267"}, 2 // ɧ
		}
		if di == "sh" {
			return []string{"\u0267"}, 2 // ɧ (loanword)
		}
		if di == "ch" {
			if svCHExceptionsK[fullWord] {
				return []string{"k"}, 2
			}
			return []string{"\u0267"}, 2 // ɧ (loanword)
		}
		if di == "ph" {
			return []string{"f"}, 2 // loanword
		}
		if di == "th" {
			return []string{"t"}, 2 // loanword
		}
		if di == "tj" {
			return []string{"\u0255"}, 2 // ɕ
		}
		if di == "kj" {
			return []string{"\u0255"}, 2 // ɕ
		}
		if di == "gn" {
			if pos == 0 {
				return []string{"\u0261", "n"}, 2 // ɡn (word-initial)
			}
			return []string{"\u014b", "n"}, 2 // ŋn (word-medial)
		}
		if di == "ng" {
			return []string{"\u014b"}, 2 // ŋ
		}
		if di == "nk" {
			return []string{"\u014b", "k"}, 2 // ŋk
		}
		if di == "ck" {
			return []string{"k"}, 2 // geminate marker
		}
		// gj/lj/dj/hj: word-initial only
		if di == "gj" && pos == 0 {
			return []string{"j"}, 2
		}
		if di == "lj" && pos == 0 {
			return []string{"j"}, 2
		}
		if di == "dj" && pos == 0 {
			return []string{"j"}, 2
		}
		if di == "hj" && pos == 0 {
			return []string{"j"}, 2
		}
	}

	// === 1-char patterns ===

	// k + front vowel → soft /ɕ/ (default) or hard /k/ (exception)
	if ch == 'k' && svFrontVowels[nextCh] {
		if isHardK(fullWord) {
			return []string{"k"}, 1
		}
		return []string{"\u0255"}, 1 // ɕ
	}

	// g + front vowel → soft /j/ (default) or hard /ɡ/ (exception)
	if ch == 'g' && svFrontVowels[nextCh] {
		if isHardG(fullWord) {
			return []string{"\u0261"}, 1 // ɡ
		}
		return []string{"j"}, 1
	}

	// g + back vowel / consonant / word-final → /ɡ/
	if ch == 'g' {
		return []string{"\u0261"}, 1 // ɡ
	}

	// c before e/i → /s/, otherwise /k/
	if ch == 'c' {
		if nextCh == 'e' || nextCh == 'i' {
			return []string{"s"}, 1
		}
		return []string{"k"}, 1
	}

	// x → /ks/
	if ch == 'x' {
		return []string{"k", "s"}, 1
	}

	// Default single consonant
	if ipa, ok := svConsonantDefault[ch]; ok {
		if len(ipa) > 1 {
			// Multi-char default (shouldn't happen after x handling, but defensive)
			var out []string
			for _, r := range ipa {
				out = append(out, string(r))
			}
			return out, 1
		}
		return []string{ipa}, 1
	}

	// Unknown consonant: pass through
	return []string{string(ch)}, 1
}

// isHardK checks if k in this word is hard /k/ before a front vowel.
func isHardK(word string) bool {
	if svHardKWords[word] {
		return true
	}
	// Morphological heuristic: strip 1-3 suffix chars, check stems
	runes := []rune(word)
	for suffixLen := 3; suffixLen >= 1; suffixLen-- {
		if len(runes) > suffixLen {
			stem := string(runes[:len(runes)-suffixLen])
			if svHardKStems[stem] {
				return true
			}
		}
	}
	return false
}

// isHardG checks if g in this word is hard /ɡ/ before a front vowel.
func isHardG(word string) bool {
	if svHardGWords[word] {
		return true
	}
	// -era verb heuristic
	if strings.HasSuffix(word, "era") || strings.HasSuffix(word, "erar") || strings.HasSuffix(word, "erade") {
		return true
	}
	// Morphological heuristic: strip 1-3 suffix chars, check stems
	runes := []rune(word)
	for suffixLen := 3; suffixLen >= 1; suffixLen-- {
		if len(runes) > suffixLen {
			stem := string(runes[:len(runes)-suffixLen])
			if svHardGStems[stem] {
				return true
			}
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// Vowel length determination (T-M2-04)
// ---------------------------------------------------------------------------

// svCountFollowingConsonants counts consecutive consonant characters after pos.
func svCountFollowingConsonants(word []rune, pos int) int {
	count := 0
	i := pos + 1
	for i < len(word) && svConsonants[word[i]] {
		count++
		i++
	}
	return count
}

// svGetVowelPhoneme determines the vowel phoneme (long or short) at position pos.
// Implements Complementary Quantity rules with 5-stage priority.
func svGetVowelPhoneme(word []rune, pos int, fullWord string, isStressed bool) string {
	ch := word[pos]

	// 1. Unstressed → short
	if !isStressed {
		if v, ok := svShortVowelMap[ch]; ok {
			return v
		}
		return string(ch)
	}

	// 2. Function word → short
	if svFunctionWords[fullWord] {
		if v, ok := svShortVowelMap[ch]; ok {
			return v
		}
		return string(ch)
	}

	// 3. Final-m exception → short
	if svFinalMShortWords[fullWord] {
		if v, ok := svShortVowelMap[ch]; ok {
			return v
		}
		return string(ch)
	}

	// 4. Count following consonants
	nFollowing := svCountFollowingConsonants(word, pos)

	// 4a. Word-final vowel (0 consonants) → long
	if nFollowing == 0 && pos == len(word)-1 {
		return svLongVowel(ch, fullWord)
	}

	// 4b+4c. r + single C exception: vowel stays long
	// Exception: 'o' is excluded (too ambiguous: kort=/ɔ/, bord=/uː/)
	if nFollowing == 2 && ch != 'o' && pos+1 < len(word) && word[pos+1] == 'r' {
		return svLongVowel(ch, fullWord)
	}

	// 4d. Geminate / cluster (2+ consonants) → short
	if nFollowing >= 2 {
		if v, ok := svShortVowelMap[ch]; ok {
			return v
		}
		return string(ch)
	}

	// 4e. Single consonant → long
	return svLongVowel(ch, fullWord)
}

// svLongVowel returns the long vowel IPA for ch, with O_LONG_AS_OO check.
func svLongVowel(ch rune, fullWord string) string {
	if ch == 'o' && svOLongAsOO[fullWord] {
		return svOLongAsOOPhoneme // oː
	}
	if v, ok := svLongVowelMap[ch]; ok {
		return v
	}
	return string(ch)
}

// ---------------------------------------------------------------------------
// Word G2P integration (T-M2-05)
// ---------------------------------------------------------------------------

// svConvertWordNative converts a word using native Swedish G2P rules.
// Processes characters left-to-right, applying consonant and vowel rules.
func svConvertWordNative(word string, fullWord string, stressedSyl int) []string {
	runes := []rune(word)
	n := len(runes)
	var phonemes []string
	pos := 0
	sylCount := 0
	prevWasVowel := false

	for pos < n {
		ch := runes[pos]

		switch {
		case svAllVowels[ch]:
			if !prevWasVowel {
				isStressed := sylCount == stressedSyl && stressedSyl >= 0
				vowel := svGetVowelPhoneme(runes, pos, fullWord, isStressed)
				phonemes = append(phonemes, vowel)
				sylCount++
			} else {
				// Consecutive vowel (rare in Swedish): short
				if v, ok := svShortVowelMap[ch]; ok {
					phonemes = append(phonemes, v)
				} else {
					phonemes = append(phonemes, string(ch))
				}
			}
			prevWasVowel = true
			pos++

		case svConsonants[ch]:
			prevWasVowel = false
			ipaList, consumed := svConvertConsonant(runes, pos, fullWord)
			phonemes = append(phonemes, ipaList...)
			pos += consumed

		default:
			// Unknown character: skip
			prevWasVowel = false
			pos++
		}
	}

	return phonemes
}

// ---------------------------------------------------------------------------
// Retroflex assimilation (M3: T-M3-01)
// ---------------------------------------------------------------------------

// svRetroflexMap maps consonants to their retroflex counterparts after r.
var svRetroflexMap = map[string]string{
	"t": "\u0288", // ʈ
	"d": "\u0256", // ɖ
	"s": "\u0282", // ʂ
	"n": "\u0273", // ɳ
	"l": "\u026d", // ɭ
}

// svPropagatingRetroflexes are retroflexes that propagate cascade.
// ɭ (U+026D) is NOT included — it stops the cascade.
var svPropagatingRetroflexes = map[string]bool{
	"\u0288": true, // ʈ
	"\u0256": true, // ɖ
	"\u0282": true, // ʂ
	"\u0273": true, // ɳ
}

// Retroflex state machine states.
const (
	svRetroNormal    = iota
	svRetroRDetected // r detected, pending assimilation check
	svRetroCascading // active cascade propagation
)

// svApplyRetroflex applies retroflex assimilation to a phoneme sequence.
// r + {t,d,s,n,l} → {ʈ,ɖ,ʂ,ɳ,ɭ}.
// Geminate rr blocks assimilation.
// Cascade: {ʈ,ɖ,ʂ,ɳ} propagate; ɭ stops.
func svApplyRetroflex(phonemes []string) []string {
	result := make([]string, 0, len(phonemes))
	state := svRetroNormal

	for _, ph := range phonemes {
		switch state {
		case svRetroNormal:
			if ph == "r" {
				state = svRetroRDetected
			} else {
				result = append(result, ph)
			}

		case svRetroRDetected:
			if ph == "r" {
				// Geminate block: rr → r + r, no assimilation
				result = append(result, "r", "r")
				state = svRetroNormal
			} else if retro, ok := svRetroflexMap[ph]; ok {
				result = append(result, retro)
				if svPropagatingRetroflexes[retro] {
					state = svRetroCascading
				} else {
					state = svRetroNormal // ɭ stops cascade
				}
			} else {
				// r + non-assimilable → output r and the phoneme
				result = append(result, "r", ph)
				state = svRetroNormal
			}

		case svRetroCascading:
			if retro, ok := svRetroflexMap[ph]; ok {
				result = append(result, retro)
				if !svPropagatingRetroflexes[retro] {
					state = svRetroNormal // ɭ stops cascade
				}
			} else {
				result = append(result, ph)
				state = svRetroNormal
			}
		}
	}

	// Terminal flush: if r was pending, output it
	if state == svRetroRDetected {
		result = append(result, "r")
	}
	return result
}

// ---------------------------------------------------------------------------
// Stress detection + marker insertion (M3: T-M3-02)
// ---------------------------------------------------------------------------

// svStressAttractingSuffixes lists suffixes that attract stress (longest first).
var svStressAttractingSuffixes = []string{
	"ssion", "tion", "sion", "itet",
	"eri", "era", "ist", "\u00f6r", // ör
	"ment", "ans", "ens", "ell",
	"ent", "ant", "ik", "ur", "al", "\u00f6s", // ös
}

// svUnstressedPrefixes lists prefixes that shift stress to the 2nd syllable.
var svUnstressedPrefixes = []string{
	"f\u00f6r", // för
	"be",
	"ge",
	"er",
	"an",
}

// svIPAVowelSet contains all vowel runes used for IPA vowel detection.
var svIPAVowelSet = map[rune]bool{
	// Basic vowels
	'a': true, 'e': true, 'i': true, 'o': true, 'u': true,
	'y': true, '\u00e5': true, '\u00e4': true, '\u00f6': true, // å ä ö
	// IPA vowels
	'\u0251': true, // ɑ
	'\u025b': true, // ɛ
	'\u026a': true, // ɪ
	'\u0254': true, // ɔ
	'\u028a': true, // ʊ
	'\u0289': true, // ʉ
	'\u028f': true, // ʏ
	'\u0153': true, // œ
	'\u00f8': true, // ø
	'\u0275': true, // ɵ
}

// svIsIPAVowel checks if a phoneme string contains a vowel character.
func svIsIPAVowel(ph string) bool {
	for _, c := range ph {
		if svIPAVowelSet[c] {
			return true
		}
	}
	return false
}

// svDetectStress detects the primary stress syllable index (0-based).
// Returns -1 for function words (no stress).
// Priority: function word → monosyllabic → stress-attracting suffix →
// unstressed prefix → default (first syllable).
func svDetectStress(word string) int {
	// Priority 1: Function word
	if svFunctionWords[word] {
		return -1
	}

	// Priority 2: Monosyllabic
	nSyl := svCountSyllables(word)
	if nSyl <= 1 {
		return 0
	}

	// Priority 3: Stress-attracting suffix (longest match first)
	for _, suffix := range svStressAttractingSuffixes {
		if strings.HasSuffix(word, suffix) && len(word) > len(suffix) {
			prefixPart := word[:len(word)-len(suffix)]
			return svCountSyllables(prefixPart)
		}
	}

	// Priority 4: Unstressed prefix
	for _, prefix := range svUnstressedPrefixes {
		if strings.HasPrefix(word, prefix) && len(word) > len(prefix)+1 {
			return 1
		}
	}

	// Priority 5: Default — first syllable
	return 0
}

// svInsertStressMarker inserts ˈ (U+02C8) before the onset of the stressed syllable.
// stressSyl < 0 means no stress (function word) → returns phonemes unchanged.
func svInsertStressMarker(phonemes []string, stressSyl int) []string {
	if stressSyl < 0 || len(phonemes) == 0 {
		return phonemes
	}

	// Step 1: Find the index of the first vowel of the target syllable
	sylCount := 0
	vowelIdx := -1
	prevWasVowel := false

	for i, ph := range phonemes {
		isV := svIsIPAVowel(ph)
		if isV && !prevWasVowel {
			if sylCount == stressSyl {
				vowelIdx = i
				break
			}
			sylCount++
		}
		prevWasVowel = isV
	}

	if vowelIdx < 0 {
		return phonemes
	}

	// Step 2: Walk backwards to find syllable onset (consonants before the vowel)
	onsetIdx := vowelIdx
	for onsetIdx > 0 && !svIsIPAVowel(phonemes[onsetIdx-1]) {
		onsetIdx--
	}

	// For syllable 0, onset starts at beginning
	if stressSyl == 0 {
		onsetIdx = 0
	}

	// Step 3: Insert ˈ at onsetIdx
	result := make([]string, 0, len(phonemes)+1)
	result = append(result, phonemes[:onsetIdx]...)
	result = append(result, "\u02c8") // ˈ
	result = append(result, phonemes[onsetIdx:]...)
	return result
}

// svCountSyllables counts syllables by counting vowel clusters.
func svCountSyllables(word string) int {
	count := 0
	prevVowel := false
	for _, ch := range word {
		if svAllVowels[ch] {
			if !prevVowel {
				count++
			}
			prevVowel = true
		} else {
			prevVowel = false
		}
	}
	if count == 0 {
		return 1
	}
	return count
}

// svPhonemizeWord runs the full G2P pipeline for a single word:
// stress detection → loanword/native G2P → retroflex → stress marker insertion.
func svPhonemizeWord(word string) []string {
	if word == "" {
		return nil
	}

	// Stage 6 (first half): Stress detection
	stressedSyl := svDetectStress(word)

	// Stage 2: Loanword suffix check
	var rawPhonemes []string
	stem, suffixPhonemes, found := svDetectLoanwordSuffix(word)
	if found {
		stemSylCount := svCountSyllables(stem)
		stemStress := stressedSyl
		if stressedSyl >= stemSylCount {
			stemStress = -1 // stress is in the suffix → stem is unstressed
		}
		stemPhonemes := svConvertWordNative(stem, word, stemStress)
		rawPhonemes = append(rawPhonemes, stemPhonemes...)
		rawPhonemes = append(rawPhonemes, suffixPhonemes...)
	} else {
		// Stage 4: Native G2P
		rawPhonemes = svConvertWordNative(word, word, stressedSyl)
	}

	// Stage 5: Retroflex assimilation
	phonemes := svApplyRetroflex(rawPhonemes)

	// Stage 6 (second half): Stress marker insertion
	phonemes = svInsertStressMarker(phonemes, stressedSyl)

	return phonemes
}

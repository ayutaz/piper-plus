package phonemize

import (
	"fmt"
	"log/slog"
	"strings"
	"unicode"
)

// ---------------------------------------------------------------------------
// ChinesePhonemizer converts Chinese text to IPA via pinyin.
// ---------------------------------------------------------------------------

// ChinesePhonemizer converts Chinese text to IPA via pinyin.
type ChinesePhonemizer struct {
	singleCharPinyin map[rune]string   // char -> pinyin (e.g., '你'->"ni3")
	phrasesPinyin    map[string]string // phrase -> pinyin (e.g., "你好"->"ni3hao3")
}

// NewChinesePhonemizer creates a phonemizer with pinyin dictionaries.
// If both dictionaries are nil, CJK characters will not be phonemized (skipped).
func NewChinesePhonemizer(singleChar map[rune]string, phrases map[string]string) *ChinesePhonemizer {
	if singleChar == nil && phrases == nil {
		slog.Warn("Chinese phonemizer created without pinyin dictionaries; CJK characters will not be phonemized")
	}
	if singleChar == nil {
		singleChar = make(map[rune]string)
	}
	if phrases == nil {
		phrases = make(map[string]string)
	}
	return &ChinesePhonemizer{
		singleCharPinyin: singleChar,
		phrasesPinyin:    phrases,
	}
}

// LanguageCode returns "zh".
func (p *ChinesePhonemizer) LanguageCode() string {
	return "zh"
}

// ---------------------------------------------------------------------------
// Pinyin initial -> IPA mapping (21 entries)
// ---------------------------------------------------------------------------
// Ordered longest-first for prefix matching: zh before z, ch before c, sh before s.

var zhInitialsOrder = []string{
	"zh", "ch", "sh",
	"b", "p", "m", "f",
	"d", "t", "n", "l",
	"g", "k", "h",
	"j", "q", "x",
	"r",
	"z", "c", "s",
}

var zhInitialToIPA = map[string]string{
	"b":  "p",
	"p":  "pʰ",
	"m":  "m",
	"f":  "f",
	"d":  "t",
	"t":  "tʰ",
	"n":  "n",
	"l":  "l",
	"g":  "k",
	"k":  "kʰ",
	"h":  "x",
	"j":  "tɕ",
	"q":  "tɕʰ",
	"x":  "ɕ",
	"zh": "tʂ",
	"ch": "tʂʰ",
	"sh": "ʂ",
	"r":  "ɻ",
	"z":  "ts",
	"c":  "tsʰ",
	"s":  "s",
}

// ---------------------------------------------------------------------------
// Pinyin final -> IPA mapping
// ---------------------------------------------------------------------------

var zhFinalToIPA = map[string]string{
	// Simple vowels
	"a": "a",
	"o": "o",
	"e": "ɤ",
	"i": "i",
	"u": "u",
	"ü": "y_vowel",
	"v": "y_vowel",
	// Diphthongs
	"ai": "aɪ",
	"ei": "eɪ",
	"ao": "aʊ",
	"ou": "oʊ",
	// Nasal finals
	"an":  "an",
	"en":  "ən",
	"ang": "aŋ",
	"eng": "əŋ",
	"ong": "uŋ",
	// Retroflex final
	"er": "ɚ",
	// i-compound finals (齐齿呼)
	"ia":   "ia",
	"ie":   "iɛ",
	"iao":  "iaʊ",
	"iu":   "iou",
	"iou":  "iou",
	"ian":  "iɛn",
	"in":   "in",
	"iang": "iaŋ",
	"ing":  "iŋ",
	"iong": "iuŋ",
	// u-compound finals (合口呼)
	"ua":   "ua",
	"uo":   "uo",
	"uai":  "uaɪ",
	"ui":   "ueɪ",
	"uei":  "ueɪ",
	"uan":  "uan",
	"un":   "uən",
	"uen":  "uən",
	"uang": "uaŋ",
	"ueng": "uəŋ",
	// ü-compound finals (撮口呼)
	"üe":  "yɛ",
	"ve":  "yɛ",
	"üan": "yɛn",
	"van": "yɛn",
	"ün":  "yn",
	"vn":  "yn",
	// Syllabic consonants (internal keys set by zhSplitPinyin)
	"-i_retroflex": "ɻ̩",
	"-i_alveolar":  "ɨ",
}

// ---------------------------------------------------------------------------
// Retroflex / alveolar initial sets
// ---------------------------------------------------------------------------

var zhRetroflexInitials = map[string]bool{
	"zh": true, "ch": true, "sh": true, "r": true,
}

var zhAlveolarInitials = map[string]bool{
	"z": true, "c": true, "s": true,
}

// ---------------------------------------------------------------------------
// Chinese punctuation mapping (fullwidth -> ASCII)
// ---------------------------------------------------------------------------

var zhPunctMap = map[rune]rune{
	'\u3002': '.',  // 。
	'\uff0c': ',',  // ，
	'\uff01': '!',  // ！
	'\uff1f': '?',  // ？
	'\u3001': ',',  // 、
	'\uff1b': ';',  // ；
	'\uff1a': ':',  // ：
	'\u2026': '.',  // …
	'\u2014': ',',  // —
	'\u201c': '"',  // "
	'\u201d': '"',  // "
	'\u2018': '\'', // '
	'\u2019': '\'', // '
}

var zhPunctuationSet = map[rune]bool{
	',': true, '.': true, ';': true, ':': true, '!': true, '?': true,
	'\u3002': true, '\uff0c': true, '\uff01': true, '\uff1f': true,
	'\u3001': true, '\uff1b': true, '\uff1a': true,
	'\u201c': true, '\u201d': true, '\u2018': true, '\u2019': true,
	'\u2026': true, '\u2014': true,
}

// ---------------------------------------------------------------------------
// CJK detection
// ---------------------------------------------------------------------------

func isCJK(r rune) bool {
	return (r >= 0x4E00 && r <= 0x9FFF) || (r >= 0x3400 && r <= 0x4DBF)
}

// ---------------------------------------------------------------------------
// Pinyin normalization (y/w conventions, v->ü)
// ---------------------------------------------------------------------------

func zhNormalizePinyin(py string) string {
	// v -> ü
	py = strings.ReplaceAll(py, "v", "ü")

	// y- initial
	if strings.HasPrefix(py, "yu") {
		rest := py[2:]
		if rest == "" {
			return "ü"
		}
		return "ü" + rest
	}
	if strings.HasPrefix(py, "y") {
		rest := py[1:]
		if strings.HasPrefix(rest, "i") {
			return rest // yi->i, yin->in, ying->ing
		}
		return "i" + rest // ya->ia, ye->ie, yan->ian
	}

	// w- initial
	if strings.HasPrefix(py, "w") {
		rest := py[1:]
		if strings.HasPrefix(rest, "u") {
			return rest // wu->u
		}
		return "u" + rest // wa->ua, wo->uo, wai->uai
	}

	return py
}

// ---------------------------------------------------------------------------
// Split normalized pinyin into (initial, final)
// ---------------------------------------------------------------------------

func zhSplitPinyin(pinyin string) (string, string) {
	for _, init := range zhInitialsOrder {
		if strings.HasPrefix(pinyin, init) {
			final_ := pinyin[len(init):]

			// Syllabic consonant: bare "i" after retroflex or alveolar initials
			if final_ == "i" {
				if zhRetroflexInitials[init] {
					return init, "-i_retroflex"
				}
				if zhAlveolarInitials[init] {
					return init, "-i_alveolar"
				}
			}

			// After j/q/x, u represents ü
			if (init == "j" || init == "q" || init == "x") && strings.HasPrefix(final_, "u") {
				final_ = "ü" + final_[1:]
			}

			return init, final_
		}
	}

	// No consonant initial
	return "", pinyin
}

// ---------------------------------------------------------------------------
// Pinyin -> IPA conversion (single syllable)
// ---------------------------------------------------------------------------

func zhPinyinToIPA(syllable string, tone int) []string {
	initial, final_ := zhSplitPinyin(syllable)

	var tokens []string

	// Initial consonant
	if initial != "" {
		if ipa, ok := zhInitialToIPA[initial]; ok {
			tokens = append(tokens, ipa)
		}
	}

	// Final vowel(s) as a single compound token
	if final_ != "" {
		if ipa, ok := zhFinalToIPA[final_]; ok {
			tokens = append(tokens, ipa)
		} else {
			// Fallback: decompose unknown finals character by character
			for _, ch := range final_ {
				s := string(ch)
				if ipa2, ok2 := zhFinalToIPA[s]; ok2 {
					tokens = append(tokens, ipa2)
				} else if unicode.IsLetter(ch) {
					tokens = append(tokens, s)
				}
			}
		}
	}

	// Tone marker
	if tone >= 1 && tone <= 5 {
		tokens = append(tokens, fmt.Sprintf("tone%d", tone))
	}

	return tokens
}

// ---------------------------------------------------------------------------
// Extract tone digit from pinyin syllable string
// ---------------------------------------------------------------------------

func zhExtractTone(syllable string) (string, int) {
	if len(syllable) == 0 {
		return "", 5
	}
	last := syllable[len(syllable)-1]
	if last >= '1' && last <= '5' {
		return syllable[:len(syllable)-1], int(last - '0')
	}
	return syllable, 5
}

// ---------------------------------------------------------------------------
// Tone sandhi
// ---------------------------------------------------------------------------

type syllableTone struct {
	syllable string
	tone     int
}

func zhApplyToneSandhi(st []syllableTone) {
	n := len(st)
	for i := 0; i < n-1; i++ {
		toneI := st[i].tone
		toneNext := st[i+1].tone

		// Rule 1: T3 + T3 -> T2 + T3
		if toneI == 3 && toneNext == 3 {
			st[i].tone = 2
			continue
		}

		// Rule 2 & 3: yi (normalized to "i") tone sandhi
		if st[i].syllable == "i" && toneI == 1 {
			if toneNext == 4 {
				st[i].tone = 2 // T1 -> T2 before T4
			} else if toneNext >= 1 && toneNext <= 3 {
				st[i].tone = 4 // T1 -> T4 before T1/T2/T3
			}
			continue
		}

		// Rule 4: bu T4 + T4 -> T2 + T4
		if st[i].syllable == "bu" && toneI == 4 && toneNext == 4 {
			st[i].tone = 2
		}
	}
}

// ---------------------------------------------------------------------------
// Word boundary info for prosody
// ---------------------------------------------------------------------------

type wordPos struct {
	sylPos  int // 1-based syllable position in word
	wordLen int // total syllables in word
}

func zhBuildWordInfo(runes []rune) map[int]wordPos {
	info := make(map[int]wordPos)
	var groupIndices []int

	for i, r := range runes {
		if isCJK(r) {
			groupIndices = append(groupIndices, i)
		} else if len(groupIndices) > 0 {
			wl := len(groupIndices)
			for pos, idx := range groupIndices {
				info[idx] = wordPos{sylPos: pos + 1, wordLen: wl}
			}
			groupIndices = groupIndices[:0]
		}
	}

	// Trailing group
	if len(groupIndices) > 0 {
		wl := len(groupIndices)
		for pos, idx := range groupIndices {
			info[idx] = wordPos{sylPos: pos + 1, wordLen: wl}
		}
	}

	return info
}

// ---------------------------------------------------------------------------
// Phrase matching (longest prefix)
// ---------------------------------------------------------------------------

func zhPhraseMatch(runes []rune, pos int, phraseDict map[string]string) (int, string, bool) {
	maxLen := len(runes) - pos
	if maxLen > 8 {
		maxLen = 8
	}
	for l := maxLen; l >= 2; l-- {
		key := string(runes[pos : pos+l])
		if py, ok := phraseDict[key]; ok {
			return l, py, true
		}
	}
	return 0, "", false
}

// ---------------------------------------------------------------------------
// Internal character-pinyin structure
// ---------------------------------------------------------------------------

type charPinyin struct {
	isChinese  bool
	normalized string
	tone       int
}

// ---------------------------------------------------------------------------
// Text -> pinyin conversion
// ---------------------------------------------------------------------------

func zhTextToPinyin(runes []rune, singleDict map[rune]string, phraseDict map[string]string) []charPinyin {
	n := len(runes)
	result := make([]charPinyin, 0, n)
	i := 0

	for i < n {
		r := runes[i]

		if !isCJK(r) {
			result = append(result, charPinyin{isChinese: false})
			i++
			continue
		}

		// Try phrase match first
		if matchLen, pyStr, ok := zhPhraseMatch(runes, i, phraseDict); ok {
			// Split phrase pinyin by spaces to get individual syllables
			syllables := strings.Fields(pyStr)
			for j := 0; j < matchLen; j++ {
				var base string
				var tone int
				if j < len(syllables) {
					base, tone = zhExtractTone(syllables[j])
				} else {
					base = ""
					tone = 5
				}
				normalized := zhNormalizePinyin(base)
				result = append(result, charPinyin{
					isChinese:  true,
					normalized: normalized,
					tone:       tone,
				})
			}
			i += matchLen
			continue
		}

		// Single character lookup
		if raw, ok := singleDict[r]; ok {
			// Take first alternative if comma-separated
			first := raw
			if idx := strings.IndexByte(raw, ','); idx >= 0 {
				first = raw[:idx]
			}
			base, tone := zhExtractTone(first)
			normalized := zhNormalizePinyin(base)
			result = append(result, charPinyin{
				isChinese:  true,
				normalized: normalized,
				tone:       tone,
			})
		} else {
			// Unknown CJK character
			result = append(result, charPinyin{isChinese: false})
		}
		i++
	}

	return result
}

// ---------------------------------------------------------------------------
// Apply tone sandhi to consecutive Chinese character groups
// ---------------------------------------------------------------------------

func zhApplyToneSandhiToChars(chars []charPinyin) {
	n := len(chars)
	i := 0

	for i < n {
		if !chars[i].isChinese {
			i++
			continue
		}

		// Find end of consecutive Chinese group
		groupStart := i
		for i < n && chars[i].isChinese {
			i++
		}
		groupEnd := i

		if groupEnd-groupStart < 2 {
			continue
		}

		// Build syllable-tone slice for this group
		st := make([]syllableTone, groupEnd-groupStart)
		for j := groupStart; j < groupEnd; j++ {
			st[j-groupStart] = syllableTone{
				syllable: chars[j].normalized,
				tone:     chars[j].tone,
			}
		}

		zhApplyToneSandhi(st)

		// Write back
		for j := groupStart; j < groupEnd; j++ {
			chars[j].tone = st[j-groupStart].tone
		}
	}
}

// ---------------------------------------------------------------------------
// PhonemizeWithProsody — main entry point
// ---------------------------------------------------------------------------

// PhonemizeWithProsody converts Chinese text to IPA phonemes with prosody.
func (p *ChinesePhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	if len(text) == 0 {
		return &PhonemizeResult{
			EOSToken: "$",
		}, nil
	}

	runes := []rune(text)
	wordInfo := zhBuildWordInfo(runes)

	// Step 1: text -> pinyin
	charPinyins := zhTextToPinyin(runes, p.singleCharPinyin, p.phrasesPinyin)

	// Step 2: tone sandhi
	zhApplyToneSandhiToChars(charPinyins)

	// Step 3: generate phonemes
	var tokens []string
	var prosody []*ProsodyInfo
	eosToken := "$"

	for charIdx := 0; charIdx < len(runes) && charIdx < len(charPinyins); charIdx++ {
		ch := runes[charIdx]
		cpdata := &charPinyins[charIdx]

		if !cpdata.isChinese {
			// Punctuation mapping
			if mapped, ok := zhPunctMap[ch]; ok {
				ms := string(mapped)
				tokens = append(tokens, ms)
				prosody = append(prosody, nil)
				// Track EOS-relevant punctuation
				switch ms {
				case "?":
					eosToken = "?"
				case "!":
					eosToken = "!"
				}
				continue
			}
			if zhPunctuationSet[ch] {
				s := string(ch)
				tokens = append(tokens, s)
				prosody = append(prosody, nil)
				switch s {
				case "?":
					eosToken = "?"
				case "!":
					eosToken = "!"
				}
				continue
			}

			// Whitespace
			if unicode.IsSpace(ch) {
				tokens = append(tokens, " ")
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
				continue
			}

			// Digits
			if unicode.IsDigit(ch) {
				tokens = append(tokens, string(ch))
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 1})
				continue
			}

			// Other alphabetic characters pass through
			if unicode.IsLetter(ch) {
				tokens = append(tokens, string(ch))
				prosody = append(prosody, &ProsodyInfo{A1: 0, A2: 0, A3: 1})
			}
			// Other characters: skip
			continue
		}

		// Chinese character: convert pinyin to IPA
		normalized := cpdata.normalized
		tone := cpdata.tone

		// Erhua handling: trailing 'r' that is not standalone "er"
		hasErhua := false
		if len(normalized) > 1 && normalized != "er" && strings.HasSuffix(normalized, "r") {
			hasErhua = true
			// Remove trailing 'r' safely (it is a single ASCII byte)
			normalized = normalized[:len(normalized)-1]
		}

		// Convert to IPA tokens
		ipaTokens := zhPinyinToIPA(normalized, tone)

		// Insert erhua token before tone marker
		if hasErhua && len(ipaTokens) > 0 {
			lastIsTone := strings.HasPrefix(ipaTokens[len(ipaTokens)-1], "tone")
			if lastIsTone {
				// Insert ɚ before the last (tone) token
				insertIdx := len(ipaTokens) - 1
				ipaTokens = append(ipaTokens, "")
				copy(ipaTokens[insertIdx+1:], ipaTokens[insertIdx:])
				ipaTokens[insertIdx] = "ɚ"
			} else {
				ipaTokens = append(ipaTokens, "ɚ")
			}
		}

		// Prosody: A1=tone, A2=position in word, A3=word length
		wp, ok := wordInfo[charIdx]
		if !ok {
			wp = wordPos{sylPos: 1, wordLen: 1}
		}
		sylProsody := &ProsodyInfo{A1: tone, A2: wp.sylPos, A3: wp.wordLen}

		for _, tok := range ipaTokens {
			tokens = append(tokens, tok)
			prosody = append(prosody, sylProsody)
		}
	}

	// Map multi-character tokens to PUA codepoints
	mapped := MapSequence(tokens)

	return &PhonemizeResult{
		Tokens:   mapped,
		Prosody:  prosody,
		EOSToken: eosToken,
	}, nil
}

// ---------------------------------------------------------------------------
// Ensure ChinesePhonemizer implements Phonemizer at compile time.
// ---------------------------------------------------------------------------

var _ Phonemizer = (*ChinesePhonemizer)(nil)

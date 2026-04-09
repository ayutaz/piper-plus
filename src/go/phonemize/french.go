package phonemize

import (
	"strings"
	"unicode"
)

// FrenchPhonemizer converts French text to IPA phonemes using rule-based G2P.
type FrenchPhonemizer struct{}

func NewFrenchPhonemizer() *FrenchPhonemizer     { return &FrenchPhonemizer{} }
func (p *FrenchPhonemizer) LanguageCode() string { return "fr" }

var (
	frV  = mkSet("aeiouy\u00e0\u00e2\u00e6\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb\u00fc\u0153")
	frC  = mkSet("bcdfghjklmnpqrstvwxz")
	frSF = mkSet("dghmnpstxz")                              // silent final consonants
	frSo = mkSet("eiy\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef") // soft c/g triggers
	frPu = mkSet(",.;:!?\u00a1\u00bf\u2014\u2013\u2026\u00ab\u00bb")
	frVP = map[string]bool{"a": true, "e": true, "\u025b": true, "i": true, "o": true,
		"\u0254": true, "u": true, "y_vowel": true, "\u0259": true, "\u00f8": true,
		"\u0153": true, "\u025b\u0303": true, "\u0251\u0303": true, "\u0254\u0303": true}
	frSC = map[rune]string{'b': "b", 'd': "d", 'f': "f", 'k': "k", 'l': "l", 'm': "m",
		'n': "n", 'p': "p", 's': "s", 't': "t", 'v': "v", 'w': "w", 'z': "z"}
	ilIL = map[string]bool{"ville": true, "mille": true, "tranquille": true}
	erEH = map[string]bool{"hiver": true, "enfer": true, "amer": true, "cancer": true,
		"super": true, "laser": true, "hamster": true, "master": true, "poster": true,
		"cluster": true, "starter": true, "leader": true, "transfer": true, "fer": true}
)

func mkSet(s string) map[rune]bool {
	m := make(map[rune]bool, len(s))
	for _, r := range s {
		m[r] = true
	}
	return m
}

func frVC(rs []rune) int {
	c := 0
	for _, r := range rs {
		if frV[r] {
			c++
		}
	}
	return c
}

func frOpenTail(t []rune) bool {
	e := t
	n := len(e)
	if n >= 2 && e[n-2] == 'e' && e[n-1] == 's' {
		e = e[:n-2]
	} else if n >= 1 && e[n-1] == 'e' {
		e = e[:n-1]
	}
	if len(e) == 0 {
		return false
	}
	any := false
	for _, r := range e {
		if !frC[r] {
			return false
		}
		if !frSF[r] {
			any = true
		}
	}
	return any
}

func frEPh(t []rune) string {
	cc := 0
	for _, r := range t {
		if frC[r] {
			cc++
		} else {
			break
		}
	}
	if cc >= 2 {
		return "\u025b"
	}
	any := false
	for _, r := range t {
		if !frC[r] {
			return "\u0259"
		}
		if !frSF[r] {
			any = true
		}
	}
	if any {
		return "\u025b"
	}
	return "\u0259"
}

func frNas(rs []rune, p, n int) bool { return p >= n || !frV[rs[p]] }

func frWord(word string) []string {
	rs := []rune(word)
	n := len(rs)
	var ph []string
	i := 0
	at := func(o int) rune {
		if i+o < n {
			return rs[i+o]
		}
		return 0
	}
	sub := func(a, b int) string {
		if i+b > n {
			return ""
		}
		return string(rs[i+a : i+b])
	}

	for i < n {
		c := rs[i]
		// -er word-final verb infinitive
		if c == 'e' && i+1 == n-1 && rs[i+1] == 'r' && frVC(rs) >= 2 && !erEH[word] {
			ph = append(ph, "e")
			i += 2
			continue
		}
		if c == 'e' && at(1) == 'a' && at(2) == 'u' {
			ph = append(ph, "o")
			i += 3
			continue
		} // eau
		if c == 'o' && sub(1, 6) == "uille" && frNas(rs, i+6, n) {
			ph = append(ph, "u", "j")
			i += 6
			continue
		}
		if c == 'a' && sub(1, 5) == "ille" && frNas(rs, i+5, n) {
			ph = append(ph, "a", "j")
			i += 5
			continue
		}
		if c == 'e' && sub(1, 6) == "uille" && i+6 >= n {
			ph = append(ph, "\u0153", "j")
			i += 6
			continue
		}
		if c == 'e' && at(1) == 'i' && at(2) == 'l' && i+3 >= n {
			ph = append(ph, "\u025b", "j")
			i += 3
			continue
		}
		if c == 'e' && sub(1, 5) == "ille" && frNas(rs, i+5, n) {
			ph = append(ph, "\u025b", "j")
			i += 5
			continue
		}
		if (c == 'a' || c == 'e') && at(1) == 'i' && (at(2) == 'n' || at(2) == 'm') && frNas(rs, i+3, n) {
			ph = append(ph, "\u025b\u0303")
			i += 3
			continue
		}
		if c == 'o' && at(1) == 'i' && at(2) == 'n' && frNas(rs, i+3, n) {
			ph = append(ph, "w", "\u025b\u0303")
			i += 3
			continue
		}
		if c == 'i' && at(1) == 'e' && at(2) == 'n' && frNas(rs, i+3, n) {
			ph = append(ph, "j", "\u025b\u0303")
			i += 3
			continue
		}
		if c == 't' && at(1) == 'i' && at(2) == 'o' && at(3) == 'n' && frNas(rs, i+4, n) {
			if i > 0 && rs[i-1] == 's' {
				ph = append(ph, "t")
			} else {
				ph = append(ph, "s")
			}
			ph = append(ph, "j", "\u0254\u0303")
			i += 4
			continue
		}
		if c == 'i' && at(1) == 'l' && at(2) == 'l' && at(3) == 'e' && frNas(rs, i+4, n) {
			if ilIL[word] {
				ph = append(ph, "i", "l")
			} else {
				ph = append(ph, "i", "j")
			}
			i += 4
			continue
		}
		// Consonant digraphs
		if c == 'g' && at(1) == 'n' {
			ph = append(ph, "\u0272")
			i += 2
			continue
		}
		if c == 'p' && at(1) == 'h' {
			ph = append(ph, "f")
			i += 2
			continue
		}
		if c == 't' && at(1) == 'h' {
			ph = append(ph, "t")
			i += 2
			continue
		}
		if c == 'c' && at(1) == 'h' {
			ph = append(ph, "\u0283")
			i += 2
			continue
		}
		if c == 'q' && at(1) == 'u' {
			ph = append(ph, "k")
			i += 2
			continue
		}
		if c == 'g' && at(1) == 'u' && i+2 < n && frSo[rs[i+2]] {
			ph = append(ph, "\u0261")
			i += 2
			continue
		}
		// Nasal vowels: V + n/m
		if c == 'a' && (at(1) == 'n' || at(1) == 'm') && (i+2 >= n || (!frV[rs[i+2]] && rs[i+2] != rs[i+1])) {
			ph = append(ph, "\u0251\u0303")
			i += 2
			continue // am/an → ɑ̃
		}
		if c == 'e' && (at(1) == 'n' || at(1) == 'm') && (i+2 >= n || (!frV[rs[i+2]] && rs[i+2] != rs[i+1])) {
			ph = append(ph, "\u0251\u0303")
			i += 2
			continue // em/en → ɑ̃ (merged with an/am in standard French)
		}
		if c == 'i' && (at(1) == 'n' || at(1) == 'm') && (i+2 >= n || (!frV[rs[i+2]] && rs[i+2] != rs[i+1])) {
			ph = append(ph, "\u025b\u0303")
			i += 2
			continue
		}
		if c == 'o' && (at(1) == 'n' || at(1) == 'm') && (i+2 >= n || (!frV[rs[i+2]] && rs[i+2] != rs[i+1])) {
			ph = append(ph, "\u0254\u0303")
			i += 2
			continue
		}
		if (c == 'u' || c == 'y') && (at(1) == 'n' || at(1) == 'm') && (i+2 >= n || (!frV[rs[i+2]] && rs[i+2] != rs[i+1])) {
			ph = append(ph, "\u025b\u0303")
			i += 2
			continue
		}
		// Vowel digraphs
		if c == 'o' && at(1) == 'u' {
			ph = append(ph, "u")
			i += 2
			continue
		}
		if c == 'a' && at(1) == 'u' {
			ph = append(ph, "o")
			i += 2
			continue
		}
		if c == 'o' && at(1) == 'i' {
			ph = append(ph, "w", "a")
			i += 2
			continue
		}
		if c == 'a' && at(1) == 'i' {
			ph = append(ph, "\u025b")
			i += 2
			continue
		}
		if c == 'e' && at(1) == 'i' {
			ph = append(ph, "\u025b")
			i += 2
			continue
		}
		if (c == 'e' || c == '\u0153') && at(1) == 'u' {
			if i+2 < n && frC[rs[i+2]] && !frSF[rs[i+2]] {
				ph = append(ph, "\u0153")
			} else {
				ph = append(ph, "\u00f8")
			}
			i += 2
			continue
		}
		// Single vowels
		switch c {
		case '\u00e9':
			ph = append(ph, "e")
		case '\u00e8', '\u00ea', '\u00eb':
			ph = append(ph, "\u025b")
		case '\u00e0', '\u00e2', 'a':
			ph = append(ph, "a")
		case '\u00ee', '\u00ef':
			ph = append(ph, "i")
		case 'i':
			if i+1 < n && frV[rs[i+1]] && (i+1 != n-1 || rs[i+1] != 'e') {
				ph = append(ph, "j")
			} else {
				ph = append(ph, "i")
			}
		case '\u00f4':
			ph = append(ph, "o")
		case 'o':
			if frOpenTail(rs[i+1:]) {
				ph = append(ph, "\u0254")
			} else {
				ph = append(ph, "o")
			}
		case '\u00f9', '\u00fb', '\u00fc':
			ph = append(ph, "y_vowel")
		case 'u':
			if at(1) == 'i' {
				ph = append(ph, "\u0265", "i")
				i += 2
				continue
			}
			ph = append(ph, "y_vowel")
			i++
			continue
		case 'y':
			if i+1 < n && frV[rs[i+1]] {
				ph = append(ph, "j")
			} else {
				ph = append(ph, "i")
			}
		case '\u0153':
			ph = append(ph, "\u0153")
		case '\u00e6':
			ph = append(ph, "e")
		case 'e':
			if i == n-1 {
				i++
				continue
			}
			ph = append(ph, frEPh(rs[i+1:]))
		// Consonants
		case 'c':
			if i+1 < n && frSo[rs[i+1]] {
				ph = append(ph, "s")
			} else {
				ph = append(ph, "k")
			}
		case '\u00e7':
			ph = append(ph, "s")
		case 'g':
			if i+1 < n && frSo[rs[i+1]] {
				ph = append(ph, "\u0292")
			} else {
				ph = append(ph, "\u0261")
			}
		case 'j':
			ph = append(ph, "\u0292")
		case 'r':
			ph = append(ph, "\u0281")
			if at(1) == 'r' {
				i += 2
				continue
			}
		case 'x':
			if i == n-1 {
				i++
				continue
			}
			tl := string(rs[i+1:])
			if tl == "e" || tl == "es" {
				i++
				continue
			}
			if i > 0 && rs[i-1] == 'e' && i+1 < n && frV[rs[i+1]] {
				ph = append(ph, "\u0261", "z")
			} else {
				ph = append(ph, "k", "s")
			}
		case 'h':
			i++
			continue
		default:
			if ipa, ok := frSC[c]; ok {
				if (i == n-1 || (i == n-2 && rs[n-1] == 's')) && frSF[c] {
					i++
					continue
				}
				if c == 's' && i > 0 && frV[rs[i-1]] && i+1 < n && frV[rs[i+1]] && at(1) != 's' {
					ph = append(ph, "z")
					i++
					continue
				}
				ph = append(ph, ipa)
				if at(1) == c {
					i += 2
					continue
				}
			}
		}
		i++
	}
	return ph
}

func frSplit(text string) []string {
	text = strings.NewReplacer("\u2019", "'", "\u2018", "'").Replace(text)
	var t []string
	rs := []rune(text)
	i := 0
	for i < len(rs) {
		ch := rs[i]
		if unicode.IsSpace(ch) {
			i++
			continue
		}
		if frPu[ch] {
			t = append(t, string(ch))
			i++
			continue
		}
		if unicode.IsLetter(ch) {
			s := i
			for i < len(rs) && unicode.IsLetter(rs[i]) {
				i++
			}
			t = append(t, string(rs[s:i]))
			continue
		}
		i++
	}
	return t
}

// PhonemizeWithProsody converts French text to phoneme tokens with prosody.
func (p *FrenchPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	text = strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(text))), " ")
	toks := frSplit(text)
	var phs []string
	var pro []*ProsodyInfo
	sp := false
	eos := "$"
	for _, tk := range toks {
		pu := true
		for _, c := range tk {
			if !frPu[c] {
				pu = false
				break
			}
		}
		if !pu && sp {
			phs = append(phs, " ")
			pro = append(pro, &ProsodyInfo{})
		}
		if pu {
			for _, c := range tk {
				ch := string(c)
				phs = append(phs, ch)
				pro = append(pro, &ProsodyInfo{})
				if c == '?' || c == '!' {
					eos = ch
				}
			}
		} else {
			wp := frWord(tk)
			cnt := len(wp)
			lv := -1
			for j := cnt - 1; j >= 0; j-- {
				if frVP[wp[j]] {
					lv = j
					break
				}
			}
			for j, ph := range wp {
				a2 := 0
				if j == lv {
					a2 = 2
				}
				phs = append(phs, ph)
				pro = append(pro, &ProsodyInfo{A1: 0, A2: a2, A3: cnt})
			}
		}
		sp = true
	}
	phs = MapSequence(phs)
	return &PhonemizeResult{Tokens: phs, Prosody: pro, EOSToken: eos}, nil
}

var _ Phonemizer = (*FrenchPhonemizer)(nil)

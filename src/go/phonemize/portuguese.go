package phonemize

import (
	"strings"
	"unicode"
)

// PortuguesePhonemizer converts Brazilian Portuguese text to IPA phonemes
// using rule-based G2P. No external dependencies required.
type PortuguesePhonemizer struct{}

func NewPortuguesePhonemizer() *PortuguesePhonemizer { return &PortuguesePhonemizer{} }
func (p *PortuguesePhonemizer) LanguageCode() string { return "pt" }

var _ Phonemizer = (*PortuguesePhonemizer)(nil)

// --- lookup tables ---

var ptVowels = map[rune]bool{
	'a': true, 'e': true, 'i': true, 'o': true, 'u': true,
	'\u00e1': true, '\u00e0': true, '\u00e2': true, '\u00e3': true,
	'\u00e9': true, '\u00ea': true, '\u00ed': true,
	'\u00f3': true, '\u00f4': true, '\u00f5': true,
	'\u00fa': true, '\u00fc': true,
}
var ptAccBase = map[rune]rune{
	'\u00e1': 'a', '\u00e0': 'a', '\u00e2': 'a', '\u00e3': 'a',
	'\u00e9': 'e', '\u00ea': 'e', '\u00ed': 'i',
	'\u00f3': 'o', '\u00f4': 'o', '\u00f5': 'o',
	'\u00fa': 'u', '\u00fc': 'u',
}
var ptAcute = map[rune]bool{'\u00e1': true, '\u00e9': true, '\u00ed': true, '\u00f3': true, '\u00fa': true}
var ptCirc = map[rune]bool{'\u00e2': true, '\u00ea': true, '\u00f4': true}
var ptTild = map[rune]bool{'\u00e3': true, '\u00f5': true}
var ptPunct = map[rune]bool{'.': true, ',': true, ';': true, ':': true, '!': true, '?': true,
	'\u00a1': true, '\u00bf': true, '\u2014': true, '\u2013': true, '\u2026': true}

// ptConsStr is a string-based consonant phoneme set that includes multi-char
// phonemes (e.g. "tʃ", "dʒ") that a rune-based set cannot represent.
var ptConsStr = map[string]bool{
	"b": true, "d": true, "f": true, "\u0261": true, "k": true, "l": true,
	"m": true, "n": true, "p": true, "\u0272": true, "\u027E": true, "\u0281": true,
	"s": true, "\u0283": true, "t": true, "\u028E": true, "v": true, "w": true,
	"z": true, "\u0292": true,
	// multi-char consonant phonemes produced by ptConvert
	"t\u0283": true, "d\u0292": true,
}
var ptNasV = map[string]bool{"\u00e3": true, "\u1ebd": true, "\u0129": true, "\u00f5": true, "\u0169": true}

func ptV(c rune) bool { return ptVowels[c] }
func ptB(c rune) rune {
	if b, ok := ptAccBase[c]; ok {
		return b
	}
	return c
}
func ptHasAcc(c rune) bool { return ptAcute[c] || ptCirc[c] || ptTild[c] }
func ptEI(c rune) bool {
	return c == 'e' || c == 'i' || c == '\u00e9' || c == '\u00ea' || c == '\u00ed'
}
func ptInterV(r []rune, i int) bool { return i > 0 && i < len(r)-1 && ptV(r[i-1]) && ptV(r[i+1]) }

func ptNasal(b rune) string {
	switch b {
	case 'a':
		return "\u00e3"
	case 'e':
		return "\u1ebd"
	case 'i':
		return "\u0129"
	case 'o':
		return "\u00f5"
	case 'u':
		return "\u0169"
	}
	return string(b)
}
func ptOpen(b rune) string {
	switch b {
	case 'e':
		return "\u025B"
	case 'o':
		return "\u0254"
	}
	return string(b)
}

// --- stress ---

func ptCountVG(r []rune) int {
	c, i, n := 0, 0, len(r)
	for i < n {
		ch := r[i]
		if ch == 'q' && i+1 < n && r[i+1] == 'u' {
			i += 2
			continue
		}
		if ch == 'g' && i+1 < n && r[i+1] == 'u' && i+2 < n && ptEI(r[i+2]) {
			i += 2
			continue
		}
		if ch == 'o' && i+1 < n && r[i+1] == 'u' {
			c++
			i += 2
			continue
		}
		if ptV(ch) {
			c++
		}
		i++
	}
	return c
}

func ptStressPos(r []rune) int {
	vg := ptCountVG(r)
	if vg == 0 {
		return 0
	}
	ag, cg, i, n := -1, 0, 0, len(r)
	for i < n {
		ch := r[i]
		if ch == 'q' && i+1 < n && r[i+1] == 'u' {
			i += 2
			continue
		}
		if ch == 'g' && i+1 < n && r[i+1] == 'u' && i+2 < n && ptEI(r[i+2]) {
			i += 2
			continue
		}
		if ch == 'o' && i+1 < n && r[i+1] == 'u' {
			if ptHasAcc(ch) {
				ag = cg
			}
			cg++
			i += 2
			continue
		}
		if ptV(ch) {
			if ptHasAcc(ch) {
				ag = cg
			}
			cg++
		}
		i++
	}
	if ag >= 0 {
		return vg - 1 - ag
	}
	s := r
	if len(s) > 0 && s[len(s)-1] == 's' {
		s = s[:len(s)-1]
	}
	if len(s) > 0 {
		l := s[len(s)-1]
		if l == 'a' || l == 'e' || l == 'o' {
			if vg > 1 {
				return 1
			}
			return 0
		}
		if len(s) >= 2 {
			t := string(s[len(s)-2:])
			if t == "am" || t == "em" || t == "en" {
				if vg > 1 {
					return 1
				}
				return 0
			}
		}
	}
	return 0
}

// --- word conversion ---

func ptConvert(r []rune) ([]string, int) {
	var ph []string
	si := -1
	sfe := ptStressPos(r)
	vg := ptCountVG(r)
	st := vg - 1 - sfe
	cv := 0
	i, n := 0, len(r)
	for i < n {
		c := r[i]
		// digraphs
		if c == 'n' && i+1 < n && r[i+1] == 'h' {
			ph = append(ph, "\u0272")
			i += 2
			continue
		}
		if c == 'l' && i+1 < n && r[i+1] == 'h' {
			ph = append(ph, "\u028E")
			i += 2
			continue
		}
		if c == 'c' && i+1 < n && r[i+1] == 'h' {
			ph = append(ph, "\u0283")
			i += 2
			continue
		}
		if c == 'r' && i+1 < n && r[i+1] == 'r' {
			ph = append(ph, "\u0281")
			i += 2
			continue
		}
		if c == 's' && i+1 < n && r[i+1] == 's' {
			ph = append(ph, "s")
			i += 2
			continue
		}
		if c == 's' && i+1 < n && r[i+1] == 'c' && i+2 < n && ptEI(r[i+2]) {
			ph = append(ph, "s")
			i += 2
			continue
		}
		if c == 'q' && i+1 < n && r[i+1] == 'u' {
			ph = append(ph, "k")
			if i+2 >= n || !ptEI(r[i+2]) {
				ph = append(ph, "w")
			}
			i += 2
			continue
		}
		if c == 'g' && i+1 < n && r[i+1] == 'u' && i+2 < n && ptEI(r[i+2]) {
			ph = append(ph, "\u0261")
			i += 2
			continue
		}
		if c == 'o' && i+1 < n && r[i+1] == 'u' {
			if cv == st {
				si = len(ph)
			}
			ph = append(ph, "o")
			cv++
			i += 2
			continue
		}
		// consonants (switch replaces if-else chain)
		switch c {
		case 'r':
			if ptInterV(r, i) {
				ph = append(ph, "\u027E")
			} else {
				ph = append(ph, "\u0281")
			}
			i++
			continue
		case 's':
			if i > 0 && i+1 < n && ptV(r[i-1]) && ptV(r[i+1]) {
				ph = append(ph, "z")
			} else {
				ph = append(ph, "s")
			}
			i++
			continue
		case 'x':
			switch {
			case i == 0:
				ph = append(ph, "\u0283")
			case i > 0 && ptV(r[i-1]) && i+1 < n && ptV(r[i+1]):
				ph = append(ph, "z")
			default:
				ph = append(ph, "\u0283")
			}
			i++
			continue
		case 'c':
			if i+1 < n && ptEI(r[i+1]) {
				ph = append(ph, "s")
			} else {
				ph = append(ph, "k")
			}
			i++
			continue
		case '\u00e7':
			ph = append(ph, "s")
			i++
			continue
		case 'g':
			if i+1 < n && ptEI(r[i+1]) {
				ph = append(ph, "\u0292")
			} else {
				ph = append(ph, "\u0261")
			}
			i++
			continue
		case 'j':
			ph = append(ph, "\u0292")
			i++
			continue
		case 't':
			if i+1 < n && (r[i+1] == 'i' || r[i+1] == '\u00ed') {
				ph = append(ph, "t\u0283")
			} else {
				ph = append(ph, "t")
			}
			i++
			continue
		case 'd':
			if i+1 < n && (r[i+1] == 'i' || r[i+1] == '\u00ed') {
				ph = append(ph, "d\u0292")
			} else {
				ph = append(ph, "d")
			}
			i++
			continue
		case 'h':
			i++
			continue
		case 'b', 'f', 'k', 'l', 'm', 'n', 'p', 'v':
			ph = append(ph, string(c))
			i++
			continue
		case 'z':
			ph = append(ph, "z")
			i++
			continue
		case 'w':
			ph = append(ph, "w")
			i++
			continue
		}
		// vowels
		if ptV(c) {
			isSt := cv == st
			base := ptB(c)
			isNas, absN := false, false
			if ptTild[c] {
				isNas = true
			} else if i+1 < n && (r[i+1] == 'n' || r[i+1] == 'm') {
				switch {
				case r[i+1] == 'n' && i+2 < n && r[i+2] == 'h': /* nh: not nasal */
				case i+2 >= n:
					isNas = true
					absN = true
				case !ptV(r[i+2]):
					isNas = true
					absN = true
				}
			}
			var p string
			switch {
			case isNas:
				p = ptNasal(base)
			case ptAcute[c]:
				p = ptOpen(base)
			default:
				p = string(base)
			}
			if isSt {
				si = len(ph)
			}
			ph = append(ph, p)
			cv++
			if absN {
				i += 2
			} else {
				i++
			}
			continue
		}
		i++
	}
	ph = ptRmNasCoda(ph)
	ph = ptCodaL(ph)
	ph = ptBRPost(ph, si)
	return ph, si
}

// --- post-processing ---

func ptRmNasCoda(p []string) []string {
	r := make([]string, len(p))
	copy(r, p)
	for i := len(r) - 1; i >= 1; i-- {
		if (r[i] == "n" || r[i] == "m") && ptNasV[r[i-1]] {
			if i == len(r)-1 || r[i+1] == " " || ptPunct[[]rune(r[i+1])[0]] {
				r = append(r[:i], r[i+1:]...)
			}
		}
	}
	return r
}

func ptCodaL(p []string) []string {
	r := make([]string, len(p))
	copy(r, p)
	for i, s := range r {
		if s != "l" {
			continue
		}
		if i == len(r)-1 {
			r[i] = "w"
			continue
		}
		nx := r[i+1]
		if nx == " " || ptPunct[[]rune(nx)[0]] || ptConsStr[nx] {
			r[i] = "w"
		}
	}
	return r
}

func ptBRPost(p []string, si int) []string {
	r := make([]string, len(p))
	copy(r, p)
	s := 0
	check := func(start, end int) {
		if end-start < 2 {
			return
		}
		l := end - 1
		for l >= start && ptPunct[[]rune(r[l])[0]] {
			l--
		}
		if l < start {
			return
		}
		if r[l] == "e" && l != si {
			if l >= start+1 && r[l-1] == "t" {
				r[l-1] = "t\u0283"
				r[l] = "i"
				return
			}
			if l >= start+1 && r[l-1] == "d" {
				r[l-1] = "d\u0292"
				r[l] = "i"
				return
			}
			r[l] = "i"
		} else if r[l] == "o" && l != si {
			r[l] = "u"
		}
	}
	for i, ph := range r {
		if ph == " " {
			if i > s {
				check(s, i)
			}
			s = i + 1
		}
	}
	if s < len(r) {
		check(s, len(r))
	}
	return r
}

// --- tokenizer + PhonemizeWithProsody ---

func ptTokenize(text string) []textToken {
	var toks []textToken
	rs := []rune(text)
	i := 0
	for i < len(rs) {
		c := rs[i]
		if unicode.IsSpace(c) {
			i++
			continue
		}
		if ptPunct[c] {
			toks = append(toks, textToken{string(c), tokenPunct})
			i++
			continue
		}
		if unicode.IsLetter(c) || c == '\u00e7' {
			s := i
			for i < len(rs) && (unicode.IsLetter(rs[i]) || rs[i] == '\u00e7') {
				i++
			}
			toks = append(toks, textToken{string(rs[s:i]), tokenWord})
			continue
		}
		i++
	}
	return toks
}

// PhonemizeWithProsody converts Brazilian Portuguese text to IPA tokens with prosody.
func (p *PortuguesePhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	text = strings.ToLower(strings.TrimSpace(text))
	toks := ptTokenize(text)
	var phons []string
	var pros []*ProsodyInfo
	sp := false
	eos := "$"
	for _, tk := range toks {
		if tk.kind == tokenPunct {
			phons = append(phons, tk.text)
			pros = append(pros, &ProsodyInfo{0, 0, 0})
			if tk.text == "?" || tk.text == "!" {
				eos = tk.text
			}
			continue
		}
		if sp {
			phons = append(phons, " ")
			pros = append(pros, &ProsodyInfo{0, 0, 0})
		}
		wr := []rune(tk.text)
		wp, si := ptConvert(wr)
		wl := len(wp)
		for j, ph := range wp {
			a2 := 0
			if j == si {
				a2 = 2
			}
			phons = append(phons, ph)
			pros = append(pros, &ProsodyInfo{0, a2, wl})
		}
		sp = true
	}
	phons = MapSequence(phons)
	return &PhonemizeResult{Tokens: phons, Prosody: pros, EOSToken: eos}, nil
}

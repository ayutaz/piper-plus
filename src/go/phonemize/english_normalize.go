package phonemize

// English text normalization, ported from Python's g2p_en.
//
// Python's English G2P (g2p_en.G2p.__call__) rewrites the text before its
// dictionary lookup. This file ports those steps so the Go phonemizer sees
// the same words, with the same rules as the Rust port
// (src/rust/piper-plus-g2p/src/english_normalize.rs):
//
//  1. normalizeNumbers spells numbers out the way inflect does
//     (123 -> one hundred twenty-three, 1984 -> nineteen eighty-four,
//     $5 -> five dollars, 2nd -> second);
//  2. accents are stripped (NFD, combining marks removed);
//  3. every character other than a-z A-Z ' . , ? ! - and the ASCII space is
//     removed (tabs and newlines too, so the words around them join);
//  4. i.e. / e.g. become "that is" / "for example" (case-insensitively);
//  5. the subset of nltk's TweetTokenizer that this character set can reach
//     splits the text into words.
//
// Python lowercases at step 2; the port keeps the case because the OOV
// fallback splits CamelCase words. Callers lowercase for dictionary lookup.
// english_normalize_test.go checks both steps against
// tests/fixtures/g2p/english_normalize_cases.json, generated from Python.

import (
	"regexp"
	"strconv"
	"strings"
	"unicode"
)

// ---------------------------------------------------------------------------
// Number expansion (g2p_en expand.py + inflect number_to_words)
// ---------------------------------------------------------------------------

var (
	commaNumberRE   = regexp.MustCompile(`([0-9][0-9,]+[0-9])`)
	poundsRE        = regexp.MustCompile(`£([0-9,]*[0-9]+)`)
	dollarsRE       = regexp.MustCompile(`\$([0-9.,]*[0-9]+)`)
	decimalNumberRE = regexp.MustCompile(`([0-9]+\.[0-9]+)`)
	ordinalRE       = regexp.MustCompile(`[0-9]+(st|nd|rd|th)`)
	numberRE        = regexp.MustCompile(`[0-9]+`)

	// inflect's post-processing of the joined groups.
	whitespacesCommaRE = regexp.MustCompile(`\s+,`)
	commaWordRE        = regexp.MustCompile(`, (\S+)\s+\z`)
	whitespacesRE      = regexp.MustCompile(`\s+`)
)

var numberUnit = [10]string{
	"", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
}

var numberTeen = [10]string{
	"ten", "eleven", "twelve", "thirteen", "fourteen",
	"fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
}

var numberTen = [10]string{
	"", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
}

// numberMill holds the group scales. inflect goes on to decillion; the port
// stops at quintillion and reads longer digit runs digit by digit.
var numberMill = [7]string{
	" ", " thousand", " million", " billion", " trillion", " quadrillion", " quintillion",
}

var digitNames = [10]string{
	"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
}

// ordinalSuffixes are tried at the end of the last word (inflect ordinal).
var ordinalSuffixes = [8][2]string{
	{"ty", "tieth"},
	{"one", "first"},
	{"two", "second"},
	{"three", "third"},
	{"five", "fifth"},
	{"eight", "eighth"},
	{"nine", "ninth"},
	{"twelve", "twelfth"},
}

// normalizeNumbers expands numbers in text to English words, like g2p_en's
// normalize_numbers. The regex substitutions run in Python's order.
func normalizeNumbers(text string) string {
	text = commaNumberRE.ReplaceAllStringFunc(text, func(m string) string {
		return strings.ReplaceAll(m, ",", "")
	})
	text = poundsRE.ReplaceAllString(text, "${1} pounds")
	text = replaceAllSubmatchFunc(dollarsRE, text, func(groups []string) string {
		return expandDollars(groups[1])
	})
	text = decimalNumberRE.ReplaceAllStringFunc(text, func(m string) string {
		return strings.ReplaceAll(m, ".", " point ")
	})
	text = ordinalRE.ReplaceAllStringFunc(text, expandOrdinal)
	return numberRE.ReplaceAllStringFunc(text, expandNumber)
}

// replaceAllSubmatchFunc is regexp.ReplaceAllStringFunc with the submatches
// passed to repl.
func replaceAllSubmatchFunc(re *regexp.Regexp, text string, repl func([]string) string) string {
	var b strings.Builder
	last := 0
	for _, loc := range re.FindAllStringSubmatchIndex(text, -1) {
		groups := make([]string, len(loc)/2)
		for i := range groups {
			if loc[2*i] >= 0 {
				groups[i] = text[loc[2*i]:loc[2*i+1]]
			}
		}
		b.WriteString(text[last:loc[0]])
		b.WriteString(repl(groups))
		last = loc[1]
	}
	b.WriteString(text[last:])
	return b.String()
}

// canonicalDigits returns the decimal digits of s without leading zeros ("0"
// when there are none). Matches Python's str(int(s)); non-digits (a stray
// comma) are ignored.
func canonicalDigits(s string) string {
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		if isASCIIDigit(s[i]) {
			b.WriteByte(s[i])
		}
	}
	if trimmed := strings.TrimLeft(b.String(), "0"); trimmed != "" {
		return trimmed
	}
	return "0"
}

// expandDollars turns $D.C into "D dollar(s), C cent(s)" (g2p_en
// _expand_dollars).
func expandDollars(amount string) string {
	parts := strings.Split(amount, ".")
	if len(parts) > 2 {
		return amount + " dollars" // Unexpected format
	}
	dollars := canonicalDigits(parts[0])
	cents := "0"
	if len(parts) == 2 {
		cents = canonicalDigits(parts[1])
	}
	dollarUnit := "dollars"
	if dollars == "1" {
		dollarUnit = "dollar"
	}
	centUnit := "cents"
	if cents == "1" {
		centUnit = "cent"
	}
	switch {
	case dollars != "0" && cents != "0":
		return dollars + " " + dollarUnit + ", " + cents + " " + centUnit
	case dollars != "0":
		return dollars + " " + dollarUnit
	case cents != "0":
		return cents + " " + centUnit
	default:
		return "zero dollars"
	}
}

// expandOrdinal turns 21st into twenty-first (inflect number_to_words with an
// ordinal suffix).
func expandOrdinal(matched string) string {
	digits := canonicalDigits(matched[:len(matched)-2])
	return toOrdinal(numberWords(digits, "and"))
}

// expandNumber reads a cardinal number, as a year between 1001 and 2999
// (g2p_en _expand_number).
func expandNumber(matched string) string {
	digits := canonicalDigits(matched)
	if len(digits) == 4 {
		if n, err := strconv.Atoi(digits); err == nil && n > 1000 && n < 3000 {
			return yearWords(n)
		}
	}
	return numberWords(digits, "")
}

func yearWords(n int) string {
	switch {
	case n == 2000:
		return "two thousand"
	case n > 2000 && n < 2010:
		return "two thousand " + numberWords(strconv.Itoa(n%100), "and")
	case n%100 == 0:
		return numberWords(strconv.Itoa(n/100), "and") + " hundred"
	}
	// inflect group=2 with zero="oh": two digits at a time.
	low := n % 100
	var lowWords string
	if low < 10 {
		lowWords = "oh " + numberUnit[low]
	} else {
		lowWords = strings.TrimRight(tensWords(low/10, low%10, 0), " ")
	}
	high := n / 100
	return strings.TrimRight(tensWords(high/10, high%10, 0), " ") + " " + lowWords
}

// tensWords is inflect tenfn: 0-99 followed by the scale of group mill.
func tensWords(tens, units, mill int) string {
	if tens == 1 {
		return numberTeen[units] + numberMill[mill]
	}
	hyphen := ""
	if tens > 0 && units > 0 {
		hyphen = "-"
	}
	return numberTen[tens] + hyphen + numberUnit[units] + numberMill[mill]
}

// hundredsWords is inflect hundfn: one full group of three digits.
func hundredsWords(hundreds, tens, units, mill int, and string) string {
	switch {
	case hundreds > 0:
		andWord := ""
		if tens > 0 || units > 0 {
			andWord = " " + and + " "
		}
		return numberUnit[hundreds] + " hundred" + andWord + tensWords(tens, units, 0) + numberMill[mill] + ", "
	case tens > 0 || units > 0:
		return tensWords(tens, units, 0) + numberMill[mill] + ", "
	default:
		return ""
	}
}

// numberWords is inflect number_to_words(digits, andword=and) for a
// canonical digit string. Groups are joined with ", " except that a last
// group of 1-99 is joined with and (" " when and is empty): "one million one".
func numberWords(digits, and string) string {
	switch digits {
	case "0":
		return "zero"
	case "1":
		return "one"
	}
	d := make([]int, len(digits))
	for i := 0; i < len(digits); i++ {
		d[i] = int(digits[i] - '0')
	}
	if len(d) > 3*len(numberMill) {
		// Beyond quintillion: read each digit.
		names := make([]string, len(d))
		for i, x := range d {
			names[i] = digitNames[x]
		}
		return strings.Join(names, " ")
	}

	groups := len(d) / 3
	lead := len(d) % 3
	var b strings.Builder
	switch lead {
	case 2:
		b.WriteString(tensWords(d[0], d[1], groups) + ", ")
	case 1:
		b.WriteString(numberUnit[d[0]] + numberMill[groups] + ", ")
	}
	for g := range groups {
		i := lead + 3*g
		b.WriteString(hundredsWords(d[i], d[i+1], d[i+2], groups-1-g, and))
	}

	s := strings.TrimSuffix(b.String(), ", ")
	s = whitespacesCommaRE.ReplaceAllString(s, ",")
	if loc := commaWordRE.FindStringSubmatchIndex(s); loc != nil {
		s = s[:loc[0]] + " " + and + " " + s[loc[2]:loc[3]] + s[loc[1]:]
	}
	return strings.TrimSpace(whitespacesRE.ReplaceAllString(s, " "))
}

// toOrdinal is inflect _sub_ord: the ordinal of the last word.
func toOrdinal(words string) string {
	for _, sr := range ordinalSuffixes {
		if stem, ok := strings.CutSuffix(words, sr[0]); ok {
			return stem + sr[1]
		}
	}
	return words + "th"
}

// ---------------------------------------------------------------------------
// Accent stripping and character filter
// ---------------------------------------------------------------------------

// latinBase00C0 is the base letter of each code point in U+00C0..U+024F whose
// NFD form is an ASCII letter followed by combining marks; '-' where there is
// none. Generated with Python's unicodedata.
const latinBase00C0 = "AAAAAA-CEEEEIIII-NOOOOO--UUUUY--aaaaaa-ceeeeiiii-nooooo--uuuuy-y" +
	"AaAaAaCcCcCcCcDd--EeEeEeEeEeGgGgGgGgHh--IiIiIiIiI---JjKk-LlLlLl-" +
	"---NnNnNn---OoOoOo--RrRrRrSsSsSsSsTtTt--UuUuUuUuUuUuWwYyYZzZzZz-" +
	"--------------------------------Oo-------------Uu---------------" +
	"-------------AaIiOoUuUuUuUuUu-AaAa----GgKkOoOo--j---Gg--NnAa----" +
	"AaAaEeEeIiIiOoOoRrRrUuUuSsTt--Hh------AaEeOoOoOoOoYy------------" +
	"----------------"

// latinBase1E00 is the same for U+1E00..U+1EFF (Latin Extended Additional).
const latinBase1E00 = "AaBbBbBbCcDdDdDdDdDdEeEeEeEeEeFfGgHhHhHhHhHhIiIiKkKkKkLlLlLlLlMm" +
	"MmMmNnNnNnNnOoOoOoOoPpPpRrRrRrRrSsSsSsSsSsTtTtTtTtUuUuUuUuUuVvVv" +
	"WwWwWwWwWwXxXxYyZzZzZzhtwy------AaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEe" +
	"EeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuYyYyYyYy------"

// foldAccent returns the ASCII letter left after NFD and removing combining
// marks, for a non-ASCII character. Combining marks themselves and every
// other character give false: the character filter would remove them anyway.
func foldAccent(ch rune) (byte, bool) {
	fromTable := func(table string, offset rune) (byte, bool) {
		if int(offset) < len(table) && table[offset] != '-' {
			return table[offset], true
		}
		return 0, false
	}
	switch {
	case ch >= 0x00C0 && ch <= 0x024F:
		return fromTable(latinBase00C0, ch-0x00C0)
	case ch >= 0x1E00 && ch <= 0x1EFF:
		return fromTable(latinBase1E00, ch-0x1E00)
	case ch == 0x212A: // KELVIN SIGN
		return 'K', true
	case ch == 0x212B: // ANGSTROM SIGN
		return 'A', true
	}
	return 0, false
}

func isASCIILetter(c byte) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
}

func isASCIIDigit(c byte) bool {
	return c >= '0' && c <= '9'
}

// stripAccentsAndFilter is steps 2-3: strip accents and keep
// a-z A-Z ' . , ? ! - and the ASCII space. The result is ASCII. Unlike
// g2p_en, any whitespace (tab, newline, no-break space, ...) becomes a space
// instead of being removed: removing it joins the words around it, and Python
// reads the joined word with a neural predictor this port does not have.
func stripAccentsAndFilter(text string) string {
	var b strings.Builder
	for _, ch := range text {
		var c byte
		switch {
		case unicode.IsSpace(ch):
			c = ' '
		case ch < 0x80:
			c = byte(ch)
		default:
			folded, ok := foldAccent(ch)
			if !ok {
				continue
			}
			c = folded
		}
		if isASCIILetter(c) || strings.IndexByte(" '.,?!-", c) >= 0 {
			b.WriteByte(c)
		}
	}
	return b.String()
}

// replaceIgnoreASCIICase is Python's str.replace (left to right,
// non-overlapping), ignoring ASCII case. text and pattern are ASCII.
func replaceIgnoreASCIICase(text, pattern, replacement string) string {
	var b strings.Builder
	for i := 0; i < len(text); {
		if len(text)-i >= len(pattern) && strings.EqualFold(text[i:i+len(pattern)], pattern) {
			b.WriteString(replacement)
			i += len(pattern)
		} else {
			b.WriteByte(text[i])
			i++
		}
	}
	return b.String()
}

// ---------------------------------------------------------------------------
// TweetTokenizer subset
// ---------------------------------------------------------------------------

// shortenHang is nltk HANG_RE: 4+ copies of a non-letter, non-digit
// character become 3.
func shortenHang(text string) string {
	var b strings.Builder
	for i := 0; i < len(text); {
		c := text[i]
		j := i + 1
		for j < len(text) && text[j] == c {
			j++
		}
		run := j - i
		if !isASCIILetter(c) && !isASCIIDigit(c) {
			run = min(run, 3)
		}
		for range run {
			b.WriteByte(c)
		}
		i = j
	}
	return b.String()
}

func letterRunEnd(s string, start int) int {
	j := start
	for j < len(s) && isASCIILetter(s[j]) {
		j++
	}
	return j
}

// matchDomain matches a naked domain,
// [a-z]+([.-][a-z]+){0,126}\.[a-z]{2,13} not followed by a letter. Like the
// backtracking regex, it takes the most labels for which the next separator
// is '.' and the label after it has 2-13 letters.
func matchDomain(s string, start int) (int, bool) {
	pos := letterRunEnd(s, start)
	if pos == start {
		return 0, false
	}
	// The separator and bounds of each label after the first run.
	type label struct {
		sep        byte
		start, end int
	}
	var labels []label
	for pos+1 < len(s) && (s[pos] == '.' || s[pos] == '-') && isASCIILetter(s[pos+1]) {
		end := letterRunEnd(s, pos+1)
		labels = append(labels, label{sep: s[pos], start: pos + 1, end: end})
		pos = end
	}
	for k := min(len(labels)-1, 126); k >= 0; k-- {
		l := labels[k]
		if n := l.end - l.start; l.sep == '.' && n >= 2 && n <= 13 {
			return l.end, true
		}
	}
	return 0, false
}

// matchHyphenatedWord matches a word with apostrophes or dashes,
// [a-z]([a-z]|['-])+[a-z].
func matchHyphenatedWord(s string, start int) (int, bool) {
	if !isASCIILetter(s[start]) {
		return 0, false
	}
	end := start + 1
	for end < len(s) && (isASCIILetter(s[end]) || s[end] == '\'' || s[end] == '-') {
		end++
	}
	for i := end - 1; i >= start+2; i-- {
		if isASCIILetter(s[i]) {
			return i + 1, true
		}
	}
	return 0, false
}

// matchEllipsis matches an ellipsis, \.( *\.)+.
func matchEllipsis(s string, start int) (int, bool) {
	if s[start] != '.' {
		return 0, false
	}
	end, found := 0, false
	for j := start + 1; ; {
		k := j
		for k < len(s) && s[k] == ' ' {
			k++
		}
		if k >= len(s) || s[k] != '.' {
			return end, found
		}
		end, found = k+1, true
		j = k + 1
	}
}

// tweetTokenize is the part of nltk's TweetTokenizer that the filtered
// character set (a-z A-Z ' . , ? ! - and space) can reach. At each position
// the first matching alternative wins, in nltk's order; spaces only separate
// words.
func tweetTokenize(text string) []string {
	text = shortenHang(text)
	var words []string
	for i := 0; i < len(text); {
		if text[i] == ' ' {
			i++
			continue
		}
		end, ok := matchDomain(text, i)
		if !ok {
			end, ok = matchHyphenatedWord(text, i)
		}
		if !ok {
			end = letterRunEnd(text, i)
			ok = end > i
		}
		if !ok {
			end, ok = matchEllipsis(text, i)
		}
		if !ok {
			end = i + 1
		}
		words = append(words, text[i:end])
		i = end
	}
	return words
}

// normalizeAndTokenize is all of g2p_en's preprocessing: number expansion,
// accent stripping, the character filter, the i.e./e.g. replacement and
// tokenization. The words keep their case; Python's are these words
// lowercased.
func normalizeAndTokenize(text string) []string {
	text = stripAccentsAndFilter(normalizeNumbers(text))
	text = replaceIgnoreASCIICase(text, "i.e.", "that is")
	text = replaceIgnoreASCIICase(text, "e.g.", "for example")
	return tweetTokenize(text)
}

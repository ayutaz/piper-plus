package phonemize

// CJK punctuation contract (Issue #823).
//
// Reads tests/fixtures/g2p/cjk_punctuation_cases.json, which
// scripts/build_cjk_punctuation_fixture.py builds from
// docs/spec/cjk-punctuation-contract.toml. Every runtime has the same test,
// so a detector or Latin-segment rewrite that drifts from the contract fails
// in the runtime that drifted.

import (
	"strings"
	"testing"
	"unicode/utf8"
)

type cjkPunctuationChar struct {
	CodePoint string `json:"code_point"`
	Char      string `json:"char"`
	Latin     string `json:"latin"`
}

type cjkPunctuationFixture struct {
	DetectorLanguages []string             `json:"detector_languages"`
	DefaultLatin      string               `json:"default_latin"`
	LatinLanguages    []string             `json:"latin_languages"`
	Neutral           []cjkPunctuationChar `json:"neutral"`
	FullwidthLatin    []cjkPunctuationChar `json:"fullwidth_latin"`
}

func loadCJKPunctuationFixture(t *testing.T) *cjkPunctuationFixture {
	t.Helper()
	var f cjkPunctuationFixture
	readRepoJSON(t, "tests/fixtures/g2p/cjk_punctuation_cases.json", &f)
	if len(f.Neutral) <= 100 || len(f.FullwidthLatin) != 52 {
		t.Fatalf("fixture too small: %d neutral, %d fullwidth Latin",
			len(f.Neutral), len(f.FullwidthLatin))
	}
	return &f
}

// fixtureRune returns the single character of a fixture entry.
func fixtureRune(t *testing.T, c cjkPunctuationChar) rune {
	t.Helper()
	r, size := utf8.DecodeRuneInString(c.Char)
	if r == utf8.RuneError || size != len(c.Char) {
		t.Fatalf("%s: char %q is not one character", c.CodePoint, c.Char)
	}
	return r
}

func TestCJKPunctuationContract_NeutralCodePointsBelongToNoLanguage(t *testing.T) {
	f := loadCJKPunctuationFixture(t)
	d := NewUnicodeLanguageDetector(f.DetectorLanguages, f.DefaultLatin)
	for _, contextHasKana := range []bool{false, true} {
		var wrong []string
		for _, c := range f.Neutral {
			if lang := d.DetectChar(fixtureRune(t, c), contextHasKana); lang != "" {
				wrong = append(wrong, c.CodePoint+"="+lang)
			}
		}
		if len(wrong) > 0 {
			t.Errorf("contextHasKana=%v: %d neutral code point(s) got a language: %s",
				contextHasKana, len(wrong), strings.Join(wrong, " "))
		}
	}
}

func TestCJKPunctuationContract_FullwidthLatinLettersStayLatin(t *testing.T) {
	f := loadCJKPunctuationFixture(t)
	d := NewUnicodeLanguageDetector(f.DetectorLanguages, f.DefaultLatin)
	var wrong []string
	for _, c := range f.FullwidthLatin {
		if lang := d.DetectChar(fixtureRune(t, c), false); lang != f.DefaultLatin {
			wrong = append(wrong, c.CodePoint+"="+lang)
		}
	}
	if len(wrong) > 0 {
		t.Errorf("fullwidth Latin letters not %q: %s", f.DefaultLatin, strings.Join(wrong, " "))
	}
}

func TestCJKPunctuationContract_LatinSegmentRewrite(t *testing.T) {
	f := loadCJKPunctuationFixture(t)
	for _, c := range f.Neutral {
		if got := NormalizeCJKPunctuationForLatin(c.Char); got != c.Latin {
			t.Errorf("%s: got %q, want %q", c.CodePoint, got, c.Latin)
		}
	}
	// Everything else is left alone, the fullwidth Latin letters included.
	for _, text := range []string{"Hello, world!", "café", "ＡＢＣ", "你好", "こんにちは", ""} {
		if got := NormalizeCJKPunctuationForLatin(text); got != text {
			t.Errorf("NormalizeCJKPunctuationForLatin(%q) = %q, want it unchanged", text, got)
		}
	}
}

// cjkPunctuationPhonemizer is a multilingual phonemizer for the fixture's
// languages with the checked-in dictionaries. Japanese needs OpenJTalk, so
// "ja" is a configured language without a phonemizer: a segment detected as
// Japanese is skipped, which is how the old classification of these
// characters dropped them.
func cjkPunctuationPhonemizer(t *testing.T, f *cjkPunctuationFixture) *MultilingualPhonemizer {
	t.Helper()
	phonemizers := goldenParityPhonemizer(t).phonemizers
	return NewMultilingualPhonemizer(f.DetectorLanguages, f.DefaultLatin, phonemizers)
}

func phonemizeTokens(t *testing.T, p *MultilingualPhonemizer, text string) []string {
	t.Helper()
	result, err := p.PhonemizeWithProsody(text)
	if err != nil {
		t.Fatalf("PhonemizeWithProsody(%q): %v", text, err)
	}
	return result.Tokens
}

func TestCJKPunctuationContract_ChineseSentenceKeepsItsPunctuation(t *testing.T) {
	f := loadCJKPunctuationFixture(t)
	p := cjkPunctuationPhonemizer(t, f)

	tokens := phonemizeTokens(t, p, "你好，今天天气很好。")
	commas := 0
	for _, tok := range tokens {
		if tok == "," {
			commas++
		}
	}
	if commas != 1 {
		t.Errorf("你好，今天天气很好。: %d commas in %q, want 1", commas, tokens)
	}
	if len(tokens) == 0 || tokens[len(tokens)-1] != "." {
		t.Errorf("你好，今天天气很好。: %q does not end with \".\"", tokens)
	}
	if tokens := phonemizeTokens(t, p, "北京欢迎你。"); len(tokens) == 0 || tokens[len(tokens)-1] != "." {
		t.Errorf("北京欢迎你。: %q does not end with \".\"", tokens)
	}

	segs := SegmentText("你好，今天天气很好。", NewUnicodeLanguageDetector(f.DetectorLanguages, f.DefaultLatin))
	if len(segs) != 1 || segs[0].Language != "zh" {
		t.Errorf("你好，今天天气很好。: segments %+v, want one zh segment", segs)
	}
}

func TestCJKPunctuationContract_EnglishAfterChineseCommaIsReadAsALoanword(t *testing.T) {
	// The ZH-EN dispatch needs the Chinese segment right before the English
	// one; a Japanese segment for "，" used to sit between them.
	f := loadCJKPunctuationFixture(t)
	p := cjkPunctuationPhonemizer(t, f)

	var withComma []string
	for _, tok := range phonemizeTokens(t, p, "你好，GPS") {
		if tok != "," {
			withComma = append(withComma, tok)
		}
	}
	without := phonemizeTokens(t, p, "你好GPS")
	if !tokenSliceEqual(withComma, without) {
		t.Errorf("你好，GPS without \",\" = %q, want %q (你好GPS)", withComma, without)
	}
}

func TestCJKPunctuationContract_LatinTextWithCJKPunctuationReadsLikeASCII(t *testing.T) {
	// The English G2P drops characters it does not know, which used to join
	// "Hello，world" into one word.
	f := loadCJKPunctuationFixture(t)
	p := cjkPunctuationPhonemizer(t, f)

	cases := []struct{ cjk, ascii string }{
		{"Hello，world", "Hello,world"},
		{"Hello、world。", "Hello,world."},
		{"Hola，amigo！", "Hola,amigo!"},
		{"I have ３ cats．", "I have 3 cats."},
	}
	for _, c := range cases {
		got := phonemizeTokens(t, p, c.cjk)
		want := phonemizeTokens(t, p, c.ascii)
		if !tokenSliceEqual(got, want) {
			t.Errorf("%q = %q, want %q (%q)", c.cjk, got, want, c.ascii)
		}
		// The same holds when the text is read as each Latin language.
		for _, lang := range f.LatinLanguages {
			gotLang, err := p.PhonemizeWithLanguage(c.cjk, lang)
			if err != nil {
				t.Fatalf("PhonemizeWithLanguage(%q, %q): %v", c.cjk, lang, err)
			}
			wantLang, err := p.PhonemizeWithLanguage(c.ascii, lang)
			if err != nil {
				t.Fatalf("PhonemizeWithLanguage(%q, %q): %v", c.ascii, lang, err)
			}
			if !tokenSliceEqual(gotLang.Tokens, wantLang.Tokens) {
				t.Errorf("[%s] %q = %q, want %q (%q)", lang, c.cjk, gotLang.Tokens, wantLang.Tokens, c.ascii)
			}
		}
	}
}

func TestCJKPunctuationContract_EuropeanPortugueseSegmentIsRewritten(t *testing.T) {
	// "pt-PT" is a Latin-script language too (the contract counts it as "pt").
	phonemizers := map[string]Phonemizer{"pt-PT": NewEuropeanPortuguesePhonemizer()}
	p := NewMultilingualPhonemizer([]string{"ja", "pt-PT"}, "pt-PT", phonemizers)
	got := phonemizeTokens(t, p, "Olá，amigo！")
	want := phonemizeTokens(t, p, "Olá,amigo!")
	if !tokenSliceEqual(got, want) {
		t.Errorf("Olá，amigo！ = %q, want %q (Olá,amigo!)", got, want)
	}
}

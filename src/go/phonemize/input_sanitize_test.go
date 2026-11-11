package phonemize

// Control characters are stripped before a text is phonemized.
//
// Contract: docs/spec/input-sanitize-contract.toml (runtime "go").
// Cases: tests/fixtures/g2p/input_sanitize_cases.json, read here directly
// like the golden parity test reads its fixtures, so one edit there re-tests
// Go too.
//
// Regression focus: #934 (2026-11) stripped control characters in the
// Python G2P only. Here a NUL inside "hola" split the word in two, a NUL
// after "?" hid the Japanese question (the EOS token is read from the raw
// text) and a custom dictionary missed a word with a NUL inside it.

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

type sanitizeStripCase struct {
	Name     string `json:"name"`
	Input    string `json:"input"`
	Expected string `json:"expected"`
}

type sanitizeTextCase struct {
	Name     string `json:"name"`
	Language string `json:"language"`
	Control  string `json:"control"`
	Clean    string `json:"clean"`
	Dirty    string `json:"dirty"`
}

type sanitizeCases struct {
	StripCases    []sanitizeStripCase `json:"strip_cases"`
	WordCases     []sanitizeTextCase  `json:"word_cases"`
	PipelineCases []sanitizeTextCase  `json:"pipeline_cases"`
}

func loadSanitizeCases(t *testing.T) sanitizeCases {
	t.Helper()
	var c sanitizeCases
	readRepoJSON(t, "tests/fixtures/g2p/input_sanitize_cases.json", &c)
	if len(c.StripCases) == 0 || len(c.WordCases) == 0 {
		t.Fatal("input_sanitize_cases.json has no cases")
	}
	return c
}

func (c sanitizeCases) onlyControls(t *testing.T) string {
	t.Helper()
	for _, s := range c.StripCases {
		if s.Name == "only_controls" {
			return s.Input
		}
	}
	t.Fatal("input_sanitize_cases.json has no only_controls case")
	return ""
}

// sanitizePhonemizers are the per-language phonemizers with the checked-in
// dictionaries. Japanese needs OpenJTalk and is tested with a recording
// engine below.
func sanitizePhonemizers(t *testing.T) map[string]Phonemizer {
	t.Helper()
	out := make(map[string]Phonemizer)
	for lang, p := range goldenParityPhonemizer(t).phonemizers {
		out[lang] = p
	}
	out["pt-PT"] = NewEuropeanPortuguesePhonemizer()
	return out
}

func phonemizeOrFail(t *testing.T, label string, read func(string) (*PhonemizeResult, error), text string) *PhonemizeResult {
	t.Helper()
	result, err := read(text)
	if err != nil {
		t.Fatalf("%s: phonemize %q: %v", label, text, err)
	}
	return result
}

func requireSameReading(t *testing.T, label string, read func(string) (*PhonemizeResult, error), dirty, clean string) {
	t.Helper()
	got := phonemizeOrFail(t, label, read, dirty)
	want := phonemizeOrFail(t, label, read, clean)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: %q read differently from %q\n  dirty: %q (eos %q)\n  clean: %q (eos %q)",
			label, dirty, clean, got.Tokens, got.EOSToken, want.Tokens, want.EOSToken)
	}
}

func TestStripControlChars_Cases(t *testing.T) {
	for _, c := range loadSanitizeCases(t).StripCases {
		if got := StripControlChars(c.Input); got != c.Expected {
			t.Errorf("%s: StripControlChars(%q) = %q, want %q", c.Name, c.Input, got, c.Expected)
		}
	}
}

func TestStripControlChars_Idempotent(t *testing.T) {
	for _, c := range loadSanitizeCases(t).StripCases {
		once := StripControlChars(c.Input)
		if twice := StripControlChars(once); twice != once {
			t.Errorf("%s: not idempotent: %q then %q", c.Name, once, twice)
		}
	}
}

func TestStripControlChars_KeepsInvalidUTF8Bytes(t *testing.T) {
	// Only control characters change; other bytes pass through as they are.
	in := "a\xffb\x00c"
	if got := StripControlChars(in); got != "a\xffbc" {
		t.Errorf("StripControlChars(%q) = %q, want %q", in, got, "a\xffbc")
	}
}

// Every per-language phonemizer, called directly as a G2P library caller
// does, reads a dirty word like the clean one.
func TestInputSanitize_PerLanguagePhonemizers(t *testing.T) {
	cases := loadSanitizeCases(t)
	phonemizers := sanitizePhonemizers(t)
	for _, c := range cases.WordCases {
		if c.Language == "ja" || c.Language == "multilingual" {
			continue
		}
		p, ok := phonemizers[c.Language]
		if !ok {
			t.Fatalf("no Go phonemizer for fixture language %q", c.Language)
		}
		requireSameReading(t, c.Language+" "+c.Control, p.PhonemizeWithProsody, c.Dirty, c.Clean)
	}
}

func TestInputSanitize_OnlyControlsReadAsEmpty(t *testing.T) {
	cases := loadSanitizeCases(t)
	only := cases.onlyControls(t)
	phonemizers := sanitizePhonemizers(t)
	m := goldenParityPhonemizer(t)
	phonemizers["multilingual"] = m
	for lang, p := range phonemizers {
		requireSameReading(t, lang, p.PhonemizeWithProsody, only, "")
	}
}

func TestInputSanitize_Multilingual(t *testing.T) {
	cases := loadSanitizeCases(t)
	m := goldenParityPhonemizer(t)
	for _, c := range append(append([]sanitizeTextCase(nil), cases.WordCases...), cases.PipelineCases...) {
		if c.Language == "ja" || c.Name == "ssml" || c.Name == "inline_phonemes" {
			// ja needs OpenJTalk; SSML and [[ ]] are read by piperplus.
			continue
		}
		label := c.Language + " " + c.Control + c.Name
		requireSameReading(t, label+" PhonemizeWithProsody", m.PhonemizeWithProsody, c.Dirty, c.Clean)
		if c.Language != "multilingual" {
			lang := c.Language
			if lang == "pt-PT" {
				lang = "pt"
			}
			read := func(text string) (*PhonemizeResult, error) { return m.PhonemizeWithLanguage(text, lang) }
			requireSameReading(t, label+" PhonemizeWithLanguage", read, c.Dirty, c.Clean)
		}
	}
}

func TestInputSanitize_CustomDictionaryFindsTheWord(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("hola", []string{"x"})
	p := d.WrapPhonemizer(NewSpanishPhonemizer())
	requireSameReading(t, "dict", p.PhonemizeWithProsody, "ho\x00la", "hola")
}

// recordingEngine returns fixed labels and records the text it was given.
type recordingEngine struct {
	labels []string
	texts  []string
}

func (e *recordingEngine) ExtractFullcontext(text string) ([]string, error) {
	e.texts = append(e.texts, text)
	return e.labels, nil
}

func TestInputSanitize_Japanese(t *testing.T) {
	labels := []string{
		"xx^xx-sil+k=a/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+a=sil/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-a+sil=xx/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	cases := loadSanitizeCases(t)
	checked := 0
	for _, c := range cases.WordCases {
		if c.Language != "ja" {
			continue
		}
		engine := &recordingEngine{labels: labels}
		p := NewJapanesePhonemizer(engine)
		// The EOS token (question type) is read from the text, so the
		// fixed labels still show a wrong reading.
		requireSameReading(t, "ja "+c.Control, p.PhonemizeWithProsody, c.Dirty, c.Clean)
		if len(engine.texts) != 2 || engine.texts[0] != engine.texts[1] {
			t.Errorf("ja %s: OpenJTalk got %q, want the clean text twice", c.Control, engine.texts)
		}
		checked++
	}
	if checked == 0 {
		t.Fatal("no ja word case")
	}
}

// Every PhonemizeWithProsody / PhonemizeWithLanguage method in the package,
// and ChinesePhonemizer.PhonemizeEmbeddedEnglish (MultilingualPhonemizer
// calls it for the English run between Chinese text), calls
// StripControlChars, so a new language that forgets it fails here.
// This reads the source instead of a registry: the package has none, and
// piperplus builds its own list.
func TestInputSanitize_EveryPhonemizerMethodStrips(t *testing.T) {
	files, err := filepath.Glob("*.go")
	if err != nil {
		t.Fatal(err)
	}
	fset := token.NewFileSet()
	var methods, missing []string
	for _, name := range files {
		if strings.HasSuffix(name, "_test.go") {
			continue
		}
		src, err := os.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		f, err := parser.ParseFile(fset, name, src, 0)
		if err != nil {
			t.Fatalf("parse %s: %v", name, err)
		}
		for _, decl := range f.Decls {
			fn, ok := decl.(*ast.FuncDecl)
			if !ok || fn.Recv == nil || fn.Body == nil {
				continue
			}
			switch fn.Name.Name {
			case "PhonemizeWithProsody", "PhonemizeWithLanguage", "PhonemizeEmbeddedEnglish":
			default:
				continue
			}
			label := name + ":" + receiverName(fn) + "." + fn.Name.Name
			methods = append(methods, label)
			if !callsStripControlChars(fn.Body) {
				missing = append(missing, label)
			}
		}
	}
	if len(methods) < 11 {
		t.Fatalf("found only %d phonemizer methods: %v", len(methods), methods)
	}
	sort.Strings(missing)
	if len(missing) > 0 {
		t.Errorf("these methods do not call StripControlChars:\n  %s", strings.Join(missing, "\n  "))
	}
}

func receiverName(fn *ast.FuncDecl) string {
	expr := fn.Recv.List[0].Type
	if star, ok := expr.(*ast.StarExpr); ok {
		expr = star.X
	}
	if id, ok := expr.(*ast.Ident); ok {
		return id.Name
	}
	return "?"
}

func callsStripControlChars(body *ast.BlockStmt) bool {
	found := false
	ast.Inspect(body, func(n ast.Node) bool {
		if call, ok := n.(*ast.CallExpr); ok {
			if id, ok := call.Fun.(*ast.Ident); ok && id.Name == "StripControlChars" {
				found = true
			}
		}
		return !found
	})
	return found
}

// The English run between Chinese text is read as pinyin; a NUL inside
// "Python" split it into two runs and the letters were spelled out.
func TestInputSanitize_ChineseEmbeddedEnglish(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, err := LoadLoanwordData()
	if err != nil {
		t.Fatal(err)
	}
	clean := cp.PhonemizeEmbeddedEnglish("Python", data)
	if len(clean) == 0 {
		t.Fatal("Python has no loanword reading")
	}
	for _, dirty := range []string{"Py\x00thon", "\x07Python\x1b", "Pyth\u009fon"} {
		if got := cp.PhonemizeEmbeddedEnglish(dirty, data); !reflect.DeepEqual(got, clean) {
			t.Errorf("PhonemizeEmbeddedEnglish(%q) = %v, want %v", dirty, got, clean)
		}
	}
}

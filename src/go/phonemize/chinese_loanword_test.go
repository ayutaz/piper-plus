// ZH-EN code-switching unit tests (TICKET-02 G5, mirror of TICKET-01 R5).

package phonemize

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestLoadLoanwordData(t *testing.T) {
	data, err := LoadLoanwordData()
	if err != nil {
		t.Fatalf("LoadLoanwordData: %v", err)
	}
	if data.Version != 1 {
		t.Errorf("version = %d, want 1", data.Version)
	}
	if len(data.Acronyms) < 60 {
		t.Errorf("acronyms count = %d, want >= 60", len(data.Acronyms))
	}
	if len(data.Loanwords) < 35 {
		t.Errorf("loanwords count = %d, want >= 35", len(data.Loanwords))
	}
	if len(data.LetterFallback) != 26 {
		t.Errorf("letter_fallback count = %d, want 26", len(data.LetterFallback))
	}
}

func TestLoadLoanwordData_OnceOnly(t *testing.T) {
	d1, err1 := LoadLoanwordData()
	d2, err2 := LoadLoanwordData()
	if err1 != nil || err2 != nil {
		t.Fatalf("errors: %v, %v", err1, err2)
	}
	if d1 != d2 {
		t.Error("LoadLoanwordData should return the same pointer (sync.Once)")
	}
}

func TestPhonemizeEmbeddedEnglish_AcronymGPS(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	tokens := cp.PhonemizeEmbeddedEnglish("GPS", data)
	// ji4(3) + pi4(3) + ai1(2 zero initial) + si4(3) = 11
	if len(tokens) != 11 {
		t.Errorf("GPS token count = %d, want 11; tokens=%v", len(tokens), tokens)
	}
}

func TestPhonemizeEmbeddedEnglish_LoanwordPython(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	tokens := cp.PhonemizeEmbeddedEnglish("Python", data)
	// pai4(3) + sen1(3) = 6
	if len(tokens) != 6 {
		t.Errorf("Python token count = %d, want 6; tokens=%v", len(tokens), tokens)
	}
}

func TestPhonemizeEmbeddedEnglish_ChatGPT(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	tokens := cp.PhonemizeEmbeddedEnglish("ChatGPT", data)
	// 5 syllables × 3 = 15
	if len(tokens) != 15 {
		t.Errorf("ChatGPT token count = %d, want 15; tokens=%v", len(tokens), tokens)
	}
}

func TestPhonemizeEmbeddedEnglish_LetterFallback(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	zz := cp.PhonemizeEmbeddedEnglish("ZZ", data)
	z := cp.PhonemizeEmbeddedEnglish("Z", data)
	if len(zz) != len(z)*2 {
		t.Errorf("ZZ length = %d, want %d (2 × Z)", len(zz), len(z)*2)
	}
}

func TestPhonemizeEmbeddedEnglish_Empty(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	if got := cp.PhonemizeEmbeddedEnglish("", data); len(got) != 0 {
		t.Errorf("empty input got %d tokens, want 0", len(got))
	}
	if got := cp.PhonemizeEmbeddedEnglish("   ", data); len(got) != 0 {
		t.Errorf("whitespace input got %d tokens, want 0", len(got))
	}
	if got := cp.PhonemizeEmbeddedEnglish(",.!?", data); len(got) != 0 {
		t.Errorf("punctuation input got %d tokens, want 0", len(got))
	}
}

func TestLookupPriority_LoanwordBeatsAcronym(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data := &LoanwordData{
		Loanwords:      map[string][]string{"AI": {"ma1"}},
		Acronyms:       map[string][]string{"AI": {"ji4"}},
		LetterFallback: map[string][]string{},
	}
	got := cp.PhonemizeEmbeddedEnglish("AI", data)
	loanOnly := cp.PhonemizeEmbeddedEnglish("AI", &LoanwordData{
		Loanwords:      map[string][]string{"AI": {"ma1"}},
		Acronyms:       map[string][]string{},
		LetterFallback: map[string][]string{},
	})
	if !equalSlices(got, loanOnly) {
		t.Errorf("loanword path = %v, want loan-only %v", got, loanOnly)
	}
}

func TestLookupPriority_AcronymBeatsFallback(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data := &LoanwordData{
		Loanwords:      map[string][]string{},
		Acronyms:       map[string][]string{"ZX": {"ma1"}},
		LetterFallback: map[string][]string{"Z": {"zi4"}, "X": {"ai4"}},
	}
	got := cp.PhonemizeEmbeddedEnglish("ZX", data)
	// Acronym: 1 syllable -> ~3 IPA. Letter fallback would be 2 syllables -> ~6.
	if len(got) >= 6 {
		t.Errorf("acronym path produced %d tokens, expected fewer than letter-fallback (6)", len(got))
	}
}

func TestCaseSensitivity_PythonVsPYTHON(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	lower := cp.PhonemizeEmbeddedEnglish("Python", data)
	upper := cp.PhonemizeEmbeddedEnglish("PYTHON", data)
	if len(lower) == 0 || len(upper) == 0 {
		t.Fatal("expected non-empty outputs for both cases")
	}
	if equalSlices(lower, upper) {
		t.Error("Python and PYTHON should differ (case-sensitive loanword vs fallback)")
	}
}

func TestPunctuation_TrailingComma(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoanwordData_orPanic(t)
	plain := cp.PhonemizeEmbeddedEnglish("GPS", data)
	for _, suffix := range []string{",", ".", "!", ":"} {
		got := cp.PhonemizeEmbeddedEnglish("GPS"+suffix, data)
		if !equalSlices(plain, got) {
			t.Errorf("GPS%s = %v, want %v", suffix, got, plain)
		}
	}
}

func TestMultiSegment_TwoEmbeddedEn(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	combined := cp.PhonemizeEmbeddedEnglish("ChatGPT 和 Python", data)
	chatgpt := cp.PhonemizeEmbeddedEnglish("ChatGPT", data)
	python := cp.PhonemizeEmbeddedEnglish("Python", data)
	if len(combined) != len(chatgpt)+len(python) {
		t.Errorf("ChatGPT 和 Python length = %d, want %d", len(combined), len(chatgpt)+len(python))
	}
}

func TestDigits_Z2Z9EqualsZZ(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data, _ := LoadLoanwordData()
	z2z9 := cp.PhonemizeEmbeddedEnglish("Z2Z9", data)
	zz := cp.PhonemizeEmbeddedEnglish("ZZ", data)
	if !equalSlices(z2z9, zz) {
		t.Errorf("Z2Z9 = %v, want ZZ %v", z2z9, zz)
	}
}

func TestAcronymWithDigits_MP3(t *testing.T) {
	cp := &ChinesePhonemizer{}
	data := &LoanwordData{
		Loanwords:      map[string][]string{},
		Acronyms:       map[string][]string{"MP3": {"ai1"}},
		LetterFallback: map[string][]string{"M": {"ai1", "mu5"}, "P": {"pi4"}},
	}
	got := cp.PhonemizeEmbeddedEnglish("MP3", data)
	acronymOnly := cp.PhonemizeEmbeddedEnglish("MP3", &LoanwordData{
		Loanwords:      map[string][]string{},
		Acronyms:       map[string][]string{"MP3": {"ai1"}},
		LetterFallback: map[string][]string{},
	})
	if !equalSlices(got, acronymOnly) {
		t.Errorf("MP3 = %v, acronym-only path = %v", got, acronymOnly)
	}
}

func TestValidate_InvalidSchemaListType(t *testing.T) {
	bad := []byte(`{"version": 1, "acronyms": {"GPS": "not_a_list"}}`)
	_, err := LoadLoanwordDataFromBytes("test.json", bad)
	if err == nil {
		t.Fatal("expected error for non-list value")
	}
	if !strings.Contains(err.Error(), "'acronyms.GPS'") {
		t.Errorf("error %v does not name section.key", err)
	}
	if !strings.Contains(err.Error(), "must be list[str]") {
		t.Errorf("error %v missing 'must be list[str]'", err)
	}
}

func TestValidate_InvalidSchemaSection(t *testing.T) {
	bad := []byte(`{"version": 1, "acronyms": "not_a_dict"}`)
	_, err := LoadLoanwordDataFromBytes("test.json", bad)
	if err == nil {
		t.Fatal("expected error for non-dict section")
	}
	if !strings.Contains(err.Error(), "'acronyms'") {
		t.Errorf("error %v missing 'acronyms'", err)
	}
	if !strings.Contains(err.Error(), "must be a mapping") {
		t.Errorf("error %v missing 'must be a mapping'", err)
	}
}

func TestLoaderAcceptsUnknownFieldsInSchemaV2(t *testing.T) {
	// YELLOW-5: unknown top-level fields in a future schema_version: 2 must
	// not break this loader. encoding/json default behaviour is to ignore
	// unknown fields; this test pins that contract.
	v2 := []byte(`{
		"version": 2,
		"schema_version": 2,
		"metadata": {"experimental": true},
		"acronyms": {"GPS": ["ji4"]},
		"loanwords": {"Python": ["pai4"]},
		"letter_fallback": {"A": ["ei1"]},
		"tone_overrides": {"GPS": "high"}
	}`)
	data, err := LoadLoanwordDataFromBytes("future_v2.json", v2)
	if err != nil {
		t.Fatalf("forward-compat loader rejected v2: %v", err)
	}
	if data.Version != 2 {
		t.Errorf("version = %d, want 2", data.Version)
	}
	if _, ok := data.Acronyms["GPS"]; !ok {
		t.Error("GPS acronym not loaded")
	}
}

// Review feedback C-1: a future “schema_version: 2“ manifest may legitimately
// drop the legacy “version“ field. The loader must accept that, falling back
// to “schema_version“ (and silently to 1 if neither is present) so the
// runtime stays in sync with Rust / Python / C# / C++ peers.
func TestLoaderForwardCompat_VersionAbsent_UsesSchemaVersion(t *testing.T) {
	noVersion := []byte(`{
		"schema_version": 2,
		"metadata": {"experimental": true},
		"acronyms": {"GPS": ["ji4"]},
		"loanwords": {"Python": ["pai4"]},
		"letter_fallback": {"A": ["ei1"]}
	}`)
	data, err := LoadLoanwordDataFromBytes("future_no_version.json", noVersion)
	if err != nil {
		t.Fatalf("loader rejected schema_version-only manifest: %v", err)
	}
	if data.Version != 2 {
		t.Errorf("version = %d, want 2 (from schema_version fallback)", data.Version)
	}
	if _, ok := data.Acronyms["GPS"]; !ok {
		t.Error("GPS acronym not loaded")
	}
}

func TestLoaderForwardCompat_NeitherVersionNorSchemaVersion_DefaultsToOne(t *testing.T) {
	noVersionField := []byte(`{
		"acronyms": {"GPS": ["ji4"]},
		"loanwords": {"Python": ["pai4"]},
		"letter_fallback": {"A": ["ei1"]}
	}`)
	data, err := LoadLoanwordDataFromBytes("no_version.json", noVersionField)
	if err != nil {
		t.Fatalf("loader rejected manifest without any version field: %v", err)
	}
	if data.Version != 1 {
		t.Errorf("version = %d, want 1 (default)", data.Version)
	}
}

func TestEmbedConsistency(t *testing.T) {
	// The embedded JSON must contain canonical keys.
	raw, err := loanwordFS.ReadFile("data/zh_en_loanword.json")
	if err != nil {
		t.Fatalf("read embed: %v", err)
	}
	for _, key := range []string{`"GPS"`, `"Python"`, `"ChatGPT"`} {
		if !strings.Contains(string(raw), key) {
			t.Errorf("embed missing %s", key)
		}
	}
}

// --- helpers ---

func equalSlices(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func LoanwordData_orPanic(t *testing.T) (*LoanwordData, error) {
	t.Helper()
	d, err := LoadLoanwordData()
	if err != nil {
		t.Fatal(err)
	}
	return d, nil
}

// --- Multilingual dispatch integration tests (TICKET-02 G3) ---

// makeZhEnDispatchPhonemizer creates a multilingual phonemizer with a real
// ChinesePhonemizer (empty dicts — embedded en path doesn't need them) and a
// stub English phonemizer (character-level passthrough) so the dispatch logic
// can be exercised without loading 20K-entry dictionaries.
func makeZhEnDispatchPhonemizer() *MultilingualPhonemizer {
	zh := &ChinesePhonemizer{}
	en := &stubEnglishPhonemizer{}
	return NewMultilingualPhonemizer(
		[]string{"zh", "en"}, "en",
		map[string]Phonemizer{"zh": zh, "en": en},
	)
}

// stubEnglishPhonemizer emits character-level tokens for any input.
type stubEnglishPhonemizer struct{}

func (s *stubEnglishPhonemizer) LanguageCode() string { return "en" }
func (s *stubEnglishPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	var tokens []string
	var prosody []*ProsodyInfo
	for _, r := range text {
		tokens = append(tokens, string(r))
		prosody = append(prosody, nil)
	}
	return &PhonemizeResult{Tokens: tokens, Prosody: prosody, EOSToken: "$"}, nil
}

func TestZhEnDispatch_DefaultEnabled(t *testing.T) {
	mp := makeZhEnDispatchPhonemizer()
	if !mp.IsZhEnDispatchEnabled() {
		t.Error("expected zh-en dispatch enabled by default when both zh+en registered")
	}
}

func TestZhEnDispatch_DisabledWhenNoEn(t *testing.T) {
	zh := &ChinesePhonemizer{}
	mp := NewMultilingualPhonemizer(
		[]string{"zh"}, "zh",
		map[string]Phonemizer{"zh": zh},
	)
	if mp.IsZhEnDispatchEnabled() {
		t.Error("expected zh-en dispatch disabled when only zh is registered")
	}
}

func TestZhEnDispatch_PatternZhEnZh(t *testing.T) {
	mp := makeZhEnDispatchPhonemizer()
	// 你好 GPS 世界 — embedded English routes through loanword path.
	// stub English would produce tokens like ["G", "P", "S"]; the
	// loanword path produces PUA-mapped pinyin IPA tokens.
	result, err := mp.PhonemizeWithProsody("你好 GPS 世界")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody: %v", err)
	}
	puaCount := 0
	for _, tok := range result.Tokens {
		for _, r := range tok {
			if r >= 0xE020 && r <= 0xE04A {
				puaCount++
				break
			}
		}
	}
	if puaCount == 0 {
		t.Errorf("expected PUA tone markers from loanword path; got %v", result.Tokens)
	}
}

func TestZhEnDispatch_DisabledFallsThrough(t *testing.T) {
	mp := makeZhEnDispatchPhonemizer()
	mp.SetZhEnDispatch(false)
	result, err := mp.PhonemizeWithProsody("你好 GPS")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody: %v", err)
	}
	puaCount := 0
	for _, tok := range result.Tokens {
		for _, r := range tok {
			if r >= 0xE020 && r <= 0xE04A {
				puaCount++
				break
			}
		}
	}
	if puaCount != 0 {
		t.Errorf("dispatch disabled: expected 0 loanword PUA markers, got %d in %v", puaCount, result.Tokens)
	}
}

func TestZhEnDispatch_PureZhUnaffected(t *testing.T) {
	mp := makeZhEnDispatchPhonemizer()
	result, err := mp.PhonemizeWithProsody("你好世界")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody: %v", err)
	}
	// Pure ZH must NOT introduce loanword PUA markers (0xE020-0xE04A) —
	// those are reserved for the ZH-EN code-switching pinyin path. If they
	// appear here it means the dispatch is firing on pure ZH input.
	puaCount := 0
	for _, tok := range result.Tokens {
		for _, r := range tok {
			if r >= 0xE020 && r <= 0xE04A {
				puaCount++
				break
			}
		}
	}
	if puaCount != 0 {
		t.Errorf("pure ZH input introduced %d loanword PUA marker(s) in %v",
			puaCount, result.Tokens)
	}
}

func TestZhEnDispatch_PureEnUnaffected(t *testing.T) {
	mp := makeZhEnDispatchPhonemizer()
	result, err := mp.PhonemizeWithProsody("Hello GPS world")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody: %v", err)
	}
	// Pure en — no zh segment, dispatch doesn't fire. stub produces
	// character-level tokens. No PUA codepoints expected.
	puaCount := 0
	for _, tok := range result.Tokens {
		for _, r := range tok {
			if r >= 0xE020 && r <= 0xE04A {
				puaCount++
				break
			}
		}
	}
	if puaCount != 0 {
		t.Errorf("pure en: expected 0 PUA markers, got %d", puaCount)
	}
}

// =========================================================================
// CI-C1: cross-runtime fixture matrix consumer (Go side).
//
// `testdata/zh_en_loanword_matrix.json` is mirrored from
// `tests/fixtures/g2p/zh_en_loanword_matrix.json` by the JSON sync gate.
// Until this consumer landed the file had no test depending on it in the Go
// runtime, so a drift between the matrix and the implementation would have
// gone unnoticed. Mirrors `test_fixture_matrix_loadable_and_well_formed` in
// piper-core (Rust).
//
// Strict per-case checks (review feedback G-M2): every case with both
// ``input`` and ``expected_token_count`` MUST match exactly. The previous
// "log-only" form let drift rot silently. If a counting convention legitimately
// changes, update the matrix in ``tests/fixtures/g2p/`` and re-sync via
// ``python scripts/check_loanword_consistency.py --fix``.
// =========================================================================

func TestFixtureMatrixLoadable(t *testing.T) {
	type matrixCase struct {
		Name               string  `json:"name"`
		Input              *string `json:"input,omitempty"`
		ExpectedTokenCount *int    `json:"expected_token_count,omitempty"`
	}
	type matrix struct {
		SchemaVersion int          `json:"schema_version"`
		Cases         []matrixCase `json:"cases"`
	}

	raw, err := os.ReadFile("testdata/zh_en_loanword_matrix.json")
	if err != nil {
		t.Fatalf("matrix not found: %v", err)
	}
	var m matrix
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("matrix is not valid JSON: %v", err)
	}
	if len(m.Cases) == 0 {
		t.Fatal("matrix `cases` must be non-empty")
	}
	for _, c := range m.Cases {
		if c.Name == "" {
			t.Errorf("case missing `name`: %+v", c)
		}
	}

	cp := &ChinesePhonemizer{}
	data, err := LoadLoanwordData()
	if err != nil {
		t.Fatalf("LoadLoanwordData: %v", err)
	}

	total := 0
	for _, c := range m.Cases {
		if c.Input == nil || c.ExpectedTokenCount == nil {
			// Loader-only / equivalence cases don't have direct counts.
			continue
		}
		tokens := cp.PhonemizeEmbeddedEnglish(*c.Input, data)
		total++
		if len(tokens) != *c.ExpectedTokenCount {
			t.Errorf(
				"matrix case %q (input=%q): expected_token_count=%d, got %d (tokens=%v)\n"+
					"  → if this is intentional, update tests/fixtures/g2p/zh_en_loanword_matrix.json "+
					"and re-sync via `python scripts/check_loanword_consistency.py --fix`",
				c.Name, *c.Input, *c.ExpectedTokenCount, len(tokens), tokens,
			)
		}
	}
	if total == 0 {
		t.Fatal("no cases had `expected_token_count` — matrix is stale")
	}
}

package phonemize

import (
	"reflect"
	"strings"
	"testing"
)

// =========================================================================
// Test helpers
// =========================================================================

// mockEngine implements JapaneseG2PEngine for testing.
type mockEngine struct {
	labels []string
}

func (m *mockEngine) ExtractFullcontext(_ string) ([]string, error) {
	return m.labels, nil
}

// =========================================================================
// 1. getQuestionType — question type detection
// =========================================================================

func TestGetQuestionType_Basic(t *testing.T) {
	tests := []struct {
		name string
		text string
		want string
	}{
		// Declarative
		{"declarative_plain", "こんにちは", "$"},
		{"declarative_period", "こんにちは。", "$"},
		{"declarative_empty", "", "$"},
		{"declarative_whitespace", "   ", "$"},

		// Generic question — ASCII
		{"question_ascii", "これは何?", "?"},
		{"question_ascii_space", "これは何? ", "?"},

		// Generic question — fullwidth
		{"question_fullwidth", "これは何？", "?"},
		{"question_fullwidth_space", "  これは何？  ", "?"},

		// Emphatic question ?!
		{"emphatic_ascii", "何だって?!", "?!"},
		{"emphatic_fw_excl_q", "何だって！？", "?!"},
		{"emphatic_fw_q_excl", "何だって？！", "?!"},

		// Neutral/rhetorical question ?.
		{"neutral_ascii", "そうなの?.", "?."},
		{"neutral_fw_period_q", "そうなの。？", "?."},
		{"neutral_fw_q_period", "そうなの？。", "?."},

		// Tag question ?~
		{"tag_ascii", "いいよね?~", "?~"},
		{"tag_fw_tilde_q", "いいよね～？", "?~"},
		{"tag_fw_q_tilde", "いいよね？～", "?~"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := getQuestionType(tc.text)
			if got != tc.want {
				t.Errorf("getQuestionType(%q) = %q, want %q", tc.text, got, tc.want)
			}
		})
	}
}

// Python: _get_question_type returns same results — cross-verified
func TestGetQuestionType_PythonParity(t *testing.T) {
	// These pairs are taken from Python test expectations.
	pairs := map[string]string{
		"こんにちは？":     "?",
		"本当？！":       "?!",
		"いいね？。":      "?.",
		"そうだね？～":     "?~",
		"こんにちは":      "$",
		"Hello?":     "?",
		"Really?!":   "?!",
		"Right?~":    "?~",
		"Hmm?.":      "?.",
		"Statement.": "$",
	}
	for text, want := range pairs {
		got := getQuestionType(text)
		if got != want {
			t.Errorf("getQuestionType(%q) = %q, want %q (Python parity)", text, got, want)
		}
	}
}

// Ensure priority: multi-char patterns match before single "?"
func TestGetQuestionType_Priority(t *testing.T) {
	// "?!" should NOT match as generic "?" — the multi-char check must come first.
	got := getQuestionType("test?!")
	if got != "?!" {
		t.Errorf("priority: getQuestionType(\"test?!\") = %q, want \"?!\"", got)
	}
	got = getQuestionType("test?.")
	if got != "?." {
		t.Errorf("priority: getQuestionType(\"test?.\") = %q, want \"?.\"", got)
	}
	got = getQuestionType("test?~")
	if got != "?~" {
		t.Errorf("priority: getQuestionType(\"test?~\") = %q, want \"?~\"", got)
	}
}

// =========================================================================
// 2. applyNPhonemeRules — context-dependent N phoneme variants
// =========================================================================

func TestApplyNPhonemeRules_Bilabial(t *testing.T) {
	// N before bilabials: m, my, b, by, p, py -> N_m
	bilabials := []string{"m", "my", "b", "by", "p", "py"}
	for _, next := range bilabials {
		input := []string{"a", "N", next, "a"}
		got := applyNPhonemeRules(input)
		if got[1] != "N_m" {
			t.Errorf("N before %q: got %q, want N_m", next, got[1])
		}
	}
}

func TestApplyNPhonemeRules_Alveolar(t *testing.T) {
	// N before alveolars: n, ny, t, ty, d, dy, ts, ch -> N_n
	alveolarPhonemes := []string{"n", "ny", "t", "ty", "d", "dy", "ts", "ch"}
	for _, next := range alveolarPhonemes {
		input := []string{"a", "N", next, "a"}
		got := applyNPhonemeRules(input)
		if got[1] != "N_n" {
			t.Errorf("N before %q: got %q, want N_n", next, got[1])
		}
	}
}

func TestApplyNPhonemeRules_Velar(t *testing.T) {
	// N before velars: k, ky, kw, g, gy, gw -> N_ng
	velarPhonemes := []string{"k", "ky", "kw", "g", "gy", "gw"}
	for _, next := range velarPhonemes {
		input := []string{"a", "N", next, "a"}
		got := applyNPhonemeRules(input)
		if got[1] != "N_ng" {
			t.Errorf("N before %q: got %q, want N_ng", next, got[1])
		}
	}
}

func TestApplyNPhonemeRules_Uvular(t *testing.T) {
	// N before vowels -> N_uvular
	vowels := []string{"a", "i", "u", "e", "o"}
	for _, next := range vowels {
		input := []string{"k", "N", next}
		got := applyNPhonemeRules(input)
		if got[1] != "N_uvular" {
			t.Errorf("N before vowel %q: got %q, want N_uvular", next, got[1])
		}
	}

	// N at end -> N_uvular
	input := []string{"k", "o", "N"}
	got := applyNPhonemeRules(input)
	if got[2] != "N_uvular" {
		t.Errorf("N at end: got %q, want N_uvular", got[2])
	}

	// N before other consonants (s, h, w, etc.) -> N_uvular
	others := []string{"s", "sh", "h", "hy", "w", "y", "r", "ry", "z", "j", "f", "v"}
	for _, next := range others {
		input := []string{"a", "N", next, "a"}
		got := applyNPhonemeRules(input)
		if got[1] != "N_uvular" {
			t.Errorf("N before %q: got %q, want N_uvular", next, got[1])
		}
	}
}

func TestApplyNPhonemeRules_SkipTokens(t *testing.T) {
	// N should look through prosody/boundary tokens to find the next phoneme.
	skip := []string{"_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"}
	for _, sk := range skip {
		input := []string{"a", "N", sk, "b", "a"}
		got := applyNPhonemeRules(input)
		if got[1] != "N_m" {
			t.Errorf("N skip %q then b: got %q, want N_m", sk, got[1])
		}
	}
}

func TestApplyNPhonemeRules_MultipleSkipTokens(t *testing.T) {
	// N followed by multiple skip tokens then a velar
	input := []string{"a", "N", "#", "[", "k", "a"}
	got := applyNPhonemeRules(input)
	if got[1] != "N_ng" {
		t.Errorf("N with multiple skips before k: got %q, want N_ng", got[1])
	}
}

func TestApplyNPhonemeRules_NFollowedByOnlySkipTokens(t *testing.T) {
	// N followed only by skip tokens -> N_uvular (end of phrase)
	input := []string{"a", "N", "#", "$"}
	got := applyNPhonemeRules(input)
	if got[1] != "N_uvular" {
		t.Errorf("N followed by only skip tokens: got %q, want N_uvular", got[1])
	}
}

func TestApplyNPhonemeRules_MultipleN(t *testing.T) {
	// Two N tokens in same sequence
	input := []string{"a", "N", "b", "a", "N", "k", "a"}
	got := applyNPhonemeRules(input)
	if got[1] != "N_m" {
		t.Errorf("first N: got %q, want N_m", got[1])
	}
	if got[4] != "N_ng" {
		t.Errorf("second N: got %q, want N_ng", got[4])
	}
}

func TestApplyNPhonemeRules_NoN(t *testing.T) {
	// No N in input — should be unchanged.
	input := []string{"k", "o", "n", "n", "i", "ch", "i", "w", "a"}
	got := applyNPhonemeRules(input)
	if !reflect.DeepEqual(got, input) {
		t.Errorf("no N: got %v, want %v", got, input)
	}
}

func TestApplyNPhonemeRules_TokenCountPreserved(t *testing.T) {
	// The N replacement is 1-to-1, so token count must stay the same.
	input := []string{"^", "k", "o", "N", "#", "b", "a", "N", "$"}
	got := applyNPhonemeRules(input)
	if len(got) != len(input) {
		t.Errorf("token count changed: got %d, want %d", len(got), len(input))
	}
}

// Cross-check against Python implementation's classification tables
func TestApplyNPhonemeRules_PythonParity_AllPhonemes(t *testing.T) {
	// Exhaustive list matching Python's _apply_n_phoneme_rules classification
	// bilabial: m, my, b, by, p, py
	// alveolar: n, ny, t, ty, d, dy, ts, ch
	// velar: k, ky, kw, g, gy, gw
	// all others: uvular
	pythonClassification := map[string]string{
		// Bilabial -> N_m
		"m": "N_m", "my": "N_m", "b": "N_m", "by": "N_m", "p": "N_m", "py": "N_m",
		// Alveolar -> N_n
		"n": "N_n", "ny": "N_n", "t": "N_n", "ty": "N_n",
		"d": "N_n", "dy": "N_n", "ts": "N_n", "ch": "N_n",
		// Velar -> N_ng
		"k": "N_ng", "ky": "N_ng", "kw": "N_ng",
		"g": "N_ng", "gy": "N_ng", "gw": "N_ng",
		// Vowels -> N_uvular
		"a": "N_uvular", "i": "N_uvular", "u": "N_uvular",
		"e": "N_uvular", "o": "N_uvular",
		// Others -> N_uvular
		"s": "N_uvular", "sh": "N_uvular", "z": "N_uvular", "j": "N_uvular",
		"zy": "N_uvular", "h": "N_uvular", "hy": "N_uvular", "f": "N_uvular",
		"w": "N_uvular", "y": "N_uvular", "r": "N_uvular", "ry": "N_uvular",
		"v": "N_uvular", "cl": "N_uvular", "q": "N_uvular",
		// Unvoiced vowels -> N_uvular
		"A": "N_uvular", "I": "N_uvular", "U": "N_uvular",
		"E": "N_uvular", "O": "N_uvular",
	}
	for phoneme, want := range pythonClassification {
		input := []string{"a", "N", phoneme}
		got := applyNPhonemeRules(input)
		if got[1] != want {
			t.Errorf("Python parity: N before %q -> got %q, want %q", phoneme, got[1], want)
		}
	}
}

// =========================================================================
// 3. labelsToTokensWithProsody — Kurihara method label conversion
// =========================================================================

// Simulated OpenJTalk fullcontext label for "こんにちは" (konnichiwa).
// Simplified labels that exercise the Kurihara BOS/EOS, prosody marks, and N handling.
func TestLabelsToTokensWithProsody_BasicDeclarative(t *testing.T) {
	// Minimal label set: sil -> k -> o -> sil
	// This tests BOS (^), phoneme extraction, and EOS ($).
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx", // sil at start
		"xx^xx-k+o=xx/A:0+2+3/B:xx-xx_xx/C:xx_xx+xx",       // k phoneme
		"xx^xx-o+N=xx/A:0+3+3/B:xx-xx_xx/C:xx_xx+xx",       // o phoneme
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx", // sil at end
	}
	result, err := labelsToTokensWithProsody(labels, "こんにちは")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Expect: "^", "k", "o", "$"
	// (After MapSequence, single-char tokens are unchanged)
	if result.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want \"$\"", result.EOSToken)
	}

	// First token should be ^ (BOS), last should be $ (EOS)
	if len(result.Tokens) < 2 {
		t.Fatalf("too few tokens: %v", result.Tokens)
	}
	if result.Tokens[0] != "^" {
		t.Errorf("first token = %q, want \"^\"", result.Tokens[0])
	}
	if result.Tokens[len(result.Tokens)-1] != "$" {
		t.Errorf("last token = %q, want \"$\"", result.Tokens[len(result.Tokens)-1])
	}
}

func TestLabelsToTokensWithProsody_QuestionMark(t *testing.T) {
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:0+1+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "これは？")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != "?" {
		t.Errorf("EOSToken = %q, want \"?\"", result.EOSToken)
	}
	// Last token should be "?" (generic question)
	last := result.Tokens[len(result.Tokens)-1]
	if last != "?" {
		t.Errorf("last token = %q, want \"?\"", last)
	}
}

func TestLabelsToTokensWithProsody_PauInsertion(t *testing.T) {
	// Test that "pau" labels become "_" tokens.
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:0+1+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-pau+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx", // pau
		"xx^xx-o+sil=xx/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト。テスト。")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	found := false
	for _, tok := range result.Tokens {
		if tok == "_" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected \"_\" (pau) in tokens, got %v", result.Tokens)
	}
}

func TestLabelsToTokensWithProsody_ProsodyAlignment(t *testing.T) {
	// Tokens and Prosody arrays must be the same length.
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:0+1+3/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-o+N=xx/A:0+2+3/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-N+n=xx/A:0+3+3/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != len(result.Prosody) {
		t.Errorf("Tokens length (%d) != Prosody length (%d)",
			len(result.Tokens), len(result.Prosody))
	}
}

func TestLabelsToTokensWithProsody_ProsodyValues(t *testing.T) {
	// Test that A1/A2/A3 values are correctly extracted.
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:-2+1+5/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Find the phoneme token "k" and check its prosody
	for i, tok := range result.Tokens {
		if tok != "k" {
			continue
		}
		p := result.Prosody[i]
		if p == nil {
			t.Fatal("prosody for 'k' is nil, expected non-nil")
		}
		if p.A1 != -2 {
			t.Errorf("A1 for 'k' = %d, want -2", p.A1)
		}
		if p.A2 != 1 {
			t.Errorf("A2 for 'k' = %d, want 1", p.A2)
		}
		if p.A3 != 5 {
			t.Errorf("A3 for 'k' = %d, want 5", p.A3)
		}
		return
	}
	t.Error("phoneme 'k' not found in tokens")
}

// =========================================================================
// 4. Kurihara prosody mark insertion (], #, [)
// =========================================================================

func TestLabelsToTokensWithProsody_AccentNucleus(t *testing.T) {
	// "]" is inserted when a1==0 and a2_next == a2+1
	// This simulates: phoneme at position a2=2 with a1=0, next phoneme at a2=3
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:0+2+4/B:xx-xx_xx/C:xx_xx+xx", // a1=0, a2=2
		"xx^xx-o+n=xx/A:1+3+4/B:xx-xx_xx/C:xx_xx+xx", // a2_next=3 == 2+1 -> insert "]"
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	found := false
	for _, tok := range result.Tokens {
		if tok == "]" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected \"]\" (accent nucleus) in tokens %v", result.Tokens)
	}
}

func TestLabelsToTokensWithProsody_PhraseBoundary(t *testing.T) {
	// "#" is inserted when a2==a3 and a2_next==1
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:1+3+3/B:xx-xx_xx/C:xx_xx+xx", // a2=3, a3=3
		"xx^xx-o+n=xx/A:0+1+2/B:xx-xx_xx/C:xx_xx+xx", // a2_next=1 -> insert "#"
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	found := false
	for _, tok := range result.Tokens {
		if tok == "#" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected \"#\" (phrase boundary) in tokens %v", result.Tokens)
	}
}

func TestLabelsToTokensWithProsody_RisingPitch(t *testing.T) {
	// "[" is inserted when a2==1 and a2_next==2
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:1+1+3/B:xx-xx_xx/C:xx_xx+xx", // a2=1
		"xx^xx-o+n=xx/A:0+2+3/B:xx-xx_xx/C:xx_xx+xx", // a2_next=2 -> insert "["
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	found := false
	for _, tok := range result.Tokens {
		if tok == "[" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected \"[\" (rising pitch) in tokens %v", result.Tokens)
	}
}

// =========================================================================
// 5. N phoneme + MapSequence integration
// =========================================================================

func TestLabelsToTokensWithProsody_NPhonemeIntegration(t *testing.T) {
	// Test that N in labels is converted to N_variant after applyNPhonemeRules,
	// and then PUA-mapped by MapSequence.
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:0+1+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-o+N=xx/A:0+2+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-N+b=xx/A:0+1+2/B:xx-xx_xx/C:xx_xx+xx", // N followed by b -> N_m
		"xx^xx-b+a=xx/A:0+2+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// The N should have been replaced with N_m and PUA-mapped to U+E019
	nmPUA := string(rune(0xE019))
	found := false
	for _, tok := range result.Tokens {
		if tok == nmPUA {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected PUA-mapped N_m (U+E019) in tokens, got %v", result.Tokens)
	}

	// Original "N" should NOT appear (it was replaced)
	for _, tok := range result.Tokens {
		if tok == "N" {
			t.Errorf("unreplaced \"N\" found in tokens after N phoneme rules: %v", result.Tokens)
		}
	}
}

// =========================================================================
// 6. Edge cases
// =========================================================================

func TestLabelsToTokensWithProsody_EmptyLabels(t *testing.T) {
	result, err := labelsToTokensWithProsody(nil, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("empty labels should produce empty tokens, got %v", result.Tokens)
	}
}

func TestLabelsToTokensWithProsody_OnlySilLabels(t *testing.T) {
	// Two sil labels (BOS + EOS) with no phonemes in between
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 2 {
		t.Errorf("expected 2 tokens (^ and $), got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "^" {
		t.Errorf("first token = %q, want \"^\"", result.Tokens[0])
	}
	if result.Tokens[1] != "$" {
		t.Errorf("second token = %q, want \"$\"", result.Tokens[1])
	}
}

func TestLabelsToTokensWithProsody_NoMatchingPhonemeRegex(t *testing.T) {
	// Labels that don't match the phoneme regex are skipped
	labels := []string{
		"no_match_here",
		"another_no_match",
	}
	result, err := labelsToTokensWithProsody(labels, "test")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("unmatched labels should produce empty tokens, got %v", result.Tokens)
	}
}

func TestLabelsToTokensWithProsody_MissingA1A2A3(t *testing.T) {
	// Phoneme label without A1/A2/A3 — should still extract phoneme, prosody=nil
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/B:xx-xx_xx/C:xx_xx+xx", // missing /A: field
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should still have the phoneme "k"
	foundK := false
	for i, tok := range result.Tokens {
		if tok == "k" {
			foundK = true
			if result.Prosody[i] != nil {
				t.Errorf("prosody for 'k' without A-fields should be nil, got %+v", result.Prosody[i])
			}
		}
	}
	if !foundK {
		t.Error("phoneme 'k' not found despite being in label")
	}
}

// =========================================================================
// 7. PUA mapping integration — verifying Go matches Python
// =========================================================================

func TestPUAMapping_JapaneseSpecialTokens(t *testing.T) {
	// Verify that all Japanese-specific PUA mappings match Python's FIXED_PUA_MAPPING
	pythonPUA := map[string]rune{
		"a:":       0xE000,
		"i:":       0xE001,
		"u:":       0xE002,
		"e:":       0xE003,
		"o:":       0xE004,
		"cl":       0xE005,
		"ky":       0xE006,
		"kw":       0xE007,
		"gy":       0xE008,
		"gw":       0xE009,
		"ty":       0xE00A,
		"dy":       0xE00B,
		"py":       0xE00C,
		"by":       0xE00D,
		"ch":       0xE00E,
		"ts":       0xE00F,
		"sh":       0xE010,
		"zy":       0xE011,
		"hy":       0xE012,
		"ny":       0xE013,
		"my":       0xE014,
		"ry":       0xE015,
		"?!":       0xE016,
		"?.":       0xE017,
		"?~":       0xE018,
		"N_m":      0xE019,
		"N_n":      0xE01A,
		"N_ng":     0xE01B,
		"N_uvular": 0xE01C,
	}
	for token, expectedRune := range pythonPUA {
		goMapped := RegisterToken(token)
		if goMapped != string(expectedRune) {
			t.Errorf("PUA mismatch for %q: Go=%q, Python=U+%04X", token, goMapped, expectedRune)
		}
	}
}

func TestPUAMapping_SingleCharTokensPassThrough(t *testing.T) {
	// Single-char Japanese phonemes should pass through RegisterToken unchanged.
	singleChars := []string{
		"a", "i", "u", "e", "o",
		"A", "I", "U", "E", "O",
		"N", "k", "g", "t", "d", "p", "b",
		"s", "z", "j", "f", "h", "v",
		"n", "m", "r", "w", "y", "q",
	}
	for _, ch := range singleChars {
		got := RegisterToken(ch)
		if got != ch {
			t.Errorf("RegisterToken(%q) = %q, want %q (passthrough)", ch, got, ch)
		}
	}
}

// =========================================================================
// 8. Full pipeline test with mock engine
// =========================================================================

func TestJapanesePhonemizer_FullPipeline(t *testing.T) {
	// Simulated labels for a simple utterance: "か" (ka)
	labels := []string{
		"xx^xx-sil+k=a/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+a=sil/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-a+sil=xx/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}

	engine := &mockEngine{labels: labels}
	phonemizer := NewJapanesePhonemizer(engine)

	result, err := phonemizer.PhonemizeWithProsody("か")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	if phonemizer.LanguageCode() != "ja" {
		t.Errorf("LanguageCode() = %q, want \"ja\"", phonemizer.LanguageCode())
	}

	// Should produce tokens including "^", "k", "a", "$"
	joined := strings.Join(result.Tokens, " ")
	for _, want := range []string{"^", "k", "a", "$"} {
		if !strings.Contains(joined, want) {
			t.Errorf("expected token %q in result, got tokens: %v", want, result.Tokens)
		}
	}
}

func TestJapanesePhonemizer_QuestionPipeline(t *testing.T) {
	labels := []string{
		"xx^xx-sil+k=a/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+a=sil/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-a+sil=xx/A:0+1+1/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}

	engine := &mockEngine{labels: labels}
	phonemizer := NewJapanesePhonemizer(engine)

	result, err := phonemizer.PhonemizeWithProsody("か？")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	// EOS should be "?" for a question
	if result.EOSToken != "?" {
		t.Errorf("EOSToken = %q, want \"?\"", result.EOSToken)
	}
}

// =========================================================================
// 9. Regex correctness tests
// =========================================================================

func TestRegex_PhonemeExtraction(t *testing.T) {
	tests := []struct {
		label string
		want  string
	}{
		{"xx^xx-k+o=xx", "k"},
		{"xx^xx-sil+xx=xx", "sil"},
		{"xx^xx-pau+xx=xx", "pau"},
		{"xx^xx-N+b=xx", "N"},
		{"xx^xx-ch+i=xx", "ch"},
		{"xx^xx-sh+a=xx", "sh"},
		{"xx^xx-cl+k=xx", "cl"},
		{"xx^xx-ky+a=xx", "ky"},
	}
	for _, tc := range tests {
		m := rePhoneme.FindStringSubmatch(tc.label)
		if m == nil {
			t.Errorf("rePhoneme failed to match %q", tc.label)
			continue
		}
		if m[1] != tc.want {
			t.Errorf("rePhoneme(%q) captured %q, want %q", tc.label, m[1], tc.want)
		}
	}
}

func TestRegex_A1Extraction(t *testing.T) {
	tests := []struct {
		label string
		want  string
	}{
		{"/A:0+1+2/B:", "0"},
		{"/A:-2+1+5/B:", "-2"},
		{"/A:10+3+3/B:", "10"},
	}
	for _, tc := range tests {
		m := reA1.FindStringSubmatch(tc.label)
		if m == nil {
			t.Errorf("reA1 failed to match %q", tc.label)
			continue
		}
		if m[1] != tc.want {
			t.Errorf("reA1(%q) captured %q, want %q", tc.label, m[1], tc.want)
		}
	}
}

func TestRegex_A2Extraction(t *testing.T) {
	tests := []struct {
		label string
		want  string
	}{
		{"/A:0+1+2/B:", "1"},
		{"/A:-2+10+5/B:", "10"},
	}
	for _, tc := range tests {
		m := reA2.FindStringSubmatch(tc.label)
		if m == nil {
			t.Errorf("reA2 failed to match %q", tc.label)
			continue
		}
		if m[1] != tc.want {
			t.Errorf("reA2(%q) captured %q, want %q", tc.label, m[1], tc.want)
		}
	}
}

func TestRegex_A3Extraction(t *testing.T) {
	tests := []struct {
		label string
		want  string
	}{
		{"/A:0+1+2/B:", "2"},
		{"/A:-2+10+5/B:", "5"},
	}
	for _, tc := range tests {
		m := reA3.FindStringSubmatch(tc.label)
		if m == nil {
			t.Errorf("reA3 failed to match %q", tc.label)
			continue
		}
		if m[1] != tc.want {
			t.Errorf("reA3(%q) captured %q, want %q", tc.label, m[1], tc.want)
		}
	}
}

func TestRegex_A1NegativeValues(t *testing.T) {
	// A1 can be negative (relative position from accent nucleus)
	label := "xx^xx-k+o=xx/A:-3+2+5/B:xx-xx_xx/C:xx_xx+xx"
	m := reA1.FindStringSubmatch(label)
	if m == nil {
		t.Fatal("reA1 failed to match label with negative A1")
	}
	if m[1] != "-3" {
		t.Errorf("reA1 captured %q, want \"-3\"", m[1])
	}
}

// =========================================================================
// 10. Regression: prosody marks don't corrupt N phoneme rules
// =========================================================================

func TestApplyNPhonemeRules_AfterProsodyMarks(t *testing.T) {
	// Realistic token sequence: N followed by prosody marks, then a phoneme.
	// This tests the interaction between Kurihara marks and N replacement.
	input := []string{"^", "k", "o", "N", "]", "#", "[", "t", "a", "$"}
	got := applyNPhonemeRules(input)

	// N followed by ] # [ then t -> should classify as alveolar (N_n)
	if got[3] != "N_n" {
		t.Errorf("N after prosody marks before t: got %q, want N_n\n  input:  %v\n  output: %v",
			got[3], input, got)
	}

	// Token count must be preserved
	if len(got) != len(input) {
		t.Errorf("token count changed: %d -> %d", len(input), len(got))
	}
}

// =========================================================================
// 11. Skip tokens set parity with Python
// =========================================================================

func TestSkipTokens_PythonParity(t *testing.T) {
	// Python: _SKIP_TOKENS = frozenset(("_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"))
	pythonSkipTokens := []string{"_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"}
	for _, tok := range pythonSkipTokens {
		if !skipTokens[tok] {
			t.Errorf("skipTokens missing %q (present in Python _SKIP_TOKENS)", tok)
		}
	}
	// Check no extra entries in Go
	if len(skipTokens) != len(pythonSkipTokens) {
		t.Errorf("skipTokens has %d entries, Python has %d", len(skipTokens), len(pythonSkipTokens))
	}
}

// =========================================================================
// 12. Bilabial/Alveolar/Velar sets parity with Python
// =========================================================================

func TestPhonemeClassification_PythonParity(t *testing.T) {
	// Python bilabials: ("m", "my", "b", "by", "p", "py")
	pyBilabials := []string{"m", "my", "b", "by", "p", "py"}
	for _, p := range pyBilabials {
		if !bilabials[p] {
			t.Errorf("bilabials missing %q", p)
		}
	}
	if len(bilabials) != len(pyBilabials) {
		t.Errorf("bilabials has %d entries, Python has %d", len(bilabials), len(pyBilabials))
	}

	// Python alveolars: ("n", "ny", "t", "ty", "d", "dy", "ts", "ch")
	pyAlveolars := []string{"n", "ny", "t", "ty", "d", "dy", "ts", "ch"}
	for _, p := range pyAlveolars {
		if !alveolars[p] {
			t.Errorf("alveolars missing %q", p)
		}
	}
	if len(alveolars) != len(pyAlveolars) {
		t.Errorf("alveolars has %d entries, Python has %d", len(alveolars), len(pyAlveolars))
	}

	// Python velars: ("k", "ky", "kw", "g", "gy", "gw")
	pyVelars := []string{"k", "ky", "kw", "g", "gy", "gw"}
	for _, p := range pyVelars {
		if !velars[p] {
			t.Errorf("velars missing %q", p)
		}
	}
	if len(velars) != len(pyVelars) {
		t.Errorf("velars has %d entries, Python has %d", len(velars), len(pyVelars))
	}
}

// =========================================================================
// 13. Negative A1 value handling in prosody
// =========================================================================

func TestLabelsToTokensWithProsody_NegativeA1(t *testing.T) {
	// A1 can be negative in OpenJTalk labels (e.g., -2 means 2 morae before accent nucleus)
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:-2+1+5/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for i, tok := range result.Tokens {
		if tok == "k" {
			p := result.Prosody[i]
			if p == nil {
				t.Fatal("prosody for 'k' is nil")
			}
			if p.A1 != -2 {
				t.Errorf("negative A1: got %d, want -2", p.A1)
			}
			return
		}
	}
	t.Error("phoneme 'k' not found")
}

// =========================================================================
// 14. Complex Kurihara scenario — combined marks
// =========================================================================

func TestLabelsToTokensWithProsody_CombinedProsodyMarks(t *testing.T) {
	// Test scenario where "]", "#", and "[" are all triggered in sequence.
	// This happens at an accent phrase boundary where the previous phrase ends
	// with accent nucleus and the next phrase begins.
	//
	// Label 1: a1=0, a2=3, a3=3 -> a2_next=1
	//   - a1==0, a2_next==a2+1 -> NO (a2_next=1 != 4)
	//   - a2==a3 (3==3), a2_next==1 -> YES: insert "#"
	//   - a2==1, a2_next==2 -> NO
	// Label 2: a1=1, a2=1, a3=2 -> a2_next=2
	//   - a2==1, a2_next==2 -> YES: insert "["
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-a+k=xx/A:0+3+3/B:xx-xx_xx/C:xx_xx+xx", // end of phrase
		"xx^xx-k+a=xx/A:1+1+2/B:xx-xx_xx/C:xx_xx+xx", // start of new phrase
		"xx^xx-a+sil=xx/A:0+2+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	result, err := labelsToTokensWithProsody(labels, "テスト")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Check that "#" appears (phrase boundary)
	foundHash := false
	foundBracket := false
	for _, tok := range result.Tokens {
		if tok == "#" {
			foundHash = true
		}
		if tok == "[" {
			foundBracket = true
		}
	}
	if !foundHash {
		t.Errorf("expected \"#\" in tokens, got %v", result.Tokens)
	}
	if !foundBracket {
		t.Errorf("expected \"[\" in tokens, got %v", result.Tokens)
	}
}

// =========================================================================
// 15. MapSequence for multi-char Japanese phonemes
// =========================================================================

func TestMapSequence_JapanesePhonemes(t *testing.T) {
	input := []string{"^", "k", "o", "N_m", "#", "ch", "a", "$"}
	got := MapSequence(input)

	// Single-char tokens should be unchanged
	if got[0] != "^" {
		t.Errorf("MapSequence[0] = %q, want \"^\"", got[0])
	}
	if got[1] != "k" {
		t.Errorf("MapSequence[1] = %q, want \"k\"", got[1])
	}

	// Multi-char tokens should be PUA-mapped
	nmExpected := string(rune(0xE019))
	if got[3] != nmExpected {
		t.Errorf("MapSequence[3] N_m = %q, want %q (U+E019)", got[3], nmExpected)
	}
	chExpected := string(rune(0xE00E))
	if got[5] != chExpected {
		t.Errorf("MapSequence[5] ch = %q, want %q (U+E00E)", got[5], chExpected)
	}
}

// =========================================================================
// 16. Verify labelsToTokensWithProsody is deterministic
// =========================================================================

func TestLabelsToTokensWithProsody_Deterministic(t *testing.T) {
	labels := []string{
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-k+o=xx/A:0+1+3/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-o+N=xx/A:0+2+3/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-N+n=xx/A:0+3+3/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-n+a=xx/A:0+1+2/B:xx-xx_xx/C:xx_xx+xx",
		"xx^xx-sil+xx=xx/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx",
	}
	r1, _ := labelsToTokensWithProsody(labels, "テスト")
	r2, _ := labelsToTokensWithProsody(labels, "テスト")

	if !reflect.DeepEqual(r1.Tokens, r2.Tokens) {
		t.Errorf("non-deterministic tokens: %v vs %v", r1.Tokens, r2.Tokens)
	}
}

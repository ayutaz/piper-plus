package phonemize

import (
	"testing"
)

// ===========================================================================
// Helper: extract raw phonemes from koProcess (no PUA mapping).
// ===========================================================================

func koPhonemes(text string) []string {
	tokens, _ := koProcess(text)
	return tokens
}

// ===========================================================================
// 1. Hangul decomposition
// ===========================================================================

func TestKoDecompose_Ga(t *testing.T) {
	// 가 = U+AC00 = initial 0 (ㄱ), medial 0 (ㅏ), final 0 (none)
	i, m, f := koDecompose('\uAC00')
	if i != 0 || m != 0 || f != 0 {
		t.Errorf("koDecompose('가') = (%d,%d,%d), want (0,0,0)", i, m, f)
	}
}

func TestKoDecompose_Han(t *testing.T) {
	// 한 = initial 18 (ㅎ), medial 0 (ㅏ), final 4 (ㄴ)
	i, m, f := koDecompose('한')
	if i != 18 || m != 0 || f != 4 {
		t.Errorf("koDecompose('한') = (%d,%d,%d), want (18,0,4)", i, m, f)
	}
}

func TestKoDecompose_Gul(t *testing.T) {
	// 글 = initial 0 (ㄱ), medial 18 (ㅡ), final 8 (ㄹ)
	i, m, f := koDecompose('글')
	if i != 0 || m != 18 || f != 8 {
		t.Errorf("koDecompose('글') = (%d,%d,%d), want (0,18,8)", i, m, f)
	}
}

func TestKoIsHangulSyllable(t *testing.T) {
	tests := []struct {
		ch   rune
		want bool
		desc string
	}{
		{'\uAC00', true, "가 (start of range)"},
		{'\uD7A3', true, "힣 (end of range)"},
		{'A', false, "Latin A"},
		{'あ', false, "Japanese hiragana"},
		{' ', false, "space"},
	}
	for _, tc := range tests {
		got := koIsHangulSyllable(tc.ch)
		if got != tc.want {
			t.Errorf("koIsHangulSyllable(%q) [%s] = %v, want %v", tc.ch, tc.desc, got, tc.want)
		}
	}
}

// ===========================================================================
// 2. NFD recomposition
// ===========================================================================

func TestKoComposeJamo_WithTrailing(t *testing.T) {
	// NFD for 한 = ㅎ (U+1112) + ㅏ (U+1161) + ㄴ (U+11AB)
	nfd := []rune{'\u1112', '\u1161', '\u11AB'}
	composed := koComposeHangulJamo(nfd)
	if len(composed) != 1 || composed[0] != '한' {
		t.Errorf("koComposeHangulJamo(NFD 한) = %v, want [한]", composed)
	}
}

func TestKoComposeJamo_NoTrailing(t *testing.T) {
	// NFD for 가 = ㄱ (U+1100) + ㅏ (U+1161)
	nfd := []rune{'\u1100', '\u1161'}
	composed := koComposeHangulJamo(nfd)
	if len(composed) != 1 || composed[0] != '\uAC00' {
		t.Errorf("koComposeHangulJamo(NFD 가) = %v, want [가]", composed)
	}
}

// ===========================================================================
// 3. Single syllable phonemization
// ===========================================================================

func TestKoSingleSyllable_Ga(t *testing.T) {
	// 가 -> k + a
	got := koPhonemes("가")
	want := []string{"k", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"가\") = %v, want %v", got, want)
	}
}

func TestKoSingleSyllable_Han(t *testing.T) {
	// 한 -> h + a + n
	got := koPhonemes("한")
	want := []string{"h", "a", "n"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"한\") = %v, want %v", got, want)
	}
}

func TestKoSingleSyllable_Eung(t *testing.T) {
	// 앙 -> (silent ㅇ) + a + ŋ
	got := koPhonemes("앙")
	want := []string{"a", koEng}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"앙\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 4. Multi-syllable word
// ===========================================================================

func TestKoWord_Hangul(t *testing.T) {
	// 한글 -> h a n + k ɯ l
	got := koPhonemes("한글")
	want := []string{"h", "a", "n", "k", koCloseBackUnr, "l"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"한글\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 5. Liaison (연음화)
// ===========================================================================

func TestKoLiaison_GukEo(t *testing.T) {
	// 국어 = ㄱ+ㅜ+ㄱ(final=1) + ㅇ(initial=11)+ㅓ
	// Liaison: final ㄱ (idx 1) has liaisonInitial=0 (ㄱ initial)
	// After liaison: 구 + 거 -> k u + k ʌ
	got := koPhonemes("국어")
	want := []string{"k", "u", "k", koOpenMidBack}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"국어\") = %v, want %v", got, want)
	}
}

func TestKoComplexLiaison_IlkEo(t *testing.T) {
	// 읽어 = ㅇ+ㅣ+ㄺ(final=9) + ㅇ(initial=11)+ㅓ
	// ㄺ (final=9): liaisonInitial=0 (ㄱ), residualFinal=8 (ㄹ)
	// After liaison: 일(residual ㄹ) + 거(ㄱ initial)
	// -> (silent)i l + k ʌ
	got := koPhonemes("읽어")
	want := []string{"i", "l", "k", koOpenMidBack}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"읽어\") = %v, want %v", got, want)
	}
}

func TestKoLiaison_DoesNotCascade(t *testing.T) {
	// 먹어요 = ㅁ+ㅓ+ㄱ(final=1) + ㅇ+ㅓ + ㅇ+ㅛ
	// First liaison: ㄱ -> next syllable initial ㄱ(0)
	// Second: 어(no final) + 요(initial=ㅇ but no final to move)
	// -> m ʌ + k ʌ + j o
	got := koPhonemes("먹어요")
	want := []string{"m", koOpenMidBack, "k", koOpenMidBack, "j", "o"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"먹어요\") = %v, want %v", got, want)
	}
}

func TestKoNoLiaison_NonIeungInitial(t *testing.T) {
	// 국민 = ㄱ+ㅜ+ㄱ(final=1) + ㅁ(initial=6)+ㅣ+ㄴ(final=4)
	// No liaison: next initial is ㅁ(6), not ㅇ(11)
	// -> k u k̚ + m i n
	got := koPhonemes("국민")
	want := []string{"k", "u", "k̚", "m", "i", "n"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"국민\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 6. Tense consonants (경음)
// ===========================================================================

func TestKoTense_Kk(t *testing.T) {
	// 까 = ㄲ(initial=1) + ㅏ -> k͈ + a
	got := koPhonemes("까")
	want := []string{"k͈", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"까\") = %v, want %v", got, want)
	}
}

func TestKoTense_Tt(t *testing.T) {
	// 따 = ㄸ(initial=4) + ㅏ -> t͈ + a
	got := koPhonemes("따")
	want := []string{"t͈", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"따\") = %v, want %v", got, want)
	}
}

func TestKoTense_Pp(t *testing.T) {
	// 빠 = ㅃ(initial=8) + ㅏ -> p͈ + a
	got := koPhonemes("빠")
	want := []string{"p͈", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"빠\") = %v, want %v", got, want)
	}
}

func TestKoTense_Ss(t *testing.T) {
	// 싸 = ㅆ(initial=10) + ㅏ -> s͈ + a
	got := koPhonemes("싸")
	want := []string{"s͈", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"싸\") = %v, want %v", got, want)
	}
}

func TestKoTense_Jj(t *testing.T) {
	// 짜 = ㅉ(initial=13) + ㅏ -> t͈ɕ + a
	got := koPhonemes("짜")
	want := []string{"t͈ɕ", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"짜\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 7. Aspirated consonants
// ===========================================================================

func TestKoAspirated_Kh(t *testing.T) {
	// 카 = ㅋ(initial=15) + ㅏ -> kʰ + a
	got := koPhonemes("카")
	want := []string{"kʰ", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"카\") = %v, want %v", got, want)
	}
}

func TestKoAspirated_Th(t *testing.T) {
	// 타 = ㅌ(initial=16) + ㅏ -> tʰ + a
	got := koPhonemes("타")
	want := []string{"tʰ", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"타\") = %v, want %v", got, want)
	}
}

func TestKoAspirated_Ph(t *testing.T) {
	// 파 = ㅍ(initial=17) + ㅏ -> pʰ + a
	got := koPhonemes("파")
	want := []string{"pʰ", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"파\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 8. Unreleased finals (내파음)
// ===========================================================================

func TestKoUnreleasedFinal_K(t *testing.T) {
	// 박 = ㅂ + ㅏ + ㄱ(final=1) -> p a k̚
	got := koPhonemes("박")
	want := []string{"p", "a", "k̚"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"박\") = %v, want %v", got, want)
	}
}

func TestKoUnreleasedFinal_T(t *testing.T) {
	// 맛 = ㅁ + ㅏ + ㅅ(final=19) -> m a t̚
	got := koPhonemes("맛")
	want := []string{"m", "a", "t̚"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"맛\") = %v, want %v", got, want)
	}
}

func TestKoUnreleasedFinal_P(t *testing.T) {
	// 밥 = ㅂ + ㅏ + ㅂ(final=17) -> p a p̚
	got := koPhonemes("밥")
	want := []string{"p", "a", "p̚"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"밥\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 9. Diphthongs (이중모음)
// ===========================================================================

func TestKoDiphthong_Wa(t *testing.T) {
	// 와 = ㅇ(silent) + ㅘ(medial=9: w+a) -> w a
	got := koPhonemes("와")
	want := []string{"w", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"와\") = %v, want %v", got, want)
	}
}

func TestKoDiphthong_Wi(t *testing.T) {
	// 위 = ㅇ(silent) + ㅟ(medial=16: w+i) -> w i
	got := koPhonemes("위")
	want := []string{"w", "i"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"위\") = %v, want %v", got, want)
	}
}

func TestKoDiphthong_Ui(t *testing.T) {
	// 의 = ㅇ(silent) + ㅢ(medial=19: ɰ+i) -> ɰ i
	got := koPhonemes("의")
	want := []string{koVelarApprox, "i"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"의\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 10. Affricate consonants
// ===========================================================================

func TestKoAffricate_J(t *testing.T) {
	// 자 = ㅈ(initial=12) + ㅏ -> tɕ + a
	got := koPhonemes("자")
	want := []string{"tɕ", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"자\") = %v, want %v", got, want)
	}
}

func TestKoAffricate_Ch(t *testing.T) {
	// 차 = ㅊ(initial=14) + ㅏ -> tɕʰ + a
	got := koPhonemes("차")
	want := []string{"tɕʰ", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"차\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 11. Alveolar flap (ㄹ)
// ===========================================================================

func TestKoInitial_Rieul(t *testing.T) {
	// 라 = ㄹ(initial=5) + ㅏ -> ɾ + a
	got := koPhonemes("라")
	want := []string{koFlap, "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"라\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 12. Word boundary / space handling
// ===========================================================================

func TestKoWordBoundary_Space(t *testing.T) {
	got := koPhonemes("가 나")
	want := []string{"k", "a", " ", "n", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"가 나\") = %v, want %v", got, want)
	}
}

func TestKoNoLeadingSpace(t *testing.T) {
	got := koPhonemes("  가")
	want := []string{"k", "a"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"  가\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 13. Punctuation
// ===========================================================================

func TestKoPunctuation_Period(t *testing.T) {
	got := koPhonemes("가.")
	want := []string{"k", "a", "."}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"가.\") = %v, want %v", got, want)
	}
}

func TestKoPunctuation_Question(t *testing.T) {
	tokens, eos := koProcess("가?")
	wantTokens := []string{"k", "a", "?"}
	if !sliceEqual(tokens, wantTokens) {
		t.Errorf("koProcess(\"가?\") tokens = %v, want %v", tokens, wantTokens)
	}
	if eos != "?" {
		t.Errorf("koProcess(\"가?\") eos = %q, want %q", eos, "?")
	}
}

func TestKoPunctuation_Exclamation(t *testing.T) {
	tokens, eos := koProcess("가!")
	wantTokens := []string{"k", "a", "!"}
	if !sliceEqual(tokens, wantTokens) {
		t.Errorf("koProcess(\"가!\") tokens = %v, want %v", tokens, wantTokens)
	}
	if eos != "!" {
		t.Errorf("koProcess(\"가!\") eos = %q, want %q", eos, "!")
	}
}

// ===========================================================================
// 14. Mixed text (Hangul + Latin)
// ===========================================================================

func TestKoMixedText(t *testing.T) {
	// Space between Hangul and Latin runs
	got := koPhonemes("가 OK")
	want := []string{"k", "a", " ", "o", " ", "k"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"가 OK\") = %v, want %v", got, want)
	}
}

func TestKoLatinPassthrough(t *testing.T) {
	// Each Latin char is processed individually; space inserted between each
	got := koPhonemes("Hello")
	want := []string{"h", " ", "e", " ", "l", " ", "l", " ", "o"}
	if !sliceEqual(got, want) {
		t.Errorf("koPhonemes(\"Hello\") = %v, want %v", got, want)
	}
}

// ===========================================================================
// 15. Empty input
// ===========================================================================

func TestKoEmptyInput(t *testing.T) {
	got := koPhonemes("")
	if len(got) != 0 {
		t.Errorf("koPhonemes(\"\") = %v, want empty", got)
	}
}

func TestKoEmptyInput_EOS(t *testing.T) {
	_, eos := koProcess("")
	if eos != "$" {
		t.Errorf("koProcess(\"\") eos = %q, want \"$\"", eos)
	}
}

// ===========================================================================
// 16. Phonemizer interface
// ===========================================================================

func TestKoLanguageCode(t *testing.T) {
	p := NewKoreanPhonemizer()
	if p.LanguageCode() != "ko" {
		t.Errorf("LanguageCode() = %q, want \"ko\"", p.LanguageCode())
	}
}

func TestKoProsody_SingleSyllable(t *testing.T) {
	p := NewKoreanPhonemizer()
	result, err := p.PhonemizeWithProsody("가")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	if len(result.Tokens) == 0 {
		t.Fatal("expected non-empty tokens")
	}
	if len(result.Tokens) != len(result.Prosody) {
		t.Fatalf("tokens len (%d) != prosody len (%d)", len(result.Tokens), len(result.Prosody))
	}
	// 가 is a single Hangul syllable word -> A3=1
	for i, pi := range result.Prosody {
		if pi == nil {
			t.Errorf("prosody[%d] is nil, want non-nil", i)
			continue
		}
		if pi.A1 != 0 || pi.A2 != 0 || pi.A3 != 1 {
			t.Errorf("prosody[%d] = (%d,%d,%d), want (0,0,1)", i, pi.A1, pi.A2, pi.A3)
		}
	}
}

func TestKoProsody_MultiSyllableWord(t *testing.T) {
	p := NewKoreanPhonemizer()
	// 한글 = 2 Hangul syllables -> all phoneme tokens should have A3=2
	result, err := p.PhonemizeWithProsody("한글")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	for i, pi := range result.Prosody {
		if pi == nil {
			t.Errorf("prosody[%d] is nil, want non-nil", i)
			continue
		}
		if pi.A3 != 2 {
			t.Errorf("prosody[%d].A3 = %d, want 2", i, pi.A3)
		}
	}
}

func TestKoProsody_SpaceSeparatedWords(t *testing.T) {
	p := NewKoreanPhonemizer()
	// 가 나 = two 1-syllable words with a space between
	result, err := p.PhonemizeWithProsody("가 나")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	// Expect: tokens for 가 (A3=1), space (A3=0), tokens for 나 (A3=1)
	for i, pi := range result.Prosody {
		if pi == nil {
			t.Errorf("prosody[%d] is nil, want non-nil", i)
			continue
		}
		tok := result.Tokens[i]
		if tok == " " {
			if pi.A3 != 0 {
				t.Errorf("space prosody[%d].A3 = %d, want 0", i, pi.A3)
			}
		} else {
			if pi.A3 != 1 {
				t.Errorf("prosody[%d].A3 = %d, want 1 (token=%q)", i, pi.A3, tok)
			}
		}
	}
}

func TestKoPhonemizer_SingleCharTokens(t *testing.T) {
	p := NewKoreanPhonemizer()
	result, err := p.PhonemizeWithProsody("한글")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	for _, tok := range result.Tokens {
		runes := []rune(tok)
		if len(runes) != 1 {
			t.Errorf("expected single-char token, got %q (len %d)", tok, len(runes))
		}
	}
}

func TestKoPhonemizer_EmptyInput(t *testing.T) {
	p := NewKoreanPhonemizer()
	result, err := p.PhonemizeWithProsody("")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("expected empty tokens, got %v", result.Tokens)
	}
	if result.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want \"$\"", result.EOSToken)
	}
}

// ===========================================================================
// 17. PUA mapping integration
// ===========================================================================

func TestKoPUA_TenseConsonants(t *testing.T) {
	p := NewKoreanPhonemizer()
	// 까 -> k͈ + a ; after PUA mapping, k͈ should be a single PUA char
	result, err := p.PhonemizeWithProsody("까")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	// k͈ should be mapped to PUA U+E04D
	if len(result.Tokens) < 1 {
		t.Fatal("expected at least 1 token")
	}
	firstRune := []rune(result.Tokens[0])[0]
	if firstRune != 0xE04D {
		t.Errorf("first token rune = U+%04X, want U+E04D (k͈)", firstRune)
	}
}

func TestKoPUA_UnreleasedFinals(t *testing.T) {
	p := NewKoreanPhonemizer()
	tests := []struct {
		input   string
		wantPUA rune
		desc    string
	}{
		{"박", 0xE050, "k̚ -> U+E050"},
		{"맛", 0xE051, "t̚ -> U+E051"},
		{"밥", 0xE052, "p̚ -> U+E052"},
	}
	for _, tc := range tests {
		result, err := p.PhonemizeWithProsody(tc.input)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.input, err)
		}
		// The unreleased final should be the last token
		lastTok := result.Tokens[len(result.Tokens)-1]
		lastRune := []rune(lastTok)[0]
		if lastRune != tc.wantPUA {
			t.Errorf("[%s] last token rune = U+%04X, want U+%04X", tc.desc, lastRune, tc.wantPUA)
		}
	}
}

// ===========================================================================
// 18. Full-width CJK punctuation
// ===========================================================================

func TestKoFullWidthPunctuation(t *testing.T) {
	// Test fullwidth question mark (？ U+FF1F)
	tokens, eos := koProcess("가？")
	if eos != "?" {
		t.Errorf("eos for fullwidth ? = %q, want \"?\"", eos)
	}
	if len(tokens) < 2 {
		t.Fatalf("expected at least 2 tokens, got %v", tokens)
	}
}

// ===========================================================================
// Helper used across tests (reused from spanish_test.go)
// ===========================================================================

// sliceEqual is defined in spanish_test.go; no need to redefine here.

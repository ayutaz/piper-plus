package phonemize

import (
	"fmt"
	"sync"
	"testing"
	"unicode/utf8"
)

// ---------------------------------------------------------------------------
// 1. Fixed PUA mapping — exhaustive verification of all 99 entries
// ---------------------------------------------------------------------------

// allFixedPUA defines the complete expected mapping between Python and Go.
// Every entry corresponds 1:1 to Python's FIXED_PUA_MAPPING in token_mapper.py
// plus the Swedish long vowel entries.
//
// The tokens use Go string literals with explicit Unicode escapes for IPA
// combining characters to ensure byte-exact matching with the Go fixedPUA map.
var allFixedPUA = []struct {
	token string
	want  rune
	group string // for error messages
}{
	// Japanese (0xE000-0xE01C) — 29 entries
	{"a:", 0xE000, "JA"},
	{"i:", 0xE001, "JA"},
	{"u:", 0xE002, "JA"},
	{"e:", 0xE003, "JA"},
	{"o:", 0xE004, "JA"},
	{"cl", 0xE005, "JA"},
	{"ky", 0xE006, "JA"},
	{"kw", 0xE007, "JA"},
	{"gy", 0xE008, "JA"},
	{"gw", 0xE009, "JA"},
	{"ty", 0xE00A, "JA"},
	{"dy", 0xE00B, "JA"},
	{"py", 0xE00C, "JA"},
	{"by", 0xE00D, "JA"},
	{"ch", 0xE00E, "JA"},
	{"ts", 0xE00F, "JA"},
	{"sh", 0xE010, "JA"},
	{"zy", 0xE011, "JA"},
	{"hy", 0xE012, "JA"},
	{"ny", 0xE013, "JA"},
	{"my", 0xE014, "JA"},
	{"ry", 0xE015, "JA"},
	{"?!", 0xE016, "JA"},
	{"?.", 0xE017, "JA"},
	{"?~", 0xE018, "JA"},
	{"N_m", 0xE019, "JA"},
	{"N_n", 0xE01A, "JA"},
	{"N_ng", 0xE01B, "JA"},
	{"N_uvular", 0xE01C, "JA"},

	// Multilingual shared (0xE01D-0xE01E) — 2 entries
	{"rr", 0xE01D, "shared"},
	{"y_vowel", 0xE01E, "shared"},

	// Chinese (0xE020-0xE04A) — 43 entries
	// Initials
	{"p\u02b0", 0xE020, "ZH"},       // pʰ
	{"t\u02b0", 0xE021, "ZH"},       // tʰ
	{"k\u02b0", 0xE022, "ZH"},       // kʰ
	{"t\u0255", 0xE023, "ZH"},       // tɕ
	{"t\u0255\u02b0", 0xE024, "ZH"}, // tɕʰ
	{"t\u0282", 0xE025, "ZH"},       // tʂ
	{"t\u0282\u02b0", 0xE026, "ZH"}, // tʂʰ
	{"ts\u02b0", 0xE027, "ZH"},      // tsʰ
	// Diphthongs
	{"a\u026a", 0xE028, "ZH"}, // aɪ
	{"e\u026a", 0xE029, "ZH"}, // eɪ
	{"a\u028a", 0xE02A, "ZH"}, // aʊ
	{"o\u028a", 0xE02B, "ZH"}, // oʊ
	// Nasal finals
	{"an", 0xE02C, "ZH"},
	{"\u0259n", 0xE02D, "ZH"},      // ən
	{"a\u014b", 0xE02E, "ZH"},      // aŋ
	{"\u0259\u014b", 0xE02F, "ZH"}, // əŋ
	{"u\u014b", 0xE030, "ZH"},      // uŋ
	// i-compound finals
	{"ia", 0xE031, "ZH"},
	{"i\u025b", 0xE032, "ZH"}, // iɛ
	{"iou", 0xE033, "ZH"},
	{"ia\u028a", 0xE034, "ZH"}, // iaʊ
	{"i\u025bn", 0xE035, "ZH"}, // iɛn
	{"in", 0xE036, "ZH"},
	{"ia\u014b", 0xE037, "ZH"}, // iaŋ
	{"i\u014b", 0xE038, "ZH"},  // iŋ
	{"iu\u014b", 0xE039, "ZH"}, // iuŋ
	// u-compound finals
	{"ua", 0xE03A, "ZH"},
	{"uo", 0xE03B, "ZH"},
	{"ua\u026a", 0xE03C, "ZH"}, // uaɪ
	{"ue\u026a", 0xE03D, "ZH"}, // ueɪ
	{"uan", 0xE03E, "ZH"},
	{"u\u0259n", 0xE03F, "ZH"},      // uən
	{"ua\u014b", 0xE040, "ZH"},      // uaŋ
	{"u\u0259\u014b", 0xE041, "ZH"}, // uəŋ
	// u-umlaut compound finals
	{"y\u025b", 0xE042, "ZH"},  // yɛ
	{"y\u025bn", 0xE043, "ZH"}, // yɛn
	{"yn", 0xE044, "ZH"},
	// Syllabic consonants
	{"\u027b\u0329", 0xE045, "ZH"}, // ɻ̩
	// Tone markers
	{"tone1", 0xE046, "ZH"},
	{"tone2", 0xE047, "ZH"},
	{"tone3", 0xE048, "ZH"},
	{"tone4", 0xE049, "ZH"},
	{"tone5", 0xE04A, "ZH"},

	// Korean (0xE04B-0xE052) — 8 entries
	{"p\u0348", 0xE04B, "KO"},       // p͈
	{"t\u0348", 0xE04C, "KO"},       // t͈
	{"k\u0348", 0xE04D, "KO"},       // k͈
	{"s\u0348", 0xE04E, "KO"},       // s͈
	{"t\u0348\u0255", 0xE04F, "KO"}, // t͈ɕ
	{"k\u031a", 0xE050, "KO"},       // k̚
	{"t\u031a", 0xE051, "KO"},       // t̚
	{"p\u031a", 0xE052, "KO"},       // p̚

	// Spanish/Portuguese (0xE054-0xE055) — 2 entries
	{"t\u0283", 0xE054, "ES/PT"}, // tʃ
	{"d\u0292", 0xE055, "ES/PT"}, // dʒ

	// French (0xE056-0xE058) — 3 entries
	{"\u025b\u0303", 0xE056, "FR"}, // ɛ̃
	{"\u0251\u0303", 0xE057, "FR"}, // ɑ̃
	{"\u0254\u0303", 0xE058, "FR"}, // ɔ̃

	// Swedish (0xE059-0xE061) — 9 entries (long vowels)
	{"i\u02d0", 0xE059, "SV"},      // iː
	{"y\u02d0", 0xE05A, "SV"},      // yː
	{"e\u02d0", 0xE05B, "SV"},      // eː
	{"\u025b\u02d0", 0xE05C, "SV"}, // ɛː
	{"\u00f8\u02d0", 0xE05D, "SV"}, // øː
	{"\u0251\u02d0", 0xE05E, "SV"}, // ɑː
	{"o\u02d0", 0xE05F, "SV"},      // oː
	{"u\u02d0", 0xE060, "SV"},      // uː
	{"\u0289\u02d0", 0xE061, "SV"}, // ʉː

	// Additional multi-codepoint diphthongs / nasal vowels (PUA v2) — 3 entries
	{"ɔɪ", 0xE062, "MULTI_V2"}, // ɔɪ  English diphthong (OY)
	{"œ̃", 0xE063, "MULTI_V2"}, // œ̃   French nasal open-mid front rounded vowel
	{"ɐ̃", 0xE064, "MULTI_V2"}, // ɐ̃   Portuguese nasal near-open central vowel
}

// TestFixedPUA_TotalCount ensures the Go fixedPUA map has exactly 99 entries,
// matching the Python FIXED_PUA_MAPPING plus Swedish long vowels and PUA v2 additions.
func TestFixedPUA_TotalCount(t *testing.T) {
	const want = 99
	if got := len(fixedPUA); got != want {
		t.Errorf("fixedPUA has %d entries, want %d (must match Python FIXED_PUA_MAPPING)", got, want)
	}
}

// TestFixedPUA_AllEntries verifies every single one of the 99 fixed PUA
// entries against the Python reference. This is an exhaustive golden test.
func TestFixedPUA_AllEntries(t *testing.T) {
	for _, tc := range allFixedPUA {
		t.Run(fmt.Sprintf("%s_U+%04X", tc.group, tc.want), func(t *testing.T) {
			got, ok := fixedPUA[tc.token]
			if !ok {
				t.Fatalf("fixedPUA missing token %q (expected U+%04X, group %s)", tc.token, tc.want, tc.group)
			}
			if got != tc.want {
				t.Errorf("fixedPUA[%q] = U+%04X, want U+%04X (group %s)", tc.token, got, tc.want, tc.group)
			}
		})
	}

	// Reverse check: ensure allFixedPUA covers ALL entries in fixedPUA.
	if len(allFixedPUA) != len(fixedPUA) {
		t.Errorf("allFixedPUA has %d entries but fixedPUA has %d; test table is incomplete",
			len(allFixedPUA), len(fixedPUA))
	}
}

// TestFixedPUA_NoDuplicateCodepoints ensures no two tokens map to the same PUA codepoint.
func TestFixedPUA_NoDuplicateCodepoints(t *testing.T) {
	seen := make(map[rune]string, len(fixedPUA))
	for token, r := range fixedPUA {
		if prev, ok := seen[r]; ok {
			t.Errorf("duplicate PUA codepoint U+%04X: %q and %q", r, prev, token)
		}
		seen[r] = token
	}
}

// TestFixedPUA_NoDuplicateTokens ensures no token appears with two different codepoints.
// (This is inherently guaranteed by Go maps, but we verify the test table too.)
func TestFixedPUA_NoDuplicateTokens(t *testing.T) {
	seen := make(map[string]rune, len(allFixedPUA))
	for _, tc := range allFixedPUA {
		if prev, ok := seen[tc.token]; ok {
			t.Errorf("duplicate token %q: U+%04X and U+%04X", tc.token, prev, tc.want)
		}
		seen[tc.token] = tc.want
	}
}

// TestFixedPUA_CodepointRanges verifies that each language group uses its documented range.
func TestFixedPUA_CodepointRanges(t *testing.T) {
	ranges := map[string][2]rune{
		"JA":     {0xE000, 0xE01C},
		"shared": {0xE01D, 0xE01E},
		"ZH":     {0xE020, 0xE04A},
		"KO":     {0xE04B, 0xE052},
		"ES/PT":  {0xE054, 0xE055},
		"FR":       {0xE056, 0xE058},
		"SV":       {0xE059, 0xE061},
		"MULTI_V2": {0xE062, 0xE064},
	}
	for _, tc := range allFixedPUA {
		r := ranges[tc.group]
		if tc.want < r[0] || tc.want > r[1] {
			t.Errorf("token %q (group %s) has codepoint U+%04X outside expected range U+%04X-U+%04X",
				tc.token, tc.group, tc.want, r[0], r[1])
		}
	}
}

// TestFixedPUA_GroupCounts verifies each language group has the expected number of entries.
func TestFixedPUA_GroupCounts(t *testing.T) {
	expected := map[string]int{
		"JA":     29,
		"shared": 2,
		"ZH":     43,
		"KO":     8,
		"ES/PT":  2,
		"FR":       3,
		"SV":       9,
		"MULTI_V2": 3,
	}
	counts := make(map[string]int)
	for _, tc := range allFixedPUA {
		counts[tc.group]++
	}
	for group, want := range expected {
		if got := counts[group]; got != want {
			t.Errorf("group %s has %d entries, want %d", group, got, want)
		}
	}
}

// ---------------------------------------------------------------------------
// 2. RegisterToken — fixed PUA, single-char, and edge cases
// ---------------------------------------------------------------------------

func TestRegisterToken_FixedPUA(t *testing.T) {
	tests := []struct {
		token string
		want  rune
	}{
		{"a:", 0xE000},
		{"N_m", 0xE019},
		{"tone1", 0xE046},
		{"t\u0283", 0xE054},      // tʃ
		{"\u025b\u0303", 0xE056}, // ɛ̃
	}
	for _, tc := range tests {
		got := RegisterToken(tc.token)
		expected := string(tc.want)
		if got != expected {
			t.Errorf("RegisterToken(%q) = %q, want %q (U+%04X)", tc.token, got, expected, tc.want)
		}
	}
}

func TestRegisterToken_AllFixedPUA(t *testing.T) {
	// Verify RegisterToken returns the correct PUA for every fixed entry.
	for _, tc := range allFixedPUA {
		got := RegisterToken(tc.token)
		expected := string(tc.want)
		if got != expected {
			t.Errorf("RegisterToken(%q) = %q, want PUA U+%04X (group %s)",
				tc.token, got, tc.want, tc.group)
		}
	}
}

func TestRegisterToken_SingleChar(t *testing.T) {
	tests := []struct {
		token string
		want  string
	}{
		{"a", "a"},
		{"k", "k"},
		{"ə", "ə"}, // single IPA character (U+0259)
		{"ɕ", "ɕ"}, // single IPA character (U+0255)
		{" ", " "}, // space
		{",", ","}, // punctuation
	}
	for _, tc := range tests {
		got := RegisterToken(tc.token)
		if got != tc.want {
			t.Errorf("RegisterToken(%q) = %q, want %q", tc.token, got, tc.want)
		}
	}
}

// TestRegisterToken_Idempotent ensures calling RegisterToken twice returns the same result.
func TestRegisterToken_Idempotent(t *testing.T) {
	for _, tc := range allFixedPUA {
		first := RegisterToken(tc.token)
		second := RegisterToken(tc.token)
		if first != second {
			t.Errorf("RegisterToken(%q) not idempotent: first=%q, second=%q", tc.token, first, second)
		}
	}
}

// ---------------------------------------------------------------------------
// 3. Reverse mapping — PUAToToken
// ---------------------------------------------------------------------------

func TestPUAToToken_ReverseMapping(t *testing.T) {
	tests := []struct {
		r    rune
		want string
	}{
		{0xE000, "a:"},
		{0xE019, "N_m"},
		{0xE046, "tone1"},
		{0xE054, "t\u0283"},      // tʃ
		{0xE056, "\u025b\u0303"}, // ɛ̃
	}
	for _, tc := range tests {
		got, ok := PUAToToken(tc.r)
		if !ok {
			t.Errorf("PUAToToken(U+%04X) returned ok=false, want token %q", tc.r, tc.want)
			continue
		}
		if got != tc.want {
			t.Errorf("PUAToToken(U+%04X) = %q, want %q", tc.r, got, tc.want)
		}
	}
}

// TestPUAToToken_AllFixedEntries verifies reverse mapping for all 99 entries (PUA v2).
func TestPUAToToken_AllFixedEntries(t *testing.T) {
	for _, tc := range allFixedPUA {
		got, ok := PUAToToken(tc.want)
		if !ok {
			t.Errorf("PUAToToken(U+%04X) returned ok=false, want token %q (group %s)",
				tc.want, tc.token, tc.group)
			continue
		}
		if got != tc.token {
			t.Errorf("PUAToToken(U+%04X) = %q, want %q (group %s)",
				tc.want, got, tc.token, tc.group)
		}
	}
}

// TestPUAToToken_UnknownCodepoint ensures unknown codepoints return ok=false.
func TestPUAToToken_UnknownCodepoint(t *testing.T) {
	// 0xE01F is a reserved gap, 0xE053 is a reserved gap, 0xE100 is unallocated.
	for _, r := range []rune{0xE01F, 0xE053, 0xE100, 0xF000} {
		_, ok := PUAToToken(r)
		if ok {
			t.Errorf("PUAToToken(U+%04X) returned ok=true for unallocated codepoint", r)
		}
	}
}

// TestPUAToToken_Roundtrip verifies token -> PUA -> token roundtrip for all fixed entries.
func TestPUAToToken_Roundtrip(t *testing.T) {
	for _, tc := range allFixedPUA {
		mapped := RegisterToken(tc.token)
		r, _ := utf8.DecodeRuneInString(mapped)
		got, ok := PUAToToken(r)
		if !ok {
			t.Errorf("roundtrip failed for %q: PUAToToken(U+%04X) returned ok=false", tc.token, r)
			continue
		}
		if got != tc.token {
			t.Errorf("roundtrip failed for %q: RegisterToken -> U+%04X -> PUAToToken = %q",
				tc.token, r, got)
		}
	}
}

// ---------------------------------------------------------------------------
// 4. MapSequence
// ---------------------------------------------------------------------------

func TestMapSequence(t *testing.T) {
	input := []string{"a:", "k", "o", "N_m"}
	got := MapSequence(input)
	expected := []string{"\uE000", "k", "o", "\uE019"}
	if len(got) != len(expected) {
		t.Fatalf("MapSequence length = %d, want %d", len(got), len(expected))
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("MapSequence[%d] = %q, want %q", i, got[i], expected[i])
		}
	}
}

// TestMapSequence_Empty verifies that MapSequence handles an empty input.
func TestMapSequence_Empty(t *testing.T) {
	got := MapSequence(nil)
	if len(got) != 0 {
		t.Errorf("MapSequence(nil) returned %d items, want 0", len(got))
	}
	got = MapSequence([]string{})
	if len(got) != 0 {
		t.Errorf("MapSequence([]) returned %d items, want 0", len(got))
	}
}

// TestMapSequence_MixedLanguages tests a sequence containing tokens from
// multiple language groups (JA + ZH + FR).
func TestMapSequence_MixedLanguages(t *testing.T) {
	input := []string{
		"a:",           // JA 0xE000
		"k",            // single char
		"tone1",        // ZH 0xE046
		"\u025b\u0303", // FR ɛ̃ 0xE056
	}
	got := MapSequence(input)
	expected := []string{
		string(rune(0xE000)),
		"k",
		string(rune(0xE046)),
		string(rune(0xE056)),
	}
	if len(got) != len(expected) {
		t.Fatalf("MapSequence length = %d, want %d", len(got), len(expected))
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("MapSequence[%d] = %q, want %q", i, got[i], expected[i])
		}
	}
}

// ---------------------------------------------------------------------------
// 5. Dynamic PUA allocation
// ---------------------------------------------------------------------------

func TestRegisterToken_DynamicPUA(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	// Unknown multi-char token should get dynamically allocated.
	token := "xx_unknown"
	mapped := RegisterToken(token)

	// Should be a single rune (PUA codepoint), not the original multi-char token.
	if utf8.RuneCountInString(mapped) != 1 {
		t.Fatalf("RegisterToken(%q) returned %q (len=%d runes), want single rune",
			token, mapped, utf8.RuneCountInString(mapped))
	}

	r, _ := utf8.DecodeRuneInString(mapped)
	if r != 0xE065 {
		t.Errorf("RegisterToken(%q) allocated U+%04X, want U+E065", token, r)
	}

	// Calling again with the same token should return the same mapping.
	mapped2 := RegisterToken(token)
	if mapped2 != mapped {
		t.Errorf("RegisterToken(%q) second call = %q, want %q (same as first)", token, mapped2, mapped)
	}

	// Reverse mapping should work.
	got, ok := PUAToToken(r)
	if !ok {
		t.Errorf("PUAToToken(U+%04X) returned ok=false after dynamic allocation", r)
	}
	if got != token {
		t.Errorf("PUAToToken(U+%04X) = %q, want %q", r, got, token)
	}

	if DynamicPUACount() != 1 {
		t.Errorf("DynamicPUACount() = %d, want 1", DynamicPUACount())
	}
}

// TestRegisterToken_DynamicPUA_Sequential verifies sequential dynamic allocations
// get consecutive PUA codepoints starting at 0xE065.
func TestRegisterToken_DynamicPUA_Sequential(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	tokens := []string{"dyn_a", "dyn_b", "dyn_c"}
	for i, tok := range tokens {
		mapped := RegisterToken(tok)
		r, _ := utf8.DecodeRuneInString(mapped)
		expectedR := rune(0xE065 + i)
		if r != expectedR {
			t.Errorf("RegisterToken(%q) = U+%04X, want U+%04X (sequential allocation #%d)",
				tok, r, expectedR, i)
		}
	}

	if DynamicPUACount() != 3 {
		t.Errorf("DynamicPUACount() = %d, want 3", DynamicPUACount())
	}
}

// TestRegisterToken_DynamicPUA_DoesNotShadowFixed ensures dynamic allocation
// never overwrites fixed PUA entries.
func TestRegisterToken_DynamicPUA_DoesNotShadowFixed(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	// Register several dynamic tokens.
	for i := range 10 {
		RegisterToken(fmt.Sprintf("shadow_test_%d", i))
	}

	// Verify all fixed PUA entries are still intact.
	for _, tc := range allFixedPUA {
		got := RegisterToken(tc.token)
		expected := string(tc.want)
		if got != expected {
			t.Errorf("after dynamic allocation, RegisterToken(%q) = %q, want PUA U+%04X",
				tc.token, got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// 6. Thread safety for dynamic PUA allocation
// ---------------------------------------------------------------------------

func TestRegisterToken_DynamicPUA_ThreadSafety(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	const goroutines = 50
	var wg sync.WaitGroup
	wg.Add(goroutines)

	results := make([]string, goroutines)
	for i := range goroutines {
		go func(idx int) {
			defer wg.Done()
			// Each goroutine registers the same token; all should get the same mapping.
			results[idx] = RegisterToken("concurrent_test_token")
		}(i)
	}
	wg.Wait()

	// All results should be identical.
	for i := 1; i < goroutines; i++ {
		if results[i] != results[0] {
			t.Errorf("goroutine %d got %q, goroutine 0 got %q", i, results[i], results[0])
		}
	}

	// Should have allocated exactly 1 dynamic PUA codepoint.
	if DynamicPUACount() != 1 {
		t.Errorf("DynamicPUACount() = %d, want 1 (concurrent registration of same token)", DynamicPUACount())
	}
}

// TestRegisterToken_DynamicPUA_ThreadSafety_DistinctTokens verifies concurrent
// registration of DIFFERENT tokens produces unique, non-overlapping codepoints.
func TestRegisterToken_DynamicPUA_ThreadSafety_DistinctTokens(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	const goroutines = 100
	var wg sync.WaitGroup
	wg.Add(goroutines)

	results := make([]string, goroutines)
	for i := range goroutines {
		go func(idx int) {
			defer wg.Done()
			results[idx] = RegisterToken(fmt.Sprintf("distinct_token_%d", idx))
		}(i)
	}
	wg.Wait()

	// Every result should be a single rune.
	for i, r := range results {
		if utf8.RuneCountInString(r) != 1 {
			t.Errorf("goroutine %d: result %q is not a single rune", i, r)
		}
	}

	// All results should be unique (no two goroutines got the same PUA codepoint).
	seen := make(map[string]int, goroutines)
	for i, r := range results {
		if prev, ok := seen[r]; ok {
			t.Errorf("goroutine %d and %d both got %q", prev, i, r)
		}
		seen[r] = i
	}

	if DynamicPUACount() != goroutines {
		t.Errorf("DynamicPUACount() = %d, want %d", DynamicPUACount(), goroutines)
	}
}

// TestPUAToToken_ConcurrentReadDuringDynamicWrite tests that PUAToToken can
// safely read while RegisterToken writes dynamic entries.
func TestPUAToToken_ConcurrentReadDuringDynamicWrite(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	const goroutines = 50
	var wg sync.WaitGroup
	wg.Add(goroutines * 2)

	// Half goroutines write dynamic PUA entries.
	for i := range goroutines {
		go func(idx int) {
			defer wg.Done()
			RegisterToken(fmt.Sprintf("concurrent_rw_%d", idx))
		}(i)
	}

	// Other half goroutines read fixed PUA entries concurrently.
	errors := make([]error, goroutines)
	for i := range goroutines {
		go func(idx int) {
			defer wg.Done()
			tc := allFixedPUA[idx%len(allFixedPUA)]
			got, ok := PUAToToken(tc.want)
			if !ok {
				errors[idx] = fmt.Errorf("PUAToToken(U+%04X) returned ok=false during concurrent write", tc.want)
			} else if got != tc.token {
				errors[idx] = fmt.Errorf("PUAToToken(U+%04X) = %q, want %q during concurrent write", tc.want, got, tc.token)
			}
		}(i)
	}
	wg.Wait()

	for _, err := range errors {
		if err != nil {
			t.Error(err)
		}
	}
}

// ---------------------------------------------------------------------------
// 7. ResetDynamicPUA
// ---------------------------------------------------------------------------

func TestResetDynamicPUA(t *testing.T) {
	ResetDynamicPUA()

	RegisterToken("reset_test_token")
	if DynamicPUACount() != 1 {
		t.Fatalf("DynamicPUACount() = %d before reset, want 1", DynamicPUACount())
	}

	ResetDynamicPUA()
	if DynamicPUACount() != 0 {
		t.Errorf("DynamicPUACount() = %d after reset, want 0", DynamicPUACount())
	}

	// After reset, the same starting PUA codepoint should be reused.
	mapped := RegisterToken("reset_test_token_2")
	r, _ := utf8.DecodeRuneInString(mapped)
	if r != 0xE065 {
		t.Errorf("after reset, first dynamic allocation = U+%04X, want U+E065", r)
	}

	ResetDynamicPUA()
}

// TestResetDynamicPUA_PreservesFixed ensures reset does not affect fixed PUA entries.
func TestResetDynamicPUA_PreservesFixed(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	// Register some dynamic tokens.
	RegisterToken("preserve_test_1")
	RegisterToken("preserve_test_2")

	ResetDynamicPUA()

	// All fixed entries should still work.
	for _, tc := range allFixedPUA {
		got := RegisterToken(tc.token)
		expected := string(tc.want)
		if got != expected {
			t.Errorf("after reset, RegisterToken(%q) = %q, want PUA U+%04X", tc.token, got, tc.want)
		}
	}
}

// TestResetDynamicPUA_ClearsReversePUA ensures reset properly removes
// dynamic entries from reversePUA.
func TestResetDynamicPUA_ClearsReversePUA(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	// Register a dynamic token and remember its codepoint.
	mapped := RegisterToken("reverse_clear_test")
	r, _ := utf8.DecodeRuneInString(mapped)

	// Before reset, reverse mapping should work.
	_, ok := PUAToToken(r)
	if !ok {
		t.Fatal("PUAToToken returned ok=false before reset for dynamic entry")
	}

	ResetDynamicPUA()

	// After reset, reverse mapping should fail.
	_, ok = PUAToToken(r)
	if ok {
		t.Error("PUAToToken returned ok=true after reset for cleared dynamic entry")
	}
}

// ---------------------------------------------------------------------------
// 8. TokensToIDs
// ---------------------------------------------------------------------------

func TestTokensToIDs(t *testing.T) {
	idMap := map[string][]int64{
		"\uE000": {10}, // a: -> PUA
		"k":      {20},
		"o":      {30},
		"\uE019": {40}, // N_m -> PUA
	}
	tokens := []string{"a:", "k", "o", "N_m"}
	got := TokensToIDs(tokens, idMap)
	expected := []int64{10, 20, 30, 40}
	if len(got) != len(expected) {
		t.Fatalf("TokensToIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("TokensToIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestTokensToIDs_EmptyInput verifies TokensToIDs with no tokens.
func TestTokensToIDs_EmptyInput(t *testing.T) {
	idMap := map[string][]int64{"a": {1}}
	got := TokensToIDs(nil, idMap)
	if len(got) != 0 {
		t.Errorf("TokensToIDs(nil) returned %v, want empty", got)
	}
}

// TestTokensToIDs_UnknownTokenSkipped verifies unknown tokens are skipped.
func TestTokensToIDs_UnknownTokenSkipped(t *testing.T) {
	idMap := map[string][]int64{
		"k": {20},
	}
	tokens := []string{"k", "UNKNOWN", "k"}
	got := TokensToIDs(tokens, idMap)
	expected := []int64{20, 20}
	if len(got) != len(expected) {
		t.Fatalf("TokensToIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("TokensToIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestTokensToIDs_MultiIDPhoneme verifies that phonemes with multi-element ID lists
// (e.g., id_map["x"] = [5, 6]) are expanded correctly.
func TestTokensToIDs_MultiIDPhoneme(t *testing.T) {
	// Use single-char key "x" which passes through RegisterToken unchanged,
	// and map it to a multi-element ID list to verify expansion.
	idMap := map[string][]int64{
		"a": {1},
		"x": {10, 11, 12},
		"b": {2},
	}
	tokens := []string{"a", "x", "b"}
	got := TokensToIDs(tokens, idMap)
	expected := []int64{1, 10, 11, 12, 2}
	if len(got) != len(expected) {
		t.Fatalf("TokensToIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("TokensToIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestTokensToIDs_ChineseTokens verifies Chinese IPA tokens are correctly
// mapped through PUA to IDs.
func TestTokensToIDs_ChineseTokens(t *testing.T) {
	idMap := map[string][]int64{
		string(rune(0xE023)): {50}, // tɕ
		string(rune(0xE028)): {51}, // aɪ
		string(rune(0xE046)): {52}, // tone1
	}
	tokens := []string{"t\u0255", "a\u026a", "tone1"} // tɕ, aɪ, tone1
	got := TokensToIDs(tokens, idMap)
	expected := []int64{50, 51, 52}
	if len(got) != len(expected) {
		t.Fatalf("TokensToIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("TokensToIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestTokensToIDs_SpecialTokens verifies BOS, EOS, pad, and question markers.
func TestTokensToIDs_SpecialTokens(t *testing.T) {
	idMap := map[string][]int64{
		"_":                  {0},
		"^":                  {1},
		"$":                  {2},
		"?":                  {3},
		string(rune(0xE016)): {4}, // ?!
		string(rune(0xE017)): {5}, // ?.
		string(rune(0xE018)): {6}, // ?~
		"#":                  {7},
		"[":                  {8},
		"]":                  {9},
	}
	tokens := []string{"^", "_", "#", "[", "]", "?!", "?.", "?~", "$", "?"}
	got := TokensToIDs(tokens, idMap)
	expected := []int64{1, 0, 7, 8, 9, 4, 5, 6, 2, 3}
	if len(got) != len(expected) {
		t.Fatalf("TokensToIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("TokensToIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// ---------------------------------------------------------------------------
// 9. PostProcessIDs — pad interspersing, BOS/EOS
// ---------------------------------------------------------------------------

func TestPostProcessIDs_BasicPadding(t *testing.T) {
	ids := []int64{10, 11, 12}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	got, _ := PostProcessIDs(ids, nil, idMap, "$")
	// Expected: BOS(1) + pad(0) + 10 + pad(0) + 11 + pad(0) + 12 + pad(0) + EOS(2)
	expected := []int64{1, 0, 10, 0, 11, 0, 12, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

func TestPostProcessIDs_SkipDoublePad(t *testing.T) {
	// 0 is the pad token; padding should NOT be inserted after it.
	ids := []int64{10, 0, 11}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	got, _ := PostProcessIDs(ids, nil, idMap, "$")
	// Expected: BOS(1) + pad(0) + 10 + pad(0) + 0 + 11 + pad(0) + EOS(2)
	// The existing 0 (pad) does NOT get an additional pad after it.
	expected := []int64{1, 0, 10, 0, 0, 11, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

func TestPostProcessIDs_CustomEOS(t *testing.T) {
	ids := []int64{10, 11}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
		"?": {3},
	}
	got, _ := PostProcessIDs(ids, nil, idMap, "?")
	// Should end with EOS=3 instead of 2.
	lastID := got[len(got)-1]
	if lastID != 3 {
		t.Errorf("PostProcessIDs with custom EOS: last ID = %d, want 3; got %v", lastID, got)
	}
}

// TestPostProcessIDs_QuestionMarkerEOS verifies EOS tokens for question types.
func TestPostProcessIDs_QuestionMarkerEOS(t *testing.T) {
	idMap := map[string][]int64{
		"_":                  {0},
		"^":                  {1},
		"$":                  {2},
		"?":                  {3},
		string(rune(0xE016)): {4}, // ?!
		string(rune(0xE017)): {5}, // ?.
		string(rune(0xE018)): {6}, // ?~
	}

	tests := []struct {
		eosToken string
		wantLast int64
	}{
		{"$", 2},
		{"?", 3},
		{string(rune(0xE016)), 4}, // ?!
		{string(rune(0xE017)), 5}, // ?.
		{string(rune(0xE018)), 6}, // ?~
	}

	for _, tc := range tests {
		ids := []int64{10}
		got, _ := PostProcessIDs(ids, nil, idMap, tc.eosToken)
		lastID := got[len(got)-1]
		if lastID != tc.wantLast {
			t.Errorf("PostProcessIDs(eosToken=%q): last ID = %d, want %d; got %v",
				tc.eosToken, lastID, tc.wantLast, got)
		}
	}
}

// TestPostProcessIDs_FallbackEOS verifies that if the custom EOS token is not
// in the ID map, it falls back to "$".
func TestPostProcessIDs_FallbackEOS(t *testing.T) {
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	ids := []int64{10}
	// "?" is not in idMap, should fall back to "$" (ID 2).
	got, _ := PostProcessIDs(ids, nil, idMap, "?")
	lastID := got[len(got)-1]
	if lastID != 2 {
		t.Errorf("PostProcessIDs with missing EOS token: last ID = %d, want 2 (fallback to $); got %v",
			lastID, got)
	}
}

// TestPostProcessIDs_EmptyInput verifies that empty phoneme IDs still produce BOS + pad + EOS.
func TestPostProcessIDs_EmptyInput(t *testing.T) {
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	got, _ := PostProcessIDs(nil, nil, idMap, "$")
	// Expected: BOS(1) + pad(0) + EOS(2)
	expected := []int64{1, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs(empty) length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs(empty)[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestPostProcessIDs_SinglePhoneme verifies the pattern for a single phoneme input.
func TestPostProcessIDs_SinglePhoneme(t *testing.T) {
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	ids := []int64{42}
	got, _ := PostProcessIDs(ids, nil, idMap, "$")
	// Expected: BOS(1) + pad(0) + 42 + pad(0) + EOS(2)
	expected := []int64{1, 0, 42, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs(single) length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs(single)[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestPostProcessIDs_ConsecutivePads verifies behavior when input contains
// consecutive pad tokens.
func TestPostProcessIDs_ConsecutivePads(t *testing.T) {
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	ids := []int64{0, 0, 10}
	got, _ := PostProcessIDs(ids, nil, idMap, "$")
	// 0 is pad, no pad inserted after pads.
	// Expected: BOS(1) + pad(0) + 0 + 0 + 10 + pad(0) + EOS(2)
	expected := []int64{1, 0, 0, 0, 10, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs(consecutive pads) length = %d, want %d; got %v",
			len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs(consecutive pads)[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

// TestPostProcessIDs_ProsodyAlignment verifies prosody array stays aligned with IDs.
func TestPostProcessIDs_ProsodyAlignment(t *testing.T) {
	ids := []int64{10, 11}
	prosody := []*ProsodyInfo{
		{A1: 1, A2: 2, A3: 3},
		{A1: 4, A2: 5, A3: 6},
	}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	gotIDs, gotProsody := PostProcessIDs(ids, prosody, idMap, "$")

	// IDs and prosody must have the same length.
	if len(gotIDs) != len(gotProsody) {
		t.Fatalf("PostProcessIDs: IDs len=%d, prosody len=%d (must be equal)",
			len(gotIDs), len(gotProsody))
	}

	// BOS, pad, and EOS positions should have nil prosody.
	// Expected IDs: [1, 0, 10, 0, 11, 0, 2]
	// Expected prosody: [nil, nil, {1,2,3}, nil, {4,5,6}, nil, nil]
	if gotProsody[0] != nil {
		t.Error("BOS position should have nil prosody")
	}
	if gotProsody[1] != nil {
		t.Error("pad after BOS should have nil prosody")
	}
	if gotProsody[2] == nil || gotProsody[2].A1 != 1 {
		t.Errorf("phoneme position 2: prosody = %v, want A1=1", gotProsody[2])
	}
	if gotProsody[3] != nil {
		t.Error("pad position should have nil prosody")
	}
	if gotProsody[4] == nil || gotProsody[4].A1 != 4 {
		t.Errorf("phoneme position 4: prosody = %v, want A1=4", gotProsody[4])
	}
	if gotProsody[len(gotProsody)-1] != nil {
		t.Error("EOS position should have nil prosody")
	}
}

// ---------------------------------------------------------------------------
// 10. Unicode normalization and combining character edge cases
// ---------------------------------------------------------------------------

// TestFixedPUA_CombiningCharacters verifies that tokens with Unicode combining
// characters are stored with the correct byte representation. These are the
// most error-prone entries due to NFC/NFD normalization differences.
func TestFixedPUA_CombiningCharacters(t *testing.T) {
	// Entries that use combining characters (diacritics after base char).
	combiningEntries := []struct {
		token   string
		wantPUA rune
		desc    string
	}{
		// Korean tense: base + U+0348 (combining double acute accent above)
		{"p\u0348", 0xE04B, "KO p͈ (p + combining double acute accent)"},
		{"t\u0348", 0xE04C, "KO t͈"},
		{"k\u0348", 0xE04D, "KO k͈"},
		{"s\u0348", 0xE04E, "KO s͈"},
		{"t\u0348\u0255", 0xE04F, "KO t͈ɕ"},
		// Korean unreleased: base + U+031A (combining left angle above)
		{"k\u031a", 0xE050, "KO k̚"},
		{"t\u031a", 0xE051, "KO t̚"},
		{"p\u031a", 0xE052, "KO p̚"},
		// French nasal: vowel + U+0303 (combining tilde)
		{"\u025b\u0303", 0xE056, "FR ɛ̃ (ɛ + combining tilde)"},
		{"\u0251\u0303", 0xE057, "FR ɑ̃ (ɑ + combining tilde)"},
		{"\u0254\u0303", 0xE058, "FR ɔ̃ (ɔ + combining tilde)"},
		// Chinese syllabic: base + U+0329 (combining vertical line below)
		{"\u027b\u0329", 0xE045, "ZH ɻ̩ (ɻ + combining vertical line below)"},
	}
	for _, tc := range combiningEntries {
		got, ok := fixedPUA[tc.token]
		if !ok {
			t.Errorf("fixedPUA missing %s: token %q not found", tc.desc, tc.token)
			continue
		}
		if got != tc.wantPUA {
			t.Errorf("fixedPUA %s: got U+%04X, want U+%04X", tc.desc, got, tc.wantPUA)
		}

		// Also verify through RegisterToken.
		mapped := RegisterToken(tc.token)
		if mapped != string(tc.wantPUA) {
			t.Errorf("RegisterToken(%s) = %q, want PUA U+%04X", tc.desc, mapped, tc.wantPUA)
		}
	}
}

// TestFixedPUA_MultiCodepointTokenRuneCount verifies that multi-codepoint
// tokens (which contain combining characters) do indeed have RuneCount > 1
// and thus require PUA mapping.
func TestFixedPUA_MultiCodepointTokenRuneCount(t *testing.T) {
	for _, tc := range allFixedPUA {
		rc := utf8.RuneCountInString(tc.token)
		if rc <= 1 {
			t.Errorf("fixedPUA token %q (U+%04X, group %s) has rune count %d; expected >1 for PUA mapping",
				tc.token, tc.want, tc.group, rc)
		}
	}
}

// ---------------------------------------------------------------------------
// 11. Dynamic PUA space boundary
// ---------------------------------------------------------------------------

// TestDynamicPUA_StartsAfterFixed ensures dynamic allocation starts at 0xE065,
// which is past the last fixed codepoint (0xE064 = PT ɐ̃, PUA v2).
func TestDynamicPUA_StartsAfterFixed(t *testing.T) {
	ResetDynamicPUA()
	defer ResetDynamicPUA()

	mapped := RegisterToken("boundary_test_first_dynamic")
	r, _ := utf8.DecodeRuneInString(mapped)
	if r != 0xE065 {
		t.Errorf("first dynamic PUA = U+%04X, want U+E065", r)
	}
}

// TestMaxPUA_Constant verifies the BMP PUA upper bound constant.
func TestMaxPUA_Constant(t *testing.T) {
	if maxPUA != 0xF8FF {
		t.Errorf("maxPUA = U+%04X, want U+F8FF", maxPUA)
	}
}

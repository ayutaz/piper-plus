package phonemize

import (
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// Helper: extract raw phonemes from ptConvert (pre-PUA, pre-MapSequence).
// ---------------------------------------------------------------------------

func ptPhonemes(word string) ([]string, int) {
	return ptConvert([]rune(strings.ToLower(word)))
}

// joinPh joins phoneme slices for readable comparison.
func joinPh(ph []string) string { return strings.Join(ph, " ") }

// ---------------------------------------------------------------------------
// 1. Digraphs: lh->ʎ, nh->ɲ, ch->ʃ, rr->ʁ, ss->s
// ---------------------------------------------------------------------------

func TestPtConvert_Digraphs(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// lh -> ʎ
		{"filho", []string{"f", "i", "ʎ", "u"}},
		{"trabalho", []string{"t", "ʁ", "a", "b", "a", "ʎ", "u"}},
		// nh -> ɲ (vowel before nh is NOT nasal -- nh exception)
		{"vinho", []string{"v", "i", "ɲ", "u"}},
		{"banho", []string{"b", "a", "ɲ", "u"}},
		// ch -> ʃ
		{"chave", []string{"ʃ", "a", "v", "i"}},
		// rr -> ʁ
		{"carro", []string{"k", "a", "ʁ", "u"}},
		// ss -> s
		{"passo", []string{"p", "a", "s", "u"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2. Nasal vowels: tilde, V+m/n at word-end, V+m/n before consonant
// ---------------------------------------------------------------------------

func TestPtConvert_NasalVowels(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// Tilde nasal: ã -> ã  (final o after ã is unstressed -> u via BRPost)
		{"mão", []string{"m", "ã", "u"}},
		{"não", []string{"n", "ã", "u"}},
		{"irmã", []string{"i", "ʁ", "m", "ã"}},
		// Tilde nasal: õ -> õ  (final e -> i via BRPost)
		{"põe", []string{"p", "õ", "i"}},
		// Vowel + m at word end -> nasal vowel (absorb m)
		{"bom", []string{"b", "õ"}},
		{"sim", []string{"s", "ĩ"}},
		{"bem", []string{"b", "ẽ"}},
		{"um", []string{"ũ"}},
		// Vowel + m before consonant -> nasal vowel (absorb m)
		{"campo", []string{"k", "ã", "p", "u"}},
		// Vowel + n before consonant -> nasal vowel (absorb n)
		{"gente", []string{"ʒ", "ẽ", "tʃ", "i"}},
		// nh digraph: vowel before nh is NOT nasal
		{"vinha", []string{"v", "i", "ɲ", "a"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 3. Coda-l vocalization: l->w
// ---------------------------------------------------------------------------

func TestPtConvert_CodaL(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// l at word end -> w
		{"brasil", []string{"b", "ʁ", "a", "z", "i", "w"}},
		{"sol", []string{"s", "o", "w"}},
		{"mal", []string{"m", "a", "w"}},
		// l before consonant -> w
		{"alto", []string{"a", "w", "t", "u"}},
		// l before vowel -> l (onset, NOT coda)
		{"bolo", []string{"b", "o", "l", "u"}},
		{"lá", []string{"l", "a"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 4. Consonant conversions: r, s, x, c, ç, g, j, t/d palatalization
// ---------------------------------------------------------------------------

func TestPtConvert_Consonants(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// r: word-initial -> ʁ
		{"rio", []string{"ʁ", "i", "u"}},
		// r: intervocalic -> ɾ
		{"cara", []string{"k", "a", "ɾ", "a"}},
		// s: intervocalic -> z
		{"casa", []string{"k", "a", "z", "a"}},
		// s: word-initial -> s (plain 'o' with stress = 'o', not ɔ)
		{"sol", []string{"s", "o", "w"}},
		// x: word-initial -> ʃ
		{"xadrez", []string{"ʃ", "a", "d", "ʁ", "e", "z"}},
		// c before e/i -> s
		{"cidade", []string{"s", "i", "d", "a", "dʒ", "i"}},
		// c before a/o/u -> k
		{"casa", []string{"k", "a", "z", "a"}},
		// ç -> s  (final unstressed o -> u)
		{"ação", []string{"a", "s", "ã", "u"}},
		// g before e/i -> ʒ
		{"gente", []string{"ʒ", "ẽ", "tʃ", "i"}},
		// g before a/o/u -> ɡ
		{"gato", []string{"ɡ", "a", "t", "u"}},
		// j -> ʒ
		{"hoje", []string{"o", "ʒ", "i"}},
		// t before i -> tʃ (palatalization)
		{"tipo", []string{"tʃ", "i", "p", "u"}},
		// d before i -> dʒ (palatalization)
		{"dia", []string{"dʒ", "i", "a"}},
		// h is silent (plain 'o' with stress = 'o', not ɔ; only ó -> ɔ)
		{"hora", []string{"o", "ɾ", "a"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 5. Special characters: ç, accent marks (acute/circumflex/tilde)
// ---------------------------------------------------------------------------

func TestPtConvert_SpecialChars(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// ç always -> s
		{"cabeça", []string{"k", "a", "b", "e", "s", "a"}},
		// r after consonant (c) is not intervocalic -> ʁ
		{"criança", []string{"k", "ʁ", "i", "ã", "s", "a"}},
		// Acute accent: open vowels (é->ɛ, ó->ɔ)
		{"café", []string{"k", "a", "f", "ɛ"}},
		{"avó", []string{"a", "v", "ɔ"}},
		// Circumflex: closed vowels (ê->e, ô->o)
		{"você", []string{"v", "o", "s", "e"}},
		// Tilde: nasal vowels (final unstressed o -> u)
		{"coração", []string{"k", "o", "ɾ", "a", "s", "ã", "u"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 6. Complex digraphs: qu, gu, ou, sc
// ---------------------------------------------------------------------------

func TestPtConvert_DigraphsComplex(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// qu before e/i -> k (u silent)
		{"queijo", []string{"k", "e", "i", "ʒ", "u"}},
		// qu before e -> k; plain 'e' with stress is 'e' (not ɛ -- only é gives ɛ)
		{"quero", []string{"k", "e", "ɾ", "u"}},
		// qu before a/o -> kw
		{"quando", []string{"k", "w", "ã", "d", "u"}},
		{"quatro", []string{"k", "w", "a", "t", "ʁ", "u"}},
		// gu before e/i -> ɡ (u silent); plain 'e' with stress is 'e' (not ɛ)
		{"guerra", []string{"ɡ", "e", "ʁ", "a"}},
		// ou -> o (BR reduction); r after 'ou' is intervocalic (u before, o after) -> ɾ
		{"ouro", []string{"o", "ɾ", "u"}},
		{"pouco", []string{"p", "o", "k", "u"}},
		// sc before e/i -> s
		{"nascer", []string{"n", "a", "s", "e", "ʁ"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 7. BR post-processing: unstressed final e->i, o->u; te->tʃi, de->dʒi
// ---------------------------------------------------------------------------

func TestPtConvert_BRPostprocessing(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// Unstressed final e -> i (r after consonant = ʁ, not ɾ)
		{"grande", []string{"ɡ", "ʁ", "ã", "dʒ", "i"}},
		// Unstressed final o -> u
		{"livro", []string{"l", "i", "v", "ʁ", "u"}},
		// te# -> tʃi (final unstressed)
		{"gente", []string{"ʒ", "ẽ", "tʃ", "i"}},
		// de# -> dʒi (final unstressed)
		{"cidade", []string{"s", "i", "d", "a", "dʒ", "i"}},
		// Stressed final e (acute accent) stays as ɛ
		{"café", []string{"k", "a", "f", "ɛ"}},
		// Stressed final o (acute accent) stays as ɔ
		{"avó", []string{"a", "v", "ɔ"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 8. Stress position detection
// ---------------------------------------------------------------------------

func TestPtStressPos(t *testing.T) {
	tests := []struct {
		word string
		want int // stress position from end (0 = last, 1 = penultimate)
	}{
		// Accented: stress on accented syllable
		{"café", 0},   // final: ca-FÉ
		{"música", 2}, // antepenultimate: MÚ-si-ca
		{"avó", 0},    // final: a-VÓ
		{"você", 0},   // final: vo-CÊ
		// Default rules: ends in vowel -> penultimate
		{"casa", 1}, // CA-sa
		{"gato", 1}, // GA-to
		// Default rules: ends in consonant -> ultimate
		{"brasil", 0}, // bra-SIL
		{"feliz", 0},  // fe-LIZ
		// Ends in -am, -em -> penultimate
		{"falam", 1}, // FA-lam
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got := ptStressPos([]rune(tc.word))
			if got != tc.want {
				t.Errorf("ptStressPos(%q) = %d, want %d", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 9. Vowel group counting (digraph-aware)
// ---------------------------------------------------------------------------

func TestPtCountVG(t *testing.T) {
	tests := []struct {
		word string
		want int
	}{
		{"casa", 2},   // ca-sa
		{"queijo", 3}, // qu(silent)-e-i-j-o: e, i, o = 3 groups
		{"guerra", 2}, // gue-rra (gu: silent u)
		{"ouro", 2},   // ou(1 group)-r-o(1 group) = 2 groups
		{"quando", 2}, // quan-do (qu before a: u is consonantal, skipped)
		{"a", 1},
		{"brasil", 2}, // bra-sil
		{"música", 3}, // mú-si-ca
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got := ptCountVG([]rune(tc.word))
			if got != tc.want {
				t.Errorf("ptCountVG(%q) = %d, want %d", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 10. Stress index in phoneme array
// ---------------------------------------------------------------------------

func TestPtConvert_StressIndex(t *testing.T) {
	tests := []struct {
		word    string
		wantIdx int
	}{
		// café: stress on final ɛ -> index 3 (k=0, a=1, f=2, ɛ=3)
		{"café", 3},
		// casa: stress on first a -> index 1 (k=0, a=1, z=2, a=3)
		{"casa", 1},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			_, si := ptPhonemes(tc.word)
			if si != tc.wantIdx {
				t.Errorf("ptConvert(%q) stress_idx = %d, want %d", tc.word, si, tc.wantIdx)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 11. Edge cases: empty input, single character, punctuation only
// ---------------------------------------------------------------------------

func TestPtPhonemize_EdgeCases(t *testing.T) {
	p := NewPortuguesePhonemizer()

	t.Run("empty_string", func(t *testing.T) {
		res, err := p.PhonemizeWithProsody("")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(res.Tokens) != 0 {
			t.Errorf("empty input should produce no tokens, got %v", res.Tokens)
		}
	})

	t.Run("whitespace_only", func(t *testing.T) {
		res, err := p.PhonemizeWithProsody("   ")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(res.Tokens) != 0 {
			t.Errorf("whitespace-only input should produce no tokens, got %v", res.Tokens)
		}
	})

	t.Run("punctuation_only", func(t *testing.T) {
		res, err := p.PhonemizeWithProsody("!?")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(res.Tokens) == 0 {
			t.Error("punctuation input should produce tokens")
		}
	})

	t.Run("single_vowel", func(t *testing.T) {
		res, err := p.PhonemizeWithProsody("a")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(res.Tokens) == 0 {
			t.Error("single vowel should produce tokens")
		}
	})
}

// ---------------------------------------------------------------------------
// 12. Sentence-level PhonemizeWithProsody: structure checks
// ---------------------------------------------------------------------------

func TestPtPhonemize_Sentence(t *testing.T) {
	p := NewPortuguesePhonemizer()

	t.Run("bom_dia", func(t *testing.T) {
		res, err := p.PhonemizeWithProsody("Bom dia!")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(res.Tokens) != len(res.Prosody) {
			t.Errorf("tokens/prosody length mismatch: %d vs %d",
				len(res.Tokens), len(res.Prosody))
		}
		// Should contain a space between words
		hasSpace := false
		for _, tok := range res.Tokens {
			if tok == " " {
				hasSpace = true
				break
			}
		}
		if !hasSpace {
			t.Error("multi-word sentence should contain space token")
		}
		if res.EOSToken != "!" {
			t.Errorf("EOSToken = %q, want \"!\"", res.EOSToken)
		}
	})

	t.Run("olá_como_você_está", func(t *testing.T) {
		res, err := p.PhonemizeWithProsody("Olá, como você está?")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(res.Tokens) == 0 {
			t.Error("expected non-empty tokens")
		}
		if len(res.Tokens) != len(res.Prosody) {
			t.Errorf("tokens/prosody length mismatch: %d vs %d",
				len(res.Tokens), len(res.Prosody))
		}
	})
}

// ---------------------------------------------------------------------------
// 13. Prosody: stress marking (a2) consistency
// ---------------------------------------------------------------------------

func TestPtProsody_StressMarking(t *testing.T) {
	p := NewPortuguesePhonemizer()

	// "Brasil" is a content word (not in ptFunc). Exactly one phoneme should
	// have a2=2.
	res, err := p.PhonemizeWithProsody("Brasil")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	stressCount := 0
	for _, pr := range res.Prosody {
		if pr != nil && pr.A2 == 2 {
			stressCount++
		}
	}
	if stressCount != 1 {
		t.Errorf("'Brasil' should have exactly 1 stressed phoneme (a2=2), got %d", stressCount)
	}
}

// ---------------------------------------------------------------------------
// 14. Nasal coda removal post-processing
// ---------------------------------------------------------------------------

func TestPtRmNasCoda(t *testing.T) {
	tests := []struct {
		name  string
		input []string
		want  []string
	}{
		{
			name:  "nasal_vowel_plus_m_at_end",
			input: []string{"b", "õ", "m"},
			want:  []string{"b", "õ"},
		},
		{
			name:  "nasal_vowel_plus_n_at_end",
			input: []string{"b", "ẽ", "n"},
			want:  []string{"b", "ẽ"},
		},
		{
			name:  "no_removal_mid_word",
			input: []string{"k", "ã", "p", "u"},
			want:  []string{"k", "ã", "p", "u"},
		},
		{
			name:  "nasal_vowel_plus_m_before_punct",
			input: []string{"b", "õ", "m", "."},
			want:  []string{"b", "õ", "."},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := ptRmNasCoda(tc.input)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptRmNasCoda(%v) = %v, want %v", tc.input, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 15. Coda-l vocalization post-processing
// ---------------------------------------------------------------------------

func TestPtCodaL(t *testing.T) {
	tests := []struct {
		name  string
		input []string
		want  []string
	}{
		{
			name:  "l_at_end",
			input: []string{"s", "o", "l"},
			want:  []string{"s", "o", "w"},
		},
		{
			name:  "l_before_consonant",
			input: []string{"a", "l", "t", "u"},
			want:  []string{"a", "w", "t", "u"},
		},
		{
			name:  "l_before_vowel_stays",
			input: []string{"l", "a"},
			want:  []string{"l", "a"},
		},
		{
			name:  "l_before_space",
			input: []string{"m", "a", "l", " ", "d", "i", "a"},
			want:  []string{"m", "a", "w", " ", "d", "i", "a"},
		},
		{
			name:  "l_before_punct",
			input: []string{"m", "a", "l", "."},
			want:  []string{"m", "a", "w", "."},
		},
		{
			name:  "l_before_affricate_tʃ",
			input: []string{"a", "l", "tʃ", "i"},
			want:  []string{"a", "w", "tʃ", "i"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := ptCodaL(tc.input)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptCodaL(%v) = %v, want %v", tc.input, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 16. BR post-processing: te->tʃi, de->dʒi, e->i, o->u at word end
// ---------------------------------------------------------------------------

func TestPtBRPost(t *testing.T) {
	tests := []struct {
		name  string
		input []string
		si    int // stress index
		want  []string
	}{
		{
			name:  "final_te_unstressed",
			input: []string{"ʒ", "ẽ", "t", "e"},
			si:    1, // stress on ẽ
			want:  []string{"ʒ", "ẽ", "tʃ", "i"},
		},
		{
			name:  "final_de_unstressed",
			input: []string{"ɡ", "ɾ", "ã", "d", "e"},
			si:    2, // stress on ã
			want:  []string{"ɡ", "ɾ", "ã", "dʒ", "i"},
		},
		{
			name:  "final_e_unstressed_general",
			input: []string{"n", "o", "i", "t", "e"},
			si:    1, // stress on o
			want:  []string{"n", "o", "i", "tʃ", "i"},
		},
		{
			name:  "final_o_unstressed",
			input: []string{"ɡ", "a", "t", "o"},
			si:    1, // stress on a
			want:  []string{"ɡ", "a", "t", "u"},
		},
		{
			name:  "stressed_final_e_no_change",
			input: []string{"k", "a", "f", "ɛ"},
			si:    3, // stress on ɛ
			want:  []string{"k", "a", "f", "ɛ"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := ptBRPost(tc.input, tc.si)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptBRPost(%v, si=%d) = %v, want %v",
					tc.input, tc.si, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 17. Tokenizer: word/punct splitting
// ---------------------------------------------------------------------------

func TestPtTokenize(t *testing.T) {
	tests := []struct {
		input     string
		words     []string
		wantPuncs int
	}{
		{
			input:     "olá, mundo!",
			words:     []string{"olá", "mundo"},
			wantPuncs: 2, // comma and exclamation
		},
		{
			input:     "bom dia",
			words:     []string{"bom", "dia"},
			wantPuncs: 0,
		},
	}
	for _, tc := range tests {
		t.Run(tc.input, func(t *testing.T) {
			toks := ptTokenize(strings.ToLower(tc.input))
			var words []string
			var puncs int
			for _, tok := range toks {
				if tok.kind == tokenWord {
					words = append(words, tok.text)
				} else {
					puncs++
				}
			}
			if len(words) != len(tc.words) {
				t.Errorf("words count: got %d, want %d; words=%v",
					len(words), len(tc.words), words)
			}
			for i := range tc.words {
				if i < len(words) && words[i] != tc.words[i] {
					t.Errorf("word[%d] = %q, want %q", i, words[i], tc.words[i])
				}
			}
			if puncs != tc.wantPuncs {
				t.Errorf("punct count: got %d, want %d", puncs, tc.wantPuncs)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 18. Python reference parity: word-level conversions
//
// These verify Go ptConvert matches Python _convert_word. All expectations
// are traced through the Python code manually.
// ---------------------------------------------------------------------------

func TestPtConvert_PythonParity(t *testing.T) {
	tests := []struct {
		word string
		want []string
	}{
		// olá: o(penult stress), l, a(acute->open, but 'a' open='a')
		{"olá", []string{"o", "l", "a"}},
		// bola: b, o(stress, plain->o), l, a(unstressed final a stays)
		{"bola", []string{"b", "o", "l", "a"}},
		// peso: p, e(stress), z(intervocalic s), u(unstressed final o->u)
		{"peso", []string{"p", "e", "z", "u"}},
		// feliz: f, e, l, i, z (oxytone, stress on final)
		{"feliz", []string{"f", "e", "l", "i", "z"}},
		// mão: m, ã(tilde), u(unstressed final o->u)
		{"mão", []string{"m", "ã", "u"}},
		// pão: p, ã(tilde), u(unstressed final o->u)
		{"pão", []string{"p", "ã", "u"}},
		// bom: b, õ(nasal, absorbed m removed by ptRmNasCoda)
		{"bom", []string{"b", "õ"}},
		// sim: s, ĩ(nasal, absorbed m)
		{"sim", []string{"s", "ĩ"}},
		// brasil: b, ʁ(non-intervocalic), a, z(intervocalic s), i, w(coda-l)
		{"brasil", []string{"b", "ʁ", "a", "z", "i", "w"}},
		// alto: a, w(coda-l before consonant), t, u(unstressed final o->u)
		{"alto", []string{"a", "w", "t", "u"}},
		// tipo: tʃ(t before i), i, p, u(unstressed final o->u)
		{"tipo", []string{"tʃ", "i", "p", "u"}},
		// dia: dʒ(d before i), i, a
		{"dia", []string{"dʒ", "i", "a"}},
		// coração: k, o, ɾ(intervocalic), a, s(ç), ã(tilde), u(final o->u)
		{"coração", []string{"k", "o", "ɾ", "a", "s", "ã", "u"}},
		// português: p, o, ʁ(non-intervocalic), t, u, ɡ(gu before ê),
		// e(ê=circumflex=closed=e), s(final, not intervocalic)
		{"português", []string{"p", "o", "ʁ", "t", "u", "ɡ", "e", "s"}},
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			got, _ := ptPhonemes(tc.word)
			if joinPh(got) != joinPh(tc.want) {
				t.Errorf("ptConvert(%q) = %v, want %v", tc.word, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 19. PUA token mapping applied via PhonemizeWithProsody
// ---------------------------------------------------------------------------

func TestPtPhonemize_PUAMapping(t *testing.T) {
	p := NewPortuguesePhonemizer()

	// "tipo" produces tʃ which should be PUA-mapped to U+E054.
	res, err := p.PhonemizeWithProsody("tipo")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	foundTCh := false
	for _, tok := range res.Tokens {
		rs := []rune(tok)
		if len(rs) == 1 && rs[0] == 0xE054 {
			foundTCh = true
			break
		}
	}
	if !foundTCh {
		t.Errorf("expected PUA U+E054 for tʃ in tokens: %v", res.Tokens)
	}
}

// ---------------------------------------------------------------------------
// 20. LanguageCode returns "pt"
// ---------------------------------------------------------------------------

func TestPtLanguageCode(t *testing.T) {
	p := NewPortuguesePhonemizer()
	if got := p.LanguageCode(); got != "pt" {
		t.Errorf("LanguageCode() = %q, want \"pt\"", got)
	}
}

// ---------------------------------------------------------------------------
// 21. Function words get stress (matching Python reference)
//
// Go previously suppressed a2 stress for function words via ptFunc map.
// Python does NOT have this concept -- it always marks a2=2 at the stressed
// phoneme. The ptFunc map has been removed so Go matches Python.
// ---------------------------------------------------------------------------

func TestPtFuncWordStress(t *testing.T) {
	p := NewPortuguesePhonemizer()

	funcWords := []string{"de", "que", "com", "para", "em", "por", "se", "me", "um", "uma", "e", "ou"}

	for _, word := range funcWords {
		t.Run(word, func(t *testing.T) {
			res, err := p.PhonemizeWithProsody(word)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			hasStress := false
			for _, pr := range res.Prosody {
				if pr != nil && pr.A2 == 2 {
					hasStress = true
					break
				}
			}
			if !hasStress {
				t.Errorf("function word %q: expected a2=2 at stress position (Python parity), but all a2=0", word)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 21b. EOS token tracking from sentence-final punctuation
// ---------------------------------------------------------------------------

func TestPtEOSToken(t *testing.T) {
	p := NewPortuguesePhonemizer()

	tests := []struct {
		text    string
		wantEOS string
	}{
		{"Bom dia.", "$"},
		{"Bom dia!", "!"},
		{"Como vai?", "?"},
		{"Olá", "$"},
		{"Tudo bem?!", "!"},
	}
	for _, tc := range tests {
		t.Run(tc.text, func(t *testing.T) {
			res, err := p.PhonemizeWithProsody(tc.text)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if res.EOSToken != tc.wantEOS {
				t.Errorf("PhonemizeWithProsody(%q).EOSToken = %q, want %q",
					tc.text, res.EOSToken, tc.wantEOS)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 22. Intervocalic detection helper
// ---------------------------------------------------------------------------

func TestPtInterV(t *testing.T) {
	tests := []struct {
		word string
		pos  int
		want bool
	}{
		{"ara", 1, true},  // a-r-a: r is intervocalic
		{"rra", 0, false}, // word-initial: not intervocalic
		{"arr", 1, false}, // r before consonant: not intervocalic
		{"ar", 1, false},  // word-final: not intervocalic
	}
	for _, tc := range tests {
		t.Run(tc.word, func(t *testing.T) {
			r := []rune(tc.word)
			got := ptInterV(r, tc.pos)
			if got != tc.want {
				t.Errorf("ptInterV(%q, %d) = %v, want %v",
					tc.word, tc.pos, got, tc.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 23. Acute accent -> open vowel mapping
// ---------------------------------------------------------------------------

func TestPtOpen(t *testing.T) {
	tests := []struct {
		input rune
		want  string
	}{
		{'e', "ɛ"},
		{'o', "ɔ"},
		{'a', "a"}, // a has no distinct open variant
		{'i', "i"}, // i has no distinct open variant
	}
	for _, tc := range tests {
		got := ptOpen(tc.input)
		if got != tc.want {
			t.Errorf("ptOpen(%q) = %q, want %q", string(tc.input), got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// 24. Nasal vowel mapping
// ---------------------------------------------------------------------------

func TestPtNasal(t *testing.T) {
	tests := []struct {
		input rune
		want  string
	}{
		{'a', "ã"},
		{'e', "ẽ"},
		{'i', "ĩ"},
		{'o', "õ"},
		{'u', "ũ"},
	}
	for _, tc := range tests {
		got := ptNasal(tc.input)
		if got != tc.want {
			t.Errorf("ptNasal(%q) = %q, want %q", string(tc.input), got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// 25. Vowel group counting for "ouro" (edge case)
// ---------------------------------------------------------------------------

func TestPtCountVG_Ouro(t *testing.T) {
	// "ouro": 'ou' is one vowel group, 'o' is another.
	// The 'ou' digraph handler advances past both 'o' and 'u'.
	// Then 'r' (consonant) is skipped. Then final 'o' is a vowel group.
	// Total = 2.
	got := ptCountVG([]rune("ouro"))
	if got != 2 {
		t.Errorf("ptCountVG(\"ouro\") = %d, want 2", got)
	}
}

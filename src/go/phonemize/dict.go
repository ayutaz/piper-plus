package phonemize

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// CustomDictionary maps words to their phoneme sequences.
type CustomDictionary struct {
	entries map[string][]string // normalized word -> phoneme tokens
}

// NewCustomDictionary creates an empty dictionary.
func NewCustomDictionary() *CustomDictionary {
	return &CustomDictionary{entries: make(map[string][]string)}
}

// LoadDictFile loads a dictionary from a text file.
// Format: one entry per line, "word phoneme1 phoneme2 ..."
// Lines starting with # are comments. Empty lines are skipped.
func LoadDictFile(path string) (*CustomDictionary, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open dict file: %w", err)
	}
	defer func() { _ = f.Close() }()

	d := NewCustomDictionary()
	scanner := bufio.NewScanner(f)
	lineNo := 0
	for scanner.Scan() {
		lineNo++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			return nil, fmt.Errorf("dict line %d: need word + at least one phoneme, got %q", lineNo, line)
		}
		word := normalizeWord(fields[0])
		d.entries[word] = fields[1:]
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read dict file: %w", err)
	}
	return d, nil
}

// LoadDictFiles loads and merges multiple dictionary files.
// Later files override earlier ones for the same word.
func LoadDictFiles(paths []string) (*CustomDictionary, error) {
	merged := NewCustomDictionary()
	for _, p := range paths {
		d, err := LoadDictFile(p)
		if err != nil {
			return nil, err
		}
		for word, phonemes := range d.entries {
			merged.entries[word] = phonemes
		}
	}
	return merged, nil
}

// Lookup returns the phoneme sequence for a word, or nil if not found.
// Word is normalized (lowercased, trimmed).
func (d *CustomDictionary) Lookup(word string) []string {
	if ph, ok := d.entries[normalizeWord(word)]; ok {
		cp := make([]string, len(ph))
		copy(cp, ph)
		return cp
	}
	return nil
}

// Add adds or overwrites a dictionary entry.
func (d *CustomDictionary) Add(word string, phonemes []string) {
	d.entries[normalizeWord(word)] = phonemes
}

// Len returns the number of entries.
func (d *CustomDictionary) Len() int {
	return len(d.entries)
}

// WrapPhonemizer wraps an existing Phonemizer, checking the dictionary first.
// Words found in the dictionary use the dictionary phonemes;
// other words fall through to the wrapped phonemizer.
func (d *CustomDictionary) WrapPhonemizer(p Phonemizer) Phonemizer {
	return &dictPhonemizer{dict: d, wrapped: p}
}

// normalizeWord lowercases and trims a word for dictionary lookup.
func normalizeWord(w string) string {
	return strings.ToLower(strings.TrimSpace(w))
}

// dictPhonemizer wraps a Phonemizer with dictionary lookup.
type dictPhonemizer struct {
	dict    *CustomDictionary
	wrapped Phonemizer
}

// PhonemizeWithProsody tokenizes text into words and checks the dictionary
// for each word before falling through to the wrapped phonemizer.
//
// BOS/EOS tokens are stripped from each per-word result to prevent
// accumulation in multi-word output. A single BOS/EOS pair is NOT added
// here; the caller (PostProcessIDs / PostProcessMultilingualIDs) handles
// that. The last EOS token seen from the wrapped phonemizer is propagated
// in result.EOSToken so the caller can select the correct variant
// ("$", "?", "?!", etc.).
func (dp *dictPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	// Note: We split on whitespace and phonemize per-word, but re-insert " "
	// tokens between words to preserve word boundaries in the phoneme sequence.
	// This matches the behavior of the wrapped phonemizer's full-text output.
	words := strings.Fields(text)
	var allTokens []string
	var allProsody []*ProsodyInfo
	lastEOS := "$"

	for wi, w := range words {
		if wi > 0 {
			allTokens = append(allTokens, " ")
			allProsody = append(allProsody, &ProsodyInfo{A1: 0, A2: 0, A3: 0})
		}
		if ph := dp.dict.Lookup(w); ph != nil {
			allTokens = append(allTokens, ph...)
			for range ph {
				allProsody = append(allProsody, nil)
			}
		} else {
			res, err := dp.wrapped.PhonemizeWithProsody(w)
			if err != nil {
				return nil, fmt.Errorf("phonemize %q: %w", w, err)
			}
			// Strip BOS/EOS from this word's output and track the last EOS,
			// matching the approach used by MultilingualPhonemizer.
			for i, tok := range res.Tokens {
				if bosEosTokens[tok] {
					if eosOnlyTokens[tok] {
						lastEOS = tok
					}
					continue
				}
				allTokens = append(allTokens, tok)
				var p *ProsodyInfo
				if i < len(res.Prosody) {
					p = res.Prosody[i]
				}
				allProsody = append(allProsody, p)
			}
		}
	}

	return &PhonemizeResult{
		Tokens:   allTokens,
		Prosody:  allProsody,
		EOSToken: lastEOS,
	}, nil
}

// LanguageCode delegates to the wrapped phonemizer.
func (dp *dictPhonemizer) LanguageCode() string {
	return dp.wrapped.LanguageCode()
}

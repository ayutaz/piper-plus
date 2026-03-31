package phonemize

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"
)

// TextDictionary performs text-level word substitution before phonemization.
// It replaces known words with their pronunciation readings (typically katakana).
// This matches the Python/C++ custom dictionary behavior.
type TextDictionary struct {
	entries       map[string]textEntry // normalized (lowercase) key -> entry
	caseSensitive map[string]textEntry // mixed-case key -> entry (exact match)
}

type textEntry struct {
	pronunciation string
	priority      int
}

// LoadTextDictJSON loads a single JSON dictionary file (v1.0 or v2.0 format).
//
// v2.0 format:
//
//	{"version": "2.0", "entries": {"word": {"pronunciation": "...", "priority": 9}}}
//
// v1.0 format (legacy):
//
//	{"entries": {"word": "pronunciation"}}
//
// Keys starting with "//" are treated as comments and skipped.
// "version", "description", and "metadata" keys inside entries are also skipped.
func LoadTextDictJSON(path string) (*TextDictionary, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read text dict file: %w", err)
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("parse text dict JSON: %w", err)
	}

	// Extract the entries map.
	entriesRaw, ok := raw["entries"]
	if !ok {
		return nil, fmt.Errorf("text dict JSON missing \"entries\" key")
	}

	var entries map[string]json.RawMessage
	if err := json.Unmarshal(entriesRaw, &entries); err != nil {
		return nil, fmt.Errorf("parse text dict entries: %w", err)
	}

	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}

	// Reserved top-level keys that are not dictionary entries.
	reserved := map[string]bool{
		"version":     true,
		"description": true,
		"metadata":    true,
	}

	for word, valRaw := range entries {
		// Skip comment keys.
		if strings.HasPrefix(word, "//") {
			continue
		}
		// Skip reserved keys that may appear inside entries.
		if reserved[word] {
			continue
		}

		// Try parsing as object first (v2.0), then as string (v1.0).
		var objEntry struct {
			Pronunciation string `json:"pronunciation"`
			Priority      int    `json:"priority"`
		}
		if err := json.Unmarshal(valRaw, &objEntry); err == nil && objEntry.Pronunciation != "" {
			td.addEntry(word, objEntry.Pronunciation, objEntry.Priority)
			continue
		}

		var strVal string
		if err := json.Unmarshal(valRaw, &strVal); err == nil {
			td.addEntry(word, strVal, 5) // default priority for v1.0
			continue
		}

		// Skip entries that cannot be parsed as either format.
	}

	return td, nil
}

// LoadTextDictJSONFiles loads and merges multiple JSON dictionary files.
// Later files can override earlier entries only if the new priority is strictly higher.
func LoadTextDictJSONFiles(paths []string) (*TextDictionary, error) {
	merged := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}

	for _, p := range paths {
		td, err := LoadTextDictJSON(p)
		if err != nil {
			return nil, err
		}
		for word, entry := range td.entries {
			merged.addEntryToMap(merged.entries, word, entry.pronunciation, entry.priority)
		}
		for word, entry := range td.caseSensitive {
			merged.addEntryToMap(merged.caseSensitive, word, entry.pronunciation, entry.priority)
		}
	}

	return merged, nil
}

// addEntry stores a word entry in the appropriate map based on case.
//
// Mixed case words (containing both upper and lower case letters, e.g. "GitHub")
// are stored in the caseSensitive map for exact matching.
// Uniform case words (all upper, all lower, or no letters) are normalized to
// lowercase and stored in the entries map.
func (td *TextDictionary) addEntry(word string, pronunciation string, priority int) {
	if isMixedCase(word) {
		td.addEntryToMap(td.caseSensitive, word, pronunciation, priority)
	} else {
		td.addEntryToMap(td.entries, strings.ToLower(word), pronunciation, priority)
	}
}

// addEntryToMap adds an entry to the specified map, only overriding if the new
// priority is strictly higher than the existing entry.
func (td *TextDictionary) addEntryToMap(m map[string]textEntry, key string, pronunciation string, priority int) {
	if existing, ok := m[key]; ok {
		if priority <= existing.priority {
			return
		}
	}
	m[key] = textEntry{pronunciation: pronunciation, priority: priority}
}

// isMixedCase returns true if the word contains both upper and lower case letters.
func isMixedCase(word string) bool {
	hasUpper := false
	hasLower := false
	for _, r := range word {
		if unicode.IsUpper(r) {
			hasUpper = true
		}
		if unicode.IsLower(r) {
			hasLower = true
		}
		if hasUpper && hasLower {
			return true
		}
	}
	return false
}

// ApplyToText performs text substitution, replacing dictionary words with their
// pronunciation readings. This matches the Python/C++ custom dictionary behavior.
//
// Processing order:
//  1. Case-sensitive entries first (longest word first)
//  2. Case-insensitive entries (longest word first)
//
// For ASCII words, word boundary checks prevent matching inside other words
// (e.g., "API" won't match inside "RAPID"). For Japanese/CJK text, no word
// boundaries are applied.
func (td *TextDictionary) ApplyToText(text string) string {
	if text == "" {
		return ""
	}

	// Process case-sensitive entries first.
	csKeys := sortedKeysByLenDesc(td.caseSensitive)
	for _, word := range csKeys {
		entry := td.caseSensitive[word]
		text = replaceWordBounded(text, word, entry.pronunciation, false)
	}

	// Process case-insensitive entries.
	ciKeys := sortedKeysByLenDesc(td.entries)
	for _, word := range ciKeys {
		entry := td.entries[word]
		text = replaceWordBounded(text, word, entry.pronunciation, true)
	}

	return text
}

// replaceWordBounded replaces all occurrences of word in text with replacement,
// respecting word boundaries for ASCII words. For words starting with non-ASCII
// characters (Japanese/CJK), no boundary check is applied.
//
// Go's RE2 engine does not support lookahead/lookbehind, so boundary checking
// is done manually using FindAllStringIndex and rune-level inspection.
func replaceWordBounded(text, word, replacement string, caseInsensitive bool) string {
	escaped := regexp.QuoteMeta(word)
	pat := escaped
	if caseInsensitive {
		pat = "(?i)" + pat
	}
	re, err := regexp.Compile(pat)
	if err != nil {
		return text
	}

	matches := re.FindAllStringIndex(text, -1)
	if len(matches) == 0 {
		return text
	}

	// Determine if this is a non-ASCII word (no boundary check needed).
	wordRunes := []rune(word)
	isNonASCII := len(wordRunes) > 0 && wordRunes[0] > 0x7F

	// Build byte-to-rune index for boundary checking.
	runes := []rune(text)
	byteToRune := make([]int, len(text)+1)
	bi := 0
	for ri, r := range runes {
		byteToRune[bi] = ri
		bi += len(string(r))
	}
	byteToRune[len(text)] = len(runes)

	var sb strings.Builder
	lastEnd := 0
	for _, m := range matches {
		startByte, endByte := m[0], m[1]

		boundaryOK := true
		if !isNonASCII {
			startRune := byteToRune[startByte]
			endRune := byteToRune[endByte]

			// Check left boundary: preceding char must not be alphanumeric.
			if startRune > 0 && isASCIIWordChar(runes[startRune-1]) {
				boundaryOK = false
			}
			// Check right boundary: following char must not be alphanumeric.
			if endRune < len(runes) && isASCIIWordChar(runes[endRune]) {
				boundaryOK = false
			}
		}

		if boundaryOK {
			sb.WriteString(text[lastEnd:startByte])
			sb.WriteString(replacement)
			lastEnd = endByte
		}
	}
	sb.WriteString(text[lastEnd:])
	return sb.String()
}

// isASCIIWordChar returns true if r is an ASCII letter or digit.
func isASCIIWordChar(r rune) bool {
	return (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')
}

// sortedKeysByLenDesc returns map keys sorted by length descending (longest first).
func sortedKeysByLenDesc(m map[string]textEntry) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		li, lj := len([]rune(keys[i])), len([]rune(keys[j]))
		if li != lj {
			return li > lj
		}
		return keys[i] < keys[j]
	})
	return keys
}

// Len returns the total number of entries in the dictionary (both maps combined).
func (td *TextDictionary) Len() int {
	return len(td.entries) + len(td.caseSensitive)
}

// FindDefaultDicts searches for default dictionary JSON files in standard locations:
//  1. modelDir/dictionaries/*.json
//  2. <exe_dir>/../share/piper/dictionaries/*.json
//  3. $PIPER_CUSTOM_DICT_PATH/*.json
//
// Returns a sorted list of found JSON file paths.
func FindDefaultDicts(modelDir string) []string {
	var results []string
	seen := make(map[string]bool)

	addGlob := func(pattern string) {
		matches, err := filepath.Glob(pattern)
		if err != nil {
			return
		}
		for _, m := range matches {
			abs, err := filepath.Abs(m)
			if err != nil {
				abs = m
			}
			if !seen[abs] {
				seen[abs] = true
				results = append(results, abs)
			}
		}
	}

	// 1. modelDir/dictionaries/*.json
	if modelDir != "" {
		addGlob(filepath.Join(modelDir, "dictionaries", "*.json"))
	}

	// 2. <exe_dir>/../share/piper/dictionaries/*.json
	if exe, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exe)
		addGlob(filepath.Join(exeDir, "..", "share", "piper", "dictionaries", "*.json"))
	}

	// 3. $PIPER_CUSTOM_DICT_PATH/*.json
	if envPath := os.Getenv("PIPER_CUSTOM_DICT_PATH"); envPath != "" {
		addGlob(filepath.Join(envPath, "*.json"))
	}

	sort.Strings(results)
	return results
}

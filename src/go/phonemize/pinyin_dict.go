package phonemize

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// LoadPinyinDicts loads pinyin_single.json and pinyin_phrases.json.
//
// If a path is empty the corresponding map is returned empty (not nil).
// An error is returned only when a non-empty path cannot be loaded.
//
// # pinyin_single.json format
//
// Keys are Unicode codepoints as decimal strings; values are pinyin with
// numeric tones (scripts/build_pinyin_dicts.py), possibly comma-separated
// alternatives. Tone diacritics are not parsed: "yī" reads as tone 5.
//
//	{"19968": "yi1", "19981": "bu4,fou3"}
//
// # pinyin_phrases.json format
//
// Keys are Chinese phrases; values are arrays of arrays where each inner
// array contains one pinyin string:
//
//	{"一丁不识": [["yi1"], ["ding1"], ["bu4"], ["shi2"]]}
//
// Both [][]string and []string formats are accepted for the value arrays.
func LoadPinyinDicts(singlePath, phrasePath string) (map[rune]string, map[string]string, error) {
	single := make(map[rune]string)
	phrase := make(map[string]string)

	// --- pinyin_single.json ---
	if singlePath != "" {
		data, err := os.ReadFile(singlePath)
		if err != nil {
			return single, phrase, fmt.Errorf("phonemize: open pinyin_single %q: %w", singlePath, err)
		}

		var raw map[string]string
		if err := json.Unmarshal(data, &raw); err != nil {
			return single, phrase, fmt.Errorf("phonemize: parse pinyin_single %q: %w", singlePath, err)
		}

		for key, val := range raw {
			cp, err := strconv.Atoi(key)
			if err != nil {
				continue // skip malformed keys
			}
			// Reject out-of-range codepoints before the rune cast: strconv.Atoi
			// returns int (architecture-dependent, up to 64 bits), and rune is
			// int32. Unicode codepoints fit in 0..0x10FFFF, so anything outside
			// that range is a malformed dictionary entry — silently drop it.
			if cp < 0 || cp > 0x10FFFF {
				continue
			}
			single[rune(cp)] = val
		}
	}

	// --- pinyin_phrases.json ---
	if phrasePath != "" {
		data, err := os.ReadFile(phrasePath)
		if err != nil {
			return single, phrase, fmt.Errorf("phonemize: open pinyin_phrases %q: %w", phrasePath, err)
		}

		var raw map[string]json.RawMessage
		if err := json.Unmarshal(data, &raw); err != nil {
			return single, phrase, fmt.Errorf("phonemize: parse pinyin_phrases %q: %w", phrasePath, err)
		}

		for key, msg := range raw {
			// Try [][]string first (canonical C++ format).
			var nested [][]string
			if err := json.Unmarshal(msg, &nested); err == nil {
				parts := make([]string, 0, len(nested))
				for _, inner := range nested {
					if len(inner) > 0 {
						parts = append(parts, inner[0])
					}
				}
				phrase[key] = strings.Join(parts, " ")
				continue
			}

			// Fallback: try []string.
			var flat []string
			if err := json.Unmarshal(msg, &flat); err == nil {
				phrase[key] = strings.Join(flat, " ")
				continue
			}

			// Skip entries that match neither format.
		}
	}

	return single, phrase, nil
}

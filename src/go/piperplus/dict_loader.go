package piperplus

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// dictData holds all loaded dictionaries for phonemizer initialisation.
type dictData struct {
	cmuDict          map[string][]string
	pinyinSingle     map[rune]string
	pinyinPhrase     map[string]string
	openjtalkDictDir string // path to OpenJTalk dictionary directory
}

// findDictionaryFile searches for a dictionary file using a 3-tier strategy:
//  1. Model directory (modelDir/filename)
//  2. Executable-relative path (exe/../share/piper/dicts/filename)
//  3. PIPER_DICTIONARIES_PATH environment variable
//
// Returns the first existing path, or an empty string if not found.
func findDictionaryFile(filename, modelDir string) string {
	// Tier 1: model directory.
	if modelDir != "" {
		candidate := filepath.Join(modelDir, filename)
		if _, err := os.Stat(candidate); err == nil {
			slog.Debug("dictionary found in model directory", "file", filename, "path", candidate)
			return candidate
		}
	}

	// Tier 2: executable-relative path.
	if exePath, err := os.Executable(); err == nil {
		candidate := filepath.Join(filepath.Dir(exePath), "..", "share", "piper", "dicts", filename)
		if _, err := os.Stat(candidate); err == nil {
			slog.Debug("dictionary found relative to executable", "file", filename, "path", candidate)
			return candidate
		}
	}

	// Tier 3: PIPER_DICTIONARIES_PATH environment variable.
	if envDir := os.Getenv("PIPER_DICTIONARIES_PATH"); envDir != "" {
		candidate := filepath.Join(envDir, filename)
		if _, err := os.Stat(candidate); err == nil {
			slog.Debug("dictionary found via PIPER_DICTIONARIES_PATH", "file", filename, "path", candidate)
			return candidate
		}
	}

	slog.Debug("dictionary file not found", "file", filename)
	return ""
}

// findOpenJTalkDict searches for the OpenJTalk dictionary directory using a
// 3-tier strategy similar to findDictionaryFile:
//  1. modelDir/open_jtalk_dic_utf_8-1.11/ — next to model
//  2. <exe_dir>/../share/open_jtalk/dic/ — exe-relative (same as C++)
//  3. OPENJTALK_DICTIONARY_PATH environment variable — explicit override
//
// Each candidate is validated by checking for the presence of sys.dic (the main
// MeCab dictionary file). Returns the first valid path, or empty string.
func findOpenJTalkDict(modelDir string) string {
	candidates := make([]string, 0, 3)

	// Tier 1: model directory.
	if modelDir != "" {
		candidates = append(candidates, filepath.Join(modelDir, "open_jtalk_dic_utf_8-1.11"))
	}

	// Tier 2: executable-relative path.
	if exePath, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Join(filepath.Dir(exePath), "..", "share", "open_jtalk", "dic"))
	}

	// Tier 3: OPENJTALK_DICTIONARY_PATH environment variable.
	if envDir := os.Getenv("OPENJTALK_DICTIONARY_PATH"); envDir != "" {
		candidates = append(candidates, envDir)
	}

	for _, candidate := range candidates {
		if _, err := os.Stat(filepath.Join(candidate, "sys.dic")); err == nil {
			slog.Debug("OpenJTalk dictionary found", "path", candidate)
			return candidate
		}
	}

	slog.Debug("OpenJTalk dictionary not found")
	return ""
}

// loadCmuDict loads a CMU dictionary from a JSON file.
//
// The expected JSON format maps lowercase words to space-separated ARPAbet
// strings:
//
//	{"hello": "HH AH0 L OW1", "world": "W ER1 L D"}
//
// The returned map splits each value into a slice of ARPAbet tokens suitable
// for [phonemize.NewEnglishPhonemizer].
func loadCmuDict(path string) (map[string][]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("piperplus: open CMU dict %q: %w", path, err)
	}

	var raw map[string]string
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("piperplus: parse CMU dict %q: %w", path, err)
	}

	dict := make(map[string][]string, len(raw))
	for word, arpabet := range raw {
		tokens := strings.Fields(arpabet)
		if len(tokens) > 0 {
			dict[word] = tokens
		}
	}
	return dict, nil
}

// loadPinyinDicts loads pinyin_single.json and pinyin_phrases.json.
//
// If a path is empty the corresponding map is returned empty (not nil).
// An error is returned only when a non-empty path cannot be loaded.
//
// # pinyin_single.json format
//
// Keys are Unicode codepoints as decimal strings; values are pinyin with
// tone diacritics or numbers, possibly comma-separated alternatives:
//
//	{"19968": "yī", "19981": "bù,fǒu"}
//
// # pinyin_phrases.json format
//
// Keys are Chinese phrases; values are arrays of arrays where each inner
// array contains one pinyin string:
//
//	{"一丁不识": [["yī"], ["dīng"], ["bù"], ["shí"]]}
//
// Both [][]string and []string formats are accepted for the value arrays.
func loadPinyinDicts(singlePath, phrasePath string) (map[rune]string, map[string]string, error) {
	single := make(map[rune]string)
	phrase := make(map[string]string)

	// --- pinyin_single.json ---
	if singlePath != "" {
		data, err := os.ReadFile(singlePath)
		if err != nil {
			return single, phrase, fmt.Errorf("piperplus: open pinyin_single %q: %w", singlePath, err)
		}

		var raw map[string]string
		if err := json.Unmarshal(data, &raw); err != nil {
			return single, phrase, fmt.Errorf("piperplus: parse pinyin_single %q: %w", singlePath, err)
		}

		for key, val := range raw {
			cp, err := strconv.Atoi(key)
			if err != nil {
				continue // skip malformed keys
			}
			single[rune(cp)] = val
		}
	}

	// --- pinyin_phrases.json ---
	if phrasePath != "" {
		data, err := os.ReadFile(phrasePath)
		if err != nil {
			return single, phrase, fmt.Errorf("piperplus: open pinyin_phrases %q: %w", phrasePath, err)
		}

		var raw map[string]json.RawMessage
		if err := json.Unmarshal(data, &raw); err != nil {
			return single, phrase, fmt.Errorf("piperplus: parse pinyin_phrases %q: %w", phrasePath, err)
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

// loadDictionaries loads all needed dictionaries based on the languages present
// in the model configuration. It always returns a non-nil *dictData with empty
// maps for any dictionaries that could not be found or loaded.
func loadDictionaries(modelDir string, languages map[string]int64, logger *slog.Logger) *dictData {
	if logger == nil {
		logger = slog.Default()
	}

	dd := &dictData{
		cmuDict:      make(map[string][]string),
		pinyinSingle: make(map[rune]string),
		pinyinPhrase: make(map[string]string),
	}

	// English: CMU dictionary.
	if _, ok := languages["en"]; ok {
		path := findDictionaryFile("cmudict_data.json", modelDir)
		if path == "" {
			logger.Warn("CMU dictionary not found; English will use letter-by-letter fallback")
		} else {
			dict, err := loadCmuDict(path)
			if err != nil {
				logger.Warn("failed to load CMU dictionary", "path", path, "error", err)
			} else {
				dd.cmuDict = dict
				logger.Info("loaded CMU dictionary", "path", path, "entries", len(dict))
			}
		}
	}

	// Chinese: pinyin dictionaries.
	if _, ok := languages["zh"]; ok {
		singlePath := findDictionaryFile("pinyin_single.json", modelDir)
		phrasePath := findDictionaryFile("pinyin_phrases.json", modelDir)

		if singlePath == "" && phrasePath == "" {
			logger.Warn("pinyin dictionaries not found; Chinese phonemization may be degraded")
		} else {
			single, phrases, err := loadPinyinDicts(singlePath, phrasePath)
			if err != nil {
				logger.Warn("failed to load pinyin dictionaries", "error", err)
			} else {
				dd.pinyinSingle = single
				dd.pinyinPhrase = phrases
				logger.Info("loaded pinyin dictionaries",
					"single_path", singlePath,
					"phrase_path", phrasePath,
					"single_entries", len(single),
					"phrase_entries", len(phrases),
				)
			}
		}
	}

	// Japanese: OpenJTalk dictionary.
	if _, ok := languages["ja"]; ok {
		dictDir := findOpenJTalkDict(modelDir)
		if dictDir == "" {
			logger.Warn("OpenJTalk dictionary not found; Japanese phonemization will not be available")
		} else {
			dd.openjtalkDictDir = dictDir
			logger.Info("found OpenJTalk dictionary", "path", dictDir)
		}
	}

	return dd
}

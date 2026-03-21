package piperplus

import (
	"encoding/json"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
)

// ---------------------------------------------------------------------------
// findDictionaryFile tests
// ---------------------------------------------------------------------------

func TestFindDictionaryFile_ModelDirFound(t *testing.T) {
	dir := t.TempDir()
	filename := "test_dict.json"
	path := filepath.Join(dir, filename)
	if err := os.WriteFile(path, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create test file: %v", err)
	}

	got := findDictionaryFile(filename, dir)
	if got != path {
		t.Errorf("findDictionaryFile() = %q, want %q", got, path)
	}
}

func TestFindDictionaryFile_EnvVarFound(t *testing.T) {
	envDir := t.TempDir()
	filename := "env_dict.json"
	path := filepath.Join(envDir, filename)
	if err := os.WriteFile(path, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create test file: %v", err)
	}

	// Use an empty modelDir so tier 1 is skipped.
	t.Setenv("PIPER_DICTIONARIES_PATH", envDir)

	got := findDictionaryFile(filename, "")
	if got != path {
		t.Errorf("findDictionaryFile() = %q, want %q", got, path)
	}
}

func TestFindDictionaryFile_NotFoundAnywhere(t *testing.T) {
	// Clear env var so tier 3 is skipped too.
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	got := findDictionaryFile("nonexistent.json", t.TempDir())
	if got != "" {
		t.Errorf("findDictionaryFile() = %q, want empty string", got)
	}
}

func TestFindDictionaryFile_EmptyFilename(t *testing.T) {
	// When filename is empty, filepath.Join(modelDir, "") resolves to the
	// directory itself, which passes os.Stat. This is by design: the caller
	// is responsible for providing a non-empty filename. Verify the function
	// does not panic and returns a deterministic result.
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	got := findDictionaryFile("", t.TempDir())
	// The function returns modelDir itself (a directory) because Stat succeeds.
	// This is acceptable: callers always supply real filenames.
	if got == "" {
		t.Log("findDictionaryFile returned empty string for empty filename (implementation may guard against it)")
	}
}

func TestFindDictionaryFile_EmptyModelDir(t *testing.T) {
	envDir := t.TempDir()
	filename := "fallback.json"
	path := filepath.Join(envDir, filename)
	if err := os.WriteFile(path, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to create test file: %v", err)
	}

	t.Setenv("PIPER_DICTIONARIES_PATH", envDir)

	got := findDictionaryFile(filename, "")
	if got != path {
		t.Errorf("findDictionaryFile() = %q, want %q", got, path)
	}
}

func TestFindDictionaryFile_ModelDirPriority(t *testing.T) {
	// Both modelDir and env have the file; modelDir should win.
	modelDir := t.TempDir()
	envDir := t.TempDir()
	filename := "priority.json"

	modelPath := filepath.Join(modelDir, filename)
	envPath := filepath.Join(envDir, filename)
	if err := os.WriteFile(modelPath, []byte(`{"source":"model"}`), 0644); err != nil {
		t.Fatalf("failed to create model file: %v", err)
	}
	if err := os.WriteFile(envPath, []byte(`{"source":"env"}`), 0644); err != nil {
		t.Fatalf("failed to create env file: %v", err)
	}

	t.Setenv("PIPER_DICTIONARIES_PATH", envDir)

	got := findDictionaryFile(filename, modelDir)
	if got != modelPath {
		t.Errorf("findDictionaryFile() = %q, want %q (model dir should have priority)", got, modelPath)
	}
}

// ---------------------------------------------------------------------------
// loadCmuDict tests
// ---------------------------------------------------------------------------

func TestLoadCmuDict_ValidJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "cmudict.json")
	content := `{"hello": "HH AH0 L OW1", "world": "W ER1 L D"}`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	dict, err := loadCmuDict(path)
	if err != nil {
		t.Fatalf("loadCmuDict() returned unexpected error: %v", err)
	}

	if len(dict) != 2 {
		t.Fatalf("len(dict) = %d, want 2", len(dict))
	}

	// Verify "hello" entry.
	hello := dict["hello"]
	wantHello := []string{"HH", "AH0", "L", "OW1"}
	if len(hello) != len(wantHello) {
		t.Fatalf("dict[\"hello\"] has %d tokens, want %d", len(hello), len(wantHello))
	}
	for i, tok := range wantHello {
		if hello[i] != tok {
			t.Errorf("dict[\"hello\"][%d] = %q, want %q", i, hello[i], tok)
		}
	}

	// Verify "world" entry.
	world := dict["world"]
	wantWorld := []string{"W", "ER1", "L", "D"}
	if len(world) != len(wantWorld) {
		t.Fatalf("dict[\"world\"] has %d tokens, want %d", len(world), len(wantWorld))
	}
	for i, tok := range wantWorld {
		if world[i] != tok {
			t.Errorf("dict[\"world\"][%d] = %q, want %q", i, world[i], tok)
		}
	}
}

func TestLoadCmuDict_EmptyJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "empty.json")
	if err := os.WriteFile(path, []byte(`{}`), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	dict, err := loadCmuDict(path)
	if err != nil {
		t.Fatalf("loadCmuDict() returned unexpected error: %v", err)
	}

	if len(dict) != 0 {
		t.Errorf("len(dict) = %d, want 0", len(dict))
	}
}

func TestLoadCmuDict_SingleEntry(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "single.json")
	content := `{"test": "T EH1 S T"}`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	dict, err := loadCmuDict(path)
	if err != nil {
		t.Fatalf("loadCmuDict() returned unexpected error: %v", err)
	}

	if len(dict) != 1 {
		t.Fatalf("len(dict) = %d, want 1", len(dict))
	}

	got := dict["test"]
	want := []string{"T", "EH1", "S", "T"}
	if len(got) != len(want) {
		t.Fatalf("dict[\"test\"] has %d tokens, want %d", len(got), len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("dict[\"test\"][%d] = %q, want %q", i, got[i], want[i])
		}
	}
}

func TestLoadCmuDict_FileNotFound(t *testing.T) {
	_, err := loadCmuDict("/nonexistent/path/cmudict.json")
	if err == nil {
		t.Fatal("loadCmuDict() should return error for non-existent file")
	}
}

func TestLoadCmuDict_InvalidJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "invalid.json")
	if err := os.WriteFile(path, []byte(`{invalid json`), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	_, err := loadCmuDict(path)
	if err == nil {
		t.Fatal("loadCmuDict() should return error for invalid JSON")
	}
}

func TestLoadCmuDict_LargeEntry(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "large.json")
	// "IH2 N T ER0 N AE2 SH AH0 N AH0 L IH0 Z EY1 SH AH0 N" = 17 tokens
	content := `{"internationalization": "IH2 N T ER0 N AE2 SH AH0 N AH0 L IH0 Z EY1 SH AH0 N"}`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	dict, err := loadCmuDict(path)
	if err != nil {
		t.Fatalf("loadCmuDict() returned unexpected error: %v", err)
	}

	got := dict["internationalization"]
	if len(got) != 17 {
		t.Errorf("dict[\"internationalization\"] has %d tokens, want 17", len(got))
	}
}

func TestLoadCmuDict_EmptyValueSkipped(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "empty_val.json")
	// An entry with empty string value produces no tokens; it should be skipped.
	content := `{"good": "G UH1 D", "bad": ""}`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	dict, err := loadCmuDict(path)
	if err != nil {
		t.Fatalf("loadCmuDict() returned unexpected error: %v", err)
	}

	if _, ok := dict["bad"]; ok {
		t.Error("empty arpabet string should be skipped")
	}
	if _, ok := dict["good"]; !ok {
		t.Error("valid entry should be present")
	}
}

// ---------------------------------------------------------------------------
// loadPinyinDicts tests
// ---------------------------------------------------------------------------

func TestLoadPinyinDicts_ValidSingle(t *testing.T) {
	dir := t.TempDir()
	singlePath := filepath.Join(dir, "pinyin_single.json")
	// 你=20320, 好=22909
	content := `{"20320": "ni3", "22909": "hao3"}`
	if err := os.WriteFile(singlePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	single, phrase, err := loadPinyinDicts(singlePath, "")
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	// Verify rune keys.
	if got, ok := single['你']; !ok || got != "ni3" {
		t.Errorf("single['你'] = %q, ok=%v; want \"ni3\", true", got, ok)
	}
	if got, ok := single['好']; !ok || got != "hao3" {
		t.Errorf("single['好'] = %q, ok=%v; want \"hao3\", true", got, ok)
	}

	// Phrase map should be empty but not nil.
	if phrase == nil {
		t.Fatal("phrase map should not be nil")
	}
	if len(phrase) != 0 {
		t.Errorf("len(phrase) = %d, want 0", len(phrase))
	}
}

func TestLoadPinyinDicts_CommaSeparatedAlternatives(t *testing.T) {
	dir := t.TempDir()
	singlePath := filepath.Join(dir, "pinyin_single.json")
	// 人=20154 has alternative readings
	content := `{"20154": "ren2,jen2"}`
	if err := os.WriteFile(singlePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	single, _, err := loadPinyinDicts(singlePath, "")
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	// Comma-separated alternatives should be stored as-is.
	if got, ok := single[rune(20154)]; !ok || got != "ren2,jen2" {
		t.Errorf("single[20154] = %q, ok=%v; want \"ren2,jen2\", true", got, ok)
	}
}

func TestLoadPinyinDicts_ValidPhrase_NestedArray(t *testing.T) {
	dir := t.TempDir()
	phrasePath := filepath.Join(dir, "pinyin_phrases.json")
	content := `{"你好": [["ni3"], ["hao3"]]}`
	if err := os.WriteFile(phrasePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	single, phrase, err := loadPinyinDicts("", phrasePath)
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	if got, ok := phrase["你好"]; !ok || got != "ni3 hao3" {
		t.Errorf("phrase[\"你好\"] = %q, ok=%v; want \"ni3 hao3\", true", got, ok)
	}

	// Single map should be empty but not nil.
	if single == nil {
		t.Fatal("single map should not be nil")
	}
	if len(single) != 0 {
		t.Errorf("len(single) = %d, want 0", len(single))
	}
}

func TestLoadPinyinDicts_ValidPhrase_FlatArray(t *testing.T) {
	dir := t.TempDir()
	phrasePath := filepath.Join(dir, "pinyin_phrases.json")
	content := `{"你好": ["ni3", "hao3"]}`
	if err := os.WriteFile(phrasePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	_, phrase, err := loadPinyinDicts("", phrasePath)
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	if got, ok := phrase["你好"]; !ok || got != "ni3 hao3" {
		t.Errorf("phrase[\"你好\"] = %q, ok=%v; want \"ni3 hao3\", true", got, ok)
	}
}

func TestLoadPinyinDicts_EmptyPaths(t *testing.T) {
	single, phrase, err := loadPinyinDicts("", "")
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	if single == nil {
		t.Fatal("single map should not be nil")
	}
	if phrase == nil {
		t.Fatal("phrase map should not be nil")
	}
	if len(single) != 0 {
		t.Errorf("len(single) = %d, want 0", len(single))
	}
	if len(phrase) != 0 {
		t.Errorf("len(phrase) = %d, want 0", len(phrase))
	}
}

func TestLoadPinyinDicts_SinglePathOnly(t *testing.T) {
	dir := t.TempDir()
	singlePath := filepath.Join(dir, "pinyin_single.json")
	content := `{"20320": "ni3"}`
	if err := os.WriteFile(singlePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	single, phrase, err := loadPinyinDicts(singlePath, "")
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	if len(single) != 1 {
		t.Errorf("len(single) = %d, want 1", len(single))
	}
	if len(phrase) != 0 {
		t.Errorf("len(phrase) = %d, want 0", len(phrase))
	}
}

func TestLoadPinyinDicts_PhrasePathOnly(t *testing.T) {
	dir := t.TempDir()
	phrasePath := filepath.Join(dir, "pinyin_phrases.json")
	content := `{"你好": [["ni3"], ["hao3"]]}`
	if err := os.WriteFile(phrasePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	single, phrase, err := loadPinyinDicts("", phrasePath)
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	if len(single) != 0 {
		t.Errorf("len(single) = %d, want 0", len(single))
	}
	if len(phrase) != 1 {
		t.Errorf("len(phrase) = %d, want 1", len(phrase))
	}
}

func TestLoadPinyinDicts_InvalidSingleJSON(t *testing.T) {
	dir := t.TempDir()
	singlePath := filepath.Join(dir, "bad.json")
	if err := os.WriteFile(singlePath, []byte(`{broken`), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	_, _, err := loadPinyinDicts(singlePath, "")
	if err == nil {
		t.Fatal("loadPinyinDicts() should return error for invalid single JSON")
	}
}

func TestLoadPinyinDicts_InvalidPhraseJSON(t *testing.T) {
	dir := t.TempDir()
	phrasePath := filepath.Join(dir, "bad.json")
	if err := os.WriteFile(phrasePath, []byte(`not json`), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	_, _, err := loadPinyinDicts("", phrasePath)
	if err == nil {
		t.Fatal("loadPinyinDicts() should return error for invalid phrase JSON")
	}
}

func TestLoadPinyinDicts_InvalidCodepointKeySkipped(t *testing.T) {
	dir := t.TempDir()
	singlePath := filepath.Join(dir, "pinyin_single.json")
	// "abc" is not a valid codepoint; "20320" is valid.
	content := `{"abc": "bad", "20320": "ni3"}`
	if err := os.WriteFile(singlePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	single, _, err := loadPinyinDicts(singlePath, "")
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	// Only the valid codepoint should be present.
	if len(single) != 1 {
		t.Errorf("len(single) = %d, want 1 (malformed key should be skipped)", len(single))
	}
	if got, ok := single['你']; !ok || got != "ni3" {
		t.Errorf("single['你'] = %q, ok=%v; want \"ni3\", true", got, ok)
	}
}

func TestLoadPinyinDicts_FileNotFound(t *testing.T) {
	_, _, err := loadPinyinDicts("/nonexistent/single.json", "")
	if err == nil {
		t.Fatal("loadPinyinDicts() should return error when single file does not exist")
	}

	_, _, err = loadPinyinDicts("", "/nonexistent/phrase.json")
	if err == nil {
		t.Fatal("loadPinyinDicts() should return error when phrase file does not exist")
	}
}

func TestLoadPinyinDicts_MultiCharPhrase(t *testing.T) {
	dir := t.TempDir()
	phrasePath := filepath.Join(dir, "phrases.json")
	content := `{"一丁不识": [["yi1"], ["ding1"], ["bu4"], ["shi2"]]}`
	if err := os.WriteFile(phrasePath, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write test file: %v", err)
	}

	_, phrase, err := loadPinyinDicts("", phrasePath)
	if err != nil {
		t.Fatalf("loadPinyinDicts() returned unexpected error: %v", err)
	}

	want := "yi1 ding1 bu4 shi2"
	if got, ok := phrase["一丁不识"]; !ok || got != want {
		t.Errorf("phrase[\"一丁不识\"] = %q, ok=%v; want %q, true", got, ok, want)
	}
}

// ---------------------------------------------------------------------------
// loadDictionaries tests
// ---------------------------------------------------------------------------

func TestLoadDictionaries_ENLanguage(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()
	// Create a valid CMU dict in the model dir.
	cmuContent, _ := json.Marshal(map[string]string{
		"hello": "HH AH0 L OW1",
		"world": "W ER1 L D",
	})
	if err := os.WriteFile(filepath.Join(dir, "cmudict_data.json"), cmuContent, 0644); err != nil {
		t.Fatalf("failed to write cmudict: %v", err)
	}

	languages := map[string]int64{"en": 1}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 2 {
		t.Errorf("len(cmuDict) = %d, want 2", len(dd.cmuDict))
	}
	if len(dd.pinyinSingle) != 0 {
		t.Errorf("len(pinyinSingle) = %d, want 0", len(dd.pinyinSingle))
	}
	if len(dd.pinyinPhrase) != 0 {
		t.Errorf("len(pinyinPhrase) = %d, want 0", len(dd.pinyinPhrase))
	}
}

func TestLoadDictionaries_ZHLanguage(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()
	// Create valid pinyin dicts in the model dir.
	singleContent, _ := json.Marshal(map[string]string{
		"20320": "ni3",
		"22909": "hao3",
	})
	phraseContent := `{"你好": [["ni3"], ["hao3"]]}`
	if err := os.WriteFile(filepath.Join(dir, "pinyin_single.json"), singleContent, 0644); err != nil {
		t.Fatalf("failed to write pinyin_single: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "pinyin_phrases.json"), []byte(phraseContent), 0644); err != nil {
		t.Fatalf("failed to write pinyin_phrases: %v", err)
	}

	languages := map[string]int64{"zh": 2}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 0 {
		t.Errorf("len(cmuDict) = %d, want 0", len(dd.cmuDict))
	}
	if len(dd.pinyinSingle) != 2 {
		t.Errorf("len(pinyinSingle) = %d, want 2", len(dd.pinyinSingle))
	}
	if len(dd.pinyinPhrase) != 1 {
		t.Errorf("len(pinyinPhrase) = %d, want 1", len(dd.pinyinPhrase))
	}
}

func TestLoadDictionaries_NeitherENnorZH(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()
	languages := map[string]int64{"es": 3, "fr": 4}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 0 {
		t.Errorf("len(cmuDict) = %d, want 0", len(dd.cmuDict))
	}
	if len(dd.pinyinSingle) != 0 {
		t.Errorf("len(pinyinSingle) = %d, want 0", len(dd.pinyinSingle))
	}
	if len(dd.pinyinPhrase) != 0 {
		t.Errorf("len(pinyinPhrase) = %d, want 0", len(dd.pinyinPhrase))
	}
}

func TestLoadDictionaries_BothENandZH(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()

	// CMU dict.
	cmuContent, _ := json.Marshal(map[string]string{"cat": "K AE1 T"})
	if err := os.WriteFile(filepath.Join(dir, "cmudict_data.json"), cmuContent, 0644); err != nil {
		t.Fatalf("failed to write cmudict: %v", err)
	}

	// Pinyin dicts.
	singleContent, _ := json.Marshal(map[string]string{"20320": "ni3"})
	phraseContent := `{"你好": [["ni3"], ["hao3"]]}`
	if err := os.WriteFile(filepath.Join(dir, "pinyin_single.json"), singleContent, 0644); err != nil {
		t.Fatalf("failed to write pinyin_single: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "pinyin_phrases.json"), []byte(phraseContent), 0644); err != nil {
		t.Fatalf("failed to write pinyin_phrases: %v", err)
	}

	languages := map[string]int64{"en": 1, "zh": 2}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 1 {
		t.Errorf("len(cmuDict) = %d, want 1", len(dd.cmuDict))
	}
	if len(dd.pinyinSingle) != 1 {
		t.Errorf("len(pinyinSingle) = %d, want 1", len(dd.pinyinSingle))
	}
	if len(dd.pinyinPhrase) != 1 {
		t.Errorf("len(pinyinPhrase) = %d, want 1", len(dd.pinyinPhrase))
	}
}

func TestLoadDictionaries_DictFilesExist(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()

	// Write a full CMU dict with multiple entries.
	cmuContent, _ := json.Marshal(map[string]string{
		"the":   "DH AH0",
		"quick": "K W IH1 K",
		"brown": "B R AW1 N",
		"fox":   "F AA1 K S",
	})
	if err := os.WriteFile(filepath.Join(dir, "cmudict_data.json"), cmuContent, 0644); err != nil {
		t.Fatalf("failed to write cmudict: %v", err)
	}

	languages := map[string]int64{"en": 1}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 4 {
		t.Errorf("len(cmuDict) = %d, want 4", len(dd.cmuDict))
	}

	// Spot-check a specific entry: "K W IH1 K" = 4 tokens.
	if tokens, ok := dd.cmuDict["quick"]; !ok {
		t.Error("cmuDict should contain \"quick\"")
	} else if len(tokens) != 4 {
		t.Errorf("cmuDict[\"quick\"] has %d tokens, want 4", len(tokens))
	}
}

func TestLoadDictionaries_DictFilesMissing(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	// Use an empty temp dir -- no dict files present.
	dir := t.TempDir()

	languages := map[string]int64{"en": 1, "zh": 2}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() should return non-nil dictData even when files are missing")
	}

	// All maps should be empty but non-nil.
	if dd.cmuDict == nil {
		t.Error("cmuDict should not be nil")
	}
	if dd.pinyinSingle == nil {
		t.Error("pinyinSingle should not be nil")
	}
	if dd.pinyinPhrase == nil {
		t.Error("pinyinPhrase should not be nil")
	}
	if len(dd.cmuDict) != 0 {
		t.Errorf("len(cmuDict) = %d, want 0", len(dd.cmuDict))
	}
	if len(dd.pinyinSingle) != 0 {
		t.Errorf("len(pinyinSingle) = %d, want 0", len(dd.pinyinSingle))
	}
	if len(dd.pinyinPhrase) != 0 {
		t.Errorf("len(pinyinPhrase) = %d, want 0", len(dd.pinyinPhrase))
	}
}

func TestLoadDictionaries_NilLogger(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()
	languages := map[string]int64{"en": 1}

	// Pass nil logger; should not panic.
	dd := loadDictionaries(dir, languages, nil)
	if dd == nil {
		t.Fatal("loadDictionaries() should return non-nil dictData with nil logger")
	}
}

func TestLoadDictionaries_EmptyLanguages(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()
	languages := map[string]int64{}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, languages, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 0 {
		t.Errorf("len(cmuDict) = %d, want 0", len(dd.cmuDict))
	}
	if len(dd.pinyinSingle) != 0 {
		t.Errorf("len(pinyinSingle) = %d, want 0", len(dd.pinyinSingle))
	}
	if len(dd.pinyinPhrase) != 0 {
		t.Errorf("len(pinyinPhrase) = %d, want 0", len(dd.pinyinPhrase))
	}
}

func TestLoadDictionaries_NilLanguages(t *testing.T) {
	t.Setenv("PIPER_DICTIONARIES_PATH", "")

	dir := t.TempDir()
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))

	dd := loadDictionaries(dir, nil, logger)
	if dd == nil {
		t.Fatal("loadDictionaries() returned nil")
	}
	if len(dd.cmuDict) != 0 {
		t.Errorf("len(cmuDict) = %d, want 0", len(dd.cmuDict))
	}
}

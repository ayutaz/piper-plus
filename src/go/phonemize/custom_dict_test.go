package phonemize

import (
	"os"
	"path/filepath"
	"testing"
)

// ===========================================================================
// JSON Loading tests
// ===========================================================================

// Test 1: V2.0 format — object entries with pronunciation + priority.
func TestLoadTextDictJSON_V2Format(t *testing.T) {
	content := `{
		"version": "2.0",
		"entries": {
			"Python": {"pronunciation": "パイソン", "priority": 9},
			"API":    {"pronunciation": "エーピーアイ", "priority": 8}
		}
	}`
	path := writeTempJSON(t, content)

	td, err := LoadTextDictJSON(path)
	if err != nil {
		t.Fatalf("LoadTextDictJSON error: %v", err)
	}
	if td.Len() != 2 {
		t.Fatalf("Len() = %d, want 2", td.Len())
	}

	// "Python" is mixed case -> caseSensitive map.
	if e, ok := td.caseSensitive["Python"]; !ok {
		t.Error("caseSensitive[\"Python\"] not found")
	} else {
		if e.pronunciation != "パイソン" {
			t.Errorf("Python pronunciation = %q, want パイソン", e.pronunciation)
		}
		if e.priority != 9 {
			t.Errorf("Python priority = %d, want 9", e.priority)
		}
	}

	// "API" is all-upper -> entries map (normalized to lowercase).
	if e, ok := td.entries["api"]; !ok {
		t.Error("entries[\"api\"] not found")
	} else {
		if e.pronunciation != "エーピーアイ" {
			t.Errorf("API pronunciation = %q, want エーピーアイ", e.pronunciation)
		}
		if e.priority != 8 {
			t.Errorf("API priority = %d, want 8", e.priority)
		}
	}
}

// Test 2: V1.0 format — string entries with default priority 5.
func TestLoadTextDictJSON_V1Format(t *testing.T) {
	content := `{
		"entries": {
			"hello": "ハロー",
			"world": "ワールド"
		}
	}`
	path := writeTempJSON(t, content)

	td, err := LoadTextDictJSON(path)
	if err != nil {
		t.Fatalf("LoadTextDictJSON error: %v", err)
	}
	if td.Len() != 2 {
		t.Fatalf("Len() = %d, want 2", td.Len())
	}

	if e, ok := td.entries["hello"]; !ok {
		t.Error("entries[\"hello\"] not found")
	} else {
		if e.pronunciation != "ハロー" {
			t.Errorf("hello pronunciation = %q, want ハロー", e.pronunciation)
		}
		if e.priority != 5 {
			t.Errorf("hello priority = %d, want 5 (default)", e.priority)
		}
	}

	if e, ok := td.entries["world"]; !ok {
		t.Error("entries[\"world\"] not found")
	} else if e.pronunciation != "ワールド" {
		t.Errorf("world pronunciation = %q, want ワールド", e.pronunciation)
	}
}

// Test 3: Mixed format — some object, some string entries.
func TestLoadTextDictJSON_MixedFormat(t *testing.T) {
	content := `{
		"version": "2.0",
		"entries": {
			"API":    {"pronunciation": "エーピーアイ", "priority": 8},
			"hello":  "ハロー"
		}
	}`
	path := writeTempJSON(t, content)

	td, err := LoadTextDictJSON(path)
	if err != nil {
		t.Fatalf("LoadTextDictJSON error: %v", err)
	}
	if td.Len() != 2 {
		t.Fatalf("Len() = %d, want 2", td.Len())
	}

	if e, ok := td.entries["api"]; !ok {
		t.Error("entries[\"api\"] not found")
	} else if e.priority != 8 {
		t.Errorf("API priority = %d, want 8", e.priority)
	}

	if e, ok := td.entries["hello"]; !ok {
		t.Error("entries[\"hello\"] not found")
	} else if e.priority != 5 {
		t.Errorf("hello priority = %d, want 5 (default)", e.priority)
	}
}

// Test 4: Comment keys — keys starting with "//" are skipped.
func TestLoadTextDictJSON_CommentKeys(t *testing.T) {
	content := `{
		"version": "2.0",
		"entries": {
			"// this is a comment": "ignored",
			"Python": {"pronunciation": "パイソン", "priority": 9},
			"// another comment":   "also ignored"
		}
	}`
	path := writeTempJSON(t, content)

	td, err := LoadTextDictJSON(path)
	if err != nil {
		t.Fatalf("LoadTextDictJSON error: %v", err)
	}
	if td.Len() != 1 {
		t.Errorf("Len() = %d, want 1 (comments should be skipped)", td.Len())
	}
}

// Test 5: Metadata keys — "version", "description", "metadata" are skipped inside entries.
func TestLoadTextDictJSON_MetadataKeys(t *testing.T) {
	content := `{
		"version": "2.0",
		"description": "Test dictionary",
		"metadata": {"author": "test"},
		"entries": {
			"version":     "ignored inside entries",
			"description": "ignored inside entries",
			"metadata":    "ignored inside entries",
			"hello":       "ハロー"
		}
	}`
	path := writeTempJSON(t, content)

	td, err := LoadTextDictJSON(path)
	if err != nil {
		t.Fatalf("LoadTextDictJSON error: %v", err)
	}
	if td.Len() != 1 {
		t.Errorf("Len() = %d, want 1 (metadata keys inside entries should be skipped)", td.Len())
	}
}

// Test 6: Invalid JSON — returns error.
func TestLoadTextDictJSON_InvalidJSON(t *testing.T) {
	path := writeTempJSON(t, `{this is not valid json}`)

	_, err := LoadTextDictJSON(path)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

// Test 7: File not found — returns error.
func TestLoadTextDictJSON_FileNotFound(t *testing.T) {
	_, err := LoadTextDictJSON("/nonexistent/path/dict.json")
	if err == nil {
		t.Fatal("expected error for nonexistent file, got nil")
	}
}

// Test 8: Empty entries — returns empty dict, no error.
func TestLoadTextDictJSON_EmptyEntries(t *testing.T) {
	content := `{"version": "2.0", "entries": {}}`
	path := writeTempJSON(t, content)

	td, err := LoadTextDictJSON(path)
	if err != nil {
		t.Fatalf("LoadTextDictJSON error: %v", err)
	}
	if td.Len() != 0 {
		t.Errorf("Len() = %d, want 0", td.Len())
	}
}

// ===========================================================================
// Priority tests
// ===========================================================================

// Test 9: Higher priority override — second file with higher priority overrides.
func TestLoadTextDictJSONFiles_HigherPriorityOverride(t *testing.T) {
	file1 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"API": {"pronunciation": "エーピーアイ", "priority": 5}
		}
	}`)
	file2 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"API": {"pronunciation": "アピ", "priority": 9}
		}
	}`)

	td, err := LoadTextDictJSONFiles([]string{file1, file2})
	if err != nil {
		t.Fatalf("LoadTextDictJSONFiles error: %v", err)
	}
	if td.Len() != 1 {
		t.Fatalf("Len() = %d, want 1", td.Len())
	}

	e := td.entries["api"]
	if e.pronunciation != "アピ" {
		t.Errorf("pronunciation = %q, want アピ (higher priority)", e.pronunciation)
	}
	if e.priority != 9 {
		t.Errorf("priority = %d, want 9", e.priority)
	}
}

// Test 10: Lower priority ignored — second file with lower/equal priority doesn't override.
func TestLoadTextDictJSONFiles_LowerPriorityIgnored(t *testing.T) {
	file1 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"API": {"pronunciation": "エーピーアイ", "priority": 9}
		}
	}`)
	file2 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"API": {"pronunciation": "アピ", "priority": 5}
		}
	}`)

	td, err := LoadTextDictJSONFiles([]string{file1, file2})
	if err != nil {
		t.Fatalf("LoadTextDictJSONFiles error: %v", err)
	}

	e := td.entries["api"]
	if e.pronunciation != "エーピーアイ" {
		t.Errorf("pronunciation = %q, want エーピーアイ (original higher priority should be kept)", e.pronunciation)
	}

	// Also test equal priority — should NOT override.
	file3 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"API": {"pronunciation": "アピ", "priority": 9}
		}
	}`)
	td2, err := LoadTextDictJSONFiles([]string{file1, file3})
	if err != nil {
		t.Fatalf("LoadTextDictJSONFiles error: %v", err)
	}

	e2 := td2.entries["api"]
	if e2.pronunciation != "エーピーアイ" {
		t.Errorf("equal priority: pronunciation = %q, want エーピーアイ (should not override)", e2.pronunciation)
	}
}

// Test 11: Same word different case — mixed-case stored separately from normalized.
func TestLoadTextDictJSONFiles_SameWordDifferentCase(t *testing.T) {
	file1 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"GitHub":  {"pronunciation": "ギットハブ", "priority": 9},
			"github":  {"pronunciation": "ギトハブ", "priority": 5}
		}
	}`)

	td, err := LoadTextDictJSONFiles([]string{file1})
	if err != nil {
		t.Fatalf("LoadTextDictJSONFiles error: %v", err)
	}
	if td.Len() != 2 {
		t.Fatalf("Len() = %d, want 2 (mixed case and uniform case stored separately)", td.Len())
	}

	// "GitHub" (mixed case) -> caseSensitive map.
	if e, ok := td.caseSensitive["GitHub"]; !ok {
		t.Error("caseSensitive[\"GitHub\"] not found")
	} else if e.pronunciation != "ギットハブ" {
		t.Errorf("GitHub pronunciation = %q, want ギットハブ", e.pronunciation)
	}

	// "github" (all lower) -> entries map.
	if e, ok := td.entries["github"]; !ok {
		t.Error("entries[\"github\"] not found")
	} else if e.pronunciation != "ギトハブ" {
		t.Errorf("github pronunciation = %q, want ギトハブ", e.pronunciation)
	}
}

// ===========================================================================
// ApplyToText tests
// ===========================================================================

// Test 12: Basic substitution.
func TestApplyToText_BasicSubstitution(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	td.addEntry("Python", "パイソン", 9)
	td.addEntry("Rust", "ラスト", 9)

	got := td.ApplyToText("PythonとRust")
	want := "パイソンとラスト"
	if got != want {
		t.Errorf("ApplyToText = %q, want %q", got, want)
	}
}

// Test 13: Word boundary (ASCII) — "API" matches alone but not in "RAPID".
func TestApplyToText_WordBoundaryASCII(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	td.addEntry("API", "エーピーアイ", 9)

	// Standalone match.
	got := td.ApplyToText("the API is great")
	if got != "the エーピーアイ is great" {
		t.Errorf("standalone: got %q, want %q", got, "the エーピーアイ is great")
	}

	// Should NOT match inside "RAPID".
	got2 := td.ApplyToText("RAPID development")
	if got2 != "RAPID development" {
		t.Errorf("inside word: got %q, want %q (should not match inside RAPID)", got2, "RAPID development")
	}
}

// Test 14: No boundary (Japanese) — matches within continuous text.
func TestApplyToText_NoBoundaryJapanese(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	td.addEntry("成功", "セイコウ", 9)

	got := td.ApplyToText("大成功です")
	want := "大セイコウです"
	if got != want {
		t.Errorf("ApplyToText = %q, want %q", got, want)
	}
}

// Test 15: Case insensitive — "python" matches entry "Python" (uniform case entry).
func TestApplyToText_CaseInsensitive(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	// "PYTHON" is all-upper -> stored in entries (normalized to "python").
	td.addEntry("PYTHON", "パイソン", 9)

	got := td.ApplyToText("I love python")
	want := "I love パイソン"
	if got != want {
		t.Errorf("ApplyToText = %q, want %q", got, want)
	}

	// Also match uppercase.
	got2 := td.ApplyToText("PYTHON is great")
	want2 := "パイソン is great"
	if got2 != want2 {
		t.Errorf("ApplyToText = %q, want %q", got2, want2)
	}
}

// Test 16: Case sensitive — "GitHub" (mixed case) only matches exact case.
func TestApplyToText_CaseSensitive(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	td.addEntry("GitHub", "ギットハブ", 9)

	// Exact case match.
	got := td.ApplyToText("Use GitHub for repos")
	if got != "Use ギットハブ for repos" {
		t.Errorf("exact case: got %q, want %q", got, "Use ギットハブ for repos")
	}

	// Different case should NOT match.
	got2 := td.ApplyToText("Use GITHUB for repos")
	if got2 != "Use GITHUB for repos" {
		t.Errorf("wrong case: got %q, want %q (should not match)", got2, "Use GITHUB for repos")
	}

	got3 := td.ApplyToText("Use github for repos")
	if got3 != "Use github for repos" {
		t.Errorf("lowercase: got %q, want %q (should not match)", got3, "Use github for repos")
	}
}

// Test 17: Longest first — "Python3" matches before "Python".
func TestApplyToText_LongestFirst(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	// Both mixed case, so both go to caseSensitive map.
	td.addEntry("Python", "パイソン", 9)
	td.addEntry("Python3", "パイソンスリー", 9)

	got := td.ApplyToText("Use Python3 today")
	want := "Use パイソンスリー today"
	if got != want {
		t.Errorf("ApplyToText = %q, want %q", got, want)
	}

	// Plain "Python" should still match when "Python3" is not present.
	got2 := td.ApplyToText("Use Python today")
	want2 := "Use パイソン today"
	if got2 != want2 {
		t.Errorf("ApplyToText = %q, want %q", got2, want2)
	}
}

// Test 18: No match — text unchanged when word not in dict.
func TestApplyToText_NoMatch(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	td.addEntry("Python", "パイソン", 9)

	got := td.ApplyToText("Hello world")
	want := "Hello world"
	if got != want {
		t.Errorf("ApplyToText = %q, want %q", got, want)
	}
}

// Test 19: Empty text — returns empty string.
func TestApplyToText_EmptyText(t *testing.T) {
	td := &TextDictionary{
		entries:       make(map[string]textEntry),
		caseSensitive: make(map[string]textEntry),
	}
	td.addEntry("Python", "パイソン", 9)

	got := td.ApplyToText("")
	if got != "" {
		t.Errorf("ApplyToText(\"\") = %q, want empty string", got)
	}
}

// ===========================================================================
// Integration tests
// ===========================================================================

// Test 20: Multiple files merge — load 2 files, verify merged entries.
func TestLoadTextDictJSONFiles_MultipleMerge(t *testing.T) {
	file1 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"Python": {"pronunciation": "パイソン", "priority": 9},
			"API":    {"pronunciation": "エーピーアイ", "priority": 8}
		}
	}`)
	file2 := writeTempJSON(t, `{
		"version": "2.0",
		"entries": {
			"Rust":   {"pronunciation": "ラスト", "priority": 7},
			"API":    {"pronunciation": "アピ", "priority": 10}
		}
	}`)

	td, err := LoadTextDictJSONFiles([]string{file1, file2})
	if err != nil {
		t.Fatalf("LoadTextDictJSONFiles error: %v", err)
	}

	// Should have 3 entries: Python (caseSensitive), Rust (caseSensitive), API (entries).
	if td.Len() != 3 {
		t.Fatalf("Len() = %d, want 3", td.Len())
	}

	// Python from file1.
	if e, ok := td.caseSensitive["Python"]; !ok {
		t.Error("Python not found in merged dict")
	} else if e.pronunciation != "パイソン" {
		t.Errorf("Python pronunciation = %q, want パイソン", e.pronunciation)
	}

	// Rust from file2.
	if e, ok := td.caseSensitive["Rust"]; !ok {
		t.Error("Rust not found in merged dict")
	} else if e.pronunciation != "ラスト" {
		t.Errorf("Rust pronunciation = %q, want ラスト", e.pronunciation)
	}

	// API: file2 priority 10 > file1 priority 8 -> file2 wins.
	if e, ok := td.entries["api"]; !ok {
		t.Error("api not found in merged dict")
	} else {
		if e.pronunciation != "アピ" {
			t.Errorf("API pronunciation = %q, want アピ (higher priority from file2)", e.pronunciation)
		}
		if e.priority != 10 {
			t.Errorf("API priority = %d, want 10", e.priority)
		}
	}

	// Verify ApplyToText with merged dict.
	got := td.ApplyToText("Python API Rust")
	want := "パイソン アピ ラスト"
	if got != want {
		t.Errorf("ApplyToText = %q, want %q", got, want)
	}
}

// ===========================================================================
// FindDefaultDicts tests
// ===========================================================================

func TestFindDefaultDicts_ModelDir(t *testing.T) {
	dir := t.TempDir()
	dictDir := filepath.Join(dir, "dictionaries")
	if err := os.MkdirAll(dictDir, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dictDir, "test.json"), []byte(`{}`), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dictDir, "other.json"), []byte(`{}`), 0644); err != nil {
		t.Fatal(err)
	}
	// Non-JSON file should be ignored.
	if err := os.WriteFile(filepath.Join(dictDir, "readme.txt"), []byte("ignore me"), 0644); err != nil {
		t.Fatal(err)
	}

	results := FindDefaultDicts(dir)
	if len(results) != 2 {
		t.Fatalf("FindDefaultDicts returned %d files, want 2: %v", len(results), results)
	}
}

func TestFindDefaultDicts_EnvVar(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "env_dict.json"), []byte(`{}`), 0644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("PIPER_CUSTOM_DICT_PATH", dir)

	results := FindDefaultDicts("")
	found := false
	for _, r := range results {
		if filepath.Base(r) == "env_dict.json" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("FindDefaultDicts did not find env_dict.json in PIPER_CUSTOM_DICT_PATH results: %v", results)
	}
}

func TestFindDefaultDicts_EmptyModelDir(t *testing.T) {
	// Unset env var to avoid interference.
	t.Setenv("PIPER_CUSTOM_DICT_PATH", "")

	results := FindDefaultDicts("")
	// Should not panic; may return empty or find exe-relative dicts.
	_ = results
}

// ===========================================================================
// isMixedCase tests
// ===========================================================================

func TestIsMixedCase(t *testing.T) {
	tests := []struct {
		word string
		want bool
	}{
		{"GitHub", true},
		{"iPhone", true},
		{"MacOS", true},
		{"ALLCAPS", false},
		{"lowercase", false},
		{"123", false},
		{"API", false},
		{"パイソン", false},
		{"", false},
	}

	for _, tc := range tests {
		got := isMixedCase(tc.word)
		if got != tc.want {
			t.Errorf("isMixedCase(%q) = %v, want %v", tc.word, got, tc.want)
		}
	}
}

// ===========================================================================
// Helper: write a temporary JSON file
// ===========================================================================

func writeTempJSON(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "dict.json")
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write temp JSON: %v", err)
	}
	return path
}

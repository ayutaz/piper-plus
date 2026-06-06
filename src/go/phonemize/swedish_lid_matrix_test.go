// Cross-runtime Swedish per-word LID parity fixture matrix (Issue #539).
//
// Loads `testdata/swedish_lid_matrix.json` (mirrored byte-for-byte from the
// canonical `tests/fixtures/g2p/swedish_lid_matrix.json` by
// scripts/check_swedish_lid_consistency.py) and verifies that SegmentText
// agrees with each case's expect_contains_sv flag. The sister tests in
// Python / Rust×2 / C++ / C# / WASM consume the *same* fixture, so
// cross-runtime agreement on these cases is the parity proof.
//
// Mirror of TestFixtureMatrixLoadable (zh_en loanword, chinese_loanword_test.go).

package phonemize

import (
	"encoding/json"
	"os"
	"testing"
)

type swedishLidCase struct {
	Text             string `json:"text"`
	ExpectContainsSv bool   `json:"expect_contains_sv"`
}

type swedishLidMatrix struct {
	SchemaVersion int              `json:"schema_version"`
	Languages     []string         `json:"languages"`
	DefaultLatin  string           `json:"default_latin"`
	Cases         []swedishLidCase `json:"cases"`
}

// containsSwedish reports whether any segment of text is classified as "sv".
func containsSwedishSegment(langs []string, defaultLatin, text string) bool {
	d := NewUnicodeLanguageDetector(langs, defaultLatin)
	for _, seg := range SegmentText(text, d) {
		if seg.Language == "sv" {
			return true
		}
	}
	return false
}

func TestSwedishLidMatrix(t *testing.T) {
	raw, err := os.ReadFile("testdata/swedish_lid_matrix.json")
	if err != nil {
		t.Fatalf("matrix not found (sync gate should have copied it): %v", err)
	}
	var m swedishLidMatrix
	if err := json.Unmarshal(raw, &m); err != nil {
		t.Fatalf("matrix is not valid JSON: %v", err)
	}
	if m.SchemaVersion != 1 {
		t.Errorf("schema_version = %d, want 1", m.SchemaVersion)
	}
	if len(m.Cases) == 0 {
		t.Fatal("matrix `cases` must be non-empty")
	}

	checked := 0
	for _, c := range m.Cases {
		got := containsSwedishSegment(m.Languages, m.DefaultLatin, c.Text)
		if got != c.ExpectContainsSv {
			t.Errorf(
				"matrix case %q: expected contains_sv=%v, got %v\n"+
					"  → if intentional, update tests/fixtures/g2p/swedish_lid_matrix.json "+
					"and re-sync via `python scripts/check_swedish_lid_consistency.py --fix`",
				c.Text, c.ExpectContainsSv, got,
			)
		}
		checked++
	}
	if checked < 10 {
		t.Fatalf("expected >=10 matrix cases, checked %d", checked)
	}
}

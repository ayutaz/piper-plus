package phonemize

import (
	"os"
	"path/filepath"
	"testing"
)

// ---------------------------------------------------------------------------
// CustomDictionary: Add and Lookup
// ---------------------------------------------------------------------------

func TestCustomDictionary_AddAndLookup(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("hello", []string{"h", "ə", "l", "oʊ"})

	got := d.Lookup("hello")
	if got == nil {
		t.Fatal("Lookup(\"hello\") returned nil, want phonemes")
	}
	want := []string{"h", "ə", "l", "oʊ"}
	if len(got) != len(want) {
		t.Fatalf("Lookup(\"hello\") = %v, want %v", got, want)
	}
	for i, w := range want {
		if got[i] != w {
			t.Errorf("Lookup(\"hello\")[%d] = %q, want %q", i, got[i], w)
		}
	}
}

// ---------------------------------------------------------------------------
// CustomDictionary: case-insensitive lookup
// ---------------------------------------------------------------------------

func TestCustomDictionary_CaseInsensitive(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("Hello", []string{"h", "ə", "l", "oʊ"})

	got := d.Lookup("hello")
	if got == nil {
		t.Fatal("Lookup(\"hello\") returned nil after Add(\"Hello\")")
	}

	got2 := d.Lookup("HELLO")
	if got2 == nil {
		t.Fatal("Lookup(\"HELLO\") returned nil after Add(\"Hello\")")
	}
}

// ---------------------------------------------------------------------------
// CustomDictionary: not found returns nil
// ---------------------------------------------------------------------------

func TestCustomDictionary_NotFound(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("hello", []string{"h", "ə", "l", "oʊ"})

	got := d.Lookup("world")
	if got != nil {
		t.Errorf("Lookup(\"world\") = %v, want nil", got)
	}
}

// ---------------------------------------------------------------------------
// LoadDictFile: load from temp file
// ---------------------------------------------------------------------------

func TestLoadDictFile(t *testing.T) {
	content := "hello h ə l oʊ\nworld w ɜː l d\n"
	path := writeTempDict(t, content)

	d, err := LoadDictFile(path)
	if err != nil {
		t.Fatalf("LoadDictFile error: %v", err)
	}

	if d.Len() != 2 {
		t.Fatalf("Len() = %d, want 2", d.Len())
	}

	got := d.Lookup("hello")
	if got == nil {
		t.Fatal("Lookup(\"hello\") returned nil")
	}
	wantHello := []string{"h", "ə", "l", "oʊ"}
	if len(got) != len(wantHello) {
		t.Fatalf("Lookup(\"hello\") = %v, want %v", got, wantHello)
	}
	for i, w := range wantHello {
		if got[i] != w {
			t.Errorf("hello[%d] = %q, want %q", i, got[i], w)
		}
	}

	gotW := d.Lookup("world")
	if gotW == nil {
		t.Fatal("Lookup(\"world\") returned nil")
	}
	wantWorld := []string{"w", "ɜː", "l", "d"}
	if len(gotW) != len(wantWorld) {
		t.Fatalf("Lookup(\"world\") = %v, want %v", gotW, wantWorld)
	}
	for i, w := range wantWorld {
		if gotW[i] != w {
			t.Errorf("world[%d] = %q, want %q", i, gotW[i], w)
		}
	}
}

// ---------------------------------------------------------------------------
// LoadDictFile: comments and blank lines are skipped
// ---------------------------------------------------------------------------

func TestLoadDictFile_Comments(t *testing.T) {
	content := "# This is a comment\n\nhello h ə l oʊ\n# Another comment\nworld w ɜː l d\n\n"
	path := writeTempDict(t, content)

	d, err := LoadDictFile(path)
	if err != nil {
		t.Fatalf("LoadDictFile error: %v", err)
	}

	if d.Len() != 2 {
		t.Errorf("Len() = %d, want 2 (comments and blanks should be skipped)", d.Len())
	}

	if d.Lookup("hello") == nil {
		t.Error("Lookup(\"hello\") returned nil")
	}
	if d.Lookup("world") == nil {
		t.Error("Lookup(\"world\") returned nil")
	}
}

// ---------------------------------------------------------------------------
// CustomDictionary: Len
// ---------------------------------------------------------------------------

func TestCustomDictionary_Len(t *testing.T) {
	d := NewCustomDictionary()
	if d.Len() != 0 {
		t.Errorf("empty dict Len() = %d, want 0", d.Len())
	}

	d.Add("hello", []string{"h", "ə", "l", "oʊ"})
	if d.Len() != 1 {
		t.Errorf("after 1 Add, Len() = %d, want 1", d.Len())
	}

	d.Add("world", []string{"w", "ɜː", "l", "d"})
	if d.Len() != 2 {
		t.Errorf("after 2 Add, Len() = %d, want 2", d.Len())
	}

	// Overwriting an existing entry should not increase count.
	d.Add("hello", []string{"h", "ɛ", "l", "oʊ"})
	if d.Len() != 2 {
		t.Errorf("after overwrite, Len() = %d, want 2", d.Len())
	}
}

// ---------------------------------------------------------------------------
// Helper: write a temporary dictionary file
// ---------------------------------------------------------------------------

func writeTempDict(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "dict.txt")
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write temp dict: %v", err)
	}
	return path
}

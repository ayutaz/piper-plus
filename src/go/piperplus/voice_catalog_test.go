package piperplus

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestFindVoice_ExactKey(t *testing.T) {
	e, ok := FindVoice("ja_JP-tsukuyomi-chan-medium")
	if !ok {
		t.Fatal("expected to find voice")
	}
	if e.Key != "ja_JP-tsukuyomi-chan-medium" {
		t.Errorf("unexpected key: %s", e.Key)
	}
}

func TestFindVoice_Alias(t *testing.T) {
	e, ok := FindVoice("tsukuyomi-chan")
	if !ok {
		t.Fatal("expected to find voice by alias")
	}
	if e.Key != "ja_JP-tsukuyomi-chan-medium" {
		t.Errorf("unexpected key: %s", e.Key)
	}
}

func TestFindVoice_NotFound(t *testing.T) {
	_, ok := FindVoice("nonexistent")
	if ok {
		t.Error("expected not found")
	}
}

func TestListVoices_All(t *testing.T) {
	voices := ListVoices("")
	if len(voices) < 2 {
		t.Errorf("expected at least 2 voices, got %d", len(voices))
	}
}

func TestListVoices_Filter(t *testing.T) {
	voices := ListVoices("ja")
	for _, v := range voices {
		if v.LanguageFamily != "ja" && !strings.HasPrefix(v.LanguageCode, "ja") {
			t.Errorf("unexpected language: %s", v.LanguageCode)
		}
	}
}

func TestVoiceCatalogEntry_OnnxFileName(t *testing.T) {
	e, _ := FindVoice("tsukuyomi-chan")
	name := e.OnnxFileName()
	if name != "tsukuyomi-chan-6lang-fp16.onnx" {
		t.Errorf("unexpected onnx name: %s", name)
	}
}

func TestPublicBasePinnedPair(t *testing.T) {
	for _, alias := range []string{"base", "zero-shot-base-zs-v1", "ayousanz/piper-plus-base"} {
		entry, ok := FindVoice(alias)
		if !ok {
			t.Fatalf("missing alias %s", alias)
		}
		if entry.Revision != "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1" || entry.Quality != "experimental" || entry.NumSpeakers != 571 {
			t.Fatalf("wrong base metadata: %+v", entry)
		}
		if len(entry.Files) != 2 || entry.Files[0].RelativePath != "releases/zs-v1/base.onnx" || entry.Files[1].RelativePath != "releases/zs-v1/base.onnx.json" {
			t.Fatalf("wrong TTS pair: %+v", entry.Files)
		}
	}
}

// TestVoiceCatalog_NoticeMatchesCanonical compares the notice and notice_files
// of every embedded entry with test/model_resolution_vectors.json, the
// canonical source (docs/reference/model-resolution.md section 9).
func TestVoiceCatalog_NoticeMatchesCanonical(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("..", "..", "..", "test", "model_resolution_vectors.json"))
	if err != nil {
		t.Skipf("canonical vectors not available: %v", err)
	}
	var vectors struct {
		VoiceCatalog map[string]json.RawMessage `json:"voice_catalog"`
	}
	if err := json.Unmarshal(data, &vectors); err != nil {
		t.Fatalf("parse vectors: %v", err)
	}
	for _, e := range embeddedCatalog {
		raw, ok := vectors.VoiceCatalog[e.Key]
		if !ok {
			continue
		}
		var canon struct {
			Notice      []string `json:"notice"`
			NoticeFiles []string `json:"notice_files"`
		}
		if err := json.Unmarshal(raw, &canon); err != nil {
			t.Fatalf("parse %s: %v", e.Key, err)
		}
		if !reflect.DeepEqual(e.Notice, canon.Notice) {
			t.Errorf("%s: notice = %q, want %q", e.Key, e.Notice, canon.Notice)
		}
		if !reflect.DeepEqual(e.NoticeFiles, canon.NoticeFiles) {
			t.Errorf("%s: notice_files = %q, want %q", e.Key, e.NoticeFiles, canon.NoticeFiles)
		}
	}
}

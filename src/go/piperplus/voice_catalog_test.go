package piperplus

import (
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

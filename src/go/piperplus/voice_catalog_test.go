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

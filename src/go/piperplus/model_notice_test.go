package piperplus

import (
	"strings"
	"testing"
)

func TestModelNotice_Detection(t *testing.T) {
	cases := []struct {
		name  string
		input string
		want  bool
	}{
		{"key", "ja_JP-tsukuyomi-chan-medium", true},
		{"alias tsukuyomi", "tsukuyomi", true},
		{"alias tsukuyomi-chan", "tsukuyomi-chan", true},
		{"alias ja-tsukuyomi", "ja-tsukuyomi", true},
		{"repo id", "ayousanz/piper-plus-tsukuyomi-chan", true},
		{"hf url", "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx", true},
		{"hf url other file", "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/abc/releases/zs-v1/config.json", true},
		{"url by file name with query", "https://example.com/models/tsukuyomi.onnx?download=1", true},
		{"posix path fp16", "/home/u/models/tsukuyomi-chan-6lang-fp16.onnx", true},
		{"posix path zs", "/home/u/releases/zs-v1/tsukuyomi.onnx", true},
		{"windows path fp16", `C:\Users\u\models\tsukuyomi-chan-6lang-fp16.onnx`, true},
		{"windows path zs", `C:\models\tsukuyomi.onnx`, true},
		{"bare file name", "tsukuyomi.onnx", true},
		{"css10 key", "ja_JP-css10-6lang-medium", false},
		{"css10 alias", "css10", false},
		{"css10 repo", "ayousanz/piper-plus-css10-ja-6lang", false},
		{"css10 url", "https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang/resolve/main/css10-ja-6lang-fp16.onnx", false},
		{"base alias", "base", false},
		{"base repo", "ayousanz/piper-plus-base", false},
		{"base path", "/models/releases/zs-v1/base.onnx", false},
		{"empty", "", false},
		{"alias with different case", "Tsukuyomi", false},
		{"alias with spaces", " tsukuyomi ", false},
		{"similar file name", "/models/tsukuyomi.onnx.json", false},
		{"repo id without slashes in non-url", "models/ayousanz/piper-plus-tsukuyomi-chan/model.onnx", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := ModelNotice(c.input)
			if (got != nil) != c.want {
				t.Fatalf("ModelNotice(%q) = %v, want notice=%v", c.input, got, c.want)
			}
		})
	}
}

func TestModelNotice_ReturnsCatalogLines(t *testing.T) {
	entry, ok := FindVoice("tsukuyomi")
	if !ok {
		t.Fatal("tsukuyomi entry missing")
	}
	got := ModelNotice("tsukuyomi")
	if len(got) != 6 || len(got) != len(entry.Notice) {
		t.Fatalf("notice has %d lines, want 6 (catalog %d)", len(got), len(entry.Notice))
	}
	for i := range got {
		if got[i] != entry.Notice[i] {
			t.Errorf("line %d = %q, want %q", i, got[i], entry.Notice[i])
		}
	}
	if !strings.HasPrefix(got[0], "[piper-plus] ") {
		t.Errorf("first line = %q", got[0])
	}
	// The returned slice is a copy: mutating it must not alter the catalog.
	got[0] = "changed"
	if again := ModelNotice("tsukuyomi"); again[0] == "changed" {
		t.Error("ModelNotice returned the catalog's backing slice")
	}
}

func TestModelNotice_OnlyTsukuyomiHasNotice(t *testing.T) {
	for _, e := range embeddedCatalog {
		hasNotice := len(e.Notice) > 0
		if want := e.Key == "ja_JP-tsukuyomi-chan-medium"; hasNotice != want {
			t.Errorf("%s: has notice = %v, want %v", e.Key, hasNotice, want)
		}
		if hasNotice && len(e.NoticeFiles) == 0 {
			t.Errorf("%s: notice without notice_files", e.Key)
		}
		for _, line := range e.Notice {
			if strings.ContainsAny(line, "\"\\") || strings.TrimSpace(line) == "" {
				t.Errorf("%s: notice line not literal-safe: %q", e.Key, line)
			}
		}
	}
}

func TestModelNoticeFooter(t *testing.T) {
	want := "(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)"
	if ModelNoticeFooter != want {
		t.Errorf("ModelNoticeFooter = %q, want %q", ModelNoticeFooter, want)
	}
}

func TestParseModelNoticeDisabled(t *testing.T) {
	cases := []struct {
		in   string
		want bool
	}{
		{"1", true},
		{"true", true},
		{" TRUE ", true},
		{"True", true},
		{"yes", true},
		{"YES\n", true},
		{"0", false},
		{"", false},
		{"false", false},
		{"no", false},
		{"on", false},
		{"2", false},
	}
	for _, c := range cases {
		if got := ParseModelNoticeDisabled(c.in); got != c.want {
			t.Errorf("ParseModelNoticeDisabled(%q) = %v, want %v", c.in, got, c.want)
		}
	}
}

func TestModelNoticeDisabled_Env(t *testing.T) {
	t.Setenv(ModelNoticeEnv, " Yes ")
	if !ModelNoticeDisabled() {
		t.Error("expected disabled for ' Yes '")
	}
	t.Setenv(ModelNoticeEnv, "0")
	if ModelNoticeDisabled() {
		t.Error("expected enabled for '0'")
	}
	t.Setenv(ModelNoticeEnv, "")
	if ModelNoticeDisabled() {
		t.Error("expected enabled for empty value")
	}
}

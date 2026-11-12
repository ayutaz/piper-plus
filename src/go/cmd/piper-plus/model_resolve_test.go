package main

import (
	"context"
	"io"
	"log/slog"
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

func quietManager(t *testing.T) *piperplus.ModelManager {
	t.Helper()
	return piperplus.NewModelManager(t.TempDir(), slog.New(slog.NewTextHandler(io.Discard, nil)))
}

// cacheVoice places every file of a catalog voice in its cache directory with
// the catalog size, so resolution needs no network.
func cacheVoice(t *testing.T, mgr *piperplus.ModelManager, entry *piperplus.VoiceCatalogEntry) {
	t.Helper()
	dir := mgr.VoiceDir(entry)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	for _, f := range entry.Files {
		fh, err := os.Create(filepath.Join(dir, path.Base(f.RelativePath)))
		if err != nil {
			t.Fatal(err)
		}
		if err := fh.Truncate(f.SizeBytes); err != nil {
			t.Fatal(err)
		}
		_ = fh.Close()
	}
}

// Every catalog key and alias (the names test/model_resolution_vectors.json
// lists; TestFindVoice_EveryCanonicalName pins them to that file) resolves to
// the catalog voice's .onnx in the cache.
func TestResolveModelArg_EveryCatalogNameUsesTheCachedVoice(t *testing.T) {
	for _, name := range piperplus.CatalogNames() {
		t.Run(name, func(t *testing.T) {
			mgr := quietManager(t)
			entry, _ := piperplus.FindVoice(name)
			cacheVoice(t, mgr, entry)

			got, err := resolveModelArg(context.Background(), mgr, name)
			if err != nil {
				t.Fatalf("resolveModelArg(%q): %v", name, err)
			}
			want := filepath.Join(mgr.VoiceDir(entry), entry.OnnxFileName())
			if got != want {
				t.Errorf("resolveModelArg(%q) = %q, want %q", name, got, want)
			}
		})
	}
}

func TestResolveModelArg_ExistingFileIsUsedAsIs(t *testing.T) {
	mgr := quietManager(t)
	p := writeFakeModel(t, "tsukuyomi.onnx")
	got, err := resolveModelArg(context.Background(), mgr, p)
	if err != nil || got != p {
		t.Fatalf("resolveModelArg(%q) = %q, %v; want the path", p, got, err)
	}
}

// A copy downloaded by name before the CLI knew the catalog
// ({cache}/{name}.onnx) keeps working without a download.
func TestResolveModelArg_KeepsAnEarlierCacheOfTheName(t *testing.T) {
	mgr := quietManager(t)
	flat := filepath.Join(mgr.CacheDir(), "tsukuyomi.onnx")
	if err := os.WriteFile(flat, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := resolveModelArg(context.Background(), mgr, "tsukuyomi")
	if err != nil || got != flat {
		t.Fatalf("resolveModelArg = %q, %v; want %q", got, err, flat)
	}
}

func TestResolveModelArg_CachedNonCatalogName(t *testing.T) {
	mgr := quietManager(t)
	p := filepath.Join(mgr.CacheDir(), "my-voice", "my-voice.onnx")
	if err := os.MkdirAll(filepath.Dir(p), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := resolveModelArg(context.Background(), mgr, "my-voice")
	if err != nil || got != p {
		t.Fatalf("resolveModelArg = %q, %v; want %q", got, err, p)
	}
}

func TestResolveModelArg_UnknownNameListsTheCatalog(t *testing.T) {
	mgr := quietManager(t)
	_, err := resolveModelArg(context.Background(), mgr, "nonexistent-model-xyz")
	if err == nil {
		t.Fatal("unknown name resolved")
	}
	for _, want := range []string{"nonexistent-model-xyz", "tsukuyomi", "css10", "base"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q lacks %q", err, want)
		}
	}
}

func TestDownloadModelArg_CatalogNameUsesTheCatalog(t *testing.T) {
	mgr := quietManager(t)
	entry, _ := piperplus.FindVoice("css10")
	cacheVoice(t, mgr, entry)
	got, err := downloadModelArg(context.Background(), mgr, "ja-css10")
	if err != nil {
		t.Fatalf("downloadModelArg: %v", err)
	}
	if want := filepath.Join(mgr.VoiceDir(entry), entry.OnnxFileName()); got != want {
		t.Errorf("downloadModelArg = %q, want %q", got, want)
	}
}

func TestDownloadModelArg_OtherInputIsAURL(t *testing.T) {
	mgr := quietManager(t)
	_, err := downloadModelArg(context.Background(), mgr, "ftp://example.com/model.onnx")
	if err == nil || !strings.Contains(err.Error(), "https://") {
		t.Fatalf("err = %v, want the URL scheme error", err)
	}
}

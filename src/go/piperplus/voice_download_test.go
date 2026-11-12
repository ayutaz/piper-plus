package piperplus

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

// fakeHub serves catalog files as https://huggingface.co does
// (/{repo}/resolve/{revision}/{path}) with bodies of the catalog sizes.
type fakeHub struct {
	mu       sync.Mutex
	requests []string
	server   *httptest.Server
}

func newFakeHub(t *testing.T) *fakeHub {
	t.Helper()
	hub := &fakeHub{}
	sizes := map[string]int64{}
	for _, e := range embeddedCatalog {
		rev := e.Revision
		if rev == "" {
			rev = "main"
		}
		for _, f := range e.Files {
			sizes["/"+e.RepoID+"/resolve/"+rev+"/"+f.RelativePath] = f.SizeBytes
		}
	}
	hub.server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hub.mu.Lock()
		hub.requests = append(hub.requests, r.URL.Path)
		hub.mu.Unlock()
		size, ok := sizes[r.URL.Path]
		if !ok {
			http.NotFound(w, r)
			return
		}
		_, _ = w.Write(make([]byte, size))
	}))
	t.Cleanup(hub.server.Close)
	return hub
}

func (h *fakeHub) paths() []string {
	h.mu.Lock()
	defer h.mu.Unlock()
	return append([]string(nil), h.requests...)
}

func testManager(t *testing.T, hub *fakeHub) *ModelManager {
	t.Helper()
	mgr := NewModelManager(t.TempDir(), slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError})))
	if hub != nil {
		mgr.hubURL = hub.server.URL
	}
	return mgr
}

// writeSized creates a file of the given size without writing its bytes.
func writeSized(t *testing.T, path string, size int64) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatal(err)
	}
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := f.Truncate(size); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}

func mustVoice(t *testing.T, name string) *VoiceCatalogEntry {
	t.Helper()
	v, ok := FindVoice(name)
	if !ok {
		t.Fatalf("FindVoice(%q) not found", name)
	}
	return v
}

func TestDownloadVoice_FetchesEveryFileFromThePinnedRevision(t *testing.T) {
	for _, e := range embeddedCatalog {
		e := e
		t.Run(e.Key, func(t *testing.T) {
			hub := newFakeHub(t)
			mgr := testManager(t, hub)

			path, err := mgr.DownloadVoice(context.Background(), &e)
			if err != nil {
				t.Fatalf("DownloadVoice: %v", err)
			}
			wantDir := filepath.Join(mgr.CacheDir(), e.Key)
			if want := filepath.Join(wantDir, e.OnnxFileName()); path != want {
				t.Errorf("path = %q, want %q", path, want)
			}
			rev := e.Revision
			if rev == "" {
				rev = "main"
			}
			for _, f := range e.Files {
				local := filepath.Join(wantDir, filepath.Base(f.RelativePath))
				fi, err := os.Stat(local)
				if err != nil {
					t.Fatalf("%s not downloaded: %v", local, err)
				}
				if fi.Size() != f.SizeBytes {
					t.Errorf("%s size = %d, want %d", local, fi.Size(), f.SizeBytes)
				}
				want := "/" + e.RepoID + "/resolve/" + rev + "/" + f.RelativePath
				found := false
				for _, p := range hub.paths() {
					found = found || p == want
				}
				if !found {
					t.Errorf("no request for %s; got %v", want, hub.paths())
				}
			}
		})
	}
}

// Two catalog voices both ship a file named config.json; each voice has its
// own directory so one download does not overwrite the other's config.
func TestDownloadVoice_VoicesDoNotShareConfig(t *testing.T) {
	hub := newFakeHub(t)
	mgr := testManager(t, hub)
	ctx := context.Background()

	tsukuyomi := mustVoice(t, "tsukuyomi")
	css10 := mustVoice(t, "css10")
	if _, err := mgr.DownloadVoice(ctx, tsukuyomi); err != nil {
		t.Fatal(err)
	}
	if _, err := mgr.DownloadVoice(ctx, css10); err != nil {
		t.Fatal(err)
	}
	for _, v := range []*VoiceCatalogEntry{tsukuyomi, css10} {
		fi, err := os.Stat(filepath.Join(mgr.CacheDir(), v.Key, "config.json"))
		if err != nil {
			t.Fatal(err)
		}
		want := v.Files[1].SizeBytes
		if fi.Size() != want {
			t.Errorf("%s config.json size = %d, want %d", v.Key, fi.Size(), want)
		}
	}
}

func TestDownloadVoice_SkipsFilesAlreadyCached(t *testing.T) {
	for _, name := range []string{"tsukuyomi", "base"} {
		t.Run(name, func(t *testing.T) {
			hub := newFakeHub(t)
			mgr := testManager(t, hub)
			v := mustVoice(t, name)
			for _, f := range v.Files {
				writeSized(t, filepath.Join(mgr.CacheDir(), v.Key, filepath.Base(f.RelativePath)), f.SizeBytes)
			}
			if _, err := mgr.DownloadVoice(context.Background(), v); err != nil {
				t.Fatal(err)
			}
			if got := hub.paths(); len(got) != 0 {
				t.Errorf("cached voice was downloaded again: %v", got)
			}
		})
	}
}

// A voice pinned to a revision has fixed file sizes, so a cached file of
// another size is fetched again.
func TestDownloadVoice_PinnedRefetchesAFileOfTheWrongSize(t *testing.T) {
	hub := newFakeHub(t)
	mgr := testManager(t, hub)
	v := mustVoice(t, "base")
	dir := filepath.Join(mgr.CacheDir(), v.Key)
	writeSized(t, filepath.Join(dir, "base.onnx"), 10)
	writeSized(t, filepath.Join(dir, "base.onnx.json"), v.Files[1].SizeBytes)

	if _, err := mgr.DownloadVoice(context.Background(), v); err != nil {
		t.Fatal(err)
	}
	if got := hub.paths(); len(got) != 1 || !strings.HasSuffix(got[0], "/base.onnx") {
		t.Errorf("requests = %v, want only base.onnx", got)
	}
}

func TestDownloadVoice_PinnedRejectsAResponseOfTheWrongSize(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("short"))
	}))
	t.Cleanup(server.Close)
	mgr := testManager(t, nil)
	mgr.hubURL = server.URL
	v := mustVoice(t, "base")

	if _, err := mgr.DownloadVoice(context.Background(), v); err == nil {
		t.Fatal("DownloadVoice accepted a file whose size differs from the pinned catalog")
	}
	if _, ok := mgr.CachedVoice(v); ok {
		t.Error("a rejected download must not leave a cached voice")
	}
	entries, _ := os.ReadDir(filepath.Join(mgr.CacheDir(), v.Key))
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".tmp") || e.Name() == "base.onnx" {
			t.Errorf("left %s behind", e.Name())
		}
	}
}

// A voice without a revision follows "main", whose files can change after
// the catalog was written (the Tsukuyomi-chan config.json did), so a size
// that differs from the catalog is accepted, both downloaded and cached.
func TestDownloadVoice_MainAcceptsAnotherSize(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("{}"))
	}))
	t.Cleanup(server.Close)
	mgr := testManager(t, nil)
	mgr.hubURL = server.URL
	v := mustVoice(t, "tsukuyomi")

	path, err := mgr.DownloadVoice(context.Background(), v)
	if err != nil {
		t.Fatalf("DownloadVoice: %v", err)
	}
	cached, ok := mgr.CachedVoice(v)
	if !ok || cached != path {
		t.Errorf("CachedVoice = %q, %v; want %q, true", cached, ok, path)
	}
}

func TestDownloadVoice_RejectsUnsafeCatalogValues(t *testing.T) {
	base := *mustVoice(t, "css10")
	cases := map[string]func(e *VoiceCatalogEntry){
		"key traversal":      func(e *VoiceCatalogEntry) { e.Key = "../evil" },
		"key separator":      func(e *VoiceCatalogEntry) { e.Key = "a/b" },
		"repo without owner": func(e *VoiceCatalogEntry) { e.RepoID = "evil" },
		"repo traversal":     func(e *VoiceCatalogEntry) { e.RepoID = "../evil/x" },
		"revision traversal": func(e *VoiceCatalogEntry) { e.Revision = "../main" },
		"file traversal": func(e *VoiceCatalogEntry) {
			e.Files = []VoiceFileInfo{{RelativePath: "../evil.onnx", SizeBytes: 1}}
		},
		"absolute file": func(e *VoiceCatalogEntry) {
			e.Files = []VoiceFileInfo{{RelativePath: "/etc/evil.onnx", SizeBytes: 1}}
		},
		"no onnx": func(e *VoiceCatalogEntry) {
			e.Files = []VoiceFileInfo{{RelativePath: "config.json", SizeBytes: 1}}
		},
	}
	for name, edit := range cases {
		t.Run(name, func(t *testing.T) {
			hub := newFakeHub(t)
			mgr := testManager(t, hub)
			e := base
			e.Files = append([]VoiceFileInfo(nil), base.Files...)
			edit(&e)
			if _, err := mgr.DownloadVoice(context.Background(), &e); err == nil {
				t.Fatal("unsafe catalog entry was accepted")
			}
			if got := hub.paths(); len(got) != 0 {
				t.Errorf("unsafe entry made requests: %v", got)
			}
		})
	}
}

func TestResolveVoice_EveryCanonicalNameDownloadsTheCatalogFiles(t *testing.T) {
	for _, tc := range loadCanonicalNames(t) {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			hub := newFakeHub(t)
			mgr := testManager(t, hub)
			path, err := mgr.ResolveVoice(context.Background(), tc.name)
			if err != nil {
				t.Fatalf("ResolveVoice(%q): %v", tc.name, err)
			}
			want := filepath.Join(mgr.CacheDir(), tc.key, filepath.Base(tc.onnxFile))
			if path != want {
				t.Errorf("ResolveVoice(%q) = %q, want %q", tc.name, path, want)
			}
		})
	}
}

func TestResolveVoice_UsesTheCacheWithoutNetwork(t *testing.T) {
	mgr := testManager(t, nil)
	mgr.hubURL = "http://127.0.0.1:1" // nothing listens here
	v := mustVoice(t, "base")
	for _, f := range v.Files {
		writeSized(t, filepath.Join(mgr.CacheDir(), v.Key, filepath.Base(f.RelativePath)), f.SizeBytes)
	}
	path, err := mgr.ResolveVoice(context.Background(), "base")
	if err != nil {
		t.Fatalf("ResolveVoice: %v", err)
	}
	if want := filepath.Join(mgr.CacheDir(), v.Key, "base.onnx"); path != want {
		t.Errorf("path = %q, want %q", path, want)
	}
}

func TestResolveVoice_UnknownName(t *testing.T) {
	mgr := testManager(t, newFakeHub(t))
	_, err := mgr.ResolveVoice(context.Background(), "nonexistent-model-xyz")
	if !errors.Is(err, ErrVoiceNotInCatalog) {
		t.Fatalf("err = %v, want ErrVoiceNotInCatalog", err)
	}
}

func TestCatalogNames_ListsEveryKeyAndAlias(t *testing.T) {
	names := CatalogNames()
	for _, tc := range loadCanonicalNames(t) {
		found := false
		for _, n := range names {
			found = found || n == tc.name
		}
		if !found {
			t.Errorf("CatalogNames() lacks %q", tc.name)
		}
	}
}

type canonicalName struct {
	name, key, onnxFile string
}

// loadCanonicalNames returns every key and alias of the canonical catalog
// (test/model_resolution_vectors.json) with the entry it belongs to.
func loadCanonicalNames(t *testing.T) []canonicalName {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "..", "test", "model_resolution_vectors.json"))
	if err != nil {
		t.Fatalf("read canonical vectors: %v", err)
	}
	var vectors struct {
		VoiceCatalog map[string]json.RawMessage `json:"voice_catalog"`
	}
	if err := json.Unmarshal(data, &vectors); err != nil {
		t.Fatalf("parse vectors: %v", err)
	}
	var names []canonicalName
	for key, raw := range vectors.VoiceCatalog {
		if strings.HasPrefix(key, "_") {
			continue
		}
		var canon struct {
			OnnxFile string   `json:"onnx_file"`
			Aliases  []string `json:"aliases"`
		}
		if err := json.Unmarshal(raw, &canon); err != nil {
			t.Fatalf("parse %s: %v", key, err)
		}
		for _, name := range append([]string{key}, canon.Aliases...) {
			names = append(names, canonicalName{name: name, key: key, onnxFile: canon.OnnxFile})
		}
	}
	if len(names) == 0 {
		t.Fatal("canonical catalog has no names")
	}
	return names
}

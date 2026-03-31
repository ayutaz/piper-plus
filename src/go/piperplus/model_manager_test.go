package piperplus

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// DefaultCacheDir tests
// ---------------------------------------------------------------------------

func TestDefaultCacheDir(t *testing.T) {
	// Ensure PIPER_MODEL_DIR is not set so we get the platform default.
	t.Setenv("PIPER_MODEL_DIR", "")

	dir := DefaultCacheDir()
	if dir == "" {
		t.Fatal("DefaultCacheDir() returned empty string")
	}
	if !strings.Contains(dir, "piper-plus") {
		t.Errorf("DefaultCacheDir() = %q, want substring %q", dir, "piper-plus")
	}
}

func TestDefaultCacheDir_EnvOverride(t *testing.T) {
	want := "/custom/model/path"
	t.Setenv("PIPER_MODEL_DIR", want)

	got := DefaultCacheDir()
	if got != want {
		t.Errorf("DefaultCacheDir() = %q, want %q", got, want)
	}
}

// ---------------------------------------------------------------------------
// ModelManager.ListModels tests
// ---------------------------------------------------------------------------

func TestModelManager_ListModels_EmptyDir(t *testing.T) {
	dir := t.TempDir()
	mgr := NewModelManager(dir, slog.Default())

	models, err := mgr.ListModels()
	if err != nil {
		t.Fatalf("ListModels returned unexpected error: %v", err)
	}
	if len(models) != 0 {
		t.Errorf("ListModels returned %d models, want 0", len(models))
	}
}

func TestModelManager_ListModels_NonExistentDir(t *testing.T) {
	mgr := NewModelManager(filepath.Join(t.TempDir(), "nonexistent"), slog.Default())

	models, err := mgr.ListModels()
	if err != nil {
		t.Fatalf("ListModels returned unexpected error: %v", err)
	}
	if len(models) != 0 {
		t.Errorf("ListModels returned %d models, want 0", len(models))
	}
}

func TestModelManager_ListModels_FlatFile(t *testing.T) {
	dir := t.TempDir()
	onnxPath := filepath.Join(dir, "mymodel.onnx")
	if err := os.WriteFile(onnxPath, []byte("fake-onnx"), 0644); err != nil {
		t.Fatal(err)
	}

	mgr := NewModelManager(dir, slog.Default())
	models, err := mgr.ListModels()
	if err != nil {
		t.Fatalf("ListModels returned unexpected error: %v", err)
	}
	if len(models) != 1 {
		t.Fatalf("ListModels returned %d models, want 1", len(models))
	}
	if models[0].Name != "mymodel" {
		t.Errorf("Name = %q, want %q", models[0].Name, "mymodel")
	}
	if models[0].Path != onnxPath {
		t.Errorf("Path = %q, want %q", models[0].Path, onnxPath)
	}
}

func TestModelManager_ListModels_Subdirectory(t *testing.T) {
	dir := t.TempDir()
	subDir := filepath.Join(dir, "tsukuyomi-6lang-v2")
	if err := os.MkdirAll(subDir, 0755); err != nil {
		t.Fatal(err)
	}

	onnxPath := filepath.Join(subDir, "model.onnx")
	cfgPath := filepath.Join(subDir, "config.json")
	if err := os.WriteFile(onnxPath, []byte("fake-onnx"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(cfgPath, []byte("{}"), 0644); err != nil {
		t.Fatal(err)
	}

	mgr := NewModelManager(dir, slog.Default())
	models, err := mgr.ListModels()
	if err != nil {
		t.Fatalf("ListModels returned unexpected error: %v", err)
	}
	if len(models) != 1 {
		t.Fatalf("ListModels returned %d models, want 1", len(models))
	}
	if models[0].Name != "tsukuyomi-6lang-v2" {
		t.Errorf("Name = %q, want %q", models[0].Name, "tsukuyomi-6lang-v2")
	}
	if models[0].ConfigPath != cfgPath {
		t.Errorf("ConfigPath = %q, want %q", models[0].ConfigPath, cfgPath)
	}
}

// ---------------------------------------------------------------------------
// ModelManager.FindModel tests
// ---------------------------------------------------------------------------

func TestModelManager_FindModel_NotFound(t *testing.T) {
	dir := t.TempDir()
	mgr := NewModelManager(dir, slog.Default())

	_, err := mgr.FindModel("nonexistent")
	if err == nil {
		t.Fatal("FindModel should return an error for missing model")
	}
	if !strings.Contains(err.Error(), "nonexistent") {
		t.Errorf("error = %q, want substring %q", err.Error(), "nonexistent")
	}
}

func TestModelManager_FindModel_FlatFile(t *testing.T) {
	dir := t.TempDir()
	onnxPath := filepath.Join(dir, "mymodel.onnx")
	if err := os.WriteFile(onnxPath, []byte("fake-onnx"), 0644); err != nil {
		t.Fatal(err)
	}

	mgr := NewModelManager(dir, slog.Default())
	got, err := mgr.FindModel("mymodel")
	if err != nil {
		t.Fatalf("FindModel returned unexpected error: %v", err)
	}
	if got != onnxPath {
		t.Errorf("FindModel = %q, want %q", got, onnxPath)
	}
}

func TestModelManager_FindModel_Subdirectory(t *testing.T) {
	dir := t.TempDir()
	subDir := filepath.Join(dir, "voice1")
	if err := os.MkdirAll(subDir, 0755); err != nil {
		t.Fatal(err)
	}

	onnxPath := filepath.Join(subDir, "voice1.onnx")
	if err := os.WriteFile(onnxPath, []byte("fake-onnx"), 0644); err != nil {
		t.Fatal(err)
	}

	mgr := NewModelManager(dir, slog.Default())
	got, err := mgr.FindModel("voice1")
	if err != nil {
		t.Fatalf("FindModel returned unexpected error: %v", err)
	}
	if got != onnxPath {
		t.Errorf("FindModel = %q, want %q", got, onnxPath)
	}
}

// ---------------------------------------------------------------------------
// ModelManager.EnsureDir tests
// ---------------------------------------------------------------------------

func TestModelManager_EnsureDir(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "nested", "cache", "dir")
	mgr := NewModelManager(dir, slog.Default())

	if err := mgr.EnsureDir(); err != nil {
		t.Fatalf("EnsureDir returned unexpected error: %v", err)
	}

	info, err := os.Stat(dir)
	if err != nil {
		t.Fatalf("cache dir does not exist after EnsureDir: %v", err)
	}
	if !info.IsDir() {
		t.Errorf("cache path is not a directory")
	}
}

func TestModelManager_EnsureDir_Idempotent(t *testing.T) {
	dir := t.TempDir()
	mgr := NewModelManager(dir, slog.Default())

	// Call twice; the second call should not fail.
	if err := mgr.EnsureDir(); err != nil {
		t.Fatalf("first EnsureDir returned unexpected error: %v", err)
	}
	if err := mgr.EnsureDir(); err != nil {
		t.Fatalf("second EnsureDir returned unexpected error: %v", err)
	}
}

// ---------------------------------------------------------------------------
// ModelManager.CacheDir tests
// ---------------------------------------------------------------------------

func TestModelManager_CacheDir(t *testing.T) {
	mgr := NewModelManager("/some/path", slog.Default())
	if got := mgr.CacheDir(); got != "/some/path" {
		t.Errorf("CacheDir() = %q, want %q", got, "/some/path")
	}
}

func TestModelManager_CacheDir_DefaultWhenEmpty(t *testing.T) {
	// Ensure PIPER_MODEL_DIR is not set so we get the platform default.
	t.Setenv("PIPER_MODEL_DIR", "")

	mgr := NewModelManager("", slog.Default())
	got := mgr.CacheDir()
	if got == "" {
		t.Fatal("CacheDir() returned empty string when cacheDir was empty")
	}
	if !strings.Contains(got, "piper-plus") {
		t.Errorf("CacheDir() = %q, want substring %q", got, "piper-plus")
	}
}

// ---------------------------------------------------------------------------
// ModelManager.DownloadModel tests
// ---------------------------------------------------------------------------

func TestModelManager_DownloadModel(t *testing.T) {
	payload := []byte("fake-onnx-model-data")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write(payload)
	}))
	defer srv.Close()

	dir := t.TempDir()
	mgr := NewModelManager(dir, slog.Default())

	url := srv.URL + "/test-model.onnx"
	got, err := mgr.DownloadModel(context.Background(), url)
	if err != nil {
		t.Fatalf("DownloadModel returned unexpected error: %v", err)
	}

	if filepath.Base(got) != "test-model.onnx" {
		t.Errorf("downloaded filename = %q, want %q", filepath.Base(got), "test-model.onnx")
	}

	data, err := os.ReadFile(got)
	if err != nil {
		t.Fatalf("failed to read downloaded file: %v", err)
	}
	if string(data) != string(payload) {
		t.Errorf("file content = %q, want %q", string(data), string(payload))
	}
}

func TestModelManager_DownloadModel_HTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	dir := t.TempDir()
	mgr := NewModelManager(dir, slog.Default())

	_, err := mgr.DownloadModel(context.Background(), srv.URL+"/missing.onnx")
	if err == nil {
		t.Fatal("DownloadModel should return an error for HTTP 404")
	}
	if !strings.Contains(err.Error(), "404") {
		t.Errorf("error = %q, want substring %q", err.Error(), "404")
	}
}

func TestModelManager_DownloadModel_CancelledContext(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "data")
	}))
	defer srv.Close()

	dir := t.TempDir()
	mgr := NewModelManager(dir, slog.Default())

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, err := mgr.DownloadModel(ctx, srv.URL+"/model.onnx")
	if err == nil {
		t.Fatal("DownloadModel should return an error for canceled context")
	}
}

// ---------------------------------------------------------------------------
// NewModelManager tests
// ---------------------------------------------------------------------------

func TestNewModelManager_NilLogger(t *testing.T) {
	mgr := NewModelManager(t.TempDir(), nil)
	if mgr.logger == nil {
		t.Error("logger should not be nil when nil is passed to NewModelManager")
	}
}

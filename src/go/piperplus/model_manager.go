package piperplus

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// ModelInfo describes a downloaded model in the cache.
type ModelInfo struct {
	Name       string  // e.g., "tsukuyomi-6lang-v2"
	Path       string  // full path to .onnx file
	ConfigPath string  // path to config.json
	SizeMB     float64 // file size in megabytes
}

// ModelManager handles model discovery, download, and caching.
type ModelManager struct {
	cacheDir string
	logger   *slog.Logger
}

// NewModelManager creates a manager with the specified cache directory.
// If cacheDir is empty, uses the platform default.
func NewModelManager(cacheDir string, logger *slog.Logger) *ModelManager {
	if cacheDir == "" {
		cacheDir = DefaultCacheDir()
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &ModelManager{cacheDir: cacheDir, logger: logger}
}

// DefaultCacheDir returns the platform-specific default model cache directory.
// Override with the PIPER_MODEL_DIR environment variable.
func DefaultCacheDir() string {
	if env := os.Getenv("PIPER_MODEL_DIR"); env != "" {
		return env
	}

	home, _ := os.UserHomeDir()
	switch runtime.GOOS {
	case "darwin":
		return filepath.Join(home, "Library", "Application Support", "piper-plus", "models")
	case "windows":
		if appData := os.Getenv("APPDATA"); appData != "" {
			return filepath.Join(appData, "piper-plus", "models")
		}
		return filepath.Join(home, "AppData", "Roaming", "piper-plus", "models")
	default: // linux and others
		if xdg := os.Getenv("XDG_DATA_HOME"); xdg != "" {
			return filepath.Join(xdg, "piper-plus", "models")
		}
		return filepath.Join(home, ".local", "share", "piper-plus", "models")
	}
}

// CacheDir returns the resolved cache directory.
func (m *ModelManager) CacheDir() string {
	return m.cacheDir
}

// EnsureDir creates the cache directory if it does not exist.
func (m *ModelManager) EnsureDir() error {
	return os.MkdirAll(m.cacheDir, 0755)
}

// ListModels returns all downloaded models found in the cache directory.
// It searches {cacheDir}/*.onnx and {cacheDir}/*/*.onnx.
func (m *ModelManager) ListModels() ([]ModelInfo, error) {
	entries, err := os.ReadDir(m.cacheDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("piperplus: list models: %w", err)
	}

	var models []ModelInfo
	for _, entry := range entries {
		entryPath := filepath.Join(m.cacheDir, entry.Name())

		if entry.IsDir() {
			// Look inside subdirectory for .onnx files.
			subMatches, _ := filepath.Glob(filepath.Join(entryPath, "*.onnx"))
			for _, onnxPath := range subMatches {
				if info, ok := buildModelInfo(entry.Name(), onnxPath); ok {
					models = append(models, info)
				}
			}
		} else if strings.HasSuffix(entry.Name(), ".onnx") {
			name := strings.TrimSuffix(entry.Name(), ".onnx")
			if info, ok := buildModelInfo(name, entryPath); ok {
				models = append(models, info)
			}
		}
	}

	return models, nil
}

// FindModel locates a model by name in the cache directory.
// It checks {cacheDir}/{name}/*.onnx first, then {cacheDir}/{name}.onnx.
func (m *ModelManager) FindModel(name string) (string, error) {
	// 1. Subdirectory pattern.
	subMatches, _ := filepath.Glob(filepath.Join(m.cacheDir, name, "*.onnx"))
	if len(subMatches) > 0 {
		return subMatches[0], nil
	}

	// 2. Flat file.
	flat := filepath.Join(m.cacheDir, name+".onnx")
	if _, err := os.Stat(flat); err == nil {
		return flat, nil
	}

	return "", fmt.Errorf("piperplus: model %q not found in %s", name, m.cacheDir)
}

// DownloadModel downloads a model from url into the cache directory.
// It writes to a temp file then renames for atomicity.
func (m *ModelManager) DownloadModel(ctx context.Context, url string) (string, error) {
	if err := m.EnsureDir(); err != nil {
		return "", fmt.Errorf("piperplus: download model: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", fmt.Errorf("piperplus: download model: %w", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("piperplus: download model: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("piperplus: download model: HTTP %d", resp.StatusCode)
	}

	// Derive filename from URL path.
	fileName := filepath.Base(url)
	if fileName == "" || fileName == "." || fileName == "/" {
		fileName = "model.onnx"
	}
	destPath := filepath.Join(m.cacheDir, fileName)
	tmpFile, err := os.CreateTemp(m.cacheDir, "download-*.tmp")
	if err != nil {
		return "", fmt.Errorf("piperplus: download model: %w", err)
	}
	tmpPath := tmpFile.Name()

	written, err := io.Copy(tmpFile, resp.Body)
	if closeErr := tmpFile.Close(); closeErr != nil && err == nil {
		err = closeErr
	}
	if err != nil {
		os.Remove(tmpPath)
		return "", fmt.Errorf("piperplus: download model: %w", err)
	}

	m.logger.Info("model downloaded", "path", destPath, "bytes", written)

	if err := os.Rename(tmpPath, destPath); err != nil {
		os.Remove(tmpPath)
		return "", fmt.Errorf("piperplus: download model: rename: %w", err)
	}

	return destPath, nil
}

// buildModelInfo constructs a ModelInfo if the .onnx file can be stat'd.
func buildModelInfo(name, onnxPath string) (ModelInfo, bool) {
	fi, err := os.Stat(onnxPath)
	if err != nil {
		return ModelInfo{}, false
	}

	info := ModelInfo{
		Name:   name,
		Path:   onnxPath,
		SizeMB: float64(fi.Size()) / (1024 * 1024),
	}

	// Look for a config.json next to the .onnx file.
	cfgPath := filepath.Join(filepath.Dir(onnxPath), "config.json")
	if _, err := os.Stat(cfgPath); err == nil {
		info.ConfigPath = cfgPath
	}

	return info, true
}

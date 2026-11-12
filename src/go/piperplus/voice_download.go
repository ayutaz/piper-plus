package piperplus

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// huggingFaceURL is where catalog voices are downloaded from.
const huggingFaceURL = "https://huggingface.co"

// ErrVoiceNotInCatalog is returned by ResolveVoice for a name that is neither
// a catalog key nor an alias.
var ErrVoiceNotInCatalog = errors.New("piperplus: voice not in catalog")

var (
	safeSegment = regexp.MustCompile(`^[A-Za-z0-9._-]+$`)
	safeRepoID  = regexp.MustCompile(`^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`)
)

// CatalogNames returns every catalog key and alias, sorted.
func CatalogNames() []string {
	var names []string
	for _, e := range embeddedCatalog {
		names = append(names, e.Key)
		names = append(names, e.Aliases...)
	}
	sort.Strings(names)
	return names
}

// VoiceDir returns the cache directory of a catalog voice, {cacheDir}/{key}.
// Each voice has its own directory because several voices ship a file named
// config.json.
func (m *ModelManager) VoiceDir(entry *VoiceCatalogEntry) string {
	return filepath.Join(m.cacheDir, entry.Key)
}

// CachedVoice returns the .onnx path of a catalog voice when every file of it
// is in VoiceDir. For a voice pinned to a revision each file must also have
// the catalog size; a voice that follows "main" can change on the Hub, so any
// size is accepted.
func (m *ModelManager) CachedVoice(entry *VoiceCatalogEntry) (string, bool) {
	onnx := entry.OnnxFileName()
	if onnx == "" || !safeSegment.MatchString(entry.Key) || entry.Key == "." || entry.Key == ".." {
		return "", false
	}
	dir := m.VoiceDir(entry)
	for _, f := range entry.Files {
		if !haveFile(filepath.Join(dir, path.Base(f.RelativePath)), expectedSize(entry, f)) {
			return "", false
		}
	}
	return filepath.Join(dir, onnx), true
}

// expectedSize is the size a file must have: the catalog size for a voice
// pinned to a revision, 0 (any size) for one that follows "main".
func expectedSize(entry *VoiceCatalogEntry, f VoiceFileInfo) int64 {
	if entry.Revision == "" {
		return 0
	}
	return f.SizeBytes
}

// DownloadVoice downloads every file of a catalog voice from its Hugging Face
// repository at the catalog revision ("main" when the entry has none) into
// VoiceDir and returns the .onnx path. Files already there are kept (for a
// pinned voice only with the catalog size). For a pinned voice a downloaded
// file whose size differs from the catalog is removed and reported as an
// error; for a voice that follows "main" the difference is only logged.
func (m *ModelManager) DownloadVoice(ctx context.Context, entry *VoiceCatalogEntry) (string, error) {
	if err := validateVoiceEntry(entry); err != nil {
		return "", err
	}
	revision := entry.Revision
	if revision == "" {
		revision = "main"
	}
	dir := m.VoiceDir(entry)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", fmt.Errorf("piperplus: download voice %s: %w", entry.Key, err)
	}
	for _, f := range entry.Files {
		dest := filepath.Join(dir, path.Base(f.RelativePath))
		if haveFile(dest, expectedSize(entry, f)) {
			continue
		}
		hub := m.hubURL
		if hub == "" {
			hub = huggingFaceURL
		}
		fileURL := strings.TrimSuffix(hub, "/") + "/" + entry.RepoID + "/resolve/" + revision + "/" + f.RelativePath
		m.logger.Info("downloading model file", "voice", entry.Key, "url", fileURL)
		written, err := m.fetchTo(ctx, fileURL, dest)
		if err != nil {
			return "", fmt.Errorf("piperplus: download voice %s: %w", entry.Key, err)
		}
		if f.SizeBytes > 0 && written != f.SizeBytes {
			if entry.Revision != "" {
				_ = os.Remove(dest)
				return "", fmt.Errorf("piperplus: download voice %s: %s is %d bytes, catalog says %d",
					entry.Key, f.RelativePath, written, f.SizeBytes)
			}
			m.logger.Warn("model file size differs from the catalog",
				"voice", entry.Key, "file", f.RelativePath, "bytes", written, "catalog_bytes", f.SizeBytes)
		}
	}
	return filepath.Join(dir, entry.OnnxFileName()), nil
}

// ResolveVoice returns the .onnx path of the catalog voice named by a key or
// alias, downloading the voice when it is not cached. It returns
// ErrVoiceNotInCatalog for any other name.
func (m *ModelManager) ResolveVoice(ctx context.Context, name string) (string, error) {
	entry, ok := FindVoice(name)
	if !ok {
		return "", fmt.Errorf("%w: %q", ErrVoiceNotInCatalog, name)
	}
	if p, ok := m.CachedVoice(entry); ok {
		return p, nil
	}
	return m.DownloadVoice(ctx, entry)
}

func validateVoiceEntry(entry *VoiceCatalogEntry) error {
	switch {
	case !safeSegment.MatchString(entry.Key) || entry.Key == "." || entry.Key == "..":
		return fmt.Errorf("piperplus: download voice: unsafe key %q", entry.Key)
	case !safeRepoID.MatchString(entry.RepoID) || strings.Contains(entry.RepoID, ".."):
		return fmt.Errorf("piperplus: download voice %s: invalid repo ID %q", entry.Key, entry.RepoID)
	case entry.Revision != "" && (!safeSegment.MatchString(entry.Revision) || strings.Contains(entry.Revision, "..")):
		return fmt.Errorf("piperplus: download voice %s: invalid revision %q", entry.Key, entry.Revision)
	case entry.OnnxFileName() == "":
		return fmt.Errorf("piperplus: download voice %s: catalog lists no .onnx file", entry.Key)
	}
	for _, f := range entry.Files {
		p := f.RelativePath
		if p == "" || strings.HasPrefix(p, "/") || strings.Contains(p, `\`) {
			return fmt.Errorf("piperplus: download voice %s: unsafe file path %q", entry.Key, p)
		}
		for _, seg := range strings.Split(p, "/") {
			if !safeSegment.MatchString(seg) || seg == "." || seg == ".." {
				return fmt.Errorf("piperplus: download voice %s: unsafe file path %q", entry.Key, p)
			}
		}
	}
	return nil
}

// haveFile reports whether path is a regular file of the given size (any
// size when size is 0).
func haveFile(path string, size int64) bool {
	fi, err := os.Stat(path)
	if err != nil || !fi.Mode().IsRegular() {
		return false
	}
	return size <= 0 || fi.Size() == size
}

package piperplus

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// VoiceFileInfo describes a file in a voice model package.
type VoiceFileInfo struct {
	RelativePath string `json:"relative_path"`
	SizeBytes    int64  `json:"size_bytes"`
	MD5          string `json:"md5,omitempty"`
}

// VoiceCatalogEntry describes a voice model in the catalog.
type VoiceCatalogEntry struct {
	Key             string          `json:"key"`
	Name            string          `json:"name"`
	LanguageCode    string          `json:"language_code"`
	LanguageFamily  string          `json:"language_family,omitempty"`
	LanguageNative  string          `json:"language_native,omitempty"`
	LanguageEnglish string          `json:"language_english,omitempty"`
	Quality         string          `json:"quality"`
	NumSpeakers     int             `json:"num_speakers"`
	Source          string          `json:"source,omitempty"`
	RepoID          string          `json:"repo_id,omitempty"`
	Files           []VoiceFileInfo `json:"files,omitempty"`
	Aliases         []string        `json:"aliases,omitempty"`
}

// HasAlias reports whether the entry has the given alias.
func (e *VoiceCatalogEntry) HasAlias(alias string) bool {
	for _, a := range e.Aliases {
		if a == alias {
			return true
		}
	}
	return false
}

// OnnxFileName returns the .onnx file name from the entry's file list, or empty string.
func (e *VoiceCatalogEntry) OnnxFileName() string {
	for _, f := range e.Files {
		if filepath.Ext(f.RelativePath) == ".onnx" {
			return filepath.Base(f.RelativePath)
		}
	}
	return ""
}

// embeddedCatalog contains built-in piper-plus voice entries.
var embeddedCatalog = []VoiceCatalogEntry{
	{
		Key: "ja_JP-tsukuyomi-chan-medium", Name: "tsukuyomi-chan",
		LanguageCode: "ja_JP", LanguageFamily: "ja", LanguageNative: "日本語", LanguageEnglish: "Japanese",
		Quality: "medium", NumSpeakers: 1, Source: "piper-plus", RepoID: "ayousanz/piper-plus-tsukuyomi-chan",
		Files: []VoiceFileInfo{
			{RelativePath: "tsukuyomi-chan-6lang-fp16.onnx", SizeBytes: 39_652_717},
			{RelativePath: "config.json", SizeBytes: 6_279},
		},
		Aliases: []string{"tsukuyomi", "tsukuyomi-chan", "ja-tsukuyomi"},
	},
	{
		Key: "ja_JP-css10-6lang-medium", Name: "css10-6lang",
		LanguageCode: "ja_JP", LanguageFamily: "ja", LanguageNative: "日本語", LanguageEnglish: "Japanese",
		Quality: "medium", NumSpeakers: 1, Source: "piper-plus", RepoID: "ayousanz/piper-plus-css10-ja-6lang",
		Files: []VoiceFileInfo{
			{RelativePath: "css10-ja-6lang-fp16.onnx", SizeBytes: 39_652_717},
			{RelativePath: "config.json", SizeBytes: 5_912},
		},
		Aliases: []string{"css10", "css10-6lang", "css10-ja", "ja-css10"},
	},
}

// FindVoice looks up a voice by exact key, then by alias.
func FindVoice(nameOrAlias string) (*VoiceCatalogEntry, bool) {
	for i := range embeddedCatalog {
		if embeddedCatalog[i].Key == nameOrAlias {
			entry := embeddedCatalog[i]
			return &entry, true
		}
	}
	for i := range embeddedCatalog {
		if embeddedCatalog[i].HasAlias(nameOrAlias) {
			entry := embeddedCatalog[i]
			return &entry, true
		}
	}
	return nil, false
}

// ListVoices returns catalog entries, optionally filtered by language code prefix.
func ListVoices(languageFilter string) []VoiceCatalogEntry {
	var result []VoiceCatalogEntry
	for _, e := range embeddedCatalog {
		if languageFilter == "" || strings.HasPrefix(e.LanguageCode, languageFilter) || e.LanguageFamily == languageFilter {
			result = append(result, e)
		}
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].LanguageCode != result[j].LanguageCode {
			return result[i].LanguageCode < result[j].LanguageCode
		}
		return result[i].Key < result[j].Key
	})
	return result
}

// LoadExternalCatalog loads a voices.json file.
func LoadExternalCatalog(path string) ([]VoiceCatalogEntry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var entries []VoiceCatalogEntry
	if err := json.Unmarshal(data, &entries); err != nil {
		return nil, err
	}
	return entries, nil
}

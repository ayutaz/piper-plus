package piperplus

import (
	"os"
	"strings"
)

// ModelNoticeEnv is the environment variable that hides the model usage
// notice when set to 1 / true / yes (case-insensitive, surrounding spaces
// ignored). See docs/reference/model-resolution.md section 9.
const ModelNoticeEnv = "PIPER_PLUS_DISABLE_MODEL_NOTICE"

// ModelNoticeFooter is printed by executables after the notice lines. It is
// identical across runtimes.
const ModelNoticeFooter = "(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)"

// ModelNotice returns the usage notice lines for the model named by input, or
// nil when the model has no notice. input may be a catalog key, an alias, a
// repo id, a URL, or a file path. The library never prints the notice;
// executables decide whether to show it (see ModelNoticeDisabled).
//
// An entry matches when input
//  1. equals its key, one of its aliases, or its repo id,
//  2. is a URL containing "/<repo_id>/", or
//  3. is a path whose file name (last element, split on "/" or "\") equals
//     one of its notice files.
func ModelNotice(input string) []string {
	if input == "" {
		return nil
	}
	isURL := strings.Contains(input, "://")
	name := noticeFileName(input, isURL)
	for i := range embeddedCatalog {
		e := &embeddedCatalog[i]
		if len(e.Notice) == 0 {
			continue
		}
		if noticeEntryMatches(e, input, name, isURL) {
			out := make([]string, len(e.Notice))
			copy(out, e.Notice)
			return out
		}
	}
	return nil
}

func noticeEntryMatches(e *VoiceCatalogEntry, input, name string, isURL bool) bool {
	if input == e.Key || e.HasAlias(input) {
		return true
	}
	if e.RepoID != "" {
		if input == e.RepoID {
			return true
		}
		if isURL && strings.Contains(input, "/"+e.RepoID+"/") {
			return true
		}
	}
	for _, f := range e.NoticeFiles {
		if name == f {
			return true
		}
	}
	return false
}

// noticeFileName returns the last path element of input, treating both "/"
// and "\" as separators so Windows paths match on every OS. For URLs the
// query string and fragment are dropped first.
func noticeFileName(input string, isURL bool) string {
	if isURL {
		if i := strings.IndexAny(input, "?#"); i >= 0 {
			input = input[:i]
		}
	}
	if i := strings.LastIndexAny(input, `/\`); i >= 0 {
		return input[i+1:]
	}
	return input
}

// ParseModelNoticeDisabled reports whether value (the content of
// PIPER_PLUS_DISABLE_MODEL_NOTICE) disables the notice: 1 / true / yes,
// case-insensitive, with surrounding whitespace ignored.
func ParseModelNoticeDisabled(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes":
		return true
	}
	return false
}

// ModelNoticeDisabled reports whether PIPER_PLUS_DISABLE_MODEL_NOTICE hides
// the notice in the current environment.
func ModelNoticeDisabled() bool {
	return ParseModelNoticeDisabled(os.Getenv(ModelNoticeEnv))
}

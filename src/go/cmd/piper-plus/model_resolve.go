package main

import (
	"context"
	"fmt"
	"os"
	"strings"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

// resolveModelArg turns the --model value into an .onnx path
// (docs/reference/model-resolution.md section 1):
//
//  1. an existing file is used as is;
//  2. a catalog key or alias uses the voice's cache directory, then a copy
//     cached under that name earlier ({cache}/{name}/*.onnx or
//     {cache}/{name}.onnx), and otherwise downloads the voice;
//  3. any other name is looked up in the cache directory.
func resolveModelArg(ctx context.Context, mgr *piperplus.ModelManager, input string) (string, error) {
	if _, err := os.Stat(input); !os.IsNotExist(err) {
		return input, nil
	}
	if entry, ok := piperplus.FindVoice(input); ok {
		if p, ok := mgr.CachedVoice(entry); ok {
			return p, nil
		}
		if p, err := mgr.FindModel(input); err == nil {
			return p, nil
		}
		p, err := mgr.DownloadVoice(ctx, entry)
		if err != nil {
			return "", fmt.Errorf("model %s: %w", input, err)
		}
		return p, nil
	}
	if p, err := mgr.FindModel(input); err == nil {
		return p, nil
	}
	return "", fmt.Errorf("model not found: %s (not a file, a cached model or a catalog name; catalog names: %s)",
		input, strings.Join(piperplus.CatalogNames(), ", "))
}

// downloadModelArg handles --download-model: a catalog key or alias downloads
// that voice (its .onnx and config) into the cache, anything else is taken as
// the URL of a model file.
func downloadModelArg(ctx context.Context, mgr *piperplus.ModelManager, arg string) (string, error) {
	if entry, ok := piperplus.FindVoice(arg); ok {
		return mgr.DownloadVoice(ctx, entry)
	}
	return mgr.DownloadModel(ctx, arg)
}

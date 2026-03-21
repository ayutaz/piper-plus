package piperplus

import (
	"context"
	"fmt"
	"log/slog"
	"path/filepath"
	"sync/atomic"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
)

// Voice represents a loaded TTS model ready for synthesis.
type Voice struct {
	engine     *OnnxEngine
	config     *VoiceConfig
	phonemizer phonemize.Phonemizer
	textDict   *phonemize.TextDictionary // custom dictionary for text substitution
	logger     *slog.Logger
	closed     atomic.Bool
}

// LoadVoice loads a TTS model from modelPath and returns a Voice ready for synthesis.
// Options can be provided to specify the config path, device, and logger.
func LoadVoice(ctx context.Context, modelPath string, opts ...LoadOption) (*Voice, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}

	// Apply options with defaults.
	loadOpts := &LoadOptions{
		Device: "cpu",
		Logger: slog.Default(),
	}
	for _, opt := range opts {
		opt(loadOpts)
	}
	if loadOpts.Logger != nil {
		// Override default if explicitly provided.
	} else {
		loadOpts.Logger = slog.Default()
	}
	logger := loadOpts.Logger

	// Resolve config path.
	configPath, err := FindConfigPath(loadOpts.ConfigPath, modelPath)
	if err != nil {
		return nil, err
	}

	config, err := LoadConfig(configPath)
	if err != nil {
		return nil, err
	}

	// Configure ONNX session options for the target device.
	sessOpts, err := configureSessionOptions(loadOpts.Device, logger)
	if err != nil {
		return nil, &ModelLoadError{Path: modelPath, Err: err}
	}
	defer func() { _ = sessOpts.Destroy() }()

	// Create the ONNX inference engine.
	engine, err := newOnnxEngine(modelPath, config, sessOpts, logger)
	if err != nil {
		return nil, err
	}

	// Load dictionaries for languages that need them.
	// WithDictDir overrides the default model-directory search.
	dictSearchDir := loadOpts.DictDir
	if dictSearchDir == "" {
		dictSearchDir = filepath.Dir(modelPath)
	}
	dicts := loadDictionaries(dictSearchDir, config.LanguageIDMap, logger)

	// Try to create a phonemizer. For "text" phoneme type, failure is non-fatal
	// since the user provides pre-computed phoneme IDs. For all other types,
	// a working phonemizer is required.
	var ph phonemize.Phonemizer
	ph, err = createPhonemizer(config, dicts)
	if err != nil {
		if config.PhonemeType != PhonemeTypeText {
			return nil, fmt.Errorf("piperplus: phonemizer required for phoneme_type %q: %w", config.PhonemeType, err)
		}
		logger.Warn("phonemizer not available; use SynthesizeFromIDs for direct phoneme input",
			"reason", err.Error())
	}

	// Load custom dictionary for text substitution if paths provided.
	var textDict *phonemize.TextDictionary
	if len(loadOpts.CustomDictPaths) > 0 {
		td, tdErr := phonemize.LoadTextDictJSONFiles(loadOpts.CustomDictPaths)
		if tdErr != nil {
			logger.Warn("failed to load custom dictionary", "error", tdErr)
		} else if td.Len() > 0 {
			logger.Info("loaded custom dictionary", "entries", td.Len(), "files", len(loadOpts.CustomDictPaths))
		}
		// Store even if empty (nil-safe in Synthesize)
		textDict = td
	}

	logger.Info("voice loaded", "model", modelPath, "device", loadOpts.Device)

	return &Voice{
		engine:     engine,
		config:     config,
		phonemizer: ph,
		textDict:   textDict,
		logger:     logger,
	}, nil
}

// SynthesizeFromIDs synthesizes speech from pre-computed phoneme IDs.
func (v *Voice) SynthesizeFromIDs(ctx context.Context, req *SynthesisRequest) (*SynthesisResult, error) {
	if v.closed.Load() {
		return nil, ErrModelClosed
	}
	if req == nil {
		return nil, fmt.Errorf("piperplus: nil synthesis request")
	}
	return v.engine.Synthesize(ctx, req)
}

// Close releases all resources held by the Voice. It is safe to call multiple
// times; only the first call performs cleanup. Close implements io.Closer.
func (v *Voice) Close() error {
	if !v.closed.CompareAndSwap(false, true) {
		return nil
	}
	return v.engine.Close()
}

// Config returns the voice configuration. The returned pointer is shared
// with the Voice; callers must NOT modify the returned VoiceConfig.
func (v *Voice) Config() *VoiceConfig {
	return v.config
}

// Capabilities returns the model's capabilities (multi-speaker, multilingual, etc.).
func (v *Voice) Capabilities() ModelCapabilities {
	return v.engine.Capabilities()
}

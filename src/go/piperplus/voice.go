package piperplus

import (
	"context"
	"log/slog"
	"sync"
	"sync/atomic"

	"github.com/ayutaz/piper-plus/src/go/phonemize"
)

// Voice represents a loaded TTS model ready for synthesis.
type Voice struct {
	engine     *OnnxEngine
	config     *VoiceConfig
	phonemizer phonemize.Phonemizer
	logger     *slog.Logger
	closed     atomic.Bool
	mu         sync.Mutex // protects Close
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
	defer sessOpts.Destroy()

	// Create the ONNX inference engine.
	engine, err := newOnnxEngine(modelPath, config, sessOpts, logger)
	if err != nil {
		return nil, err
	}

	// Try to create a phonemizer. Failure is non-fatal: the user can still
	// use SynthesizeFromIDs with pre-computed phoneme IDs.
	var ph phonemize.Phonemizer
	ph, err = createPhonemizer(config, "")
	if err != nil {
		logger.Warn("phonemizer not available; use SynthesizeFromIDs for direct phoneme input",
			"reason", err.Error())
	}

	logger.Info("voice loaded", "model", modelPath, "device", loadOpts.Device)

	return &Voice{
		engine:     engine,
		config:     config,
		phonemizer: ph,
		logger:     logger,
	}, nil
}

// SynthesizeFromIDs synthesizes speech from pre-computed phoneme IDs.
func (v *Voice) SynthesizeFromIDs(ctx context.Context, req *SynthesisRequest) (*SynthesisResult, error) {
	if v.closed.Load() {
		return nil, ErrModelClosed
	}
	return v.engine.Synthesize(ctx, req)
}

// Close releases all resources held by the Voice. It is safe to call multiple
// times; only the first call performs cleanup. Close implements io.Closer.
func (v *Voice) Close() error {
	if !v.closed.CompareAndSwap(false, true) {
		return nil
	}
	v.mu.Lock()
	defer v.mu.Unlock()
	return v.engine.Close()
}

// Config returns the voice configuration (read-only).
func (v *Voice) Config() *VoiceConfig {
	return v.config
}

// Capabilities returns the model's capabilities (multi-speaker, multilingual, etc.).
func (v *Voice) Capabilities() ModelCapabilities {
	return v.engine.Capabilities()
}

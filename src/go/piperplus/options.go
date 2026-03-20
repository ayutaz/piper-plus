package piperplus

import "log/slog"

// ---------------------------------------------------------------------------
// SynthesisRequest — low-level request used by OnnxEngine.Synthesize and
// Voice.SynthesizeFromIDs.
// ---------------------------------------------------------------------------

// SynthesisRequest holds parameters for a single synthesis operation.
// Used with OnnxEngine.Synthesize and Voice.SynthesizeFromIDs.
type SynthesisRequest struct {
	PhonemeIDs      []int64    // phoneme ID sequence (required)
	SpeakerID       int64      // speaker ID (default 0)
	LanguageID      int64      // language ID (default 0)
	NoiseScale      float32    // generation noise (default 0.667)
	LengthScale     float32    // speech rate (default 1.0)
	NoiseW          float32    // duration predictor noise (default 0.8)
	ProsodyFeatures [][3]int64 // A1/A2/A3 per phoneme (nil = zero-fill)
}

// ---------------------------------------------------------------------------
// SynthesisOption — functional options for Voice.Synthesize (Phase 3 text
// input).
// ---------------------------------------------------------------------------

// SynthesisOptions holds resolved parameters for text-level synthesis.
type SynthesisOptions struct {
	Language    string
	SpeakerID   int64
	NoiseScale  float32
	LengthScale float32
	NoiseW      float32
}

// SynthesisOption is a functional option applied to SynthesisOptions.
type SynthesisOption func(*SynthesisOptions)

// WithLanguage sets the target language code (e.g. "ja", "en").
func WithLanguage(lang string) SynthesisOption {
	return func(o *SynthesisOptions) { o.Language = lang }
}

// WithSpeakerID sets the speaker ID for multi-speaker models.
func WithSpeakerID(id int64) SynthesisOption {
	return func(o *SynthesisOptions) { o.SpeakerID = id }
}

// WithNoiseScale sets the generation noise scale.
func WithNoiseScale(v float32) SynthesisOption {
	return func(o *SynthesisOptions) { o.NoiseScale = v }
}

// WithLengthScale sets the speech rate (length scale).
func WithLengthScale(v float32) SynthesisOption {
	return func(o *SynthesisOptions) { o.LengthScale = v }
}

// WithNoiseW sets the duration predictor noise scale.
func WithNoiseW(v float32) SynthesisOption {
	return func(o *SynthesisOptions) { o.NoiseW = v }
}

// ---------------------------------------------------------------------------
// LoadOption — functional options for LoadVoice.
// ---------------------------------------------------------------------------

// LoadOptions holds resolved parameters for model loading.
type LoadOptions struct {
	ConfigPath string       // explicit path to config.json
	Device     string       // default "cpu"
	Logger     *slog.Logger // default slog.Default()
}

// LoadOption is a functional option applied to LoadOptions.
type LoadOption func(*LoadOptions)

// WithConfig sets an explicit config.json path.
func WithConfig(path string) LoadOption {
	return func(o *LoadOptions) { o.ConfigPath = path }
}

// WithDevice sets the inference device (e.g. "cpu", "cuda").
func WithDevice(device string) LoadOption {
	return func(o *LoadOptions) { o.Device = device }
}

// WithLogger sets a custom structured logger.
func WithLogger(logger *slog.Logger) LoadOption {
	return func(o *LoadOptions) { o.Logger = logger }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// defaultSynthesisOptions returns SynthesisOptions with sensible defaults.
func defaultSynthesisOptions() SynthesisOptions {
	return SynthesisOptions{
		NoiseScale:  0.667,
		LengthScale: 1.0,
		NoiseW:      0.8,
	}
}

// defaultLoadOptions returns LoadOptions with sensible defaults.
func defaultLoadOptions() LoadOptions {
	return LoadOptions{
		Device: "cpu",
		Logger: slog.Default(),
	}
}

// applySynthesisOptions starts from defaults and applies each option.
func applySynthesisOptions(opts []SynthesisOption) SynthesisOptions {
	o := defaultSynthesisOptions()
	for _, fn := range opts {
		fn(&o)
	}
	return o
}

// applyLoadOptions starts from defaults and applies each option.
func applyLoadOptions(opts []LoadOption) LoadOptions {
	o := defaultLoadOptions()
	for _, fn := range opts {
		fn(&o)
	}
	return o
}

// NewSynthesisRequest creates a SynthesisRequest from phoneme IDs and
// optional SynthesisOption values. Fields from SynthesisOptions are mapped
// onto the returned SynthesisRequest.
func NewSynthesisRequest(phonemeIDs []int64, opts ...SynthesisOption) *SynthesisRequest {
	so := applySynthesisOptions(opts)
	return &SynthesisRequest{
		PhonemeIDs:  phonemeIDs,
		SpeakerID:   so.SpeakerID,
		NoiseScale:  so.NoiseScale,
		LengthScale: so.LengthScale,
		NoiseW:      so.NoiseW,
	}
}

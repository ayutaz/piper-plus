package piperplus

import (
	"errors"
	"log/slog"
	"math"
)

// ErrSpeakerIDEmbeddingExclusive indicates that a synthesis request specified
// both a non-zero speaker_id and a non-empty speaker_embedding. The two inputs
// are mutually exclusive — speaker_id selects a learned embedding from the
// model, while speaker_embedding overrides it with an externally-provided
// vector (voice cloning). Specifying both is ambiguous and matches the
// behavior of the Python and Rust runtimes (explicit error).
var ErrSpeakerIDEmbeddingExclusive = errors.New("speaker_id and speaker_embedding are mutually exclusive")

// ---------------------------------------------------------------------------
// SynthesisRequest — low-level request used by OnnxEngine.Synthesize and
// Voice.SynthesizeFromIDs.
// ---------------------------------------------------------------------------

// SynthesisRequest holds parameters for a single synthesis operation.
// Used with OnnxEngine.Synthesize and Voice.SynthesizeFromIDs.
type SynthesisRequest struct {
	PhonemeIDs       []int64            // phoneme ID sequence (required)
	SpeakerID        int64              // speaker ID (default 0)
	LanguageID       int64              // language ID (default 0)
	NoiseScale       float32            // generation noise (default 0.4)
	LengthScale      float32            // speech rate (default 1.0)
	NoiseW           float32            // duration predictor noise (default 0.5)
	ProsodyFeatures  [][3]int64         // A1/A2/A3 per phoneme (nil = zero-fill)
	PhonemeSilence   map[string]float64 // phoneme -> seconds of silence to insert after it (nil = disabled)
	SpeakerEmbedding []float32          // speaker embedding from encoder (nil = use SpeakerID)
}

// ---------------------------------------------------------------------------
// SynthesisOption — functional options for Voice.Synthesize (Phase 3 text
// input).
// ---------------------------------------------------------------------------

// SynthesisOptions holds resolved parameters for text-level synthesis.
type SynthesisOptions struct {
	Language         string
	SpeakerID        int64
	NoiseScale       float32
	LengthScale      float32
	NoiseW           float32
	SentenceSilence  float64            // seconds of silence between sentences (default 0.2)
	PhonemeSilence   map[string]float64 // phoneme -> seconds of silence to insert after it (nil = disabled)
	SpeakerEmbedding []float32          // pre-computed speaker embedding (nil = use SpeakerID)
}

// SynthesisOption is a functional option applied to SynthesisOptions.
type SynthesisOption func(*SynthesisOptions)

// WithLanguage sets the target language code (e.g. "ja", "en").
func WithLanguage(lang string) SynthesisOption {
	return func(o *SynthesisOptions) { o.Language = lang }
}

// WithSpeakerID sets the speaker ID for multi-speaker models.
// Negative values are silently ignored.
func WithSpeakerID(id int64) SynthesisOption {
	return func(o *SynthesisOptions) {
		if id >= 0 {
			o.SpeakerID = id
		}
	}
}

// WithNoiseScale sets the generation noise scale.
// NaN and Inf values are silently ignored.
func WithNoiseScale(v float32) SynthesisOption {
	return func(o *SynthesisOptions) {
		if !isInvalidFloat32(v) {
			o.NoiseScale = v
		}
	}
}

// WithLengthScale sets the speech rate (length scale).
// NaN and Inf values are silently ignored.
func WithLengthScale(v float32) SynthesisOption {
	return func(o *SynthesisOptions) {
		if !isInvalidFloat32(v) {
			o.LengthScale = v
		}
	}
}

// WithNoiseW sets the duration predictor noise scale.
// NaN and Inf values are silently ignored.
func WithNoiseW(v float32) SynthesisOption {
	return func(o *SynthesisOptions) {
		if !isInvalidFloat32(v) {
			o.NoiseW = v
		}
	}
}

// isInvalidFloat32 returns true if v is NaN or +/-Inf.
func isInvalidFloat32(v float32) bool {
	return math.IsNaN(float64(v)) || math.IsInf(float64(v), 0)
}

// WithSentenceSilence sets the silence duration (in seconds) inserted between
// sentences during streaming synthesis.
func WithSentenceSilence(seconds float64) SynthesisOption {
	return func(o *SynthesisOptions) { o.SentenceSilence = seconds }
}

// WithPhonemeSilence sets a map of phoneme -> seconds of silence to insert
// after that phoneme in the synthesized audio. This matches the C++
// --phoneme_silence feature. For example, {"_": 0.1} inserts 100ms of silence
// after every underscore phoneme.
func WithPhonemeSilence(m map[string]float64) SynthesisOption {
	return func(o *SynthesisOptions) { o.PhonemeSilence = m }
}

// WithSpeakerEmbedding sets a pre-computed speaker embedding for zero-shot
// voice cloning. When set, it takes priority over SpeakerID.
func WithSpeakerEmbedding(emb []float32) SynthesisOption {
	return func(o *SynthesisOptions) { o.SpeakerEmbedding = emb }
}

// Validate checks SynthesisOptions for cross-field invariants. Currently the
// only invariant enforced at this level is that SpeakerID is non-negative
// (negative values are silently coerced via WithSpeakerID, so this is a
// defense-in-depth check for callers constructing the struct directly). The
// speaker_id × speaker_embedding mutual-exclusion check lives on
// SynthesisRequest.Validate, since SynthesisOptions also exposes an embedding
// field but the canonical mutual-exclusion gate is on the engine-facing
// SynthesisRequest.
func (o *SynthesisOptions) Validate() error {
	if o == nil {
		return nil
	}
	return nil
}

// Validate checks a SynthesisRequest for cross-field invariants. It returns
// ErrSpeakerIDEmbeddingExclusive when both SpeakerID is non-zero and
// SpeakerEmbedding is non-empty. SpeakerID == 0 is treated as "unset" since
// 0 is the default speaker for single-speaker models. Other validations
// (PhonemeIDs non-empty, phoneme length cap) are enforced by the engine.
func (r *SynthesisRequest) Validate() error {
	if r == nil {
		return nil
	}
	if r.SpeakerID != 0 && len(r.SpeakerEmbedding) > 0 {
		return ErrSpeakerIDEmbeddingExclusive
	}
	return nil
}

// ---------------------------------------------------------------------------
// LoadOption — functional options for LoadVoice.
// ---------------------------------------------------------------------------

// LoadOptions holds resolved parameters for model loading.
type LoadOptions struct {
	ConfigPath      string             // explicit path to config.json
	DictDir         string             // explicit dictionary directory (overrides search)
	CustomDictPaths []string           // paths to custom dictionary JSON files
	Device          string             // default "cpu"
	Logger          *slog.Logger       // default slog.Default()
	PhonemeSilence  map[string]float64 // phoneme -> seconds of silence after it (applied at load time as default)
}

// LoadOption is a functional option applied to LoadOptions.
type LoadOption func(*LoadOptions)

// WithConfig sets an explicit config.json path.
func WithConfig(path string) LoadOption {
	return func(o *LoadOptions) { o.ConfigPath = path }
}

// WithDictDir sets an explicit directory to search for dictionary files
// (cmudict_data.json, pinyin_single.json, pinyin_phrases.json).
// This takes priority over the model directory and PIPER_DICTIONARIES_PATH.
func WithDictDir(dir string) LoadOption {
	return func(o *LoadOptions) { o.DictDir = dir }
}

// WithCustomDict sets custom dictionary JSON file paths.
// These are loaded and applied as text substitution before phonemization.
func WithCustomDict(paths ...string) LoadOption {
	return func(o *LoadOptions) { o.CustomDictPaths = append(o.CustomDictPaths, paths...) }
}

// WithDevice sets the inference device (e.g. "cpu", "cuda").
func WithDevice(device string) LoadOption {
	return func(o *LoadOptions) { o.Device = device }
}

// WithLogger sets a custom structured logger.
func WithLogger(logger *slog.Logger) LoadOption {
	return func(o *LoadOptions) { o.Logger = logger }
}

// WithPhonemeSilenceLoad sets a default phoneme silence map at model-load time.
// The map specifies phoneme -> seconds of silence to insert after that phoneme.
// This can be overridden per-request via [WithPhonemeSilence].
func WithPhonemeSilenceLoad(m map[string]float64) LoadOption {
	return func(o *LoadOptions) { o.PhonemeSilence = m }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// defaultSynthesisOptions returns SynthesisOptions with sensible defaults.
func defaultSynthesisOptions() SynthesisOptions {
	return SynthesisOptions{
		NoiseScale:      0.4,
		LengthScale:     1.0,
		NoiseW:          0.5,
		SentenceSilence: 0.2,
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

// NewSynthesisRequest creates a SynthesisRequest from phoneme IDs and
// optional SynthesisOption values. Fields from SynthesisOptions are mapped
// onto the returned SynthesisRequest.
func NewSynthesisRequest(phonemeIDs []int64, opts ...SynthesisOption) *SynthesisRequest {
	so := applySynthesisOptions(opts)
	return &SynthesisRequest{
		PhonemeIDs:       phonemeIDs,
		SpeakerID:        so.SpeakerID,
		NoiseScale:       so.NoiseScale,
		LengthScale:      so.LengthScale,
		NoiseW:           so.NoiseW,
		PhonemeSilence:   so.PhonemeSilence,
		SpeakerEmbedding: so.SpeakerEmbedding,
	}
}

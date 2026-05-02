package piperplus

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"time"

	ort "github.com/yalue/onnxruntime_go"
)

// maxPhonemeLen is the upper bound for phoneme input length to prevent
// excessively large tensor allocations.
const maxPhonemeLen = 10000

// ModelCapabilities detected from ONNX graph.
type ModelCapabilities struct {
	HasSpeakerID        bool
	HasLanguageID       bool
	HasProsody          bool
	HasDurationOutput   bool
	HasSpeakerEmbedding bool // model accepts speaker_embedding + speaker_embedding_mask
}

// OnnxEngine wraps DynamicAdvancedSession for TTS inference.
type OnnxEngine struct {
	session      *ort.DynamicAdvancedSession
	capabilities ModelCapabilities
	sampleRate   int
	hopSize      int
	inputNames   []string
	outputNames  []string
	logger       *slog.Logger
}

// containsName checks whether name exists in the given InputOutputInfo slice.
func containsName(infos []ort.InputOutputInfo, name string) bool {
	for _, info := range infos {
		if info.Name == name {
			return true
		}
	}
	return false
}

// detectCapabilities inspects the ONNX graph to determine model inputs/outputs.
func detectCapabilities(modelPath string) (*ModelCapabilities, error) {
	inputs, outputs, err := ort.GetInputOutputInfo(modelPath)
	if err != nil {
		return nil, &ModelLoadError{
			Path: modelPath,
			Err:  fmt.Errorf("failed to read model info: %w", err),
		}
	}

	caps := &ModelCapabilities{
		HasSpeakerID:        containsName(inputs, "sid"),
		HasLanguageID:       containsName(inputs, "lid"),
		HasProsody:          containsName(inputs, "prosody_features"),
		HasDurationOutput:   containsName(outputs, "durations"),
		HasSpeakerEmbedding: containsName(inputs, "speaker_embedding"),
	}
	return caps, nil
}

// newOnnxEngine creates a new OnnxEngine for the given model and config.
func newOnnxEngine(modelPath string, config *VoiceConfig, sessOpts *ort.SessionOptions, logger *slog.Logger) (*OnnxEngine, error) {
	caps, err := detectCapabilities(modelPath)
	if err != nil {
		return nil, err
	}

	// Build input names: always include base inputs, conditionally add optional ones.
	inputNames := []string{"input", "input_lengths", "scales"}
	if caps.HasSpeakerID {
		inputNames = append(inputNames, "sid")
	}
	if caps.HasLanguageID {
		inputNames = append(inputNames, "lid")
	}
	if caps.HasProsody {
		inputNames = append(inputNames, "prosody_features")
	}
	if caps.HasSpeakerEmbedding {
		inputNames = append(inputNames, "speaker_embedding")
		inputNames = append(inputNames, "speaker_embedding_mask")
	}

	// Build output names: always include audio output, conditionally add durations.
	outputNames := []string{"output"}
	if caps.HasDurationOutput {
		outputNames = append(outputNames, "durations")
	}

	session, err := ort.NewDynamicAdvancedSession(modelPath, inputNames, outputNames, sessOpts)
	if err != nil {
		return nil, &ModelLoadError{
			Path: modelPath,
			Err:  fmt.Errorf("failed to create ONNX session: %w", err),
		}
	}

	logger.Info("loaded ONNX model",
		"path", modelPath,
		"has_speaker_id", caps.HasSpeakerID,
		"has_language_id", caps.HasLanguageID,
		"has_prosody", caps.HasProsody,
		"has_duration_output", caps.HasDurationOutput,
		"has_speaker_embedding", caps.HasSpeakerEmbedding,
	)

	hopSize := config.Audio.HopSize
	if hopSize <= 0 {
		hopSize = 256 // matches docs/spec/short-text-contract.toml default
	}

	return &OnnxEngine{
		session:      session,
		capabilities: *caps,
		sampleRate:   config.Audio.SampleRate,
		hopSize:      hopSize,
		inputNames:   inputNames,
		outputNames:  outputNames,
		logger:       logger,
	}, nil
}

// Synthesize runs ONNX inference for the given synthesis request.
func (e *OnnxEngine) Synthesize(ctx context.Context, req *SynthesisRequest) (*SynthesisResult, error) {
	if e.session == nil {
		return nil, ErrModelClosed
	}

	if len(req.PhonemeIDs) == 0 {
		return nil, ErrEmptyPhonemeIDs
	}

	// Check for pre-canceled context.
	if err := ctx.Err(); err != nil {
		return nil, err
	}

	originalPhonemeLen := len(req.PhonemeIDs)

	// --- Strategy A: Silence Padding for short phoneme sequences ---
	phonemeIDs := req.PhonemeIDs
	prosodyFeatures := req.ProsodyFeatures
	var wasPadded bool
	var frontPad, backPad int
	phonemeIDs, wasPadded, frontPad, backPad = padPhonemeIDs(phonemeIDs)
	if wasPadded {
		prosodyFeatures = padProsodyFeatures(req.ProsodyFeatures, originalPhonemeLen, len(phonemeIDs))
	}

	// --- Strategy B: Dynamic Scales Adjustment for short phoneme sequences ---
	noiseScale := req.NoiseScale
	noiseW := req.NoiseW
	scalesAdjusted := originalPhonemeLen < minPhonemeIDs
	noiseScale, noiseW = adjustScalesForShortText(originalPhonemeLen, noiseScale, noiseW)

	if summary := shortTextMitigationSummary(originalPhonemeLen, len(phonemeIDs), wasPadded, scalesAdjusted); summary != "" {
		e.logger.Debug(summary)
	}

	phonemeLen := len(phonemeIDs)
	if phonemeLen > maxPhonemeLen {
		return nil, &InferenceError{
			Msg: fmt.Sprintf("phoneme length %d exceeds maximum %d", phonemeLen, maxPhonemeLen),
		}
	}

	// Collect all input tensors for cleanup.
	var tensors []ort.Value

	cleanup := func() {
		for _, t := range tensors {
			_ = t.Destroy()
		}
	}
	defer cleanup()

	// Build input tensors in order matching inputNames.
	inputs := make([]ort.Value, 0, len(e.inputNames))

	// "input": int64 [1, phonemeLen]
	inputTensor, err := ort.NewTensor(ort.NewShape(1, int64(phonemeLen)), phonemeIDs)
	if err != nil {
		return nil, &InferenceError{Msg: "failed to create input tensor", Err: err}
	}
	tensors = append(tensors, inputTensor)
	inputs = append(inputs, inputTensor)

	// "input_lengths": int64 [1]
	lengthsTensor, err := ort.NewTensor(ort.NewShape(1), []int64{int64(phonemeLen)})
	if err != nil {
		return nil, &InferenceError{Msg: "failed to create input_lengths tensor", Err: err}
	}
	tensors = append(tensors, lengthsTensor)
	inputs = append(inputs, lengthsTensor)

	// "scales": float32 [3]
	scalesTensor, err := ort.NewTensor(ort.NewShape(3), []float32{noiseScale, req.LengthScale, noiseW})
	if err != nil {
		return nil, &InferenceError{Msg: "failed to create scales tensor", Err: err}
	}
	tensors = append(tensors, scalesTensor)
	inputs = append(inputs, scalesTensor)

	// "sid": int64 [1] (if HasSpeakerID)
	if e.capabilities.HasSpeakerID {
		sidTensor, err := ort.NewTensor(ort.NewShape(1), []int64{req.SpeakerID})
		if err != nil {
			return nil, &InferenceError{Msg: "failed to create sid tensor", Err: err}
		}
		tensors = append(tensors, sidTensor)
		inputs = append(inputs, sidTensor)
	}

	// "lid": int64 [1] (if HasLanguageID)
	if e.capabilities.HasLanguageID {
		lidTensor, err := ort.NewTensor(ort.NewShape(1), []int64{req.LanguageID})
		if err != nil {
			return nil, &InferenceError{Msg: "failed to create lid tensor", Err: err}
		}
		tensors = append(tensors, lidTensor)
		inputs = append(inputs, lidTensor)
	}

	// "prosody_features": int64 [1, phonemeLen, 3] (if HasProsody)
	if e.capabilities.HasProsody {
		prosodyData := make([]int64, phonemeLen*3)
		for i, pf := range prosodyFeatures {
			if i >= phonemeLen {
				break
			}
			prosodyData[i*3+0] = pf[0]
			prosodyData[i*3+1] = pf[1]
			prosodyData[i*3+2] = pf[2]
		}
		prosodyTensor, err := ort.NewTensor(ort.NewShape(1, int64(phonemeLen), 3), prosodyData)
		if err != nil {
			return nil, &InferenceError{Msg: "failed to create prosody_features tensor", Err: err}
		}
		tensors = append(tensors, prosodyTensor)
		inputs = append(inputs, prosodyTensor)
	}

	// "speaker_embedding": float32 [1, embDim] + "speaker_embedding_mask": int64 [1, 1]
	if e.capabilities.HasSpeakerEmbedding {
		if len(req.SpeakerEmbedding) > 0 {
			embDim := len(req.SpeakerEmbedding)
			embTensor, err := ort.NewTensor(ort.NewShape(1, int64(embDim)), req.SpeakerEmbedding)
			if err != nil {
				return nil, &InferenceError{Msg: "failed to create speaker_embedding tensor", Err: err}
			}
			tensors = append(tensors, embTensor)
			inputs = append(inputs, embTensor)

			maskTensor, err := ort.NewTensor(ort.NewShape(1, 1), []int64{1})
			if err != nil {
				return nil, &InferenceError{Msg: "failed to create speaker_embedding_mask tensor", Err: err}
			}
			tensors = append(tensors, maskTensor)
			inputs = append(inputs, maskTensor)
		} else {
			// No embedding provided — send zero-length embedding placeholder and mask=0
			placeholderTensor, err := ort.NewTensor(ort.NewShape(1, 1), []float32{0})
			if err != nil {
				return nil, &InferenceError{Msg: "failed to create speaker_embedding placeholder", Err: err}
			}
			tensors = append(tensors, placeholderTensor)
			inputs = append(inputs, placeholderTensor)

			maskTensor, err := ort.NewTensor(ort.NewShape(1, 1), []int64{0})
			if err != nil {
				return nil, &InferenceError{Msg: "failed to create speaker_embedding_mask tensor", Err: err}
			}
			tensors = append(tensors, maskTensor)
			inputs = append(inputs, maskTensor)
		}
	}

	// Prepare outputs: nil for auto-allocation.
	outputs := make([]ort.Value, len(e.outputNames))

	// Create RunOptions for context cancellation support.
	runOpts, err := ort.NewRunOptions()
	if err != nil {
		return nil, &InferenceError{Msg: "failed to create run options", Err: err}
	}
	defer func() { _ = runOpts.Destroy() }()

	// Spawn goroutine to watch for context cancellation.
	canceled := make(chan struct{})
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-ctx.Done():
			e.logger.Debug("context canceled, terminating inference", "reason", ctx.Err())
			_ = runOpts.Terminate()
			close(canceled)
		case <-done:
		}
	}()

	// Run inference.
	start := time.Now()
	if err := e.session.RunWithOptions(inputs, outputs, runOpts); err != nil {
		// Destroy any auto-allocated output tensors on error.
		for i, o := range outputs {
			if o != nil {
				_ = o.Destroy()
				outputs[i] = nil
			}
		}
		// Determine whether the error is from context cancellation or an
		// inference failure. Check the canceled channel (non-blocking) to
		// avoid racing on ctx.Err() alone.
		select {
		case <-canceled:
			e.logger.Info("inference terminated due to context cancellation",
				"elapsed", time.Since(start))
			return nil, ctx.Err()
		default:
		}
		if ctx.Err() != nil {
			e.logger.Info("inference failed with concurrent context cancellation",
				"elapsed", time.Since(start), "err", err)
			return nil, ctx.Err()
		}
		return nil, &InferenceError{Msg: "ONNX inference failed", Err: err}
	}
	inferTime := time.Since(start)

	// Destroy all auto-allocated output tensors when we are done.
	// This prevents memory leaks when type assertions fail or errors occur.
	defer func() {
		for i, o := range outputs {
			if o != nil {
				_ = o.Destroy()
				outputs[i] = nil
			}
		}
	}()

	// Extract audio from the first output tensor.
	audioOutputTensor, ok := outputs[0].(*ort.Tensor[float32])
	if !ok {
		return nil, &InferenceError{Msg: "unexpected output tensor type for audio", Err: nil}
	}
	rawAudio := audioOutputTensor.GetData()
	// Copy data before the deferred Destroy runs.
	audioCopy := make([]float32, len(rawAudio))
	copy(audioCopy, rawAudio)

	// Check for NaN/Inf in audio output which indicates inference failure.
	for i, s := range audioCopy {
		if math.IsNaN(float64(s)) || math.IsInf(float64(s), 0) {
			return nil, &InferenceError{
				Msg: fmt.Sprintf("audio output contains NaN/Inf at sample %d", i),
			}
		}
	}

	// Peak-normalize and convert to int16.
	audio := peakNormalize(audioCopy)

	// Extract durations BEFORE post-trim so the precise trimmer can use them.
	// `paddedDurations` keeps the full padded-sequence durations needed by
	// trimPaddingByDurations, while `durations` (returned to callers) is
	// truncated back to the original phoneme length for timing alignment.
	var paddedDurations []float32
	var durations []float32
	if e.capabilities.HasDurationOutput && len(outputs) > 1 && outputs[1] != nil {
		durTensor, ok := outputs[1].(*ort.Tensor[float32])
		if ok {
			rawDur := durTensor.GetData()
			paddedDurations = make([]float32, len(rawDur))
			copy(paddedDurations, rawDur)
			durations = make([]float32, len(rawDur))
			copy(durations, rawDur)
			// When padding was applied, trim durations back to original length.
			if wasPadded && len(durations) > originalPhonemeLen {
				durations = durations[:originalPhonemeLen]
			}
			if len(durations) != originalPhonemeLen {
				e.logger.Warn("duration count does not match phoneme length",
					"durations", len(durations), "phoneme_len", originalPhonemeLen)
			}
		} else {
			e.logger.Warn("unexpected tensor type for duration output; durations unavailable")
		}
	}

	// --- Strategy A post-trim: remove padding-induced audio ---
	// Prefer the durations-based precise trim when the model exposes
	// durations (issue #356). Falls back to the legacy RMS trim for older
	// exports without a duration output.
	if wasPadded {
		if paddedDurations != nil {
			audio = trimPaddingByDurations(
				audio,
				paddedDurations,
				frontPad,
				backPad,
				e.hopSize,
				trimEosMaxFrames,
			)
		} else {
			audio = trimSilence(audio)
		}
	}

	// Calculate audio duration using integer arithmetic for precision.
	var audioDuration time.Duration
	if len(audio) > 0 && e.sampleRate > 0 {
		audioDuration = time.Duration(int64(len(audio)) * int64(time.Second) / int64(e.sampleRate))
	}

	e.logger.Debug("inference complete",
		"phoneme_len", phonemeLen,
		"audio_samples", len(audio),
		"audio_duration", audioDuration,
		"infer_time", inferTime,
	)

	return &SynthesisResult{
		Audio:      audio,
		SampleRate: e.sampleRate,
		Duration:   audioDuration,
		InferTime:  inferTime,
		Durations:  durations,
	}, nil
}

// Capabilities returns the detected model capabilities.
func (e *OnnxEngine) Capabilities() ModelCapabilities {
	return e.capabilities
}

// Close destroys the ONNX session and releases resources.
func (e *OnnxEngine) Close() error {
	if e.session != nil {
		err := e.session.Destroy()
		e.session = nil
		return err
	}
	return nil
}

package piperplus

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	ort "github.com/yalue/onnxruntime_go"
)

// ModelCapabilities detected from ONNX graph.
type ModelCapabilities struct {
	HasSpeakerID      bool
	HasLanguageID     bool
	HasProsody        bool
	HasDurationOutput bool
}

// OnnxEngine wraps DynamicAdvancedSession for TTS inference.
type OnnxEngine struct {
	session      *ort.DynamicAdvancedSession
	capabilities ModelCapabilities
	sampleRate   int
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
		HasSpeakerID:      containsName(inputs, "sid"),
		HasLanguageID:     containsName(inputs, "lid"),
		HasProsody:        containsName(inputs, "prosody_features"),
		HasDurationOutput: containsName(outputs, "durations"),
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
	)

	return &OnnxEngine{
		session:      session,
		capabilities: *caps,
		sampleRate:   config.Audio.SampleRate,
		inputNames:   inputNames,
		outputNames:  outputNames,
		logger:       logger,
	}, nil
}

// Synthesize runs ONNX inference for the given synthesis request.
func (e *OnnxEngine) Synthesize(ctx context.Context, req *SynthesisRequest) (*SynthesisResult, error) {
	if len(req.PhonemeIDs) == 0 {
		return nil, ErrEmptyPhonemeIDs
	}

	// Check for pre-cancelled context.
	if err := ctx.Err(); err != nil {
		return nil, err
	}

	phonemeLen := len(req.PhonemeIDs)

	// Collect all input tensors for cleanup.
	var tensors []ort.Value

	cleanup := func() {
		for _, t := range tensors {
			t.Destroy()
		}
	}
	defer cleanup()

	// Build input tensors in order matching inputNames.
	inputs := make([]ort.Value, 0, len(e.inputNames))

	// "input": int64 [1, phonemeLen]
	inputTensor, err := ort.NewTensor(ort.NewShape(1, int64(phonemeLen)), req.PhonemeIDs)
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
	scalesTensor, err := ort.NewTensor(ort.NewShape(3), []float32{req.NoiseScale, req.LengthScale, req.NoiseW})
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
		if req.ProsodyFeatures != nil {
			for i, pf := range req.ProsodyFeatures {
				if i >= phonemeLen {
					break
				}
				prosodyData[i*3+0] = pf[0]
				prosodyData[i*3+1] = pf[1]
				prosodyData[i*3+2] = pf[2]
			}
		}
		prosodyTensor, err := ort.NewTensor(ort.NewShape(1, int64(phonemeLen), 3), prosodyData)
		if err != nil {
			return nil, &InferenceError{Msg: "failed to create prosody_features tensor", Err: err}
		}
		tensors = append(tensors, prosodyTensor)
		inputs = append(inputs, prosodyTensor)
	}

	// Prepare outputs: nil for auto-allocation.
	outputs := make([]ort.Value, len(e.outputNames))

	// Create RunOptions for context cancellation support.
	runOpts, err := ort.NewRunOptions()
	if err != nil {
		return nil, &InferenceError{Msg: "failed to create run options", Err: err}
	}
	defer runOpts.Destroy()

	// Spawn goroutine to watch for context cancellation.
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-ctx.Done():
			runOpts.Terminate()
		case <-done:
		}
	}()

	// Run inference.
	start := time.Now()
	if err := e.session.RunWithOptions(inputs, outputs, runOpts); err != nil {
		// Check if it was a context cancellation.
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, &InferenceError{Msg: "ONNX inference failed", Err: err}
	}
	inferTime := time.Since(start)

	// Extract audio from the first output tensor.
	audioOutputTensor, ok := outputs[0].(*ort.Tensor[float32])
	if !ok {
		return nil, &InferenceError{Msg: "unexpected output tensor type for audio", Err: nil}
	}
	rawAudio := audioOutputTensor.GetData()
	// Copy data before destroying the tensor.
	audioCopy := make([]float32, len(rawAudio))
	copy(audioCopy, rawAudio)
	audioOutputTensor.Destroy()

	// Peak-normalize and convert to int16.
	audio := peakNormalize(audioCopy)

	// Calculate audio duration.
	var audioDuration time.Duration
	if len(audio) > 0 && e.sampleRate > 0 {
		audioDuration = time.Duration(float64(len(audio)) / float64(e.sampleRate) * float64(time.Second))
	}

	// Extract durations if available.
	var durations []float32
	if e.capabilities.HasDurationOutput && len(outputs) > 1 && outputs[1] != nil {
		durTensor, ok := outputs[1].(*ort.Tensor[float32])
		if ok {
			rawDur := durTensor.GetData()
			durations = make([]float32, len(rawDur))
			copy(durations, rawDur)
			durTensor.Destroy()
		}
	}

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

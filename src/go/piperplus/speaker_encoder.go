package piperplus

import (
	"encoding/binary"
	"fmt"
	"io"
	"math"
	"os"

	ort "github.com/yalue/onnxruntime_go"
)

// speakerEncoderInputName and speakerEncoderOutputName are read dynamically
// from the ONNX model graph to avoid hard-coded name assumptions.

// Legacy (ECAPA-TDNN) mel spectrogram parameters — unified across all runtimes.
const (
	melSampleRate = 16000
	melNFFT       = 400 // Kaldi frame_length=25ms at 16kHz = 400 samples
	melHopLength  = 160
	melNMels      = 80
	melFmin       = 20.0
	melFmax       = 7600.0
)

// CampplusEmbeddingDim is the embedding dimension of the CAM++ encoder
// bundled with the public zs-v1 base (campplus.onnx).
const CampplusEmbeddingDim = 192

// SpeakerFrontEnd selects how audio is turned into the encoder's input.
type SpeakerFrontEnd int

const (
	// SpeakerFrontEndMel is the legacy ECAPA-TDNN mel spectrogram (linear
	// resample, Hann window, 400-point DFT, 20-7600 Hz). The output is
	// returned as the model produced it.
	SpeakerFrontEndMel SpeakerFrontEnd = iota
	// SpeakerFrontEndKaldiFbank is the zs-v1 CAM++ recipe: kaiser_best
	// resample, Kaldi fbank, mean subtraction. The output is L2-normalized.
	SpeakerFrontEndKaldiFbank
)

// String returns the front end's name.
func (f SpeakerFrontEnd) String() string {
	switch f {
	case SpeakerFrontEndMel:
		return "mel"
	case SpeakerFrontEndKaldiFbank:
		return "kaldi-fbank"
	default:
		return fmt.Sprintf("SpeakerFrontEnd(%d)", int(f))
	}
}

// SpeakerFrontEndForEmbeddingDim returns the front end for an encoder whose
// embedding has dim values (0 when unknown): SpeakerFrontEndKaldiFbank for
// CAM++ (192), otherwise SpeakerFrontEndMel.
func SpeakerFrontEndForEmbeddingDim(dim int) SpeakerFrontEnd {
	if dim == CampplusEmbeddingDim {
		return SpeakerFrontEndKaldiFbank
	}
	return SpeakerFrontEndMel
}

// SpeakerEncoder loads a speaker encoder ONNX model and extracts speaker
// embeddings from audio. The embedding can be passed to
// SynthesisRequest.SpeakerEmbedding for voice cloning.
type SpeakerEncoder struct {
	session  *ort.DynamicAdvancedSession
	frontEnd SpeakerFrontEnd
}

// NewSpeakerEncoder creates a speaker encoder from an ONNX model file.
// Input and output names are read dynamically from the model graph. The
// front end follows the model's output dimension (see
// SpeakerFrontEndForEmbeddingDim): the zs-v1 CAM++ encoder gets
// SpeakerFrontEndKaldiFbank, anything else SpeakerFrontEndMel.
func NewSpeakerEncoder(modelPath string) (*SpeakerEncoder, error) {
	return newSpeakerEncoder(modelPath, nil)
}

// NewSpeakerEncoderWithFrontEnd creates a speaker encoder with an explicit
// front end.
func NewSpeakerEncoderWithFrontEnd(modelPath string, frontEnd SpeakerFrontEnd) (*SpeakerEncoder, error) {
	if frontEnd != SpeakerFrontEndMel && frontEnd != SpeakerFrontEndKaldiFbank {
		return nil, fmt.Errorf("speaker encoder: unknown front end %v", frontEnd)
	}
	return newSpeakerEncoder(modelPath, &frontEnd)
}

// FrontEnd returns the feature front end this encoder uses.
func (se *SpeakerEncoder) FrontEnd() SpeakerFrontEnd {
	return se.frontEnd
}

func newSpeakerEncoder(modelPath string, frontEnd *SpeakerFrontEnd) (*SpeakerEncoder, error) {
	// Dynamically read input/output names from the model graph.
	inputs, outputs, err := ort.GetInputOutputInfo(modelPath)
	if err != nil {
		return nil, fmt.Errorf("speaker encoder read model info %s: %w", modelPath, err)
	}
	if len(inputs) == 0 {
		return nil, fmt.Errorf("speaker encoder model has no inputs: %s", modelPath)
	}
	if len(outputs) == 0 {
		return nil, fmt.Errorf("speaker encoder model has no outputs: %s", modelPath)
	}
	inputNames := []string{inputs[0].Name}
	outputNames := []string{outputs[0].Name}

	fe := SpeakerFrontEndForEmbeddingDim(staticLastDim(outputs[0].Dimensions))
	if frontEnd != nil {
		fe = *frontEnd
	}

	sessOpts, err := ort.NewSessionOptions()
	if err != nil {
		return nil, fmt.Errorf("speaker encoder session options: %w", err)
	}
	defer func() { _ = sessOpts.Destroy() }()
	if fe == SpeakerFrontEndKaldiFbank {
		// ONNX Runtime 1.24-1.28 graph optimizations (even the basic level)
		// change CAM++ output (cosine 0.998 against the unoptimized and
		// 1.29+ result); the encoder runs once per reference, so the
		// unoptimized graph costs little.
		if err := sessOpts.SetGraphOptimizationLevel(ort.GraphOptimizationLevelDisableAll); err != nil {
			return nil, fmt.Errorf("speaker encoder optimization level: %w", err)
		}
	}

	session, err := ort.NewDynamicAdvancedSession(modelPath, inputNames, outputNames, sessOpts)
	if err != nil {
		return nil, fmt.Errorf("speaker encoder load %s: %w", modelPath, err)
	}

	return &SpeakerEncoder{session: session, frontEnd: fe}, nil
}

// staticLastDim returns the last dimension of a shape, or 0 when the shape
// is empty or that dimension is dynamic.
func staticLastDim(shape ort.Shape) int {
	if len(shape) == 0 || shape[len(shape)-1] <= 0 {
		return 0
	}
	return int(shape[len(shape)-1])
}

// Encode extracts a speaker embedding from mono float32 audio samples.
// If sampleRate is not 16000, the audio is resampled first (kaiser_best sinc
// for SpeakerFrontEndKaldiFbank, linear interpolation for
// SpeakerFrontEndMel). The zs-v1 CAM++ encoder returns a 192-d
// L2-normalized embedding, the legacy ECAPA-TDNN encoder a 256-d one.
func (se *SpeakerEncoder) Encode(audio []float32, sampleRate int) ([]float32, error) {
	if len(audio) == 0 {
		return nil, fmt.Errorf("speaker encoder: empty audio input")
	}
	if sampleRate <= 0 {
		return nil, fmt.Errorf("speaker encoder: sample rate must be positive, got %d", sampleRate)
	}
	kaldi := se.frontEnd == SpeakerFrontEndKaldiFbank

	// Resample to 16kHz if needed
	resampled := audio
	if sampleRate != melSampleRate {
		if kaldi {
			var err error
			resampled, err = ResampleKaiserBest(audio, sampleRate, melSampleRate)
			if err != nil {
				return nil, fmt.Errorf("speaker encoder: %w", err)
			}
		} else {
			resampled = resampleLinear(audio, sampleRate)
		}
	}

	// Compute features: returned in frame-major order [n_frames * n_mels]
	var mel []float32
	if kaldi {
		mel = KaldiFbank(resampled)
		subtractBandMeans(mel)
	} else {
		mel = computeMelSpectrogram(resampled)
	}
	nFrames := len(mel) / melNMels

	if nFrames == 0 {
		return nil, fmt.Errorf("speaker encoder: audio too short for mel spectrogram")
	}

	// Create input tensor: [1, n_frames, n_mels] — CAM++ expects time-first (Fbank) layout.
	melTensor, err := ort.NewTensor(ort.NewShape(1, int64(nFrames), int64(melNMels)), mel)
	if err != nil {
		return nil, fmt.Errorf("speaker encoder mel tensor: %w", err)
	}
	defer func() { _ = melTensor.Destroy() }()

	// Prepare output
	outputs := []ort.Value{nil}
	inputs := []ort.Value{melTensor}

	if err := se.session.Run(inputs, outputs); err != nil {
		return nil, fmt.Errorf("speaker encoder inference: %w", err)
	}

	// Extract output
	if outputs[0] == nil {
		return nil, fmt.Errorf("speaker encoder: nil output tensor")
	}
	defer func() { _ = outputs[0].Destroy() }()

	outputTensor, ok := outputs[0].(*ort.Tensor[float32])
	if !ok {
		return nil, fmt.Errorf("speaker encoder: unexpected output tensor type")
	}
	rawData := outputTensor.GetData()
	if kaldi {
		return l2Normalize(rawData)
	}
	result := make([]float32, len(rawData))
	copy(result, rawData)

	return result, nil
}

// l2Normalize returns a copy of embedding scaled to unit L2 norm.
func l2Normalize(embedding []float32) ([]float32, error) {
	sum := 0.0
	for _, v := range embedding {
		sum += float64(v) * float64(v)
	}
	norm := math.Sqrt(sum)
	if norm == 0 || math.IsNaN(norm) || math.IsInf(norm, 0) {
		return nil, fmt.Errorf("speaker encoder returned a zero or non-finite embedding")
	}
	out := make([]float32, len(embedding))
	for i, v := range embedding {
		out[i] = float32(float64(v) / norm)
	}
	return out, nil
}

// EncodeFile reads a WAV file and extracts a speaker embedding.
func (se *SpeakerEncoder) EncodeFile(path string) ([]float32, error) {
	samples, sampleRate, err := readWavFileForEncoder(path)
	if err != nil {
		return nil, fmt.Errorf("speaker encoder read WAV %s: %w", path, err)
	}
	return se.Encode(samples, sampleRate)
}

// Close destroys the ONNX session.
func (se *SpeakerEncoder) Close() {
	if se.session != nil {
		_ = se.session.Destroy()
		se.session = nil
	}
}

// LoadSpeakerEmbeddingFile reads a pre-computed speaker embedding from a file.
// Supports NumPy .npy format (v1.0/v2.0, little-endian float32) and raw binary
// (little-endian float32 values with no header).
func LoadSpeakerEmbeddingFile(path string) ([]float32, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read speaker embedding %s: %w", path, err)
	}

	// Detect NumPy .npy format by magic bytes: \x93NUMPY
	if len(data) >= 6 && data[0] == 0x93 && string(data[1:6]) == "NUMPY" {
		return loadNpyFloat32(data, path)
	}

	// Raw binary: every 4 bytes is one little-endian float32.
	if len(data)%4 != 0 {
		return nil, fmt.Errorf("speaker embedding file size (%d bytes) is not a multiple of 4", len(data))
	}
	floats := make([]float32, len(data)/4)
	for i := range floats {
		bits := binary.LittleEndian.Uint32(data[i*4 : i*4+4])
		floats[i] = math.Float32frombits(bits)
	}
	return floats, nil
}

// loadNpyFloat32 parses a NumPy v1.0/v2.0 .npy file containing float32 data.
// It skips the variable-length header and returns the raw float32 values.
func loadNpyFloat32(data []byte, path string) ([]float32, error) {
	// Minimum header: magic(6) + major(1) + minor(1) + headerLen(2 or 4) = 10/12 bytes
	if len(data) < 10 {
		return nil, fmt.Errorf("npy file too short: %s", path)
	}

	major := data[6]

	var headerLen int
	var dataOffset int
	switch major {
	case 1:
		// v1.0: header length stored as little-endian uint16 at offset 8
		if len(data) < 10 {
			return nil, fmt.Errorf("npy v1 file too short: %s", path)
		}
		headerLen = int(binary.LittleEndian.Uint16(data[8:10]))
		dataOffset = 10 + headerLen
	case 2, 3:
		// v2.0/v3.0: header length stored as little-endian uint32 at offset 8
		if len(data) < 12 {
			return nil, fmt.Errorf("npy v2/v3 file too short: %s", path)
		}
		headerLen = int(binary.LittleEndian.Uint32(data[8:12]))
		dataOffset = 12 + headerLen
	default:
		return nil, fmt.Errorf("unsupported npy version %d.%d: %s", major, data[7], path)
	}

	if dataOffset > len(data) {
		return nil, fmt.Errorf("npy header length %d exceeds file size %d: %s", dataOffset, len(data), path)
	}

	payload := data[dataOffset:]
	if len(payload)%4 != 0 {
		return nil, fmt.Errorf("npy payload size (%d bytes) is not a multiple of 4: %s", len(payload), path)
	}

	floats := make([]float32, len(payload)/4)
	for i := range floats {
		bits := binary.LittleEndian.Uint32(payload[i*4 : i*4+4])
		floats[i] = math.Float32frombits(bits)
	}
	return floats, nil
}

// readWavFileForEncoder reads a WAV file and returns mono float32 samples.
func readWavFileForEncoder(path string) ([]float32, int, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, 0, err
	}
	defer func() { _ = f.Close() }()

	// Read RIFF header
	var header [12]byte
	if _, err := io.ReadFull(f, header[:]); err != nil {
		return nil, 0, fmt.Errorf("read WAV header: %w", err)
	}
	if string(header[:4]) != "RIFF" || string(header[8:12]) != "WAVE" {
		return nil, 0, fmt.Errorf("not a WAV file: %s", path)
	}

	var sampleRate int
	var channels int
	var bitsPerSample int
	var audioFormat int

	for {
		var chunkHeader [8]byte
		_, err := io.ReadFull(f, chunkHeader[:])
		if err == io.EOF || err == io.ErrUnexpectedEOF {
			break
		}
		if err != nil {
			return nil, 0, fmt.Errorf("read chunk header: %w", err)
		}

		chunkID := string(chunkHeader[:4])
		chunkSize := int(binary.LittleEndian.Uint32(chunkHeader[4:8]))

		switch chunkID {
		case "fmt ":
			if chunkSize < 16 {
				return nil, 0, fmt.Errorf("fmt chunk too small")
			}
			var fmt [16]byte
			if _, err := io.ReadFull(f, fmt[:]); err != nil {
				return nil, 0, err
			}
			audioFormat = int(binary.LittleEndian.Uint16(fmt[0:2]))
			channels = int(binary.LittleEndian.Uint16(fmt[2:4]))
			sampleRate = int(binary.LittleEndian.Uint32(fmt[4:8]))
			bitsPerSample = int(binary.LittleEndian.Uint16(fmt[14:16]))

			remaining := chunkSize - 16
			if remaining > 0 {
				skip := make([]byte, remaining)
				_, _ = io.ReadFull(f, skip)
			}
		case "data":
			numSamples := chunkSize / (bitsPerSample / 8)
			samples := make([]float32, numSamples)

			switch {
			case bitsPerSample == 16:
				for i := 0; i < numSamples; i++ {
					var buf [2]byte
					if _, err := io.ReadFull(f, buf[:]); err != nil {
						break
					}
					val := int16(binary.LittleEndian.Uint16(buf[:]))
					samples[i] = float32(val) / 32768.0
				}
			case bitsPerSample == 32 && audioFormat == 3:
				for i := 0; i < numSamples; i++ {
					var buf [4]byte
					if _, err := io.ReadFull(f, buf[:]); err != nil {
						break
					}
					bits := binary.LittleEndian.Uint32(buf[:])
					samples[i] = math.Float32frombits(bits)
				}
			default:
				return nil, 0, fmt.Errorf("unsupported WAV format: %d-bit, format=%d", bitsPerSample, audioFormat)
			}

			// Convert to mono
			if channels > 1 {
				monoLen := len(samples) / channels
				mono := make([]float32, monoLen)
				for i := 0; i < monoLen; i++ {
					var sum float32
					for ch := 0; ch < channels; ch++ {
						sum += samples[i*channels+ch]
					}
					mono[i] = sum / float32(channels)
				}
				return mono, sampleRate, nil
			}
			return samples, sampleRate, nil
		default:
			// Skip unknown chunk
			skip := make([]byte, chunkSize)
			_, _ = io.ReadFull(f, skip)
		}
	}

	return nil, 0, fmt.Errorf("no data chunk found in WAV file: %s", path)
}

// resampleLinear resamples audio via linear interpolation to melSampleRate.
func resampleLinear(samples []float32, fromRate int) []float32 {
	if fromRate == melSampleRate || len(samples) == 0 {
		return samples
	}

	ratio := float64(fromRate) / float64(melSampleRate)
	outputLen := int(math.Ceil(float64(len(samples)) / ratio))
	output := make([]float32, outputLen)

	for i := 0; i < outputLen; i++ {
		srcPos := float64(i) * ratio
		idx := int(srcPos)
		frac := float32(srcPos - float64(idx))

		if idx+1 < len(samples) {
			output[i] = samples[idx]*(1-frac) + samples[idx+1]*frac
		} else if idx < len(samples) {
			output[i] = samples[idx]
		}
	}

	return output
}

// computeMelSpectrogram computes a log mel spectrogram with CMVN (mean subtraction).
// Returns a flattened [n_frames * n_mels] array (frame-major / time-first order)
// matching CAM++'s expected input layout [1, T, 80].
func computeMelSpectrogram(samples []float32) []float32 {
	melSpec := computeLogMel(samples)
	applyCMVN(melSpec)
	return melSpec
}

// computeLogMel computes the log mel spectrogram before CMVN, in the same
// frame-major layout as computeMelSpectrogram.
func computeLogMel(samples []float32) []float32 {
	melFilters := createMelFilterbank()
	window := hannWindow(melNFFT)

	nFrames := 0
	if len(samples) >= melNFFT {
		nFrames = (len(samples)-melNFFT)/melHopLength + 1
	}

	fftBins := melNFFT/2 + 1
	// Store in frame-major order: melSpec[frameIdx*melNMels + melIdx]
	melSpec := make([]float32, nFrames*melNMels)

	for frameIdx := 0; frameIdx < nFrames; frameIdx++ {
		start := frameIdx * melHopLength

		// Power spectrum via DFT — use float32 angle arithmetic to match
		// the Python reference implementation (golden test generator).
		// Using float64 angles produces a more accurate (constant) DFT for pure
		// sine waves, which CMVN then flattens to zero. float32 angle truncation
		// introduces the same per-frame variation as the Python reference.
		powerSpec := make([]float32, fftBins)
		for k := 0; k < fftBins; k++ {
			var realPart, imagPart float32
			freq := -2.0 * math.Pi * float64(k) / float64(melNFFT)
			for n := 0; n < melNFFT; n++ {
				var sample float32
				if start+n < len(samples) {
					sample = samples[start+n] * window[n]
				}
				angle := freq * float64(n)
				realPart += sample * float32(math.Cos(angle))
				imagPart += sample * float32(math.Sin(angle))
			}
			powerSpec[k] = realPart*realPart + imagPart*imagPart
		}

		// Apply mel filterbank — store in frame-major layout
		for melIdx := 0; melIdx < melNMels; melIdx++ {
			var energy float32
			for k := 0; k < fftBins; k++ {
				energy += melFilters[melIdx*fftBins+k] * powerSpec[k]
			}
			if energy < 1e-10 {
				energy = 1e-10
			}
			melSpec[frameIdx*melNMels+melIdx] = float32(math.Log(float64(energy)))
		}
	}
	return melSpec
}

// applyCMVN subtracts each mel band's mean across all frames (global mean
// normalization), in place.
func applyCMVN(melSpec []float32) {
	nFrames := len(melSpec) / melNMels
	if nFrames > 0 {
		for melIdx := 0; melIdx < melNMels; melIdx++ {
			var sum float32
			for frameIdx := 0; frameIdx < nFrames; frameIdx++ {
				sum += melSpec[frameIdx*melNMels+melIdx]
			}
			mean := sum / float32(nFrames)
			for frameIdx := 0; frameIdx < nFrames; frameIdx++ {
				melSpec[frameIdx*melNMels+melIdx] -= mean
			}
		}
	}
}

func hannWindow(length int) []float32 {
	window := make([]float32, length)
	for n := 0; n < length; n++ {
		window[n] = 0.5 * (1 - float32(math.Cos(2*math.Pi*float64(n)/float64(length))))
	}
	return window
}

func createMelFilterbank() []float32 {
	fftBins := melNFFT/2 + 1
	filterbank := make([]float32, melNMels*fftBins)

	melFminVal := hzToMel(melFmin)
	melFmaxVal := hzToMel(melFmax)

	melPoints := make([]float32, melNMels+2)
	for i := range melPoints {
		melPoints[i] = melFminVal + (melFmaxVal-melFminVal)*float32(i)/float32(melNMels+1)
	}

	binPoints := make([]float32, len(melPoints))
	for i, m := range melPoints {
		binPoints[i] = melToHz(m) * float32(melNFFT) / float32(melSampleRate)
	}

	for m := 0; m < melNMels; m++ {
		// Convert to integer bin indices (matching Python's np.floor().astype(int))
		left := int(math.Floor(float64(binPoints[m])))
		center := int(math.Floor(float64(binPoints[m+1])))
		right := int(math.Floor(float64(binPoints[m+2])))

		// Edge case: if the triangle collapses to a single bin, widen it to
		// guarantee a non-zero response (matches Python reference).
		if left == center && center == right {
			center = min(center+1, fftBins-1)
			right = min(right+2, fftBins-1)
		} else if left == center {
			center = min(center+1, fftBins-1)
		}
		if center == right {
			right = min(right+1, fftBins-1)
		}

		// Rising slope
		for k := left; k < center; k++ {
			if center > left {
				filterbank[m*fftBins+k] = float32(k-left) / float32(center-left)
			}
		}

		// Falling slope
		for k := center; k < right; k++ {
			if right > center {
				filterbank[m*fftBins+k] = float32(right-k) / float32(right-center)
			}
		}

		// Ensure center bin always has weight >= 1.0
		if center < fftBins {
			if filterbank[m*fftBins+center] < 1.0 {
				filterbank[m*fftBins+center] = 1.0
			}
		}
	}

	return filterbank
}

func hzToMel(hz float32) float32 {
	return 2595 * float32(math.Log10(float64(1+hz/700)))
}

func melToHz(mel float32) float32 {
	return 700 * (float32(math.Pow(10, float64(mel)/2595)) - 1)
}

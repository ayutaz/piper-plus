package piperplus

import (
	"encoding/binary"
	"fmt"
	"io"
	"math"
	"os"

	ort "github.com/yalue/onnxruntime_go"
)

// Mel spectrogram parameters — unified across all runtimes.
const (
	melSampleRate = 16000
	melNFFT       = 512
	melHopLength  = 160
	melNMels      = 80
	melFmin       = 20.0
	melFmax       = 7600.0
)

// SpeakerEncoder loads an ECAPA-TDNN speaker encoder ONNX model and
// extracts speaker embeddings from audio. The embedding can be passed
// to SynthesisRequest.SpeakerEmbedding for voice cloning.
type SpeakerEncoder struct {
	session *ort.DynamicAdvancedSession
}

// NewSpeakerEncoder creates a speaker encoder from an ONNX model file.
func NewSpeakerEncoder(modelPath string) (*SpeakerEncoder, error) {
	inputNames := []string{"input"}
	outputNames := []string{"output"}

	sessOpts, err := ort.NewSessionOptions()
	if err != nil {
		return nil, fmt.Errorf("speaker encoder session options: %w", err)
	}
	defer func() { _ = sessOpts.Destroy() }()

	session, err := ort.NewDynamicAdvancedSession(modelPath, inputNames, outputNames, sessOpts)
	if err != nil {
		return nil, fmt.Errorf("speaker encoder load %s: %w", modelPath, err)
	}

	return &SpeakerEncoder{session: session}, nil
}

// Encode extracts a speaker embedding from mono float32 audio samples.
// If sampleRate is not 16000, the audio is resampled via linear interpolation.
func (se *SpeakerEncoder) Encode(audio []float32, sampleRate int) ([]float32, error) {
	if len(audio) == 0 {
		return nil, fmt.Errorf("speaker encoder: empty audio input")
	}

	// Resample to 16kHz if needed
	resampled := audio
	if sampleRate != melSampleRate {
		resampled = resampleLinear(audio, sampleRate, melSampleRate)
	}

	// Compute mel spectrogram
	mel := computeMelSpectrogram(resampled)
	nFrames := len(mel) / melNMels

	if nFrames == 0 {
		return nil, fmt.Errorf("speaker encoder: audio too short for mel spectrogram")
	}

	// Create input tensor: [1, n_mels, n_frames]
	melTensor, err := ort.NewTensor(ort.NewShape(1, int64(melNMels), int64(nFrames)), mel)
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
	result := make([]float32, len(rawData))
	copy(result, rawData)

	return result, nil
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

// LoadSpeakerEmbeddingFile reads a pre-computed speaker embedding from a
// raw binary file (little-endian float32 values).
func LoadSpeakerEmbeddingFile(path string) ([]float32, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read speaker embedding %s: %w", path, err)
	}
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

// resampleLinear resamples audio via linear interpolation.
func resampleLinear(samples []float32, fromRate, toRate int) []float32 {
	if fromRate == toRate || len(samples) == 0 {
		return samples
	}

	ratio := float64(fromRate) / float64(toRate)
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

// computeMelSpectrogram computes a log mel spectrogram.
// Returns a flattened [n_mels * n_frames] array (mel-major order).
func computeMelSpectrogram(samples []float32) []float32 {
	melFilters := createMelFilterbank()
	window := hannWindow(melNFFT)

	nFrames := 0
	if len(samples) >= melNFFT {
		nFrames = (len(samples)-melNFFT)/melHopLength + 1
	}

	fftBins := melNFFT/2 + 1
	melSpec := make([]float32, melNMels*nFrames)

	for frameIdx := 0; frameIdx < nFrames; frameIdx++ {
		start := frameIdx * melHopLength

		// Power spectrum via DFT
		powerSpec := make([]float32, fftBins)
		for k := 0; k < fftBins; k++ {
			var real, imag float32
			freq := -2.0 * math.Pi * float64(k) / float64(melNFFT)
			for n := 0; n < melNFFT; n++ {
				var sample float32
				if start+n < len(samples) {
					sample = samples[start+n] * window[n]
				}
				angle := freq * float64(n)
				real += sample * float32(math.Cos(angle))
				imag += sample * float32(math.Sin(angle))
			}
			powerSpec[k] = real*real + imag*imag
		}

		// Apply mel filterbank
		for melIdx := 0; melIdx < melNMels; melIdx++ {
			var energy float32
			for k := 0; k < fftBins; k++ {
				energy += melFilters[melIdx*fftBins+k] * powerSpec[k]
			}
			if energy < 1e-10 {
				energy = 1e-10
			}
			melSpec[melIdx*nFrames+frameIdx] = float32(math.Log(float64(energy)))
		}
	}

	return melSpec
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

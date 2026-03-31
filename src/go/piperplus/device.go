package piperplus

import (
	"fmt"
	"log/slog"
	"strconv"
	"strings"

	ort "github.com/yalue/onnxruntime_go"
)

// DeviceType identifies a compute device for inference.
type DeviceType struct {
	Provider string // "cpu", "cuda", "coreml", "directml", "tensorrt"
	DeviceID int    // GPU device ID (0 for default)
}

// String returns the device type as a human-readable string, e.g. "cuda:0" or "cpu".
func (d DeviceType) String() string {
	switch d.Provider {
	case "cpu", "coreml":
		return d.Provider
	default:
		return fmt.Sprintf("%s:%d", d.Provider, d.DeviceID)
	}
}

// ParseDevice parses a device string into a DeviceType.
//
// Supported formats (case-insensitive):
//
//	""           → DeviceType{"cpu", 0}
//	"cpu"        → DeviceType{"cpu", 0}
//	"cuda"       → DeviceType{"cuda", 0}
//	"cuda:N"     → DeviceType{"cuda", N}
//	"coreml"     → DeviceType{"coreml", 0}
//	"directml"   → DeviceType{"directml", 0}
//	"directml:N" → DeviceType{"directml", N}
//	"tensorrt"   → DeviceType{"tensorrt", 0}
//	"tensorrt:N" → DeviceType{"tensorrt", N}
//	"auto"       → DeviceType{"auto", 0}
func ParseDevice(device string) (DeviceType, error) {
	device = strings.TrimSpace(device)
	if device == "" {
		return DeviceType{Provider: "cpu", DeviceID: 0}, nil
	}

	lower := strings.ToLower(device)
	parts := strings.SplitN(lower, ":", 2)
	provider := parts[0]

	const maxDeviceID = 255

	var deviceID int
	if len(parts) == 2 {
		id, err := strconv.Atoi(parts[1])
		if err != nil {
			return DeviceType{}, fmt.Errorf("piperplus: invalid device ID %q in %q: %w", parts[1], device, err)
		}
		if id < 0 {
			return DeviceType{}, fmt.Errorf("piperplus: negative device ID %d in %q", id, device)
		}
		if id > maxDeviceID {
			return DeviceType{}, fmt.Errorf("piperplus: device ID %d exceeds maximum (%d) in %q", id, maxDeviceID, device)
		}
		deviceID = id
	}

	switch provider {
	case "cpu", "cuda", "coreml", "directml", "tensorrt", "auto":
		return DeviceType{Provider: provider, DeviceID: deviceID}, nil
	default:
		return DeviceType{}, fmt.Errorf("piperplus: unknown device provider %q", provider)
	}
}

// configureSessionOptions creates ONNX Runtime SessionOptions configured for the
// specified device. On EP configuration failure the function logs a warning and
// falls back to CPU. The caller must call sessOpts.Destroy() when done.
func configureSessionOptions(device string, logger *slog.Logger) (*ort.SessionOptions, error) {
	if logger == nil {
		logger = slog.Default()
	}

	dev, err := ParseDevice(device)
	if err != nil {
		return nil, err
	}

	sessOpts, err := ort.NewSessionOptions()
	if err != nil {
		return nil, fmt.Errorf("piperplus: failed to create session options: %w", err)
	}

	selected := configureEP(sessOpts, dev, logger)
	logger.Info("ONNX Runtime execution provider configured", "device", selected.String())

	return sessOpts, nil
}

// configureEP attempts to attach the requested execution provider to the session
// options. It returns the DeviceType that was actually selected (may be CPU if
// the requested EP failed).
func configureEP(sessOpts *ort.SessionOptions, dev DeviceType, logger *slog.Logger) DeviceType {
	switch dev.Provider {
	case "cpu":
		return DeviceType{Provider: "cpu", DeviceID: 0}

	case "cuda":
		if err := appendCUDA(sessOpts, dev.DeviceID); err != nil {
			logger.Warn("CUDA execution provider unavailable, falling back to CPU", "error", err)
			return DeviceType{Provider: "cpu", DeviceID: 0}
		}
		return dev

	case "coreml":
		if err := sessOpts.AppendExecutionProviderCoreMLV2(map[string]string{}); err != nil {
			logger.Warn("CoreML execution provider unavailable, falling back to CPU", "error", err)
			return DeviceType{Provider: "cpu", DeviceID: 0}
		}
		return dev

	case "directml":
		if err := sessOpts.AppendExecutionProviderDirectML(dev.DeviceID); err != nil {
			logger.Warn("DirectML execution provider unavailable, falling back to CPU", "error", err)
			return DeviceType{Provider: "cpu", DeviceID: 0}
		}
		return dev

	case "tensorrt":
		if err := appendTensorRT(sessOpts, dev.DeviceID); err != nil {
			logger.Warn("TensorRT execution provider unavailable, falling back to CPU", "error", err)
			return DeviceType{Provider: "cpu", DeviceID: 0}
		}
		return dev

	case "auto":
		return autoSelectEP(sessOpts, logger)

	default:
		logger.Warn("unknown provider, falling back to CPU", "provider", dev.Provider)
		return DeviceType{Provider: "cpu", DeviceID: 0}
	}
}

// appendCUDA configures the CUDA execution provider for the given device ID.
func appendCUDA(sessOpts *ort.SessionOptions, deviceID int) error {
	cudaOpts, err := ort.NewCUDAProviderOptions()
	if err != nil {
		return fmt.Errorf("failed to create CUDA provider options: %w", err)
	}
	defer func() { _ = cudaOpts.Destroy() }()

	if err := cudaOpts.Update(map[string]string{
		"device_id": strconv.Itoa(deviceID),
	}); err != nil {
		return fmt.Errorf("failed to update CUDA provider options: %w", err)
	}

	if err := sessOpts.AppendExecutionProviderCUDA(cudaOpts); err != nil {
		return fmt.Errorf("failed to append CUDA execution provider: %w", err)
	}
	return nil
}

// appendTensorRT configures the TensorRT execution provider for the given device ID.
func appendTensorRT(sessOpts *ort.SessionOptions, deviceID int) error {
	trtOpts, err := ort.NewTensorRTProviderOptions()
	if err != nil {
		return fmt.Errorf("failed to create TensorRT provider options: %w", err)
	}
	defer func() { _ = trtOpts.Destroy() }()

	if err := trtOpts.Update(map[string]string{
		"device_id": strconv.Itoa(deviceID),
	}); err != nil {
		return fmt.Errorf("failed to update TensorRT provider options: %w", err)
	}

	if err := sessOpts.AppendExecutionProviderTensorRT(trtOpts); err != nil {
		return fmt.Errorf("failed to append TensorRT execution provider: %w", err)
	}
	return nil
}

// autoSelectEP tries execution providers in priority order: CUDA → CoreML →
// DirectML → CPU. The first provider that succeeds is used.
//
// NOTE: A failed AppendExecutionProvider* call may leave partial state inside
// the ONNX Runtime SessionOptions. ONNX Runtime's EP list is append-only, so
// failed attempts may remain registered but inactive. In practice the runtime
// ignores EPs it cannot initialize, and the final successful EP (or the
// default CPU EP) is the one actually used for inference.
func autoSelectEP(sessOpts *ort.SessionOptions, logger *slog.Logger) DeviceType {
	// Try CUDA first.
	if err := appendCUDA(sessOpts, 0); err == nil {
		logger.Info("auto-detected execution provider", "provider", "cuda")
		return DeviceType{Provider: "cuda", DeviceID: 0}
	}

	// Try CoreML.
	if err := sessOpts.AppendExecutionProviderCoreMLV2(map[string]string{}); err == nil {
		logger.Info("auto-detected execution provider", "provider", "coreml")
		return DeviceType{Provider: "coreml", DeviceID: 0}
	}

	// Try DirectML.
	if err := sessOpts.AppendExecutionProviderDirectML(0); err == nil {
		logger.Info("auto-detected execution provider", "provider", "directml")
		return DeviceType{Provider: "directml", DeviceID: 0}
	}

	// Fall back to CPU.
	logger.Info("auto-detected execution provider", "provider", "cpu")
	return DeviceType{Provider: "cpu", DeviceID: 0}
}
